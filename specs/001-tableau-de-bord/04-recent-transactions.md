# 04 — RecentTransactions (10 dernières)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `src/components/business/recent-transactions.tsx`, `src/components/business/transaction-row.tsx`, `src/lib/drizzle/queries.ts` + `queries.test.ts`, `src/hooks/use-*.ts`

## Ce que ça livre
Le widget des transactions récentes du tableau de bord : les 10 dernières transactions du foyer,
chacune sur une ligne portant sa date, son tiers, sa catégorie, son montant signé et un badge
d'état. Le montant signé d'une transaction est la somme des `amount_cents` de ses splits (une
transaction est une collection de splits zero-sum ; le montant de la ligne agrège ses splits). Un
clic sur une ligne mène au détail de la transaction. Lecture seule.

## Critères
- [ ] Le widget affiche au plus 10 transactions, triées par `date` décroissante.
- [ ] Chaque ligne affiche : la `date`, le tiers (`payee`), la catégorie, le montant signé et un
      badge reflétant l'`state` de la transaction.
- [ ] Le montant signé d'une transaction égale la somme des `amount_cents` de ses splits, formaté en
      EUR fr-FR (`formatCents` du ticket 01).
- [ ] Un clic sur une ligne déclenche la navigation vers le détail de la transaction cliquée.
- [ ] Les 4 états sont rendus : chargement (`Skeleton`), vide (aucune transaction → message +
      action de navigation), erreur, peuplé.
