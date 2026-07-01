# Écrans — Catégories

Présuppose `design-system.md`. Routes **protégées** sous `/categories`. Les catégories forment un
**arbre** (hiérarchie illimitée), partagé au niveau du **foyer**. Chaque catégorie porte une
**couleur** (`#RRGGBB`) et une **icône**. Pas de suppression dure : **archivage**.

> Les budgets agrègent automatiquement les sous-catégories ; réorganiser l'arbre fait suivre les
> agrégats mécaniquement (le signaler discrètement).

---

## Arbre des catégories

- **Route** : `/categories` — protégé. **Objectif** : organiser la taxonomie du foyer.

### Anatomie
```
┌──────────────────────────────────────────────────────────────┐
│ Catégories                    [☐ Afficher archivées][+ Catégorie]│
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ 🟧 Courses                                      [⋯]       │ │
│ │   └ 🟨 Frais                                    [⋯]       │ │
│ │   └ 🟫 Maison                                   [⋯]       │ │
│ │ 🟦 Logement                                     [⋯]       │ │
│ │ 🟩 Loisirs                                      [⋯]       │ │
│ │   └ 🟪 Cinéma                                   [⋯]       │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Données affichées (par nœud)
- **Pastille couleur + icône**, **nom**, **indentation** selon la profondeur. Menu `⋯` :
  **Modifier**, **Déplacer vers…**, **Archiver** (et **Désarchiver**).
- Archivées masquées par défaut (case pour les afficher, grisées).

### Réorganisation (choix d'implémentation — #240)
- MVP : **glisser-déposer** pour déplacer un nœud, **ou** un simple modal **« Déplacer vers… »**
  (sélecteur du nouveau parent). Le glisser-déposer peut être remplacé par le modal si délai serré.
- Indentation visuelle jusqu'à ~5 niveaux ; au-delà, repli (collapse).

### États
- **Vide** : « Aucune catégorie. [Créer une catégorie] ».
- **Profondeur élevée** : nœuds repliables.

### Validation & règles (**ferme**)
- **Prévention des cycles** : on ne peut pas déplacer une catégorie **sous l'un de ses descendants**
  (l'UI doit empêcher/désactiver ces cibles ; sinon refus serveur). Message : « Déplacement
  impossible : une catégorie ne peut pas être placée dans sa propre descendance. ».
- **Archivage = soft-delete**, sans cascade : archiver un parent **n'archive pas** ses enfants
  (le préciser). Désarchivage libre.

### Interactions & flux
- `[+ Catégorie]` → création (avec parent optionnel). `⋯ → Déplacer` → choix du parent.

### Copy FR
- « Catégories » · « Afficher les catégories archivées » · « Créer une catégorie » · « Modifier »
  · « Déplacer vers… » · « Archiver » / « Désarchiver ».

---

## Créer / Éditer une catégorie

- **Objectif** : nommer, colorer, illustrer, et placer une catégorie dans l'arbre.

### Anatomie
```
  Nouvelle catégorie
  Nom        [ Courses ]
  Parent     [ (Racine) ▼ ]        ( arbre des catégories existantes )
  Couleur    [■ #FF8800]  ( color picker )
  Icône      [ 🛒 ▼ ]      ( icon picker )
  [ Annuler ]  [ Créer ]
```

### Données saisies
- **Nom** (≤120), **Parent** (catégorie existante ou Racine), **Couleur** (hex `#RRGGBB`, color
  picker), **Icône** (icon picker — jeu lucide).

### Validation & règles
- Édition : changer le parent applique la **prévention des cycles** (cf. ci-dessus).
- Couleur/icône servent partout (chips de transactions, budgets) → choisir des contrastes lisibles
  en clair **et** sombre.

### Copy FR
- « Nouvelle catégorie » / « Modifier la catégorie » · « Nom » · « Parent » · « (Racine) » ·
  « Couleur » · « Icône » · « Créer » / « Enregistrer ».

---

## Archiver une catégorie

- **Objectif** : retirer une catégorie de l'usage courant sans perdre l'historique.

### Comportement
- Confirmation légère (dialog) : « Archiver « {nom} » ? Les transactions et budgets existants
  restent inchangés ; la catégorie n'apparaîtra plus dans les sélecteurs. ».
- **Désarchivage** possible à tout moment (depuis la liste, archivées affichées).

### Cas limites
- Catégorie utilisée par un budget actif : l'archiver n'empêche pas le budget de continuer à
  agréger l'historique ; signaler que la catégorie ne sera plus proposée à la saisie.
