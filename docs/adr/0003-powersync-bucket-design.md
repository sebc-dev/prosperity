# Découpage en buckets PowerSync et tables server-only

Les invariants de visibilité du domaine (compte personnel étanche, dette `personal_share_request` masquant la transaction source, isolation des pending actions par utilisateur, audit logs admin uniquement) ne sont pas satisfiables avec un sync rule naïf "tout le foyer voit tout". Nous décidons d'un découpage en **quatre familles de buckets** (`user_personal_{user_id}`, `account_shared_{account_id}`, `user_debt_{user_id}`, `household`) et d'un set de **tables server-only** non sync via PowerSync mais accessibles par API REST/SSE (`pending_actions`, `audit_logs`, `pat_tokens`, PII utilisateur). Pour les dettes `personal_share_request`, on applique un **column-level filter** dans la sync rule qui masque `source_transaction_id` au débiteur (seul le propriétaire du compte source le reçoit), évitant le besoin d'une table dérivée séparée.

## Consequences

- Le schéma physique doit porter les clés de partitionnement adéquates dès la première migration (notamment `account_id` denormalisé sur les `transactions`/`splits` pour le bucketing).
- Une table `users_public` (`user_id`, `display_name`, `avatar_url`, `role`) est synchronisée au foyer pour permettre l'affichage du nom des autres membres sans dupliquer en snapshot et sans exposer la PII.
- Les `pending_actions` (F14) ne tirent pas parti de l'offline-first : le workflow de confirmation passe par API + SSE, ce qui est cohérent avec leur durée de vie courte (24h) et le fait que la confirmation requiert une authentification fraîche.
- Tout nouveau type d'entité doit décider explicitement de son bucket d'appartenance — à intégrer dans le template de spec de module.
- Décision dépendante des ADR 0001 (aggregate immutable) et 0002 (dettes projection).
