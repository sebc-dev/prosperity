# 04 — RecentTransactions (10 dernières)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `client/src/components/business/recent-transactions.tsx`, `client/src/components/business/transaction-row.tsx`, `client/src/lib/drizzle/queries.ts` + `queries.test.ts`, `client/src/hooks/use-*.ts`

## Ce que ça livre

Le widget des transactions récentes : les 10 dernières transactions du foyer, chacune sur une ligne
portant sa date, son tiers, sa catégorie, son montant signé (somme des `amount_cents` de ses splits)
et un badge d'état. Clic sur une ligne → détail de la transaction. Lecture seule.

## Critères

- [ ] Le widget affiche au plus 10 transactions, triées par `date` décroissante   (SC-04a)
- [ ] Chaque ligne affiche : `date`, tiers (`payee`), catégorie, montant signé, badge reflétant l'`state`   (SC-04b)
- [ ] Le montant signé = somme des `amount_cents` des splits, formaté en EUR fr-FR (`formatCents` du ticket 01)   (SC-04c)
- [ ] Un clic sur une ligne navigue vers le détail de la transaction cliquée   (SC-04d)
- [ ] Les 4 états sont rendus : chargement (`Skeleton`), vide (message + action), erreur, peuplé   (SC-04e)
