# Écran — Tableau de bord

## Tableau de bord

- **Route** : `/` — protégé.
- **Objectif** : vue d'ensemble du foyer en un coup d'œil — pour chaque compte, **où on en est**
  (solde actuel) et **jusqu'où on va descendre avant la prochaine paie** (creux), les **budgets
  sous tension**, les **dettes nettes**, et les **dernières transactions**.
- **Accès** : tout membre connecté. Disposition **fixe** en V1 (widgets configurables = V2).
- **Lecture seule** : aucune écriture depuis le dashboard.

### Anatomie (responsive)

```
┌──────────────────────────────────────────────────────────────────────┐
│ SOLDES (BalancePanel) — pleine largeur                    [Tout voir] │
│ ≤ 3 comptes : rangée de cartes (toutes visibles)                      │
│ > 3 comptes : carrousel (une carte par slide, flèches + points)       │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐             │
│ │ [W] Courant    │ │ [U] Commun     │ │ [P] Livret A   │             │
│ │ Solde actuel   │ │ Solde actuel   │ │ Solde actuel   │             │
│ │ 1 234,56 €     │ │ 890,00 €       │ │ 5 600,00 €     │             │
│ │ Creux avant    │ │ Creux avant    │ │ Objectif 58 %  │             │
│ │ paie (le 27)   │ │ paie (le 02)   │ │ — pas de creux │             │
│ │ −60 € ⚠        │ │ 210 €          │ │                │             │
│ │ banque · 3 min │ │ saisie · maint.│ │ OFX · hier     │             │
│ └────────────────┘ └────────────────┘ └────────────────┘             │
├────────────────────────────────────┬─────────────────────────────────┤
│ BUDGETS (top 3 sous tension)        │ DETTES (par contrepartie)       │
│                          [Tout voir]│                       [Tout voir]│
│ Courses    ▓▓▓▓▓░  82 %  ⚠          │ Alice   vous devez    −50,00 €  │
│ Restaurants▓▓▓▓▓▓ 105 %  ⛔         │ Bob     on vous doit  +20,00 €  │
│ Loisirs    ▓▓░░░░  30 %             │                                 │
├────────────────────────────────────┴─────────────────────────────────┤
│ TRANSACTIONS RÉCENTES                                     [Tout voir] │
│ 15/06  Carrefour    [Courses]          −45,00 €   [Confirmée]         │
│ 14/06  Salaire      [Revenus]       +2 000,00 €   [Confirmée]         │
│ …  (N = 8 lignes max, AUCUN scroll interne)                           │
│                  [  Voir toutes les transactions  ]                   │
└──────────────────────────────────────────────────────────────────────┘

< md : tout empilé sur une colonne (ordre : Soldes → Budgets → Dettes → Transactions).
       Les cartes-comptes passent en carrousel quelle que soit leur quantité.
```

---

### Données affichées (4 widgets)

#### 1. BalancePanel — soldes par compte (pleine largeur)

Pour chaque compte accessible (perso + commun dont l'utilisateur est membre), une **carte-compte**
avec : **icône de type**, **nom**, **solde actuel** (chiffre héros), **creux avant paie**, et un
**indicateur de fraîcheur propre au compte**. **Deux soldes, pas plus.**

**Principe du cycle de paie**

La vie financière fonctionne par cycles entre deux paies. Ce qui est actionnable n'est pas le solde
de fin de mois, mais **le point le plus bas atteint avant la prochaine rentrée d'argent**. Le creux
répond donc à : « jusqu'où vais-je descendre avant d'être à nouveau payé ? ».

**Mode d'affichage selon le nombre de comptes**

| Comptes accessibles | Affichage         | Comportement                                              |
| ------------------- | ----------------- | --------------------------------------------------------- |
| ≤ 3                 | Rangée de cartes  | Toutes visibles, pas de défilement                        |
| > 3                 | **Carrousel**     | Une carte par slide, flèches + points, auto-rotation 4 s  |
| < md (mobile)       | **Carrousel**     | Systématique, quel que soit le nombre                     |

Contraintes du carrousel :
- Monté en **JS après rendu** ; **jamais de `display:none`** sur les slides masquées (incompatible
  offline-first PowerSync — pas de contenu fantôme).
- Auto-rotation **désactivée** si `prefers-reduced-motion: reduce`.
- **Pause** au survol et au focus clavier. Navigation clavier sur flèches et points.

**Soldes affichés par carte**

| Solde                  | Définition                                                                                              | Couleur                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Solde actuel** (réel)| Σ des splits des transactions `confirmed` non annulées, jusqu'à aujourd'hui.                            | Neutre                          |
| **Creux avant paie**   | **Minimum** de la courbe de solde sur [aujourd'hui ; prochaine date de paie[, avec **sa date**. Voir calcul. | **Danger si < seuil**, sinon neutre |

**Date de paie (paramètre par compte)**

- Chaque compte porte un paramètre **jour de paie** = jour du mois où le compte est réapprovisionné
  (paie, virement entrant récurrent). Type : jour du mois (1–31 ou « dernier jour »).
- La **prochaine date de paie** = la prochaine occurrence de ce jour à partir d'aujourd'hui (si le
  jour est déjà passé ce mois-ci, on prend celui du mois suivant ; si c'est aujourd'hui, le cycle
  redémarre et l'on vise l'occurrence du mois suivant).
- L'**horizon du creux** = [aujourd'hui ; prochaine date de paie[ (la veille de la paie incluse, la
  paie elle-même exclue puisqu'elle renfloue le compte).
- **Fallback** : si aucun jour de paie n'est défini sur un compte qui le justifie (courant/commun),
  l'horizon retombe sur **la fin du mois en cours**.
- Le jour de paie peut être **suggéré automatiquement** à partir d'une récurrence de revenu détectée
  (F06), mais reste **éditable** par l'utilisateur.

**Adaptation par type de compte**

| Type de compte            | Soldes affichés                                                            |
| ------------------------- | -------------------------------------------------------------------------- |
| Courant, commun, crédit   | Solde actuel · **Creux avant paie** (avec date)                            |
| Livret, épargne           | Solde actuel · **Progression vers l'objectif** lié (F12) — **pas de creux**|

Un compte d'épargne ne « plonge » pas (mouvement monotone croissant) : le creux n'a pas de sens, on
ne l'affiche pas. Si aucun objectif n'est lié, n'afficher que le solde actuel.

**Seuil de sécurité (par compte)**

- Paramètre **par compte**, **défaut 0 €**, configurable par le propriétaire.
- Pilote le **code couleur** du creux.
- **Règle de couleur (invariant UX)** : le rouge encode « **creux sous le seuil de sécurité** »,
  jamais « solde en baisse ». Une descente qui reste au-dessus du seuil est normale → **neutre**.

**Indicateur de fraîcheur (par compte, pas global)**

| Source du compte           | Libellé de fraîcheur                                                |
| -------------------------- | ------------------------------------------------------------------- |
| Enable Banking (bancaire)  | « banque · il y a {X} h » (polling 2×/jour)                         |
| Import OFX                 | « OFX · importé le {JJ/MM} »                                        |
| Saisie manuelle / locale   | « synchronisé {à l'instant / il y a {X} min} » (dernière sync PowerSync) |

#### 2. BudgetSummary — top 3 budgets sous tension

- Sélection : **les 3 budgets actifs au plus fort taux de consommation** (tri décroissant par
  `consommé / alloué`), pas 3 au hasard.
- Par budget : **nom de catégorie**, **barre de consommation** (% consommé / alloué), montants.
- **Alerte visuelle** : **≥ 80 %** → attention (warning) ; **> 100 %** → dépassement (danger).
- Exemple : `Courses — 82 % (245,00 € / 300,00 €)`.
- Clic → `/budgets`.

#### 3. DebtSummary — dettes nettes par contrepartie

- Net par personne, avec **sens explicite et non ambigu** :
  - « **vous devez** » → montant négatif, **danger**.
  - « **on vous doit** » → montant positif, **succès**.
- ⚠️ Ne **pas** utiliser « vous prête » (ambigu). Paire retenue : **« vous devez » / « on vous doit »**.
- Clic sur une ligne → `/debts` filtré sur cette contrepartie.

#### 4. RecentTransactions — N dernières (sans scroll)

- **N = 8** dernières transactions, triées par date décroissante.
- `TransactionRow` (cf. `screens-transactions.md`) : date, payee, catégorie (chip), montant, badge
  d'état.
- **Pas de scroll interne** : la liste ne défile pas dans le widget.
- **Bouton pleine largeur « Voir toutes les transactions »** sous la liste → `/transactions`.
- Badge d'état (`Confirmée` / `Pointée` / `Planifiée`) : porteur de sens dès F06/F07 livrés. En MVP
  strict (uniquement `confirmed`), le badge peut être masqué car redondant.
- Clic sur une ligne → détail de la transaction.

---

### Calculs (côté client, SQLite local)

Tous les soldes sont calculés **localement** (réactivité offline-first). Pour un compte donné :

```
solde_actuel = Σ splits(tx) où tx.state = confirmed et tx.date ≤ today

prochaine_paie :
  jour = compte.jour_de_paie            # paramètre, ex. 27 ; sinon dernier jour du mois
  d = prochaine occurrence de `jour` strictement après today
  → si jour == today : d = occurrence du mois suivant   # cycle redémarré

creux_avant_paie :
  courbe = solde_actuel
  min    = solde_actuel ; date_min = today
  pour chaque tx planned triée par date croissante, de today à (prochaine_paie − 1j) :
      courbe += Σ splits(tx)
      si courbe < min : min = courbe ; date_min = tx.date
  → retourne (min, date_min)
  alerte (couleur danger) si min < compte.seuil_securite
```

Notes :
- Le creux **dépend de la génération des occurrences `planned`** par les transactions récurrentes
  (F06) — sans elles, la courbe est incomplète (loyer/charges à venir manquants). Il **n'est donc
  pas disponible en MVP** (cf. Phasing).
- S'il n'y a **aucune** transaction `planned` dans l'horizon, le creux = solde actuel (courbe plate).
- Comptes d'épargne : pas de calcul de creux.

---

### États

- **Chargement** : skeletons par widget (silhouettes de cartes).
- **Vide (foyer neuf)** : chaque widget a son propre vide, encourageant —
  - BalancePanel : « Aucun compte. [Créer un compte] ».
  - BudgetSummary : « Aucun budget. [Créer un budget] ».
  - DebtSummary : « Aucune dette en cours. »
  - RecentTransactions : « Aucune transaction. [Ajouter une transaction] ».
- **Hors ligne** : les données locales restent affichées ; la fraîcheur **par compte** indique
  l'âge réel de chaque source.

---

### Interactions & flux

- Widgets cliquables → écran détaillé correspondant (`/accounts`, `/budgets`, `/debts`,
  `/transactions`). En-têtes de widget : lien « Tout voir ».
- Carte-compte → `/accounts` (détail du compte).
- Ligne de dette → `/debts` filtré sur la contrepartie.
- Bouton « Voir toutes les transactions » → `/transactions`.

---

### Validation & règles

- **Lecture seule** : aucune écriture depuis le dashboard.
- **Calculs côté client** (SQLite local) pour la réactivité offline-first.
- **Creux avant paie = V1** (dépend de F06 pour les occurrences `planned`, de F11, et du paramètre
  jour de paie). En **MVP**, fallback = **solde actuel seul**, le creux masqué.
- Compte **archivé** → exclu des soldes.
- Dette nette **nulle** avec une contrepartie → ne pas l'afficher.

---

### Copy FR

- Titres : « Soldes » · « Budgets » · « Dettes » · « Transactions récentes » · « Tout voir ».
- Bouton transactions : « Voir toutes les transactions ».
- Labels de solde : « Solde actuel » · « Creux avant paie (le {JJ}) » · « Objectif ».
- Comptes d'épargne : mention « — pas de creux » optionnelle, ou simple absence de la ligne.
- Sens des dettes : « **vous devez** » / « **on vous doit** ».
- Fraîcheur : « banque · il y a {X} h » / « OFX · importé le {JJ/MM} » /
  « synchronisé il y a {X} min » / « à l'instant ».

---

### Responsive

- **≥ md** : Soldes en **pleine largeur** (rangée si ≤ 3 comptes, carrousel si > 3) ; **Budgets |
  Dettes** en deux colonnes ; **Transactions** en pleine largeur.
- **< md** : une seule colonne empilée, ordre **Soldes → Budgets → Dettes → Transactions**. Les
  cartes-comptes passent en **carrousel systématique**.

---

### Cas limites

- **Budget sans dépense** → 0 %.
- **Compte archivé** → exclu des soldes.
- **Dette nette nulle** avec une contrepartie → ne pas l'afficher.
- **Aucune transaction `planned` dans l'horizon** → creux = solde actuel (affiché neutre).
- **Creux ≥ seuil** sur tout l'horizon → afficher en neutre, **aucune alerte**.
- **Jour de paie aujourd'hui** → cycle redémarré, horizon jusqu'à la paie du mois suivant.
- **Jour de paie non défini** (compte courant/commun) → fallback horizon = fin du mois en cours.
- **Livret sans objectif lié** → afficher seulement le solde actuel.
- **Transactions < N** → afficher ce qui existe ; masquer « Voir toutes » si le total ≤ N.
- **`prefers-reduced-motion`** → carrousel **sans** auto-rotation (navigation manuelle uniquement).
- **Beaucoup de comptes (> 6)** → le carrousel reste le mode ; prévoir une pagination des points.
- **MVP (avant F06)** → cartes-comptes réduites au seul solde actuel + fraîcheur.

---

### Décisions tranchées

| Sujet                     | Décision                                                                                     |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| Layout                    | Soldes pleine largeur en haut ; Budgets / Dettes côte à côte ; Transactions en bas           |
| Affichage des comptes     | Rangée si ≤ 3 comptes ; **carrousel si > 3** (et systématique < md)                          |
| Soldes par compte         | **Deux seulement** : Solde actuel + **Creux avant paie** (ou objectif pour épargne)          |
| Horizon du creux          | [aujourd'hui ; **prochaine date de paie**[ — plus « fin de mois »                            |
| Date de paie              | **Paramètre par compte** (jour du mois), suggérable depuis F06, éditable ; fallback fin de mois |
| Adaptation par type       | Courant/commun → creux ; livret/épargne → objectif, **pas de creux**                         |
| Seuil de sécurité         | Paramètre **par compte**, défaut 0 €, pilote le code couleur du creux                         |
| Sémantique couleur        | Rouge = « creux sous le seuil », **jamais** « en baisse »                                     |
| Fraîcheur                 | **Par compte**, distinguant banque / OFX / saisie locale — pas d'indicateur global           |
| Sens des dettes           | « **vous devez** » (−, danger) / « **on vous doit** » (+, succès)                             |
| Tri des budgets           | Top 3 **au plus fort taux de consommation** (sous tension)                                    |
| Transactions              | N = 8, **pas de scroll interne**, bouton « **Voir toutes les transactions** »                 |
| Phasing                   | Creux en **V1** (dépend F06 + jour de paie) ; MVP = solde actuel seul                         |