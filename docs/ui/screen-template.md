# Gabarit de fiche-écran

Structure que suit chaque écran de `screens-*.md`. À reprendre pour tout nouvel écran. Chaque
fiche **présuppose `design-system.md`** (tokens, composants, formatage, copy, a11y, états) — ne pas
y répéter les conventions communes.

---

## `<Nom de l'écran>`

- **Route** : `/chemin` — public / **protégé** (admin only ?).
- **Objectif** : une phrase (la valeur pour l'utilisateur).
- **Accès** : qui le voit (member/admin), depuis où on y arrive.

### Anatomie (wireframe)
```
Schéma ASCII de la disposition (zones, ordre, hiérarchie).
```

### Données affichées
Liste des champs visibles + **exemple FR concret** + format (cf. design-system §5). Préciser la
source domaine (entité/champ) sans prescrire le hook.

### États
- **Chargement** / **Vide** (texte + action) / **Erreur** / **Peuplé** (cf. design-system §8).

### Interactions & flux
Actions possibles, ce qu'elles déclenchent, navigation, dialogs de confirmation.

### Validation & règles métier
Règles à appliquer côté UI (ex. zero-sum, quote-parts = 100 %, champs gelés après `confirmed`),
et les **erreurs** attendues → message FR (cf. design-system §9).

### Copy FR
Les libellés clés (titres, boutons, placeholders, messages spécifiques à l'écran).

### Responsive
Adaptations desktop ↔ mobile notables.

### Accessibilité
Points spécifiques (au-delà des règles communes).

### Cas limites
Situations particulières et comportement attendu.
