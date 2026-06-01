---
description: Review the branch's code commit-by-commit, launching 3 parallel agents (architecture, security, tests) per commit, then post a consolidated verdict on the GitHub issue.
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

## Étape 2 — Trois agents en parallèle, **par commit**

Parcours les commits **dans l'ordre** (du plus ancien au plus récent). Pour
**chaque commit**, lance **dans un seul message trois sous-agents `Agent` en
parallèle**, un par axe, tous focalisés sur le **diff de ce seul commit**
(`git show <sha>`). Attends leurs trois retours, range les findings sous le commit
courant, puis passe au commit suivant. Ne lance pas le batch du commit suivant
avant d'avoir collecté celui en cours.

Chaque agent reçoit :
- le **SHA et le message du commit** à reviewer, et son diff via `git show <sha>` ;
- la **liste ordonnée complète des commits** de la branche, pour situer ce commit
  dans la séquence (mais il ne reviewe **que** le sien) ;
- le contexte pertinent à son axe (Étape 1).

Il renvoie ses findings au format `docs/agents/review-context.md` §3 (sévérité +
référence `commit:fichier:ligne` + verdict d'axe **pour ce commit**), en français.

1. **Architecture & code** — Correction et qualité du commit : respect du graphe
   d'imports (ADR 0005 / `.importlinter`), commit placé au bon endroit (ADR 0015),
   ADRs touchés, vocabulaire du glossaire. Atomicité et message du commit,
   réutilisation vs duplication, simplification possible, lisibilité, conformité
   au plan.

2. **Sécurité** — Vulnérabilités introduites par le diff : authz/authn, injection,
   secrets/PII dans logs ou audit, exposition de données, intégrité de l'audit log,
   oracles de timing, surface publique des modules, ADRs sécurité (0012/0013/0015/0016
   selon le périmètre).

3. **Tests** — Qualité, pertinence et couverture des tests *selon
   `docs/Stratégie de tests.md`* : chaque changement de comportement du commit est-il
   couvert ? Invariants protégés, TDD sur le domaine, property-based (Hypothesis) là
   où ça compte, intégration DB (testcontainers), tests d'architecture, snapshots de
   schéma et migrations testés (upgrade + downgrade). Cas limites manquants, tests
   fragiles ou cosmétiques.

> **Régressions corrigées plus loin** : comme chaque agent ne voit que son commit,
> il ne peut pas savoir qu'un commit ultérieur corrige un problème qu'il signale.
> C'est à l'Étape 3, qui dispose de tous les findings de tous les commits, de
> réconcilier ces cas : annoter un finding « introduit en `<sha1>`, corrigé en
> `<sha2>` » et l'abaisser en `Mineur`/`Nit` (ou le clore) selon l'impact résiduel.

## Étape 3 — Synthèse et publication

Une fois tous les commits parcourus, réconcilie d'abord les findings transverses
(régressions introduites puis corrigées plus loin, cf. encadré ci-dessus), puis
consolide en **un commentaire en français** organisé **par commit, puis par axe** :
- En-tête : **verdict global** (`APPROVE` / `CHANGES-REQUESTED` dès qu'un `Bloquant`
  ou `Majeur` subsiste après réconciliation).
- Une **section par commit** (dans l'ordre), avec à l'intérieur les findings des
  **trois axes**, triés par sévérité, références `commit:fichier:ligne`.
- Un **tableau récapitulatif** : une ligne par commit, une colonne par axe, verdict
  par cellule + verdict d'axe agrégé.

Poste-le sur l'issue : `gh issue comment <number> --body-file <tmpfile>`, puis
affiche la synthèse dans le terminal. Demande confirmation avant de poster si le
numéro d'issue a été déduit plutôt que fourni explicitement.
