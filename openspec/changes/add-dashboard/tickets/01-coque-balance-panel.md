# 01 — Coque du tableau de bord + BalancePanel (solde réel)

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `src/pages/_authenticated/index.tsx`, `src/components/business/balance-panel.tsx`, `src/components/ui/skeleton.tsx`, `src/lib/format.ts` (`formatCents`), `src/lib/drizzle/queries.ts` + `queries.test.ts`, `src/hooks/use-*.ts`

## Ce que ça livre

La route `/` cesse d'afficher « Tableau de bord — à venir » et rend le vrai tableau de bord dans la
coque authentifiée (disposition fixe accueillant les widgets), dont le premier — **BalancePanel** —
est peuplé : solde réel par compte visible au membre (perso `owner` + commun via `account_members`,
hors `archived`), chaque solde = somme des splits `confirmed` non annulés (réutilise
`selectAccountBalance`, ADR-0008), en EUR fr-FR, avec « synchronisé il y a X min ». Pose aussi les
deux briques réutilisées par les widgets suivants : la primitive `Skeleton` et l'util `formatCents`.
Offline-first.

## Critères

- [ ] La route `/` rend le tableau de bord dans la coque `_authenticated` (header + navigation), plus le placeholder   (SC-01a)
- [ ] `formatCents(123456)` rend `1 234,56 €` (fr-FR, séparateur de milliers)   (SC-01b)
- [ ] `formatCents(-500)` rend un montant négatif signé   (SC-01c)
- [ ] Le facteur de requête liste les comptes visibles (perso `owner` + commun `account_members`), hors `archived`   (SC-01d)
- [ ] Le solde d'un compte = somme des `amount_cents` des splits `confirmed` avec `voided_at IS NULL` (0 si aucun split)   (SC-01e)
- [ ] Chaque ligne de compte affiche « synchronisé il y a X min »   (SC-01f)
- [ ] État chargement : la primitive `Skeleton` est rendue ; état vide : message + action de navigation, aucun formulaire   (SC-01g)
- [ ] État erreur : un message d'erreur est rendu quand la requête échoue   (SC-01h)
