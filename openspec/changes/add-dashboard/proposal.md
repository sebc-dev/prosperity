## Why

Après connexion, le membre atterrit sur `/` qui affiche « Tableau de bord — à venir » : l'app n'a
aucune vue d'ensemble alors que toutes les données du foyer (soldes, dettes, budgets, transactions)
sont déjà répliquées en base locale (offline-first). Sert **EPIC-15 / STORY-S15.3** et décline
**FR-9** (lecture offline-first répliquée), **FR-7** (dettes croisées), **FR-6** (budgets/alertes de
seuil), **FR-5** (`Money` en centimes). C'est aussi la première matérialisation du pipeline de
lecture PowerSync → Drizzle → React que tous les écrans MVP suivants réutiliseront.

## What Changes

- La route `/` rend le vrai tableau de bord (plus de placeholder), dans la coque authentifiée
  `_authenticated`, en disposition fixe.
- **BalancePanel** : solde réel par compte visible (perso `owner` + commun via `account_members`,
  hors `archived`) = somme des splits `confirmed` non annulés ; montant EUR fr-FR + « synchronisé il
  y a X min ».
- **DebtSummary** : dette nette par contrepartie lue depuis la projection `debts`, sens explicite
  (doublé icône/couleur/signe), net nul masqué, clic → `/debts` filtré.
- **BudgetSummary** : top 3 budgets actifs, % consommé (calcul client sur le sous-arbre de
  catégories), alertes seuils 80 % / > 100 %.
- **RecentTransactions** : 10 dernières (date, tiers, catégorie, montant signé, badge d'état), clic →
  détail.
- Chaque widget porte les 4 états (chargement/vide/erreur/peuplé) ; hors-ligne = données locales
  affichées, fraîcheur = âge.
- Briques réutilisables neuves : primitives `Skeleton` et `Progress`, util `formatCents` (fr-FR), et
  les facteurs de requête purs neufs (comptes visibles+solde, net par contrepartie, top budgets +
  consommation, transactions récentes).

## Capabilities

### New Capabilities
- `dashboard` : l'écran d'accueil en lecture seule qui compose les données synchronisées du foyer
  (solde réel, dettes nettes, budgets sous tension, transactions récentes) avec indicateur de
  fraîcheur, entièrement offline-first.

### Modified Capabilities
- (aucune — pas de changement de comportement au niveau spec sur une capacité existante.)

## Impact

- **Frontend** (`client/`) : nouvelle route `/` peuplée (`src/pages/_authenticated/index.tsx`),
  composants métier `balance-panel` / `debt-summary` / `budget-summary` / `recent-transactions` /
  `transaction-row`, primitives `ui/skeleton` et `ui/progress`, util `lib/format` (`formatCents`),
  facteurs de requête purs dans `lib/drizzle/queries.ts` et hooks `useQuery`.
- **Pipeline de lecture** : PowerSync → Drizzle → React (`toCompilableQuery` + `useQuery`), patron
  réactif déjà en place.
- **ADR contraignants** : 0002 (dettes = projection serveur), 0003 (bucket/masquage débiteur), 0008
  (mono-devise), 0017 (dépense confirmable vs consommation).
- **Pas de backend** : aucune écriture, aucun nouvel endpoint ; lecture seule de tables déjà
  synchronisées.
