# 02 — DebtSummary (dette nette par contrepartie)

**Bloqué par :** 01
**Vérif :** test
**Fichiers :** `client/src/components/business/debt-summary.tsx`, `client/src/lib/drizzle/queries.ts` + `queries.test.ts`, `client/src/hooks/use-*.ts`, `client/src/pages/_authenticated/debts.tsx` (contrat minimal `validateSearch`, sans filtrage)

## Ce que ça livre

Le widget des dettes : la dette **nette** par contrepartie, lue depuis la table-projection `debts`
synchronisée. Le client agrège seulement le net par contrepartie (ADR-0002, dettes = projection
serveur ; masquage débiteur déjà porté par la projection, ADR-0003). Sens de la dette explicite,
contrepartie au net nul masquée, clic → `/debts` filtré sur la contrepartie.

## Critères

- [x] Le facteur de requête calcule, par contrepartie, le net = somme signée des rows `debts` créancier − débiteur (`from_user_id` / `to_user_id`)   (SC-02a)
- [x] Net négatif → « vous devez » (`−`) ; net positif → « vous prête » (`+`), sens doublé par icône et couleur   (SC-02b)
- [x] Une contrepartie au net nul n'apparaît pas   (SC-02c)
- [x] Les montants sont formatés en EUR fr-FR (`formatCents` du ticket 01)   (SC-02d)
- [x] Un clic sur une ligne navigue vers `/debts` filtré sur la contrepartie de la ligne   (SC-02e)
- [x] Les 4 états sont rendus : chargement (`Skeleton`), vide (message + action), erreur, peuplé   (SC-02f)
