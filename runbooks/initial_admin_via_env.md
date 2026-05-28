# Runbook — Bootstrap admin initial via env vars (S03.3)

> Story : [S03.3 — Fallback env vars `INITIAL_ADMIN_*`](https://github.com/sebc-dev/prosperity/issues/65)
> Lié à : E03 (`docs/roadmap/E03-household-bootstrap.md`), ADR 0010 (foyer singleton + lock-after-init).

## Quand l'utiliser

- **Restore from backup automatisé** (CI/CD redéploie une instance vierge sans intervention humaine).
- **Provisioning d'environnement de test reproductible** (recettes, staging, ephemeral envs).
- **Déploiement public exposé directement sur Internet** — l'opérateur n'a pas la garantie d'atteindre `/setup` avant un attaquant qui scanne les nouvelles IPs (Shodan, Censys) ; cf. la note de risque "bootstrap race attack" dans l'issue S03.2 (#64).

**NE PAS** utiliser pour un démarrage manuel ordinaire sur réseau privé ou pour le dev local — préférer le flow web `/setup`, plus simple et déjà testé interactivement.

## Pré-requis

- L'instance n'est pas encore initialisée : la table `users` est vide ET `household.initialized_at IS NULL` (cf. `accounts.service.setup.is_setup_open`).
- Vous avez accès à un shell sur la machine où vous voulez générer le hash (ce peut être votre poste local — le hash n'a pas besoin d'être généré sur l'instance cible).
- Python ≥ 3.13 + `pwdlib` installés (déjà présent comme dépendance du projet : `uv run python scripts/hash_password.py` fonctionne directement à la racine).

## Procédure

### 1. Générer le hash Argon2id hors-ligne

```bash
uv run python scripts/hash_password.py
# Password: (input masqué)
# Confirm:  (input masqué)
# $argon2id$v=19$m=65536,t=3,p=4$...   ← copier cette ligne
```

Le script :

- Lit le mdp via `getpass.getpass()` (jamais dans l'historique shell, jamais dans `ps aux`).
- Refuse de lire depuis stdin non-TTY (`< secrets.txt` est rejeté avec exit code 2) — sinon `getpass` retomberait sur `input()` avec echo activé.
- Refuse les mdp < 12 caractères (cohérence stricte avec `SetupRequest.password` qui impose la même borne pour le premier admin).
- Calcule un hash via `pwdlib.PasswordHash.recommended()`, **identique** à celui utilisé par `/setup` et `/auth/login` — un round-trip parfait est garanti par construction.

### 2. Exporter les env vars

```bash
export INITIAL_ADMIN_EMAIL="admin@foyer.local"
export INITIAL_ADMIN_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$...'
# Optionnel (défauts respectifs : "Admin" / "Foyer")
export INITIAL_ADMIN_DISPLAY_NAME="Sébastien"
export INITIAL_HOUSEHOLD_NAME="Foyer Dupont"
```

**ATTENTION** : les **single quotes** (`'...'`) sont obligatoires sur `INITIAL_ADMIN_PASSWORD_HASH`. Le hash contient des `$` que le shell expanderait sinon comme des variables vides → hash corrompu → bootstrap skip silencieux à cause de la probe canonique.

### 3. Démarrer l'app

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Au boot, vous devez voir un log structuré :

```
INFO  initial_admin_created  user_id=<uuid>
```

Le log **n'inclut pas l'email** (parité avec `setup_completed` qui ne le logge pas non plus — l'email vit dans la table `users`, le log structuré n'a pas vocation à le dupliquer).

### 4. Vérifier

```bash
curl -i http://localhost:8000/setup
# HTTP/1.1 404 Not Found   ← lock-after-init effectif

curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@foyer.local","password":"<le mdp que vous avez tapé>"}'
# HTTP/1.1 200 OK
# {"access_token":"...","refresh_token":"...","token_type":"bearer"}
```

### 5. Post-démarrage (recommandé)

Une fois le bootstrap confirmé, **unset** les env vars pour éviter qu'un redémarrage ultérieur les ré-évalue inutilement :

```bash
unset INITIAL_ADMIN_EMAIL INITIAL_ADMIN_PASSWORD_HASH \
      INITIAL_ADMIN_DISPLAY_NAME INITIAL_HOUSEHOLD_NAME
```

Les redémarrages ultérieurs n'en ont plus besoin (lock-after-init est permanent ; le précheck `is_setup_open` continuera à skipper même si les env vars restent en place, mais retirer les fait disparaître du surface d'attaque).

## Sécurité

### Règles de base

- **JAMAIS** de mot de passe en clair dans `INITIAL_ADMIN_PASSWORD_HASH`. L'orchestrateur probe le format via `pwdlib.PasswordHash.recommended().verify("x", hash)` et **skip** (log `error initial_admin_hash_invalid`) si la chaîne ne se laisse pas identifier comme un hash. Une chaîne arbitraire passerait dans la DB sinon, et `/auth/login` retournerait alors un 500 (oracle vs 401) tout en étant verrouillé à `/setup` 404 = takeover impossible à débloquer sans `DELETE FROM users` manuel.
- Le hash Argon2id ne permet **pas** de retrouver le mdp en clair (résistant aux GPU/ASIC dans les paramètres recommandés par `pwdlib`), mais il reste sensible : un attaquant qui exfiltre le hash peut monter du brute-force hors-ligne. Stocker comme un secret (chmod, secrets manager).
- Le script `scripts/hash_password.py` calcule le hash **localement** sur la machine où il tourne — aucun appel réseau, le mdp ne quitte jamais le process.

### Channels de fuite à connaître

| Channel | Risque | Mitigation |
|---|---|---|
| Shell history (`~/.bash_history`, `~/.zsh_history` avec `share_history`) | Le `export INITIAL_ADMIN_PASSWORD_HASH=...` est mémorisé en clair | Préférer un secrets manager qui injecte au runtime, ou préfixer la commande d'un espace si `HISTCONTROL=ignorespace` (bash) / `setopt HIST_IGNORE_SPACE` (zsh) |
| CI `set -x` / `trace_log` | Un assignment sous trace shell affiche la valeur expandée sur stderr → hash dans les logs CI | Désactiver `set -x` autour de l'export ; utiliser les "masked variables" du provider CI |
| `printenv` / `/proc/<pid>/environ` | Tout user local avec le même UID peut lire l'environnement du process | Restreindre l'accès shell sur l'instance ; isolation par container/utilisateur dédié |
| Dockerfile `ENV` | Grave la valeur dans les layers (visible via `docker history`) | Utiliser `--env` à `docker run` ou un secret manager (Docker secrets, Kubernetes secrets) |
| Log shippers (Datadog, Filebeat, …) | Certains agents scrapent l'environnement au startup | Vérifier la config ; mettre `INITIAL_ADMIN_*` sur une liste de variables censurées |
| SQLAlchemy debug | En debug local, désactiver `hide_parameters=True` ferait fuiter les bound params (dont le hash) dans les logs SQL | Le défaut prod est `hide_parameters=True` (cf. `backend/shared/db.py`). Documenté dans `CONTRIBUTING` — ne pas désactiver en prod |

### Préférer un secrets manager

Pour tout déploiement non-jetable, plutôt qu'un `.env` ou un `export` :

- **Doppler** / **Vault** / **AWS Secrets Manager** / **Google Secret Manager** : le secret reste centralisé, rotatable, auditable.
- **Docker / Kubernetes secrets** : injectés en lecture seule via `tmpfs`, jamais persistés sur disque.
- Si vous DEVEZ utiliser un `.env`, faites `chmod 600` et **excluez-le du contrôle de version** (vérifier `.gitignore`).

## Modes d'échec & comportement attendu

L'orchestrateur ne lève **jamais** d'exception sur les pannes infra/DB : l'app doit pouvoir démarrer même si le bootstrap échoue, pour que l'opérateur puisse `/setup` manuellement.

| Situation | Comportement | Log |
|---|---|---|
| Aucune env var set | Démarrage normal (mode standard) | (silence) |
| Une seule des deux set (EMAIL ou HASH) | Démarrage normal sans bootstrap | `warning initial_admin_partial_config has_email=… has_hash=…` |
| Hash non reconnu par `pwdlib` (mdp en clair, chaîne tronquée, …) | Skip bootstrap, démarrage normal | `error initial_admin_hash_invalid` |
| Env vars set + DB déjà initialisée (re-démarrage ou autre worker plus rapide) | Démarrage normal, admin existant intact | `info initial_admin_skipped reason=already_initialized` |
| Env vars set + race entre workers (SQLSTATE 23505/23514/40001) | Un seul gagne, les autres skippent silencieusement | `info initial_admin_race_lost sqlstate=…` (sur les perdants) |
| Erreur DB transitoire (SQLSTATE 08***, connexion brisée, instance en train de booter) | Retry léger (3× avec backoff 0.5/1/2s) | `warning initial_admin_db_error_retry attempt=… sqlstate=…` |
| Erreur DB persistante après retries OU SQLSTATE non classifié | App démarre sans admin ; `/setup` manuel reste possible | `error initial_admin_db_error_persistent attempt=… sqlstate=… error_type=…` |
| Bug applicatif (TypeError, AttributeError, …) | **Propagé** — crash startup intentionnel pour révéler le bug | (traceback) |

## Diagnostic post-mortem

Si après le boot vous voyez `/setup` retourner 200 (au lieu de 404 attendu) :

1. Le bootstrap a échoué silencieusement (cf. table ci-dessus). Vérifier les logs `initial_admin_*` au démarrage.
2. Cas typiques :
   - `initial_admin_partial_config` → revoir l'env file (typo, variable absente).
   - `initial_admin_hash_invalid` → re-générer le hash via `scripts/hash_password.py` ; vérifier les single quotes autour du `$argon2id$...` à l'export.
   - `initial_admin_db_error_persistent` → la DB n'était pas prête au moment du boot (cas Kubernetes sans `initContainer` qui attend Postgres). Redémarrer le pod après que la DB soit healthy, ou ajouter un readiness gate côté infra.
3. Solution de repli : `/setup` manuellement via le navigateur (la fenêtre d'exposition est minimale si le service est en réseau privé).

## Notes V1

- `base_currency` est figé à `"EUR"` (ADR 0008). Pas d'env var pour le changer en V1. Si vous avez besoin d'une autre devise, c'est un changement de code (E16+).
- Un seul admin créable au boot via env vars. Les autres utilisateurs passent par `/accept-invite` (E04, à venir).
- L'env-var bootstrap ne sait pas activer la 2FA automatiquement (E04). L'admin pourra l'activer post-login.
