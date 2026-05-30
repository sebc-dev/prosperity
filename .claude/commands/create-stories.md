---
description: Turn an epic into GitHub story issues — gather the full roadmap/ADR/glossary context, reconcile the breakdown with current decisions, then create the [SXX.Y] issues with confirmation.
argument-hint: "[EXX | epic issue number] (defaults to the epic of the current branch)"
---

# Création des stories d'un epic

Tu vas transformer un **epic** en **issues GitHub de story** (`[SXX.Y] …`), prêtes
à être grabbées. La cible est : `$ARGUMENTS` (si vide, déduis l'epic de la branche
courante — ex. `story/S04.2-…` → epic `E04`).

## Étape 1 — Contexte

Suis intégralement `docs/agents/story-authoring-context.md` pour :
- résoudre l'epic (`EXX`) et son issue GitHub (label `epic`, body + **commentaires**) ;
- lire le fichier roadmap `docs/roadmap/EXX-*.md` (la **source du découpage**), le
  `docs/roadmap/README.md` (hiérarchie + règles d'atomicité par phase + nommage),
  le glossaire `CONTEXT.md`, les ADRs cités et transverses, `docs/Stratégie de tests.md`,
  `.importlinter`, et les epics dont celui-ci `Dépend de` ;
- lire les **issues de story déjà créées** pour cet epic, à deux fins : (a) ne pas
  recréer une story existante ; (b) calquer le format sur une issue récente bien
  formée (ex. `[S04.1]` : Objectif / Livrable observable / Phases atomiques /
  Critères d'acceptation / Notes pour l'implémenteur).

Si l'epic n'a ni fichier roadmap ni issue, arrête-toi et signale-le.

## Étape 2 — Réconcilier le découpage

Le découpage du fichier roadmap est la **baseline**, pas une vérité figée (cf.
`story-authoring-context.md` §3). Confronte-le au contexte courant :
- ADRs ajoutés depuis, contrats import-linter, et surtout les **décisions prises en
  commentaires** des stories voisines déjà reviewées (elles priment sur le fichier).
- Respecte les **règles d'atomicité** du README (une phase = une chose, branche verte,
  pas de mix refactor+feature+test, migration DB = phase dédiée, nouvel ADR = phase
  dédiée avant son dépendant, ≤ ~400 lignes de diff).

Quand la baseline doit changer, **explicite le delta** et, si le fichier roadmap
`docs/roadmap/EXX-*.md` est lui-même devenu faux, prépare sa mise à jour dans le même
lot (et dis-le).

## Étape 3 — Rédiger chaque story

Pour **chaque story non encore créée** (et seulement celles-là), rédige une issue
riche, en français, vocabulaire du glossaire. Calque le format d'une issue de story
existante bien formée :

- **En-tête** (blockquote) : `> **Story** dans Epic #<n> ([EXX] …) | **Bloquée par** : #… / aucune`
  puis une ligne `Source : <lien permalink vers la section #sXXy du fichier roadmap>`.
- **## Objectif** — pourquoi cette story, sa place dans l'epic et ses dépendances.
- **## Livrable observable** — le critère externe et vérifiable de « fini ».
- **## Phases atomiques** — checklist `- [ ] **PXX.Y.Z** — … (~N lignes)`, une par
  phase, dans l'ordre, avec l'estimation de diff.
- **## Critères d'acceptation** — checklist exhaustive, testable, sans ambiguïté.
- **## Notes pour l'implémenteur** — décisions structurantes, pièges import-linter /
  sécurité / ADR, dépendances intra-epic, deltas vs roadmap.

## Étape 4 — Publication (avec confirmation)

Récapitule au terminal : les stories à créer (titre + résumé), les éventuelles mises
à jour du fichier roadmap, et les labels prévus. **Demande confirmation avant de
publier** (acte visible).

Après accord, pour chaque story :

```
gh issue create --title "[SXX.Y] <titre>" --body-file <tmpfile> \
  --label roadmap-mvp --label needs-triage --label module:<module>
```

(reprends les labels `module:*` de l'epic / des stories sœurs ; ajoute `needs-info`
plutôt que `ready-for-agent` tant que la spec n'est pas complète). Si le fichier
roadmap doit changer, applique l'édition. Affiche enfin la liste des issues créées
avec leurs numéros.
