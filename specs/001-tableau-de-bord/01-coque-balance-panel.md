# 01 — Coque du tableau de bord + BalancePanel (solde réel)

**Bloqué par :** rien — démarrable
**Vérif :** test
**Fichiers :** `src/pages/_authenticated/index.tsx`, `src/components/business/balance-panel.tsx`, `src/components/ui/skeleton.tsx`, `src/lib/utils.ts` (ou `src/lib/format.ts` — `formatCents`), `src/lib/drizzle/queries.ts` + `queries.test.ts`, `src/hooks/use-*.ts`

## Ce que ça livre
La route `/` cesse d'afficher « Tableau de bord — à venir » et rend le vrai tableau de bord
dans la coque authentifiée : une disposition fixe qui accueille les widgets, dont le premier est
peuplé. **BalancePanel** montre un solde réel par compte visible au membre — compte personnel dont
il est `owner`, compte commun dont il est `account_members`, comptes archivés exclus — chaque solde
étant la somme des splits `confirmed` non annulés (réutilise `selectAccountBalance`, agrégation
d'une source synchronisée, pas une re-dérivation serveur ; **ADR-0008**, mono-devise). Le montant
s'affiche en EUR fr-FR et le panneau porte la fraîcheur « synchronisé il y a X min ».

Ce ticket pose aussi les deux briques que les widgets suivants réutilisent : la primitive `Skeleton`
et l'util `formatCents` (fr-FR, centimes → chaîne). Entièrement offline-first : ce qui est en base
locale s'affiche sans réseau, et la fraîcheur indique l'âge.

## Critères
- [ ] La route `/` ne rend plus le placeholder « Tableau de bord — à venir » mais le tableau de bord,
      à l'intérieur de la coque `_authenticated` (header + navigation présents).
- [ ] `formatCents(123456)` rend `1 234,56 €` (fr-FR, séparateur de milliers) et `formatCents(-500)`
      rend un montant négatif signé.
- [ ] Le facteur de requête liste les comptes visibles au membre (perso `owner` + commun via
      `account_members`) en excluant les comptes `archived`.
- [ ] Pour un compte donné, le solde affiché égale la somme des `amount_cents` des splits de
      transactions `confirmed` avec `voided_at IS NULL` (et 0 quand il n'y a aucun split).
- [ ] Chaque ligne de compte affiche la fraîcheur « synchronisé il y a X min ».
- [ ] État chargement : la primitive `Skeleton` est rendue pendant que la requête charge.
- [ ] État vide (aucun compte visible) : un message + une action de navigation, aucun formulaire.
- [ ] État erreur : un message d'erreur est rendu quand la requête échoue.
