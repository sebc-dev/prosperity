# 03 — BudgetSummary (budgets sous tension)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `client/src/components/business/budget-summary.tsx`, `client/src/components/ui/progress.tsx`, `client/src/lib/drizzle/queries.ts` + `queries.test.ts`, `client/src/hooks/use-*.ts`

## Ce que ça livre

Le widget des budgets : les 3 budgets actifs les plus sous tension, chacun avec son % consommé et une
alerte visuelle aux seuils. La consommation n'est pas synchronisée (ADR-0017) : le MVP la calcule
côté client depuis les splits `confirmed` non annulés du sous-arbre de catégories du budget
(récursion `parent_id`, FR-6) dans sa période. Pose aussi la primitive `Progress`.

## Critères

- [ ] Le widget affiche au plus 3 budgets actifs (non `archived`)   (SC-03a)
- [ ] Consommation = somme des `amount_cents` des splits `confirmed` (`voided_at IS NULL`) du sous-arbre de catégories du budget (catégorie + descendants par `parent_id`)   (SC-03b)
- [ ] Un split rangé dans une sous-catégorie est compté dans le budget de la catégorie ancêtre   (SC-03c)
- [ ] Seuls les splits dans la fenêtre de période (`period_start` + `period_kind`) sont comptés   (SC-03d)
- [ ] Le pourcentage consommé est rendu via la primitive `Progress`   (SC-03e)
- [ ] Consommé ≥ 80 % (et ≤ 100 %) → « attention » ; > 100 % → « dépassement », distincts visuellement   (SC-03f)
- [ ] Les 4 états sont rendus : chargement (`Skeleton`), vide (message + action), erreur, peuplé   (SC-03g)
