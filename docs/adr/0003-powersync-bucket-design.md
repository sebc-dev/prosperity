# Découpage en buckets PowerSync et tables server-only

Les invariants de visibilité du domaine (compte personnel étanche, dette `personal_share_request` masquant la transaction source, isolation des pending actions par utilisateur, audit logs admin uniquement) ne sont pas satisfiables avec un sync rule naïf "tout le foyer voit tout". Nous décidons d'un découpage en **quatre familles de buckets** (`user_personal_{user_id}`, `account_shared_{account_id}`, `user_debt_{user_id}`, `household`) et d'un set de **tables server-only** non sync via PowerSync mais accessibles par API REST/SSE (`pending_actions`, `audit_logs`, `pat_tokens`, PII utilisateur). Note : la table d'audit admin est **matérialisée sous le nom `admin_audit_logs`** (S04.2, #75) — `audit_logs` reste le terme générique de cet ADR, `admin_audit_logs` en est la concrétisation. Pour les dettes `personal_share_request`, on applique un **column-level filter** dans la sync rule qui masque `source_transaction_id` au débiteur (seul le propriétaire du compte source le reçoit), évitant le besoin d'une table dérivée séparée.

> **Mise à jour (review #22 / S09.4, #145).** Le masquage débiteur est **étendu à `account_id` en plus de `source_transaction_id`** : le compte personnel source ne doit pas fuiter (glossaire §97-98 ne liste pas `account_id` parmi ce que le débiteur voit). La lecture REST (`GET /debts`, S09.4) masque déjà les **deux** colonnes ; le column-level filter PowerSync d'E13 **doit masquer les deux** (`source_transaction_id` **et** `account_id`) pour ne pas rouvrir la fuite par le canal sync. `materialization_trace` reste server-only (jamais synchronisé ni exposé).

## Consequences

- Le schéma physique doit porter les clés de partitionnement adéquates dès la première migration (notamment `account_id` denormalisé sur les `transactions`/`splits` pour le bucketing).
- Une table `users_public` (`user_id`, `display_name`, `avatar_url`, `role`) est synchronisée au foyer pour permettre l'affichage du nom des autres membres sans dupliquer en snapshot et sans exposer la PII.
- Les `pending_actions` (F14) ne tirent pas parti de l'offline-first : le workflow de confirmation passe par API + SSE, ce qui est cohérent avec leur durée de vie courte (24h) et le fait que la confirmation requiert une authentification fraîche.
- Tout nouveau type d'entité doit décider explicitement de son bucket d'appartenance — à intégrer dans le template de spec de module.
- Le futur garde-fou sync rules (E13) doit cibler le nom physique **`admin_audit_logs`** (et non l'alias générique `audit_logs`) pour vérifier qu'aucune table server-only n'apparaît dans le manifest PowerSync.
- Décision dépendante des ADR 0001 (aggregate immutable) et 0002 (dettes projection).
