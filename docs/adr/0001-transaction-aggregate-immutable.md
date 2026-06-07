# Transaction = aggregate root immutable à `confirmed`

PowerSync est server-authoritative avec un défaut last-write-wins par endpoint, ce qui rend impossible de garantir mécaniquement l'invariant de double-entrée (somme des splits = 0) sous édition concurrente fine-grained des splits. Nous décidons que `Transaction` est un **aggregate root immutable à l'état `confirmed`** : les splits et le montant total sont gelés à la confirmation ; toute correction passe par `void` + création d'une nouvelle transaction. Seul un set restreint et explicite de champs reste éditable après confirmation (`category_id`, `tags`, `description`, `debt_generation_override`, ajout/retrait de `share_request`) — aucun ne peut casser la double-entrée. Le grain de sync PowerSync est la transaction entière (splits embarqués dans le payload synchronisé), pas le split individuel.

## Considered Options

- **Sync au grain split avec CRDT** : permettrait l'édition concurrente mais coûte un modèle CRDT custom incompatible avec PowerSync prêt à l'emploi, et complique la validation server-side de la double-entrée.
- **Édition libre après confirmation, validation serveur stricte** : tolérable sur les éditions séquentielles mais fragile sous conflits offline (LWW peut sélectionner un état non zero-sum).
- **Aggregate immutable (retenu)** : aligne mécaniquement le modèle de sync avec l'invariant comptable, au prix d'un workflow `void + recreate` pour les corrections — coût accepté car les corrections rétroactives sur des transactions confirmées doivent de toute façon laisser une trace d'audit.

## Consequences

- Les **dettes** ne sont pas des entités mutables côté client : elles sont une projection serveur recalculée à chaque write de transaction. Seuls `share_ratio` (scalaire LWW-safe) et `debt_generation_override` (sur la transaction source) sont des leviers utilisateur.
- Les **soldes passés** sont stables : aucune édition rétroactive d'une transaction confirmée ne peut faire bouger un solde historique.
- La **stratégie de test PowerSync** (`docs/Stratégie de tests.md` §7) doit vérifier les propriétés Hypothesis de convergence sur ce contrat précis : aggregate immutable + projection serveur, **pas** sur un modèle LWW générique.

### Clarification S11.4 — l'édition de `category_id` se propage à la jambe `classification`

L'éditabilité post-`confirmed` de `category_id` (reclassement F10) se **propage à la jambe `classification`** du split, source de vérité de la consommation budget et de l'overflow (E08.5 : la colonne `transactions.category_id` et la jambe restent synchronisées). C'est une réécriture **bornée au champ catégorie** : ni montant ni structure de split ne change ⇒ la double-entrée (somme = 0) est préservée et l'immuabilité de l'aggregate tient. Le grain de sync reste la transaction entière. Sans cette propagation, éditer `category_id` serait un no-op pour la consommation comme pour l'overflow (tous deux lisent la jambe, pas la colonne).
