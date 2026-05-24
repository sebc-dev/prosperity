# `Reconciliation` comme entité distincte de la transaction

F07 décrit un pointage qui "absorbe l'ID bancaire" sur la transaction locale et autorise le dépointage. Coupler le lien bank ↔ local à un champ de la transaction locale créerait deux problèmes : (1) le dépointage exigerait soit de muter un champ sur une transaction `confirmed` (acceptable mais limite), soit de ramener la transaction à `planned` ce qui viole l'aggregate immutable (ADR 0001) ; (2) les suggestions multiples (un bank tx avec plusieurs candidats locaux) n'auraient pas de représentation propre. Nous décidons que le lien est porté par une **entité `Reconciliation` distincte**, avec sa propre state machine (`suggested → confirmed | rejected`, puis `confirmed → depointed`), ses propres timestamps et auteurs d'audit, et son propre cycle de vie indépendant des transactions liées. **Le dépointage ne ramène jamais la transaction locale à `planned`** — pour annuler une confirmation faite par erreur via pointage, l'utilisateur doit explicitement `void` la transaction et en créer une nouvelle.

## Consequences

- La transaction locale ne porte aucun champ `bank_transaction_id` ; le statut "pointée" se déduit de l'existence d'une `Reconciliation` en état `confirmed`.
- Les suggestions multiples sont naturellement représentées par plusieurs `Reconciliation` à l'état `suggested` partageant le même `bank_transaction_id` ; confirmer l'une marque les autres `rejected`.
- Le module `reconciliation` a un `domain.py` (algorithme de matching, state machine, score) et un `service.py` qui orchestre les transitions et appelle `transactions.public.confirm(tx_id)` pour la transition `planned → confirmed` au moment du pointage.
- L'audit de pointage/dépointage vit dans la table `reconciliations`, pas dans la transaction.
- Côté sync : la table `reconciliations` sync sur les mêmes buckets que la transaction locale concernée (`account_shared_*` ou `user_personal_*`).
- Décision dépendante de l'ADR 0001 (aggregate immutable).
