# Écran — Tableau de bord

Présuppose `design-system.md`. Premier écran après connexion (route `/`, **protégé**).

---

## Tableau de bord

- **Route** : `/` — protégé.
- **Objectif** : vue d'ensemble du foyer en un coup d'œil — **solde réel** (pas de prévisionnel en
  MVP), dernières transactions, dettes, budgets sous tension.
- **Accès** : tout membre connecté. Disposition **fixe** en MVP (widgets configurables = V2).

### Anatomie (grille de widgets, responsive)
```
┌───────────────────────────┬───────────────────────────┐
│ SOLDES (BalancePanel)     │ DETTES (DebtSummary)      │
│  par compte :             │  par contrepartie :       │
│  [icône] Courant   1 234,56 €   Alice    vous devez −50,00 € │
│  [icône] Commun      890,00 €   Bob      vous prête  +20,00 € │
│  « synchronisé il y a 3 min »                          │
├───────────────────────────┼───────────────────────────┤
│ BUDGETS (BudgetSummary)   │ TRANSACTIONS RÉCENTES     │
│  top 3 actifs :           │  10 dernières (TransactionRow)│
│  Courses ▓▓▓▓▓░ 82 % ⚠    │  15/06 Carrefour Courses −45,00 € [Confirmée]│
│  Loisirs ▓▓░░░░ 30 %      │  14/06 Salaire   …      +2 000 € [Confirmée]│
└───────────────────────────┴───────────────────────────┘
< md : widgets empilés sur une colonne (ordre : Soldes → Budgets → Dettes → Transactions).
```

### Données affichées (4 widgets)

**1. BalancePanel — solde réel par compte**
- Par compte (perso + commun dont l'utilisateur est membre) : **icône de type**, **nom**, **solde**
  (montant EUR formaté). Le solde réel = somme des splits des transactions `confirmed` non annulées.
- **Indicateur de fraîcheur** : « synchronisé il y a X min » (V1 simple).
- Exemple : `[Wallet] Compte courant — 1 234,56 €`.

**2. DebtSummary — dettes par contrepartie**
- Net par personne, avec **sens explicite** : « vous devez » (−, danger) / « vous prête » (+, succès).
- Exemple : `Alice — vous devez 50,00 €`.
- Clic sur une ligne → `/debts` filtré sur cette contrepartie.

**3. BudgetSummary — top 3 budgets actifs**
- Par budget : **nom de catégorie**, **barre de consommation** (% consommé / alloué), **alerte**
  visuelle à **80 %** (attention) et **> 100 %** (dépassement, danger).
- Exemple : `Courses — 82 % (245,00 € / 300,00 €)`.

**4. RecentTransactions — 10 dernières**
- `TransactionRow` (cf. `screens-transactions.md`) : date, payee, catégorie (chip), montant, badge
  d'état.
- Clic → détail de la transaction.

### États
- **Chargement** : skeletons par widget (silhouettes de cartes).
- **Vide (foyer neuf)** : chaque widget a son vide — ex. BalancePanel : « Aucun compte. [Créer un
  compte] » ; Transactions : « Aucune transaction. [Ajouter une transaction] ». Encourageant.
- **Hors ligne** : les données locales restent affichées ; la fraîcheur indique l'âge.

### Interactions & flux
- Widgets cliquables → écran détaillé correspondant (`/accounts`, `/debts`, `/budgets`,
  `/transactions`). En-têtes de widget : lien « Tout voir ».

### Validation & règles
- Lecture seule (aucune écriture depuis le dashboard).
- **Solde réel uniquement** (pas de projeté/prévisionnel en MVP) — ne pas afficher de solde futur.

### Copy FR
- Titres : « Soldes » · « Dettes » · « Budgets » · « Transactions récentes » · « Tout voir ».
- Fraîcheur : « synchronisé il y a {X} min » / « à l'instant ».
- Sens des dettes : « vous devez » / « vous prête ».

### Responsive
- ≥ md : grille 2×2. < md : une colonne empilée (ordre ci-dessus).

### Cas limites
- Budget sans dépense → 0 %. Compte archivé → exclu des soldes. Dette nette nulle avec une
  contrepartie → ne pas l'afficher.
