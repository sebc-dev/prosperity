# Écrans — Comptes

Présuppose `design-system.md`. Routes **protégées** sous `/accounts`.
Types de compte : `courant`, `livret`, `epargne`, `especes`, `credit` (libellés FR ci-dessous).

> **Libellés FR des types** (à fixer) : courant → **Courant**, livret → **Livret**, epargne →
> **Épargne**, especes → **Espèces**, credit → **Crédit**. Chaque type a une **icône** dédiée.

---

## Liste des comptes

- **Route** : `/accounts` — protégé.
- **Objectif** : voir ses comptes (personnels + communs dont on est membre), filtrer, créer.

### Anatomie
```
┌───────────────────────────────────────────────────────────┐
│ Comptes                  [Type ▼] [☐ Afficher archivés] [+ Compte ▼]│
│ ┌──────────────────────────────────────────────────────┐  │
│ │ [icône] Compte courant      Personnel     1 234,56 € →│  │
│ │ [icône] Compte commun       Commun · 2 membres  890 €→│  │
│ └──────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### Données affichées (par ligne)
- **Icône de type**, **nom**, **nature** (Personnel / Commun + nombre de membres), **solde réel**
  (EUR). Indicateur « archivé » si applicable.

### États
- **Vide** : « Aucun compte. [Créer un compte] ».
- **Filtres** : par **type** ; **archivés masqués par défaut** (case pour les afficher, grisés).

### Interactions & flux
- `[+ Compte ▼]` → choix **Compte personnel** / **Compte commun** (deux formulaires distincts).
- Clic sur une ligne → **détail du compte**.

### Copy FR
- Titre « Comptes » · « Personnel » / « Commun » · « Afficher les comptes archivés » · « Créer un
  compte ».

---

## Créer un compte personnel

- **Route** : modal/route depuis `/accounts`. **Objectif** : créer un compte à propriétaire unique.

### Anatomie
```
  Nouveau compte personnel
  Nom    [________________]
  Type   [ Courant ▼ ]
  ( devise : EUR — non éditable en V1 )
  [ Annuler ]  [ Créer ]
```

### Données saisies
- **Nom** (≤120), **Type** (select des 5 types). Devise = **EUR fixe** (ne pas afficher de sélecteur).

### Validation & règles
- Le propriétaire = l'utilisateur courant (implicite, pas de choix).

### Copy FR
- « Nouveau compte personnel » · « Nom » · « Type » · « Créer ».

---

## Créer un compte commun

- **Objectif** : créer un compte à ≥ 2 membres avec **quote-parts**.

### Anatomie
```
  Nouveau compte commun
  Nom    [________________]
  Type   [ Courant ▼ ]
  Membres & quote-parts :
   ┌────────────────────────────────────────────┐
   │ Alice   [====●==] 50 %                      │
   │ Bob     [===●===] 50 %                      │
   │ [+ Ajouter un membre]                       │
   └────────────────────────────────────────────┘
   Total des quote-parts : 100 %  ✓   (rouge si ≠ 100 %)
  [ Annuler ]  [ Créer ]
```

### Données saisies
- **Nom**, **Type**, **liste de membres** (parmi les membres du foyer) chacun avec une
  **quote-part** (slider + champ %).

### Validation & règles (**ferme**)
- La **somme des quote-parts doit faire exactement 100 %**. Afficher le total en direct ;
  **désactiver « Créer »** tant que ≠ 100 %.
- **Re-balance automatique** suggérée à l'ajout/retrait d'un membre (répartir l'écart), éditable.
- Minimum 2 membres pour un compte commun.

### Copy FR
- « Nouveau compte commun » · « Membres & quote-parts » · « Ajouter un membre » · « Total des
  quote-parts » · message si ≠ 100 % : « La somme des quote-parts doit faire 100 %. ».

### Accessibilité
- Slider : `aria-valuenow`/`aria-valuetext` (« 50 % ») ; chaque ligne membre labellisée.

---

## Détail d'un compte

- **Route** : `/accounts/{id}` — protégé. **Objectif** : solde + transactions du compte + actions.

### Anatomie
```
┌───────────────────────────────────────────────────────────┐
│ ← Comptes                                                 │
│ [icône] Compte commun        Commun · 2 membres           │
│ Solde réel : 890,00 €                       [Membres] [⋯] │
│ ───────────────────────────────────────────────────────── │
│ Transactions du compte           [+ Ajouter une transaction]│
│  15/06 Carrefour  Courses   −45,00 €  [Confirmée]         │
│  …                                                        │
└───────────────────────────────────────────────────────────┘
```

### Données affichées
- En-tête : icône type, nom, nature, **solde réel**, membres + quote-parts (pour un commun).
- **Liste des transactions** du compte (`TransactionRow`).
- Menu `⋯` : **Archiver** (et **Désarchiver** si archivé), **Modifier** (nom/type).

### Interactions & flux
- `[+ Ajouter une transaction]` → saisie pré-remplie sur ce compte.
- `[Membres]` → **édition des membres** (compte commun).

### Validation & règles
- **Archivage = soft-delete** (pas de suppression). Un compte avec des **dettes ouvertes** ne peut
  pas être supprimé ; proposer d'**archiver** et de régler les dettes d'abord.

### Copy FR
- « Solde réel » · « Membres » · « Archiver » / « Désarchiver » · « Ajouter une transaction ».

---

## Éditer les membres (compte commun)

- **Objectif** : ajouter/retirer des membres, ajuster les quote-parts.

### Anatomie
```
  Membres — Compte commun
   Alice   [====●==] 50 %   [retirer]
   Bob     [===●===] 50 %   [retirer]
   [+ Ajouter un membre]
   Total : 100 % ✓
  [ Annuler ]  [ Enregistrer ]
```

### Validation & règles
- Mêmes invariants que la création : **somme = 100 %**, re-balance auto, ≥ 2 membres.
- Retirer un membre redistribue (suggéré) le reliquat.

### Copy FR
- « Membres » · « Ajouter un membre » · « Retirer » · « Enregistrer ».

### Cas limites
- Retirer un membre ayant des dettes liées au compte : avertir (les dettes existantes subsistent,
  elles se règlent via l'écran Dettes).
