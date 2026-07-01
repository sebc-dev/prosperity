# Écrans — Transactions

Présuppose `design-system.md`. Routes **protégées** sous `/transactions`. Domaine le plus riche :
une transaction est composée de **splits zero-sum**, passe par des **états**, et devient
**immutable** (sauf quelques champs) une fois `confirmed`.

## Rappels domaine (essentiels pour l'UX)

- **États** : `draft` (Brouillon) → `planned` (Planifiée) → `confirmed` (Confirmée) ; `void`
  (Annulée). On ne revient **jamais** en arrière (une correction = annuler + recréer).
- **Splits** : la somme des montants des splits d'une transaction = **0** (zero-sum). Une dépense
  courante = 2 splits sur le **même compte** : une jambe **funding** (sortie du compte, montant −)
  et une jambe **classification** (la dépense catégorisée, montant +). L'UI de saisie **masque**
  cette mécanique : l'utilisateur saisit « j'ai dépensé X chez Y en catégorie Z depuis compte C ».
- **Immutabilité après `confirmed`** : seuls **catégorie, tags, description, demande de partage,
  commande de dette** restent modifiables ; le reste est **gelé**.
- **Catégorisation obligatoire pour confirmer** : toute jambe `classification` doit avoir une
  catégorie, sinon refus (`uncategorized_expense`).

---

## Liste des transactions

- **Route** : `/transactions` — protégé. **Objectif** : retrouver, filtrer, saisir.

### Anatomie
```
┌─────────────────────────────────────────────────────────────┐
│ Transactions                              [+ Ajouter]        │
│ Filtres : [Compte ▼][Catégorie ▼][Du __ Au __][Montant ⟷][🔎]│
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 15/06  Carrefour     Courses     −45,00 €   [Confirmée] │ │  ← TransactionRow
│ │ 14/06  Salaire       —         +2 000,00 €  [Confirmée] │ │
│ │ 13/06  Loyer         Logement    −800,00 €  [Planifiée] │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                   [ Charger plus ]           │
└─────────────────────────────────────────────────────────────┘
```

### Données affichées
- `TransactionRow` (voir dernier bloc) — date, payee, **chip catégorie** (couleur+icône+nom),
  **montant** (signé, couleur), **badge d'état**.

### États
- **Vide** : « Aucune transaction. [Ajouter une transaction] ».
- **Pagination** : par **curseur** (« Charger plus » / scroll infini) — pas de pages numérotées.
- Filtres : **compte, catégorie, plage de dates, plage de montant, texte** (payee/description).
  Recherche full-text = V2 (MVP = filtres simples).

### Interactions & flux
- Clic ligne → modal/écran de **détail**. `[+ Ajouter]` → saisie.

### Copy FR
- « Transactions » · « Ajouter une transaction » · « Charger plus » · filtres « Compte » /
  « Catégorie » / « Du… Au… » / « Montant ».

---

## Ajouter une transaction

- **Objectif** : saisie rapide d'une dépense/recette, convertie automatiquement en 2 splits zero-sum.

### Anatomie
```
  Nouvelle transaction
  Montant     [   45,00 € ]   ( + recette / − dépense, ou toggle Dépense/Recette )
  Bénéficiaire[ Carrefour      ]
  Compte      [ Compte courant ▼ ]
  Catégorie   [ Courses ▼ (picker hiérarchique) ]
  Date        [ 15/06/2026 ]
  Description [ (optionnel) ]
  Tags        [ #courses ×] [+]
  [ Annuler ]  [ Enregistrer en brouillon ]  [ Planifier ]
```

### Données saisies
- **Montant** (saisi en €, converti en centimes), **Bénéficiaire** (payee), **Compte source**,
  **Catégorie** (picker hiérarchique — cf. `screens-categories.md`), **Date**, **Description**
  (optionnel), **Tags** (optionnel).
- L'UI construit en interne les **2 splits** (funding + classification) ; l'utilisateur ne les voit pas.

### États & transitions
- État initial = **brouillon** (`draft`) ; l'utilisateur **confirme explicitement** plus tard.
  Possibilité de **Planifier** directement (`planned`) si la saisie est équilibrée.

### Validation & règles
- **Zero-sum** géré par l'UI (les 2 splits se compensent) ; un brouillon peut rester non équilibré,
  mais **« Planifier » exige l'équilibre** (sinon `unbalanced_transaction`).
- Catégorie : recommandée à la saisie ; **obligatoire pour confirmer** (sinon
  `uncategorized_expense` au moment de confirmer).

### Copy FR
- « Nouvelle transaction » · « Montant » · « Bénéficiaire » · « Compte » · « Catégorie » · « Date »
  · « Description » · « Enregistrer en brouillon » · « Planifier ».

### Cas limites
- Saisie hors ligne : la transaction apparaît **immédiatement** en local (optimiste), synchronisée
  plus tard (badge de synchro).

---

## Éditer une transaction

- **Objectif** : modifier selon l'état. **Édition libre** si `draft`/`planned` ; **restreinte** si
  `confirmed`.

### Comportement par état
- **`draft` / `planned`** : tous les champs éditables (montant, compte, date, payee, catégorie…).
- **`confirmed`** : champs **gelés** (montant, compte, date, payee) → affichés **désactivés** avec
  une **infobulle « Ce champ ne peut pas être modifié »** ; seuls **catégorie, tags, description,
  demande de partage, commande de dette** restent éditables. **Pas** de bouton « tout modifier ».

### Anatomie (transaction confirmée)
```
  Transaction — Confirmée
  Montant      45,00 €   🔒 (gelé · infobulle)
  Bénéficiaire Carrefour 🔒
  Compte       Courant   🔒
  Date         15/06     🔒
  Catégorie    [ Courses ▼ ]        ← éditable
  Tags         [ #courses ×][+]     ← éditable
  Description  [ … ]                ← éditable
  Commande de dette [ Standard ▼ ]  ← éditable (cf. ci-dessous)
  [ Demander un partage ]  [ Annuler la transaction ]
```

### Validation & règles
- Toute tentative de modifier un champ gelé → refus serveur `immutable_field_violation` (mais l'UI
  l'empêche en amont). Message : « Ce champ ne peut pas être modifié ».

### Copy FR
- Badge état · infobulle « Ce champ ne peut pas être modifié » · « Commande de dette ».

---

## Confirmer / Annuler une transaction

- **Objectif** : faire passer `planned → confirmed`, ou `* → void`, via des dialogs de confirmation.

### Confirmer
- Action sur une transaction `planned`. **Dialog de confirmation**.
- **Refus possibles** → **toast FR** : `uncategorized_expense` (« Cette dépense doit être
  catégorisée. ») si une jambe `classification` n'a pas de catégorie ; `unbalanced_transaction`
  (« La transaction n'est pas équilibrée. »).

### Annuler (void)
- Action sur `draft|planned|confirmed`. **Dialog** : « Annuler cette transaction ? Cette action est
  définitive. » + **motif optionnel**. Confirmer → `void`.
- **Effet** : une transaction annulée ne revient jamais à un état antérieur (corriger = recréer).

### Commande de génération de dette (sur transaction d'un compte commun)
- Champ **« Commande de dette »** (éditable même après `confirmed`) :
  - **Standard** (`default`) — seul l'excédent au budget génère une dette par quote-part.
  - **Forcer la dette totale** (`force_full_debt`) — tout le montant devient une dette, transaction
    **hors budget**.
  - **Aucune dette** (`force_no_debt`) — le compte absorbe, pas de dette.
- Changer cette commande peut **recalculer les dettes** (visible dans l'écran Dettes).

### Copy FR
- « Confirmer la transaction » · « Annuler la transaction » · « Cette action est définitive. » ·
  « Motif (optionnel) » · « Standard » / « Forcer la dette totale » / « Aucune dette ».

---

## `TransactionRow` (composant réutilisable)

Utilisé en liste, détail de compte, dashboard.
```
[date]  [payee]      [chip catégorie]      [montant signé/coloré]   [badge état]
15/06   Carrefour    🟧 Courses            −45,00 €                 [Confirmée]
```
- **date** (`JJ/MM`), **payee** (ou « — » si vide), **chip catégorie** (couleur+icône+nom ; « Non
  catégorisée » en gris si absente), **montant** (signe + couleur sémantique), **badge d'état**.
- Clic → détail. Cibles tactiles confortables ; troncature élégante des longs libellés.
