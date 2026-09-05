# 02 — DebtSummary (dette nette par contrepartie)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `src/components/business/debt-summary.tsx`, `src/lib/drizzle/queries.ts` + `queries.test.ts`, `src/hooks/use-*.ts`

## Ce que ça livre
Le widget des dettes du tableau de bord : la dette **nette** par contrepartie, lue depuis la
table-projection `debts` synchronisée. Le client **agrège seulement** le net par contrepartie sur
ces rows — il ne recalcule pas les dettes (**ADR-0002**, dettes = projection serveur ; masquage
débiteur déjà porté par la projection, **ADR-0003**). Chaque contrepartie affiche le sens de la
dette de façon explicite, une contrepartie dont le net est nul est masquée, et un clic mène à la
liste des dettes filtrée sur cette contrepartie.

## Critères
- [ ] Le facteur de requête calcule, par contrepartie, le net = somme signée des rows `debts` où le
      membre est créancier moins celles où il est débiteur (`from_user_id` / `to_user_id`).
- [ ] Un net négatif affiche « vous devez » avec signe `−` ; un net positif affiche « vous prête »
      avec signe `+` — le sens est **doublé** par une icône et une couleur, pas seulement le signe.
- [ ] Une contrepartie dont le net est nul n'apparaît pas dans le widget.
- [ ] Les montants sont formatés en EUR fr-FR (`formatCents` du ticket 01).
- [ ] Un clic sur une ligne déclenche la navigation vers `/debts` filtré sur la contrepartie de la
      ligne.
- [ ] Les 4 états sont rendus : chargement (`Skeleton`), vide (aucune dette nette → message +
      action de navigation), erreur, peuplé.
