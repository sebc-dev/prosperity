## Purpose

La capacité `dashboard` est l'écran d'accueil du foyer : quatre widgets en lecture seule qui
composent les données déjà synchronisées (solde réel par compte, dettes nettes par contrepartie,
budgets sous tension, transactions récentes) avec un indicateur de fraîcheur, entièrement
offline-first — ce qui est en base locale s'affiche même sans réseau.

## ADDED Requirements

### Requirement: Tableau de bord sur la route racine

La route `/` SHALL rendre le tableau de bord réel à l'intérieur de la coque authentifiée, en
remplacement du placeholder.

#### Scenario: Route racine rend le tableau de bord

- **WHEN** un membre authentifié navigue sur `/`
- **THEN** la route rend le tableau de bord (plus le placeholder « Tableau de bord — à venir »), à
  l'intérieur de la coque `_authenticated` (header + navigation présents)

### Requirement: Formatage monétaire fr-FR

L'util `formatCents` SHALL convertir un montant en centimes en une chaîne EUR au format fr-FR.

#### Scenario: Montant positif avec séparateur de milliers

- **WHEN** `formatCents(123456)` est appelé
- **THEN** il rend `1 234,56 €` (séparateur de milliers, fr-FR)

#### Scenario: Montant négatif signé

- **WHEN** `formatCents(-500)` est appelé
- **THEN** il rend `-5,00 €` : signe moins ASCII (U+002D) en tête, virgule décimale, espace insécable (U+00A0) avant `€`

### Requirement: BalancePanel — solde réel par compte

Le widget BalancePanel SHALL afficher le solde réel de chaque compte visible au membre, calculé
depuis les splits synchronisés, avec sa fraîcheur de synchro.

#### Scenario: Liste des comptes visibles au membre

- **WHEN** le facteur de requête liste les comptes du membre
- **THEN** il inclut le compte personnel (`owner`) et les comptes communs (via `account_members`), en
  excluant les comptes `archived`

#### Scenario: Solde = somme des splits confirmed non annulés

- **WHEN** on calcule le solde d'un compte donné
- **THEN** il égale la somme des `amount_cents` des splits de transactions `confirmed` avec
  `voided_at IS NULL`, et vaut 0 quand il n'y a aucun split

#### Scenario: Fraîcheur de synchronisation par ligne

- **WHEN** une ligne de compte est affichée
- **THEN** elle porte l'indication « synchronisé il y a X min »

#### Scenario: État chargement

- **WHEN** la requête est en cours de chargement
- **THEN** la primitive `Skeleton` est rendue

#### Scenario: État vide

- **WHEN** aucun compte n'est visible au membre
- **THEN** un message et une action de navigation sont rendus, sans aucun formulaire

#### Scenario: État erreur

- **WHEN** la requête échoue
- **THEN** un message d'erreur est rendu

### Requirement: DebtSummary — dette nette par contrepartie

Le widget DebtSummary SHALL afficher la dette nette par contrepartie, agrégée depuis la projection
`debts` synchronisée, sans recalculer les dettes.

#### Scenario: Net signé par contrepartie

- **WHEN** le facteur de requête agrège les rows de la projection `debts`
- **THEN** il calcule, par contrepartie, le net = somme des rows où le membre est créancier moins
  celles où il est débiteur (`from_user_id` / `to_user_id`)

#### Scenario: Sens explicite doublé icône/couleur

- **WHEN** le net d'une contrepartie est négatif, respectivement positif
- **THEN** il affiche « vous devez » avec signe `−`, respectivement « vous prête » avec signe `+`, le
  sens étant doublé par une icône et une couleur (pas seulement le signe)

#### Scenario: Contrepartie au net nul masquée

- **WHEN** une contrepartie a un net nul
- **THEN** elle n'apparaît pas dans le widget

#### Scenario: Montants formatés fr-FR

- **WHEN** un montant de dette est affiché
- **THEN** il est formaté en EUR fr-FR via `formatCents`

#### Scenario: Navigation vers les dettes filtrées

- **WHEN** l'utilisateur clique sur une ligne
- **THEN** la navigation mène à `/debts` filtré sur la contrepartie de la ligne

#### Scenario: Quatre états

- **WHEN** le widget est en chargement, vide (aucune dette nette), en erreur, ou peuplé
- **THEN** il rend respectivement `Skeleton`, un message + action de navigation, un message d'erreur,
  ou la liste des dettes nettes

### Requirement: BudgetSummary — budgets sous tension

Le widget BudgetSummary SHALL afficher les budgets actifs les plus sous tension avec leur
consommation calculée côté client et une alerte visuelle aux seuils.

#### Scenario: Au plus 3 budgets actifs

- **WHEN** le widget rend les budgets
- **THEN** il en affiche au plus 3, tous actifs (non `archived`)

#### Scenario: Consommation = splits confirmed du sous-arbre de catégories

- **WHEN** le facteur de requête calcule la consommation d'un budget
- **THEN** elle égale la somme des `amount_cents` des splits `confirmed` (`voided_at IS NULL`) dont la
  catégorie appartient au sous-arbre de la catégorie du budget (la catégorie elle-même + ses
  descendants par chaînage `parent_id`)

#### Scenario: Split en sous-catégorie compté dans l'ancêtre

- **WHEN** un split est rangé dans une sous-catégorie
- **THEN** il est compté dans la consommation du budget de la catégorie ancêtre

#### Scenario: Fenêtre de période du budget

- **WHEN** la consommation est calculée
- **THEN** seuls les splits dans la fenêtre de période du budget (`period_start` + `period_kind`)
  sont comptés

#### Scenario: Pourcentage via la primitive Progress

- **WHEN** un budget est affiché
- **THEN** son pourcentage consommé est rendu via la primitive `Progress`

#### Scenario: États de seuil attention et dépassement

- **WHEN** un budget est consommé à ≥ 80 % (et ≤ 100 %), respectivement à > 100 %
- **THEN** il porte l'état « attention », respectivement « dépassement », visuellement distincts

#### Scenario: Quatre états

- **WHEN** le widget est en chargement, vide (aucun budget actif), en erreur, ou peuplé
- **THEN** il rend respectivement `Skeleton`, un message + action de navigation, un message d'erreur,
  ou la liste des budgets

### Requirement: RecentTransactions — 10 dernières

Le widget RecentTransactions SHALL afficher les dernières transactions du foyer, chacune avec son
montant signé agrégé, en lecture seule.

#### Scenario: Au plus 10, triées par date décroissante

- **WHEN** le widget rend les transactions
- **THEN** il en affiche au plus 10, triées par `date` décroissante

#### Scenario: Contenu de ligne

- **WHEN** une ligne de transaction est affichée
- **THEN** elle porte la `date`, le tiers (`payee`), la catégorie, le montant signé et un badge
  reflétant l'`state` de la transaction

#### Scenario: Montant signé = somme des splits, fr-FR

- **WHEN** le montant d'une transaction est affiché
- **THEN** il égale la somme des `amount_cents` de ses splits, formaté en EUR fr-FR via `formatCents`

#### Scenario: Navigation vers le détail

- **WHEN** l'utilisateur clique sur une ligne
- **THEN** la navigation mène au détail de la transaction cliquée

#### Scenario: Quatre états

- **WHEN** le widget est en chargement, vide (aucune transaction), en erreur, ou peuplé
- **THEN** il rend respectivement `Skeleton`, un message + action de navigation, un message d'erreur,
  ou la liste des transactions
