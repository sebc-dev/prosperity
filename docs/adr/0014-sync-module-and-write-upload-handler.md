# Module `sync` + contrat du write upload handler PowerSync

Le write upload handler est le point de convergence de toutes les décisions de sync (ADR 0001 aggregate immutable, ADR 0002 dettes projection, ADR 0003 bucket design) et de l'invariant transversal #7 "server-authoritative". Le test strategy (§4.5) demande une couverture "exhaustive" mais le **contrat exact** n'était nulle part fixé. Nous décidons :

**Nouveau module `modules/sync/`** au sommet du graphe directionnel juste sous `mcp` (graphe étendu : `... → sync → mcp`), avec un dispatcher unique qui parse le batch PowerSync et route chaque mutation vers un sous-handler par table (`handlers/transactions.py`, `handlers/settlements.py`, etc.). Les sous-handlers **appellent les `service.py` des modules métier via leur `public.py`** — ils n'écrivent jamais directement en DB. Garantit que toute logique métier passe par les services normaux, qu'elle vienne de l'API REST ou du write upload handler.

**Séquence stricte de 10 étapes par mutation, dans une transaction DB unique** : auth & RBAC → idempotence check (`client_request_id` dans `sync_request_log`, lookup **scopé user** sur la PK composite `(user_id, client_request_id)`) → Pydantic validation → domain validation → DB write → matérialisation synchrone des projections (dettes) → publication d'events sur le mini-bus → **append `sync_request_log` (DANS la même transaction que le write)** → **commit** → ack. Seuls les délivery email/push sortent en `BackgroundTasks` post-commit.

> **Précision atomicité (S13.6 / delta D-B).** L'append du journal d'idempotence et le DB write sont **committés atomiquement** : l'append vit DANS la transaction du write, **avant** le commit (et non après). Lue à la lettre, la formulation initiale « commit → append » ouvrait une fenêtre de crash *entre* le commit du write et l'append — le write serait alors persisté **sans** sa ligne d'idempotence, et un replay le ré-écrirait (double-write). La frontière transactionnelle est **par mutation** : un échec rollback la mutation N seule (1..N-1 restent committées, cf. *Consequences*). Le mini-bus dispatche les events **in-transaction** (atomicité matérialisation, ADR 0002) — pas de buffering post-commit.

**`WriteResult.error` typé** (`validation_error`, `immutable_field_violation`, `auth_denied`, ...) : erreurs récupérables → client purge la mutation locale ; erreurs serveur (500) → PowerSync retry automatique.

**`client_request_id`** : idempotence en cas de retry après timeout réseau (le log dit "déjà traité" et le serveur ack sans re-écrire). UUID **v7 recommandé côté client** (ordonnancement temporel), mais **le serveur accepte tout UUID bien formé** (delta **D7**, S13.2 : contraindre la version couplerait le serveur à l'implémentation client ; Pydantic valide la *forme*, l'idempotence repose sur la **valeur scopée user** via la PK composite `(user_id, client_request_id)`, pas sur la version — ce qui ferme aussi la pré-emption / l'oracle cross-user, review Sécu F1). Ordre des mutations dans un batch **préservé** (permet "création compte puis transaction sur ce compte" en un seul batch atomique côté client).

## Consequences

- Le module `sync` est nouveau et doit être ajouté à la liste des modules dans `docs/Architectures BS.md §6` et aux contrats import-linter (cf. ADR 0005).
- Property Hypothesis naturelle : *"pour toute permutation valide d'un batch de mutations, l'état final converge selon l'ordering préservé"* — cible des tests `pytest + Hypothesis` du module `sync` (test strategy §4.5).
- Si une mutation N échoue, les mutations N+1...K restent en queue client pour re-tentative ; pas de rollback de batch entier (les 1...N-1 sont déjà commit, leurs effets valides).
- La matérialisation synchrone des dettes dans la même transaction DB respecte la promesse d'ADR 0002 (cohérence forte read-after-write pour les projections) et reste rapide tant que les recalculs sont localisés (transactions concernées du compte concerné, du budget concerné).
- Le `sync_request_log` server-only (retention 30j) ne fuit jamais via sync vers les clients.
- Décision dépendante des ADR 0001, 0002, 0003, 0005.
