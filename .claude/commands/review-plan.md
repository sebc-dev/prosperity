---
description: Review the implementation plan of a story with 3 parallel agents (architecture, security, tests), then post a consolidated verdict on the GitHub issue.
argument-hint: "[SXX.Y | issue number] (defaults to current branch)"
---

# Review du plan de story

Tu vas faire une review **du plan d'implémentation** d'une story (le document
`docs/roadmap/SXX.Y-plan.md`), avant tout code. La cible est : `$ARGUMENTS`
(si vide, déduis la story de la branche courante).

## Étape 1 — Contexte

Suis intégralement `docs/agents/review-context.md` pour :
- résoudre la story et son issue GitHub (numéro, body, **tous les commentaires**) ;
- lire le plan `docs/roadmap/SXX.Y-plan.md`, la section roadmap `docs/roadmap/E0X-*.md`,
  le glossaire `CONTEXT.md`, les ADRs pertinents, `docs/Stratégie de tests.md`,
  `.importlinter`.

Si le fichier de plan n'existe pas, arrête-toi et signale-le (rien à reviewer).

## Étape 2 — Trois agents en parallèle

Lance **dans un seul message trois sous-agents `Agent` en parallèle**. Chacun
reçoit : le texte intégral du plan, le body + commentaires de l'issue, et les
extraits de docs/ADR/glossaire pertinents à son axe. Chacun rend ses findings au
format de `docs/agents/review-context.md` §3 (sévérité + verdict d'axe), en
français.

1. **Architecture & code** — Le plan est-il correct et cohérent ? Respect du graphe
   d'imports (ADR 0005 / `.importlinter`), placement des commits (ADR 0015), des
   ADRs touchés, du vocabulaire du glossaire. Décisions structurantes justifiées,
   alternatives pesées, pas de YAGNI ni de sur-ingénierie. Réutilisation de
   l'existant identifiée. Items déférés explicites. Risques de design.

2. **Sécurité** — Le plan est-il sûr *by design* ? AuthZ/AuthN, exposition de
   données, secrets/PII dans les logs, intégrité de l'audit, oracles de timing,
   surface publique des modules, ADRs sécurité (0012/0013/0015/0016 selon le
   périmètre). Menaces non adressées par le plan.

3. **Tests** — Le plan est-il *testable* et la stratégie de test adéquate selon
   `docs/Stratégie de tests.md` ? Couverture des invariants, TDD sur le domaine,
   property-based (Hypothesis) là où ça compte, intégration DB (testcontainers),
   tests d'architecture, cas limites prévus, snapshots/migrations testés. Pas de
   couverture cosmétique.

## Étape 3 — Synthèse et publication

Consolide les trois retours en **un commentaire en français** :
- En-tête : **verdict global** (`APPROVE` / `CHANGES-REQUESTED`) — `CHANGES-REQUESTED`
  dès qu'un `Bloquant` ou `Majeur` existe sur un axe.
- Une section par axe (verdict + findings triés par sévérité, avec références
  `fichier:ligne` quand applicable).
- Tableau récapitulatif des verdicts par axe.

Poste-le sur l'issue : `gh issue comment <number> --body-file <tmpfile>`, puis
affiche la synthèse dans le terminal. Demande confirmation avant de poster si le
numéro d'issue a été déduit plutôt que fourni explicitement.
