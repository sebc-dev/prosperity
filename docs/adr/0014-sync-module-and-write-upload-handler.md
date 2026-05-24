# Module `sync` + contrat du write upload handler PowerSync

Le write upload handler est le point de convergence de toutes les décisions de sync (ADR 0001 aggregate immutable, ADR 0002 dettes projection, ADR 0003 bucket design) et de l'invariant transversal #7 "server-authoritative". Le test strategy (§4.5) demande une couverture "exhaustive" mais le **contrat exact** n'était nulle part fixé. Nous décidons :

**Nouveau module `modules/sync/`** au sommet du graphe directionnel juste sous `mcp` (graphe étendu : `... → sync → mcp`), avec un dispatcher unique qui parse le batch PowerSync et route chaque mutation vers un sous-handler par table (`handlers/transactions.py`, `handlers/settlements.py`, etc.). Les sous-handlers **appellent les `service.py` des modules métier via leur `public.py`** — ils n'écrivent jamais directement en DB. Garantit que toute logique métier passe par les services normaux, qu'elle vienne de l'API REST ou du write upload handler.

**Séquence stricte de 10 étapes par mutation, dans une transaction DB unique** : auth & RBAC → idempotence check (`client_request_id` UUID v7 dans `sync_request_log`) → Pydantic validation → domain validation → DB write → matérialisation synchrone des projections (dettes) → publication d'events sur le mini-bus → commit → append `sync_request_log` → ack. Seuls les délivery email/push sortent en `BackgroundTasks` post-commit.

**`WriteResult.error` typé** (`validation_error`, `immutable_field_violation`, `auth_denied`, ...) : erreurs récupérables → client purge la mutation locale ; erreurs serveur (500) → PowerSync retry automatique.

**`client_request_id` UUID v7** : idempotence en cas de retry après timeout réseau (le log dit "déjà traité" et le serveur ack sans re-écrire). Ordre des mutations dans un batch **préservé** (permet "création compte puis transaction sur ce compte" en un seul batch atomique côté client).

## Consequences

- Le module `sync` est nouveau et doit être ajouté à la liste des modules dans `docs/Architectures BS.md §6` et aux contrats import-linter (cf. ADR 0005).
- Property Hypothesis naturelle : *"pour toute permutation valide d'un batch de mutations, l'état final converge selon l'ordering préservé"* — cible des tests `pytest + Hypothesis` du module `sync` (test strategy §4.5).
- Si une mutation N échoue, les mutations N+1...K restent en queue client pour re-tentative ; pas de rollback de batch entier (les 1...N-1 sont déjà commit, leurs effets valides).
- La matérialisation synchrone des dettes dans la même transaction DB respecte la promesse d'ADR 0002 (cohérence forte read-after-write pour les projections) et reste rapide tant que les recalculs sont localisés (transactions concernées du compte concerné, du budget concerné).
- Le `sync_request_log` server-only (retention 30j) ne fuit jamais via sync vers les clients.
- Décision dépendante des ADR 0001, 0002, 0003, 0005.
