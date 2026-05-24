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

---

### S13.2 — Scaffolding du module `sync`

| Phase | Description | Diff |
|---|---|---|
| **P13.2.1** | `modules/sync/__init__.py`, `public.py`, `domain.py` (vide pour l'instant), `service/` (vide), `handlers/` (sous-dossier pour les sous-handlers par table) | ~60 |
| **P13.2.2** | Table `sync_request_log` : `client_request_id` UUID PK, `user_id`, `table_name`, `processed_at`. Server-only. Migration `0016_sync_request_log.py`. Retention 30j (purge nightly via APScheduler job mineur) | ~120 |
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
| **P13.4.2** | `handlers/accounts.py`, `handlers/categories.py`, `handlers/budgets.py` : mêmes patterns appelant les `public.py` respectifs. Tests | ~300 |
| **P13.4.3** | `handlers/settlements.py`, `handlers/share_requests.py`, `handlers/debt_overrides.py` : appellent `debts.public` (le seul write côté client autorisé sur debts est `share_ratio` + share_request + settlement). Tests | ~250 |
| **P13.4.4** | `handlers/reconciliations.py` (préparation V1) : placeholder qui retourne `WriteResult.error='not_implemented_yet'`. Tests | ~50 |

---

### S13.5 — Étape 6 : matérialisation synchrone des dettes

| Phase | Description | Diff |
|---|---|---|
| **P13.5.1** | Dans `handlers/transactions.py` après `transition_to_confirmed` (ou void) : appel synchrone à `debts.public.materialize_overflow_for_tx(tx_id)` (créé en E11) DANS LA MÊME TRANSACTION DB. Tests : write une tx → dette overflow visible immédiatement post-commit | ~150 |
| **P13.5.2** | Mêmes appels synchrones pour les autres handlers qui peuvent toucher les dettes : `handlers/share_requests.py` (create → matérialise une dette), `handlers/debt_overrides.py` (change `share_ratio` → recalcul). Tests | ~120 |

---

### S13.6 — Étapes 7-10 (events, commit, log, ack)

| Phase | Description | Diff |
|---|---|---|
| **P13.6.1** | Events post-commit : le dispatcher capture les events émis dans la transaction (via `shared/events.py`), les buffère, et les dispatche **après commit DB**. Cela évite qu'un event subscriber qui fait un BackgroundTask déclenche un push notification avant que le commit soit garanti. Tests | ~180 |
| **P13.6.2** | Append `sync_request_log` (étape 9) dans la même transaction DB que le write. Ack (étape 10) construit le `WriteResult` avec server-generated IDs si nécessaire. Tests | ~120 |
| **P13.6.3** | Erreur typée : `WriteResult.error` mappe les exceptions du domain (`ImmutableFieldViolation`, `UncategorizedExpenseError`, etc.) en codes typés `validation_error`, `immutable_field_violation`, `auth_denied`, etc. Tests httpx couvrant toutes les catégories d'erreur | ~150 |

---

### S13.7 — Sync rules YAML (buckets ADR 0003)

| Phase | Description | Diff |
|---|---|---|
| **P13.7.1** | `powersync/sync_rules.yaml` : bucket `user_personal_{user_id}` (tables `accounts WHERE owner_id = $user`, transactions/splits associées, budgets perso, notifications, savings perso). Tests : un user voit ses rows, pas celles des autres | ~200 |
| **P13.7.2** | Bucket `account_shared_{account_id}` : tables `accounts WHERE id IN (SELECT account_id FROM account_members WHERE user_id = $user)`, leurs transactions/splits, account_members, budgets communs. Tests | ~150 |
| **P13.7.3** | Bucket `user_debt_{user_id}` : `debts WHERE from_user_id = $user OR to_user_id = $user`, settlements/settlement_lines associés, share_requests. **Column-level filter** : `source_transaction_id` retourné NULL quand origine `personal_share_request` ET user n'est pas owner du compte source. Tests cruciaux : un débiteur ne voit jamais le source_tx_id qu'il ne devrait pas voir | ~250 |
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
- [ ] `client_request_id` UUID v7 → idempotence stricte (replay = no-op)
- [ ] Matérialisation synchrone des dettes après write transaction (visible post-commit)
- [ ] Erreurs typées : `validation_error`, `immutable_field_violation`, `auth_denied`, `unknown_table`, etc.
- [ ] Sync rules : un user ne reçoit jamais les comptes personnels d'un autre user (testé)
- [ ] Column-level filter : `source_transaction_id` NULL pour dettes `personal_share_request` quand user ≠ owner compte source (testé)
- [ ] Property Hypothesis convergence + idempotence + isolation passe
- [ ] Coverage `modules/sync/` ≥ 95% (cible exhaustive cf. stratégie de tests §4.5)

---

## Notes pour l'implémenteur

- **C'est l'epic le plus risqué.** Si quelque chose dérape, c'est probablement sur la connexion logical replication Postgres ↔ PowerSync Service. Documenter le runbook ops en détail.
- L'ordering du batch est préservé en parcourant `mutations` dans l'ordre array. Pas de parallélisation. Pour un batch de 20+ mutations, c'est OK (chacune en quelques ms).
- Les events émis dans une transaction DB doivent être **buffered** puis dispatchés **après commit**, sinon les BackgroundTasks (push, email) peuvent partir avant le commit. À factoriser dans `shared/events.py` avec un mode "transactional dispatch" qui supporte rollback.
- Les sync rules YAML PowerSync sont déclaratives — pas du Python. Versionner avec attention, écrire un test qui parse le YAML et valide la syntaxe au démarrage.
- **Column-level filter** : la sync rule PowerSync utilise une SELECT clause par bucket. On peut écrire `SELECT id, from_user_id, to_user_id, amount_cents, currency, CASE WHEN origin = 'personal_share_request' AND :user_id NOT IN (SELECT owner_id FROM accounts WHERE id = source_account_id_via_transaction) THEN NULL ELSE source_transaction_id END AS source_transaction_id FROM debts WHERE ...`. Vérifier la perf — cette CASE peut être lourde sur volume.
- Le PowerSync Service côté serveur N'EXÉCUTE PAS `/sync/upload` lui-même : les writes des clients passent par notre backend FastAPI. Le PowerSync Service ne gère que la **download** sync (push des reads vers le client). Bien différencier les deux flows.
