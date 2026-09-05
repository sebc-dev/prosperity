# 03 — BudgetSummary (budgets sous tension)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `src/components/business/budget-summary.tsx`, `src/components/ui/progress.tsx`, `src/lib/drizzle/queries.ts` + `queries.test.ts`, `src/hooks/use-*.ts`

## Ce que ça livre
Le widget des budgets du tableau de bord : les 3 budgets actifs les plus sous tension, chacun avec
son pourcentage consommé et une alerte visuelle aux seuils. La **consommation** n'est pas
synchronisée (service serveur, **ADR-0017**, dépense confirmable vs consommation) : le MVP la calcule
côté client depuis les splits `confirmed` non annulés du **sous-arbre de catégories** du budget
(agrégation récursive des sous-catégories via `parent_id`, FR-6) dans la période du budget. La
divergence possible avec la sémantique serveur est portée par un candidat ADR déposé — pas tranchée
ici. Ce ticket pose aussi la primitive `Progress`.

## Critères
- [ ] Le widget affiche au plus 3 budgets actifs (non `archived`).
- [ ] Le facteur de requête calcule la consommation d'un budget = somme des `amount_cents` des splits
      `confirmed` (`voided_at IS NULL`) dont la catégorie appartient au sous-arbre de la catégorie du
      budget (la catégorie elle-même + ses descendants par chaînage `parent_id`).
- [ ] Un split rangé dans une **sous-catégorie** est compté dans la consommation du budget de la
      catégorie **ancêtre**.
- [ ] Seuls les splits dans la fenêtre de période du budget (`period_start` + `period_kind`) sont
      comptés.
- [ ] Le pourcentage consommé est rendu via la primitive `Progress`.
- [ ] Un budget consommé à ≥ 80 % (et ≤ 100 %) porte l'état « attention » ; un budget consommé à
      > 100 % porte l'état « dépassement » — distincts visuellement.
- [ ] Les 4 états sont rendus : chargement (`Skeleton`), vide (aucun budget actif → message +
      action de navigation), erreur, peuplé.
