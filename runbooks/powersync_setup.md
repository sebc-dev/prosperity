# Runbook — PowerSync Service self-hosted (S13.1)

> Story : [S13.1 — PowerSync Service self-hosted](https://github.com/sebc-dev/prosperity/issues/186)
> Lié à : E13 (`docs/roadmap/E13-sync-write-upload-handler.md`), ADR 0003 (bucket design + tables server-only), ADR 0014 (module sync : download vs upload), ADR 0016 (JWT `aud`/`iss`).

## Quand l'utiliser

- **Démarrer la stack sync en dev local** (compose) pour développer/tester le download flow et les sync rules (S13.7+).
- **Diagnostiquer une connexion logical replication** Postgres ↔ PowerSync Service qui ne s'établit pas — le point le plus risqué de l'épic.
- **Pointeur prod** : la mise en prod (Quadlet + Caddy + Cloudflare Tunnel + Restic) est finalisée en **E16** ; ce runbook documente le SQL et les variables à reprendre, sans l'implémenter.

**NE PAS** utiliser ce setup `compose.dev.yml` en production : il est **dev-only** (mots de passe en clair, `sslmode: disable`, ports exposés).

## Architecture — download vs upload

```
                ┌─────────────────────┐   logical replication (pgoutput)
   reads        │  PowerSync Service   │◄──────────────────────────────────┐
 (download) ◄───│  (download flow)     │                                    │
                │  + bucket storage    │──────────► powersync_storage (DB)   │
                └─────────────────────┘                                     │
                                                                  ┌──────────┴─────────┐
   writes                                                         │  Postgres source   │
 (upload)  ────────► FastAPI  POST /sync/upload ───── writes ────►│  (prosperity DB)   │
                     (write upload handler, ADR 0014, S13.8)      └────────────────────┘
```

- **Download** : géré par le **PowerSync Service**. Il réplique les tables publiées (`PUBLICATION powersync`) via logical replication, calcule les buckets et pousse les reads aux clients.
- **Upload** : les **writes** clients ne passent **jamais** par PowerSync. Ils arrivent sur notre backend FastAPI (`POST /sync/upload`, S13.8). PowerSync Service n'exécute pas ce handler.
- **Deux bases Postgres** : la *source* (`prosperity`) et le *bucket storage* (`powersync_storage`, séparé — exigence PowerSync). En dev, même instance, deux bases ; en prod (E16) on peut séparer les instances.

## Pré-requis

- Podman (ou Docker) avec `compose`. Ports `5432` (Postgres) et `8080` (PowerSync) libres.
- `uv` (pour appliquer les migrations Alembic).
- Copier `.env.example` → `.env` (valeurs dev-only ; les mots de passe correspondent à `compose/initdb/00_powersync_roles.sql`).

## Démarrage dev

Le `compose.dev.yml` ne crée **pas** les tables applicatives — c'est Alembic. L'ordre est important : la `PUBLICATION` référence des tables qui doivent exister.

```bash
cp .env.example .env                      # valeurs dev-only (mdp = ceux de l'initdb)

# 1. Postgres seul : initdb crée les rôles, la base powersync_storage et une
#    PUBLICATION `powersync` VIDE (les tables n'existent pas encore).
podman compose -f compose.dev.yml up -d postgres

# 2. Créer le schéma applicatif.
uv run alembic upgrade head

# 3. Peupler la PUBLICATION (idempotent, additif, garde d'existence des tables).
psql "postgresql://prosperity:prosperity@localhost:5432/prosperity" \
  -f compose/initdb/10_powersync_publication.sql

# 4. Démarrer PowerSync : il se connecte, crée son slot de réplication pgoutput,
#    et publie l'état initial.
podman compose -f compose.dev.yml up -d powersync

# 5. Vérifier le livrable observable.
bash scripts/smoke_powersync.sh
```

> **Pourquoi cet ordre ?** `compose/initdb/*.sql` tourne au premier boot d'un volume vierge, **avant** les migrations. La `PUBLICATION` ne peut donc référencer aucune table à ce moment-là ; on crée une publication vide, puis on la peuple après `alembic upgrade head`. Le worker de réplication PowerSync **retente** la connexion jusqu'à ce que la publication soit utilisable — un `podman compose up` global converge donc une fois l'étape 3 faite.

## Variables d'env (`PS_*`)

| Variable | Rôle | Secret en prod ? |
|---|---|---|
| `PS_IMAGE_TAG` | Tag fixe de l'image `journeyapps/powersync-service` (jamais `latest`) | non |
| `PS_PORT` | Port de l'API PowerSync | non |
| `PS_SOURCE_URI` | Connexion source (rôle `powersync`, `LOGIN REPLICATION`, moindre privilège) | **oui** |
| `PS_STORAGE_URI` | Connexion bucket storage (rôle `ps_storage`, owner de `powersync_storage`) | **oui** |
| `PS_JWKS_URI` | Endpoint JWKS pour valider les JWT clients (placeholder dev ; réel en S13.8/E14) | non |
| `PS_ADMIN_TOKEN` | Token des routes admin API locales (diagnostic) | **oui** |

Seules les variables préfixées `PS_` sont substituables via le tag YAML `!env` dans `powersync/config.yaml`.

## Sécurité

- **Pas de garde-fou applicatif sur les `PS_*`.** `backend/config.py::_forbid_dev_defaults_in_prod` ne couvre que `database_url` et `jwt_secret` — **pas** la chaîne PowerSync (qui vit hors Pydantic, dans `.env`/`config.yaml`). Rien n'empêche donc un déploiement prod de réutiliser les mots de passe dev du repo. **E16 doit ajouter un garde-fou équivalent** côté PowerSync. En attendant : ne **jamais** copier `.env.example` en prod.
- **Credentials prod = secrets manager**, montés en **fichier** (pas en `environment:`, visible via `podman inspect` / logs au boot).
- **`PUBLICATION` = frontière de sécurité (ADR 0003).** Jamais `FOR ALL TABLES`. Les tables server-only (`users`, `refresh_tokens`, `invitations`, `admin_audit_logs`, staging banking) ne sont **jamais** publiées. Les tables debt-projection (`debts`, `share_requests`, `settlements`, `settlement_lines`) sont **différées à S13.7** (colonnes à masquer conditionnellement + `materialization_trace` jamais synchronisable). Le test d'intégration `tests/integration/sync/test_powersync_publication.py` verrouille l'allowlist exacte.
- **`sslmode`** : `disable` en dev. **Prod = `verify-full`** (défaut PowerSync) avec CA/certs.
- **`logging.level`** : garder `info` en prod (le niveau `debug` logge les payloads de réplication).
- **`client_auth`** : en dev, `audience: [prosperity-api]` (= `jwt_audience`, ADR 0016) + `allow_local_jwks: true` pour le JWKS placeholder http. **Dettes assumées** : le JWKS réel et l'`iss` (`prosperity-auth`) sont câblés en **S13.8/E14**.

## Prod (E16 — pointeur, non implémenté ici)

- **Quadlet** : une unit systemd dédiée par container (Postgres, PowerSync), réseau interne.
- **Caddy + Cloudflare Tunnel** : exposition TLS de l'API PowerSync.
- **`sslmode=verify-full`** sur les deux connexions, certs montés en secret.
- **Restic → B2** : sauvegardes (cohérent avec le choix "une seule famille de moteur" Postgres, pas de MongoDB).
- **Rejouer le SQL** : `compose/initdb/00_powersync_roles.sql` (rôles), `05_powersync_storage_db.sql` (base storage) et `10_powersync_publication.sql` (publication) sont idempotents et constituent le SQL canonique à reprendre en prod **après** `alembic upgrade head`.

## Dépannage logical replication

| Symptôme | Cause probable | Fix |
|---|---|---|
| `wal_level` reste `replica` | Modifié via `ALTER SYSTEM` sans redémarrage, ou volume initialisé avant l'ajout du `command:` | Vérifier le `command:` du service `postgres` (`SHOW wal_level;`) ; `podman compose down && up` |
| `relation "accounts" does not exist` à l'init | `10_powersync_publication.sql` joué avant `alembic upgrade head` | Normal au 1er boot : la publication est créée vide. Rejouer le script après les migrations (étape 3) |
| `permission denied for table …` | Rôle `powersync` sans `SELECT` sur une table publiée | Rejouer `10_powersync_publication.sql` (il ajoute le `GRANT SELECT`) |
| `replication slot "…" already exists` / slot orphelin | Container PowerSync recréé sans drop du slot ; le WAL s'accumule | `SELECT slot_name, active FROM pg_replication_slots;` puis `SELECT pg_drop_replication_slot('<slot>')` sur les slots inactifs |
| `could not connect to storage` | Base `powersync_storage` absente, ou `PS_STORAGE_URI` faux | Vérifier les logs initdb (`05_powersync_storage_db.sql` joué) ; recréer le volume `pg_data` si init partiel |
| `FATAL: number of requested standby connections exceeds max_wal_senders` | `max_wal_senders` trop bas | Augmenter le flag dans le `command:` du service `postgres` |
| Disque qui gonfle | Slot inactif qui retient le WAL (laptop en veille) | `wal_sender_timeout=0` en dev ; dropper les slots morts |
| PowerSync ne devient jamais `ready` | Publication vide / sync rules référençant une table non publiée | Vérifier `SELECT * FROM pg_publication_tables WHERE pubname='powersync';` ; `categories` doit y figurer (référencée par `sync_rules.yaml`) |

## Validation

- **Manuel** : `podman compose -f compose.dev.yml up` (séquence ci-dessus) puis `bash scripts/smoke_powersync.sh`.
- **CI nightly** : job `powersync-smoke` (`.github/workflows/nightly.yml`), re-runnable via `workflow_dispatch` — boote la stack, applique migrations + publication, exécute le smoke.
- **Allowlist** : `uv run pytest tests/integration/sync/test_powersync_publication.py` (vérifie l'ensemble exact des tables publiées + le moindre privilège du rôle).
