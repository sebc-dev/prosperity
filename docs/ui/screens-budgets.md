# Écrans — Budgets

Présuppose `design-system.md`. Routes **protégées** sous `/budgets`. Un budget alloue un montant à
une **catégorie** sur une **période**, avec un **scope** et des **contributeurs**. La consommation
agrège automatiquement les **sous-catégories**.

> **Libellés FR** : period_kind → **Mensuel / Trimestriel / Annuel** ; scope → **Personnel /
> Commun**.

---

## Liste des budgets

- **Route** : `/budgets` — protégé. **Objectif** : suivre la consommation des budgets actifs.

### Anatomie
```
┌──────────────────────────────────────────────────────────────┐
│ Budgets                         [Scope ▼]        [+ Budget]   │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Courses (Mensuel · Commun)                               │ │
│ │  ▓▓▓▓▓▓▓▓░░  245,00 € / 300,00 €   82 %  ⚠ Bientôt atteint │ │
│ │ Loisirs (Mensuel · Personnel)                            │ │
│ │  ▓▓▓░░░░░░░   90,00 € / 300,00 €   30 %                   │ │
│ │ Restaurants (Mensuel · Commun)                           │ │
│ │  ▓▓▓▓▓▓▓▓▓▓▓ 360,00 € / 300,00 € 120 %  ⛔ Dépassé        │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Données affichées (par budget)
- **Nom de catégorie**, **période** (Mensuel/Trimestriel/Annuel), **scope** (Personnel/Commun),
  **barre de consommation** (consommé / alloué), **pourcentage**, **état** :
  - < 80 % : normal · **≥ 80 %** : attention (« Bientôt atteint ») · **> 100 %** : dépassement
    (« Dépassé », danger).
- Montants formatés EUR ; pourcentage entier.

### États
- **Vide** : « Aucun budget. [Créer un budget] ».
- **Filtre** par scope (Personnel / Commun). Seuls les budgets **actifs** (non archivés) listés.

### Interactions & flux
- Clic budget → **détail**. `[+ Budget]` → création.

### Copy FR
- « Budgets » · « Mensuel/Trimestriel/Annuel » · « Personnel/Commun » · « Bientôt atteint » ·
  « Dépassé » · « Créer un budget ».

---

## Créer un budget

- **Objectif** : allouer un montant à une catégorie sur une période.

### Anatomie
```
  Nouveau budget
  Catégorie   [ Courses ▼ (picker hiérarchique) ]
  Montant     [   300,00 € ]
  Période     ( ◉ Mensuel  ○ Trimestriel  ○ Annuel )
  Début       [ 01/06/2026 ]   ( ancre de récurrence )
  Scope       ( ◉ Personnel  ○ Commun )
  Contributeurs (si Commun) : [ Alice ×][ Bob ×][+]
  ☐ Reporter le solde non utilisé au mois suivant
  [ Annuler ]  [ Créer ]
```

### Données saisies
- **Catégorie** (picker hiérarchique), **Montant** (€ → centimes, > 0), **Période**
  (Mensuel/Trimestriel/Annuel), **Date de début** (ancre de récurrence), **Scope**, **Contributeurs**
  (si Commun, ≥ 2), **report du reliquat** (option).

### Validation & règles
- Le budget **inclut automatiquement les sous-catégories** de la catégorie choisie (l'expliquer
  brièvement, ex. infobulle « inclut les sous-catégories »).
- Scope **Commun** → au moins 2 contributeurs ; **Personnel** → contributeur = soi (implicite).
- Devise = EUR (foyer mono-devise), non éditable.

### Copy FR
- « Nouveau budget » · « Catégorie » · « Montant » · « Période » · « Début » · « Scope » ·
  « Contributeurs » · « Reporter le solde non utilisé au mois suivant » · « Créer ».

---

## Détail d'un budget

- **Route** : `/budgets/{id}` — protégé. **Objectif** : voir la consommation et **ce qui contribue**.

### Anatomie
```
┌──────────────────────────────────────────────────────────────┐
│ ← Budgets                                                    │
│ Courses — Mensuel · Commun                          [⋯ Modifier]│
│ ▓▓▓▓▓▓▓▓░░  245,00 € / 300,00 €   82 %  ⚠ Bientôt atteint     │
│ Restant : 55,00 €                                            │
│ ────────────────────────────────────────────────────────────│
│ Transactions qui contribuent (jambes de classification) :    │
│  15/06 Carrefour   Courses       −45,00 €  [Confirmée]       │
│  12/06 Lidl        Courses>Frais −30,00 €  [Planifiée]       │
│                                   [ Charger plus ]           │
└──────────────────────────────────────────────────────────────┘
```

### Données affichées
- En-tête : catégorie, période, scope, **barre + % + consommé/alloué + restant**.
- **Liste paginée des splits contributeurs** (jambes `classification` des transactions
  `planned|confirmed` rattachées à la catégorie ou ses sous-catégories) : date, payee,
  catégorie réelle, montant, état. **Curseur** pour la pagination.

### Interactions & flux
- `⋯` → **Modifier** / **Archiver** le budget. Clic sur un contributeur → transaction.

### Validation & règles
- Lecture (la consommation se met à jour mécaniquement quand des transactions changent).
- Une sous-catégorie qui contribue est indiquée par son **chemin** (ex. « Courses › Frais »).

### Copy FR
- « Restant » · « Transactions qui contribuent » · « Bientôt atteint » / « Dépassé » · « Modifier »
  / « Archiver ».

### Cas limites
- Création d'un budget **après** des transactions existantes : la consommation se peuple
  rétroactivement ; un éventuel **excédent** peut générer des dettes (visible dans Dettes).
