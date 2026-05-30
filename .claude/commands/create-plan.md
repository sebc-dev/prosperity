---
description: Write a detailed, grilling-resistant implementation plan for a story — gather the full story/epic/ADR/glossary/test context and dependency work, then post it as a comment on the GitHub issue with confirmation.
argument-hint: "[SXX.Y | story issue number] (defaults to current branch)"
---

# Plan d'implémentation d'une story

Tu vas rédiger le **plan d'implémentation détaillé** d'une story, prêt à résister à
une review multi-agents. La cible est : `$ARGUMENTS` (si vide, déduis la story de la
branche courante — ex. `story/S04.2-…` → `S04.2`).

## Étape 1 — Contexte

Suis intégralement `docs/agents/story-authoring-context.md` pour :
- résoudre la story (`SXX.Y`) et son issue GitHub (body + **tous les commentaires** :
  les décisions de review y vivent et **priment sur le fichier roadmap**) ;
- lire la section de la story dans `docs/roadmap/EXX-*.md`, le `docs/roadmap/README.md`
  (règles d'atomicité par phase), le glossaire `CONTEXT.md`, les ADRs cités et
  transverses (0005 / 0015 + sécurité selon le périmètre), `docs/Stratégie de tests.md`,
  `.importlinter` ;
- lire le **travail précédent** dont cette story dépend : issues + commentaires des
  stories antérieures, et leurs plans (fichier `docs/roadmap/SXX.Y-plan.md` historique
  ou plan posté en commentaire) — pour connaître les primitives, APIs publiques et
  décisions déjà en place ;
- lire un plan existant (`docs/roadmap/S02.4-plan.md`, `S03.1-plan.md`) comme **gabarit
  de format**.

Si la story n'a pas d'issue, arrête-toi et signale-le.

## Étape 2 — Rédiger le plan

En français, vocabulaire du glossaire, snippets de code concrets. Structure attendue
(format des plans existants) :

1. **En-tête** — issue cible + branche source + docs de référence (roadmap, ADRs, glossaire).
2. **§1 État des lieux & décisions structurantes** — ce qui existe déjà (réutilisable),
   ce qui manque, puis un **tableau des décisions** structurantes avec justification
   (alternatives pesées, contraintes import-linter prises en compte, ADRs touchés).
3. **§2 Ordre d'exécution** — diagramme ASCII des phases (`PXX.Y.Z`) avec leurs
   dépendances ; respecte les règles d'atomicité (branche verte à chaque phase,
   migration DB = phase dédiée, nouvel ADR = phase dédiée avant son dépendant).
4. **§N par phase** — pour chaque phase : objectif, snippets Python concrets
   (signatures, structures, contrats), placement des modules conforme à `.importlinter`,
   et la **liste explicite des cas de test** (invariants, TDD domaine, property-based
   Hypothesis, intégration testcontainers, tests d'architecture, migrations
   upgrade+downgrade).
5. **§ Validation finale** — les commandes : `ruff`, `pyright`/type-check, `lint-imports`,
   `pytest`, coverage.
6. **§ Hors scope** — ce qui est explicitement reporté (et vers quelle story / quel
   follow-up).
7. **§ Récap des fichiers** touchés / créés.

La barre est **anti-grilling** : chaque décision justifiée, chaque cas de test nommé,
chaque contrat import-linter couvert. Pas de « TODO décider plus tard ». Surface tout
delta vs roadmap ou contradiction d'ADR explicitement.

## Étape 3 — Publication (avec confirmation)

Affiche le plan au terminal. **Demande confirmation avant de poster** (acte visible),
puis publie-le comme **commentaire sur l'issue de la story** :

```
gh issue comment <number> --body-file <tmpfile>
```

Demande systématiquement confirmation si le numéro d'issue a été déduit de la branche
plutôt que fourni explicitement.
