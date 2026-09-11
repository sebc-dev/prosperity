# 01 — Coque du tableau de bord + BalancePanel (solde réel)

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `client/src/pages/_authenticated/index.tsx`, `client/src/components/business/balance-panel.tsx`, `client/src/components/ui/skeleton.tsx`, `client/src/lib/format.ts` (`formatCents`), `client/src/lib/drizzle/queries.ts` + `queries.test.ts`, `client/src/hooks/use-*.ts`

## Ce que ça livre

La route `/` cesse d'afficher « Tableau de bord — à venir » et rend le vrai tableau de bord dans la
coque authentifiée (disposition fixe accueillant les widgets), dont le premier — **BalancePanel** —
est peuplé : solde réel par compte visible au membre (perso `owner` + commun via `account_members`,
hors `archived`), chaque solde = somme des splits `confirmed` non annulés (réutilise
`selectAccountBalance`, ADR-0008), en EUR fr-FR, avec « synchronisé il y a X min ». Pose aussi les
deux briques réutilisées par les widgets suivants : la primitive `Skeleton` et l'util `formatCents`.
Offline-first.

## Critères

- [x] La route `/` ne rend plus le placeholder « Tableau de bord — à venir » mais le tableau de bord, dans la coque `_authenticated` (header + navigation)   (SC-01a)
- [x] `formatCents(123456)` rend `1 234,56 €` (fr-FR, séparateur de milliers)   (SC-01b)
- [x] `formatCents(-500)` rend `-5,00 €` : signe moins ASCII (U+002D) en tête, virgule décimale, espace insécable (U+00A0) avant `€`   (SC-01c)
- [x] Le facteur de requête liste les comptes visibles (perso `owner` + commun `account_members`), hors `archived`   (SC-01d)
- [x] Le solde d'un compte = somme des `amount_cents` des splits `confirmed` avec `voided_at IS NULL` (0 si aucun split)   (SC-01e)
- [x] Chaque ligne de compte affiche « synchronisé il y a X min »   (SC-01f)
- [x] État chargement : la primitive `Skeleton` est rendue ; état vide : message + action de navigation, aucun formulaire   (SC-01g)
- [x] État erreur : un message d'erreur est rendu quand la requête échoue   (SC-01h)
