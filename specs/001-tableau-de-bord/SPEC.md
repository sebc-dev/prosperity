# 001 — Tableau de bord (solde réel MVP)

## Problème
Après connexion, un membre atterrit sur `/`, qui affiche « Tableau de bord — à venir ». L'app
livrée n'a aucune vue d'ensemble. Toutes les données du foyer — soldes, dettes, budgets,
transactions — sont pourtant déjà répliquées en base locale (offline-first), mais aucun écran ne les
lit. Le membre ne voit pas son argent d'un coup d'œil, ni ne sait si la synchro a eu lieu.

## Solution
L'écran d'accueil : quatre widgets en lecture seule qui composent les données déjà synchronisées —
solde réel par compte, dettes nettes par contrepartie, budgets sous tension, dernières transactions
— avec un indicateur de fraîcheur de synchro. Entièrement offline-first : ce qui est en base locale
s'affiche même sans réseau. C'est aussi la première matérialisation du pipeline de lecture
PowerSync → Drizzle → React que tous les écrans MVP suivants réutiliseront.

## Ce que ça change, concrètement
- La route `/` affiche le tableau de bord réel (plus de placeholder), dans la coque authentifiée.
- **BalancePanel** : par compte (perso + commun dont on est membre, hors archivés), solde réel =
  somme des splits `confirmed` non annulés, montant EUR fr-FR + « synchronisé il y a X min ».
- **DebtSummary** : dette nette par contrepartie, sens explicite (« vous devez » − / « vous prête »
  +, doublé icône/signe) ; nette nulle → masquée ; clic → `/debts` filtré sur la contrepartie.
- **BudgetSummary** : top 3 budgets actifs, % consommé, alerte à 80 % (attention) et > 100 %
  (dépassement).
- **RecentTransactions** : 10 dernières (date, tiers, catégorie, montant signé, badge d'état) ;
  clic → détail de la transaction.
- Chaque widget porte les 4 états : chargement (skeleton), vide (message + action de navigation),
  erreur, peuplé. Hors-ligne = données locales affichées, la fraîcheur indique l'âge.

## Décisions d'implémentation
- Décline **FR-9** (lecture offline-first répliquée), **FR-7** (dettes croisées), **FR-6**
  (budgets/alertes de seuil), **FR-5** (`Money` en centimes) ; roadmap **E15 / S15.3**. Intention
  d'interface portée par `docs/ui/screens-dashboard.md` + `docs/ui/design-system.md` (déjà validés)
  — **non dupliquée** en `maquette.md`.
- Lecture via le pipeline existant : facteurs de requête **purs** `(db, args) → query` dans le
  module drizzle, exposés par des hooks `useQuery(toCompilableQuery(…))` — parce que c'est le patron
  réactif déjà en place (`use-account-balance`, `use-transactions`, `use-debts-for-current-user`).
- **Dettes** lues depuis la table-projection `debts` synchronisée — **ADR-0002 (dettes = projection
  serveur)** : le client ne recalcule pas les dettes ; il agrège seulement le net par contrepartie
  sur ces rows. Masquage débiteur déjà porté par la projection (**ADR-0003**).
- **Solde réel** = somme des splits `confirmed` non annulés (réutilise `selectAccountBalance`,
  décision **ADR-0008 (mono-devise)**) : agrégation d'une source synchronisée, pas une re-dérivation
  de projection serveur — il n'existe aucune table de soldes.
- **Consommation budget** : NON synchronisée (service serveur, **ADR-0017 (dépense confirmable vs
  consommation)**), sans hook client. Le MVP la calcule côté client depuis les splits `confirmed`
  sur le sous-arbre de catégories du budget dans sa période (agrégation des sous-catégories, FR-6).
  Divergence possible avec la sémantique serveur → **candidat ADR déposé** (synchroniser une
  projection de consommation vs recalcul client).
- À construire : composants métier `BalancePanel` / `DebtSummary` / `BudgetSummary` /
  `TransactionRow`, primitives `Skeleton` et `Progress`, util `formatCents` fr-FR
  (`Intl.NumberFormat`), et les facteurs de requête neufs (top budgets, dette nette par
  contrepartie).

## Décisions de test
- Couture principale : les facteurs de requête/agrégation **purs** du module drizzle, testés contre
  un SQLite in-memory réel chargé du DDL généré (patron `queries.test.ts`,
  `@vitest-environment node`) — couvre le calcul (solde, dette nette, consommation, tri/limite) au
  plus haut, sans mock. Non couvert ici : la réactivité rendue.
- Couture composant : widgets testés en isolant `useQuery` (mock `@powersync/react` → fixtures) ou
  en stubbant les hooks de domaine (patron `setup-form.test.tsx`) — couvre présentation, états
  (vide/erreur/skeleton), formatage, signe+couleur+icône. Aucune couture ne pilote la réactivité
  PowerSync à travers un rendu (différée) — ne pas la simuler.
- Prior art : `queries.test.ts`, `use-account-balance.test.tsx`, `setup-form.test.tsx`, et
  `render.tsx` (`renderWithProviders`).

## Hors-périmètre
- Solde **prévisionnel/projeté** — MVP = solde réel seul.
- Toute **écriture** depuis le dashboard — lecture seule ; les CTA des états vides **naviguent**, ils
  n'ouvrent pas de formulaire ici.
- **Widgets configurables / réordonnables** — disposition fixe en MVP (V2).
- **Épargne, récurrences, pointage** — hors MVP (vision Epic I).
- Résolution du `userId` courant pour les dettes via une vraie couche auth — dépend de S14.6 ; le
  hook prend `userId` en entrée.
- Synchroniser une **projection serveur de consommation budget** — traité par le candidat ADR.
- Créer un `specs/001-*/maquette.md` — l'intention d'interface reste dans `docs/ui/` (source unique).
