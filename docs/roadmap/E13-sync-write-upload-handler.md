# E13 — Sync module + write upload handler (PowerSync)

> **Durée estimée** : 8-12 jours
> **Statut** : not started
> **Dépend de** : E07, E09, E11
> **Bloque** : E14 (frontend doit se brancher à PowerSync)
> **ADRs activés** : 0003 (bucket design appliqué via sync rules YAML), 0014 (séquence 10 étapes)

---

## Objectif

Setup de PowerSync Service self-hosted + module `modules/sync/` + write upload handler avec la séquence 10 étapes (ADR 0014) + sync rules YAML pour les 4 familles de buckets (ADR 0003) avec column-level filter sur `source_transaction_id`.

C'est l'epic le plus risqué techniquement : conjugue infra (PowerSync Service container + connexion Postgres), code applicatif (dispatcher + 10 étapes), et configuration déclarative (sync rules YAML).

Livrable agrégé : un client PowerSync peut s'authentifier, recevoir les rows visibles selon ses buckets, et envoyer des mutations qui passent par le write upload handler avec validation, idempotence, et matérialisation synchrone des dettes.

---

## Stories

### S13.1 — PowerSync Service self-hosted

**Livrable observable** : un container PowerSync tourne en local (dev compose), connecté à Postgres via logical replication.

| Phase | Description | Diff |
|---|---|---|
| **P13.1.1** | Setup `compose.dev.yml` (Podman compose) avec Postgres 17 + PowerSync Service Open Edition + paramètres de logical replication activés sur Postgres (`wal_level=logical`). Doc README dev | ~120 |
| **P13.1.2** | `powersync/config.yaml` (côté PowerSync Service) : connection Postgres, publication PostgreSQL pour les tables à sync. Tests : démarrer le compose, vérifier que PowerSync est connecté à Postgres et publie un état | ~100 |
| **P13.1.3** | Runbook ops `runbooks/powersync_setup.md` : prod = Quadlet unit dédié (qui sera fini en E16), dev = compose. Variables d'env critiques | ~80 |

> **Deltas d'implémentation (S13.1, cf. issue #186)** — écarts assumés vs le découpage initial, sans contradiction d'ADR :
> - **Bucket storage ajouté.** PowerSync exige un bucket storage **séparé de la source**. Choix : base Postgres dédiée `powersync_storage` (rôle `ps_storage`) dans la même instance dev — pas de MongoDB (une seule famille de moteur, aligné Restic→B2 d'E16). Prod (E16) peut séparer les instances.
> - **`client_auth` obligatoire au boot.** Le service ne démarre pas sans. Bloc dev : `audience: [prosperity-api]` (= `jwt_audience`, ADR 0016) + `allow_local_jwks: true`. JWKS réel + `iss` (`prosperity-auth`) câblés en **S13.8/E14**.
> - **Tables debt-projection différées à S13.7.** `debts`/`share_requests`/`settlements`/`settlement_lines` portent `account_id`/`source_transaction_id` (masquage **conditionnel** per-destinataire) et `materialization_trace` (jamais synchronisé). Une publication colonne globale ne convient pas (le propriétaire doit les recevoir). S13.1 prouve la connectivité avec un set sûr **sans colonne sensible** : `accounts`, `account_members`, `transactions`, `splits`, `categories`, `budgets`, `budget_contributors`.
> - **Ordre de setup.** La `PUBLICATION` (frontière de sécurité, jamais `FOR ALL TABLES`) est posée **hors Alembic** et **après** `alembic upgrade head` (elle référence les tables applicatives). Le script `compose/initdb/10_powersync_publication.sql` est idempotent + additif + à garde d'existence ; le runbook documente la séquence.
> - **Garde-fou prod `PS_*`.** Les credentials PowerSync vivent hors Pydantic → non couverts par `_forbid_dev_defaults_in_prod`. Asymétrie documentée dans le runbook ; équivalent prod à ajouter en **E16**.

---

### S13.2 — Scaffolding du module `sync`

| Phase | Description | Diff |
|---|---|---|
| **P13.2.1** | `modules/sync/__init__.py`, `public.py`, `domain.py` (vide pour l'instant), `service/` (vide), `handlers/` (sous-dossier pour les sous-handlers par table) | ~60 |
| **P13.2.2** | Table `sync_request_log` : PK composite `(user_id, client_request_id)` (idempotence scopée user, ferme l'oracle cross-user — review Sécu F1), `table_name`, `processed_at`. Server-only. Migration `0019_sync_request_log.py` (down revision `0018` — dernière migration mergée). Retention 30j : **purge nightly idempotente déclenchée par le cron CI** (`nightly.yml`, entrypoint `backend.scripts.purge_sync_request_log`) — **PAS** d'APScheduler runtime ici (**D2** : APScheduler reporté à l'épic récurrences, ADR 0007 / F06) | ~120 |
| **P13.2.3** | Schemas Pydantic pour le format batch PowerSync : `BatchUpload(mutations=list[Mutation])`, `Mutation(client_request_id, table, op='insert|update|delete', payload)`, `WriteResult(client_request_id, success, error?)`. Tests | ~150 |

---

### S13.3 — Dispatcher + étapes 1-2 (auth + idempotence)

| Phase | Description | Diff |
|---|---|---|
| **P13.3.1** | `modules/sync/service/dispatcher.py` : `process_batch(user, batch) → list[WriteResult]`. Pour chaque mutation : récupère le sous-handler de la table, ou retourne `WriteResult.error='unknown_table'`. Tests unitaires avec sous-handler mocké | ~150 |
| **P13.3.2** | Step 1 (auth + RBAC) : vérifie que `user` peut muter cette table sur ce row (par exemple créer une `Transaction` sur un compte dont il est member). Centralisé dans `dispatcher.py` via lookup `(table, op) → permission_check_fn`. Tests | ~200 |
| **P13.3.3** | Step 2 (idempotence) : si `client_request_id` ∈ `sync_request_log` → ack sans re-écrire. Tests : rejouer la même mutation N fois = 1 commit | ~150 |

---

### S13.4 — Sous-handlers (étapes 3-7 par table)

| Phase | Description | Diff |
|---|---|---|
| **P13.4.1** | `handlers/transactions.py` : appelle `transactions.public.create_draft`/`add_split`/`transition_*` selon l'op. Validation Pydantic → domain validation → DB write → events. Tests intégration avec `db_session` | ~250 |
| **P13.4.2** | `handlers/accounts.py` (→ `accounts.public`), `handlers/budget.py` (→ `budget.public`, qui héberge **`Category` ET `Budget`** : pas de module `categories` séparé). Tests | ~300 |
| **P13.4.3** | `handlers/settlements.py`, `handlers/share_requests.py` : appellent `debts.public` (`create_settlement`, `create_share_request`, `revoke_share_request` — **seuls writes debts autorisés côté client**). `debt_overrides`/`share_ratio` **descopés** : aucun write public n'existe côté debts, et `debt_generation_override` (reclassement F10) est déclenché par les events budget, pas par un write client. Tests | ~250 |
| **P13.4.4** | `handlers/reconciliations.py` (préparation V1) : placeholder qui retourne `WriteResult.error='not_implemented_yet'`. Tests | ~50 |

---

### S13.5 — Étape 6 : matérialisation synchrone des dettes (verrou de régression)

> **Reframe.** La matérialisation est **déjà automatique** via le mini-bus : `transactions.public.transition_to_confirmed`/`void`/`update_editable_fields` appellent `dispatch(session, event)`, et `backend/main.py` câble `subscribe_async(materialize_overflow, …)`. `debts.public.create_share_request` matérialise le `Debt` dans la même transaction. Il n'y a **pas** de fonction `materialize_overflow_for_tx(tx_id)`. Cette story est donc un **verrou de régression** (tests read-after-write via le chemin sync), pas du nouveau code de matérialisation.

| Phase | Description | Diff |
|---|---|---|
| **P13.5.1** | Tests : un batch `{create_draft, add_split dépassant budget, transition_to_confirmed}` via `process_batch` → la `Debt` overflow est lisible dans la **même** transaction (read-after-write) et persiste post-commit ; un `void` la retire. Vérifie que le handler s'appuie sur le `dispatch` des services (subscribers wirés en `main.py`), pas sur un appel manuel | ~150 |
| **P13.5.2** | Tests : un `create_share_request` via `process_batch` → `Debt` matérialisé dans la même transaction ; `revoke_share_request` le supprime. Verrou : si un handler court-circuite le mini-bus, un test casse | ~120 |

---

### S13.6 — Étapes 7-10 (events, commit, log, ack)

| Phase | Description | Diff |
|---|---|---|
| **P13.6.1** | **Transaction par mutation (étapes 8-9).** Commit par mutation : échec de N → rollback de N seulement, 1..N-1 restent committées (ADR 0014). Append `sync_request_log` (étape 9) dans la même transaction que le write. **Reframe (vs roadmap initial) :** pas de buffering d'events — le mini-bus dispatche **in-transaction** (ADR 0014 : « events → commit »). Seul le delivery email/push sort post-commit en `BackgroundTasks`, mais `notifications` est un stub → hook no-op différé. Tests | ~150 |
| **P13.6.2** | Ack (étape 10) construit le `WriteResult` avec server-generated IDs (ex. `id` d'un insert) si nécessaire. Tests | ~120 |
| **P13.6.3** | Erreur typée : `WriteResult.error` mappe les exceptions du domain (`ImmutableFieldViolation`, `UncategorizedExpenseError`, etc.) en codes typés `validation_error`, `immutable_field_violation`, `auth_denied`, etc. Tests httpx couvrant toutes les catégories d'erreur | ~150 |

---

### S13.7 — Sync rules YAML (buckets ADR 0003)

| Phase | Description | Diff |
|---|---|---|
| **P13.7.1** | `powersync/sync_rules.yaml` : bucket `user_personal_{user_id}` (tables `accounts WHERE owner_id = $user`, transactions/splits associées, budgets perso, notifications, savings perso). Tests : un user voit ses rows, pas celles des autres | ~200 |
| **P13.7.2** | Bucket `account_shared_{account_id}` : tables `accounts WHERE id IN (SELECT account_id FROM account_members WHERE user_id = $user)`, leurs transactions/splits, account_members, budgets communs. Tests | ~150 |
| **P13.7.3** | Bucket `user_debt_{user_id}` : `debts WHERE from_user_id = $user OR to_user_id = $user`, settlements/settlement_lines associés, share_requests. **Column-level filter sur DEUX colonnes** : `source_transaction_id` **ET** `account_id` retournés NULL quand origine `personal_share_request` ET user n'est pas owner du compte source (ADR 0003 maj review #22 / S09.4 #145). Tests cruciaux : un débiteur ne voit jamais ces deux colonnes | ~250 |
| **P13.7.4** | Bucket `household` : `categories`, `users_public`. Tests | ~100 |

---

### S13.8 — Endpoint HTTP `POST /sync/upload`

| Phase | Description | Diff |
|---|---|---|
| **P13.8.1** | Route `POST /sync/upload` qui appelle `dispatcher.process_batch(current_user, body)`. Tests intégration end-to-end : batch de 5 mutations diverses, vérifier que toutes commit ou que les erreurs sont typées correctement | ~150 |

---

### S13.9 — Hypothesis : invariants sync

| Phase | Description | Diff |
|---|---|---|
| **P13.9.1** | Strategy `mutation_batch_strategy` : génère un batch de mutations cohérentes (ex. create account → create tx → confirm tx). Property : (1) pour toute permutation valide, l'état final converge ; (2) rejouer le même batch est idempotent ; (3) un user ne peut jamais affecter le compte d'un autre. Run avec `max_examples=100` | ~250 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S13.1 (3 phases) | PowerSync Service setup | 300 | 300 |
| S13.2 (3 phases) | Scaffolding + sync_request_log | 330 | 630 |
| S13.3 (3 phases) | Dispatcher + auth + idempotence | 500 | 1130 |
| S13.4 (4 phases) | Sous-handlers | 850 | 1980 |
| S13.5 (2 phases) | Matérialisation synchrone dettes | 270 | 2250 |
| S13.6 (3 phases) | Events + commit + log + ack | 450 | 2700 |
| S13.7 (4 phases) | Sync rules YAML | 700 | 3400 |
| S13.8 (1 phase) | Endpoint upload | 150 | 3550 |
| S13.9 (1 phase) | Hypothesis | 250 | 3800 |
| **Total** | **9 stories / 24 phases** | **~3800 lignes** | |

---

## Critères d'acceptation

- [ ] PowerSync Service tourne en dev compose, connecté à Postgres
- [ ] `POST /sync/upload` traite un batch de N mutations avec ordering préservé
- [ ] `client_request_id` (UUID v7 recommandé côté client ; le serveur accepte **tout UUID bien formé** — **D7**) → idempotence stricte **scopée user** (replay = no-op)
- [ ] Matérialisation synchrone des dettes après write transaction (visible post-commit)
- [ ] Erreurs typées : `validation_error`, `immutable_field_violation`, `auth_denied`, `unknown_table`, etc.
- [ ] Sync rules : un user ne reçoit jamais les comptes personnels d'un autre user (testé)
- [ ] Column-level filter : `source_transaction_id` **ET** `account_id` NULL pour dettes `personal_share_request` quand user ≠ owner compte source (testé) — les deux colonnes (ADR 0003 maj #145)
- [ ] Property Hypothesis convergence + idempotence + isolation passe
- [ ] Coverage `modules/sync/` ≥ 95% (cible exhaustive cf. stratégie de tests §4.5)

---

## Notes pour l'implémenteur

- **C'est l'epic le plus risqué.** Si quelque chose dérape, c'est probablement sur la connexion logical replication Postgres ↔ PowerSync Service. Documenter le runbook ops en détail.
- L'ordering du batch est préservé en parcourant `mutations` dans l'ordre array. Pas de parallélisation. Pour un batch de 20+ mutations, c'est OK (chacune en quelques ms).
- **Events in-transaction (corrigé).** Le mini-bus `shared/events.py` dispatche déjà les events **dans** la transaction de requête (`dispatch(session, event)`), conforme à l'ADR 0014 (« events → commit ») : un handler async qui lève **rollback** le write (atomicité de la matérialisation). Ne PAS réintroduire de buffering post-commit pour les events. Seul le **delivery** email/push doit sortir post-commit en `BackgroundTasks` — et `notifications` étant un stub, ce hook est un no-op différé.
- Les sync rules YAML PowerSync sont déclaratives — pas du Python. Versionner avec attention, écrire un test qui parse le YAML et valide la syntaxe au démarrage.
- **Column-level filter (DEUX colonnes)** : la sync rule PowerSync utilise une SELECT clause par bucket masquant **`source_transaction_id` ET `account_id`** (ADR 0003 maj #145). On applique le même `CASE WHEN origin = 'personal_share_request' AND :user_id NOT IN (SELECT owner_id FROM accounts WHERE id = source_account_id_via_transaction) THEN NULL ELSE <col> END` aux deux colonnes. Vérifier la perf — ce CASE peut être lourd sur volume. `materialization_trace` reste server-only.
- Le PowerSync Service côté serveur N'EXÉCUTE PAS `/sync/upload` lui-même : les writes des clients passent par notre backend FastAPI. Le PowerSync Service ne gère que la **download** sync (push des reads vers le client). Bien différencier les deux flows.
