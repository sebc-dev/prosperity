---
description: Review the branch's code commit-by-commit with 3 parallel agents (architecture, security, tests), then post a consolidated verdict on the GitHub issue.
argument-hint: "[SXX.Y | issue number] (defaults to current branch)"
---

# Review de code, commit par commit

Tu vas faire une review **du code de la branche courante**, étape par étape, un
commit après l'autre. La story cible est : `$ARGUMENTS` (si vide, déduis-la de la
branche courante).

## Étape 1 — Contexte + périmètre des commits

Suis `docs/agents/review-context.md` pour résoudre la story, son issue (body +
**tous les commentaires**), le plan `docs/roadmap/SXX.Y-plan.md`, la roadmap,
le glossaire `CONTEXT.md`, les ADRs pertinents, `docs/Stratégie de tests.md`,
`.importlinter`.

Établis la liste ordonnée des commits à reviewer (du plus ancien au plus récent) :

```
base=$(git merge-base main HEAD)
git log --reverse --oneline $base..HEAD
```

S'il n'y a aucun commit, arrête-toi et signale-le. Le diff de chaque commit
s'obtient avec `git show <sha>`.

## Étape 2 — Trois agents en parallèle

Lance **dans un seul message trois sous-agents `Agent` en parallèle**, un par axe.
Chaque agent reçoit la **liste ordonnée des commits** et le contexte pertinent à
son axe, et **parcourt les commits un par un** (`git show <sha>`), en structurant
ses findings **par commit**. Format de `docs/agents/review-context.md` §3
(sévérité + référence `commit:fichier:ligne` + verdict d'axe), en français.

1. **Architecture & code** — Correction et qualité de chaque commit : respect du
   graphe d'imports (ADR 0005 / `.importlinter`), commits placés au bon endroit
   (ADR 0015), ADRs touchés, vocabulaire du glossaire. Atomicité et message de
   chaque commit, réutilisation vs duplication, simplification possible, lisibilité,
   conformité au plan. Régressions introduites puis corrigées plus loin (à noter).

2. **Sécurité** — Vulnérabilités introduites par les diffs : authz/authn, injection,
   secrets/PII dans logs ou audit, exposition de données, intégrité de l'audit log,
   oracles de timing, surface publique des modules, ADRs sécurité (0012/0013/0015/0016
   selon le périmètre). Évalue commit par commit (une faille introduite tôt puis
   corrigée plus tard doit être signalée comme telle).

3. **Tests** — Qualité, pertinence et couverture des tests *selon
   `docs/Stratégie de tests.md`* : chaque changement de comportement est-il couvert ?
   Invariants protégés, TDD sur le domaine, property-based (Hypothesis) là où ça
   compte, intégration DB (testcontainers), tests d'architecture, snapshots de schéma
   et migrations testés (upgrade + downgrade). Cas limites manquants, tests fragiles
   ou cosmétiques.

## Étape 3 — Synthèse et publication

Consolide en **un commentaire en français** :
- En-tête : **verdict global** (`APPROVE` / `CHANGES-REQUESTED` dès qu'un `Bloquant`
  ou `Majeur` existe).
- Une section par axe : verdict + findings regroupés **par commit**, triés par
  sévérité, avec références `commit:fichier:ligne`.
- Tableau récapitulatif des verdicts par axe.

Poste-le sur l'issue : `gh issue comment <number> --body-file <tmpfile>`, puis
affiche la synthèse dans le terminal. Demande confirmation avant de poster si le
numéro d'issue a été déduit plutôt que fourni explicitement.
