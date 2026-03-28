# Phase 1: Project Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 01-Project Foundation
**Areas discussed:** Architecture & structure, Profondeur domaine, Quality gates, Scaffolding frontend

---

## Architecture & Structure Projet

**Contexte :** L'utilisateur a interrompu la discussion Phase 1 pour remettre en question l'architecture hexagonale prevue initialement. Consideration : le projet est aussi un portfolio technique, l'over-engineering n'est pas credible.

| Option | Description | Selected |
|--------|-------------|----------|
| Module unique + layered par feature | Un seul module Maven, packages par feature (account/, transaction/...), abstraction strategique uniquement sur le connecteur bancaire | X |
| Multi-modules Maven | Modules separes domain/application/infrastructure. Garantie compile-time | |
| Hexagonale allegee (originale) | Ports/adapters generalises. Domain sans dependances externes | |

**User's choice:** Module unique + layered par feature
**Notes:** L'hexagonal est une contrainte plus qu'un apport pour un monolithe avec un seul adapter par port. Le discernement architectural (savoir quand NE PAS abstraire) est plus credible en portfolio. ADR-0002 cree pour documenter le changement. Tous les docs mis a jour (architecture.md, CLAUDE.md, PROJECT.md, SPEC.md).

---

## Profondeur du Domaine

| Option | Description | Selected |
|--------|-------------|----------|
| Entites completes + tests | Entites JPA completes, Value Objects, repositories Spring Data, migrations Flyway, tests unitaires regles metier | X |
| Squelettes + Value Objects | Value Objects avec tests, entites en squelette, completees dans chaque phase fonctionnelle | |

**User's choice:** Entites completes + tests
**Notes:** Aucune -- choix direct du recommande.

---

## Quality Gates

### Seuil de couverture

| Option | Description | Selected |
|--------|-------------|----------|
| 70% (recommande) | Standard industrie | |
| 80% | Plus exigeant | |
| 60% | Pragmatique | |
| Pas de seuil -- reporting only | JaCoCo comme outil de visibilite | X |

**User's choice:** Pas de seuil. JaCoCo en mode reporting pour juger la couverture et la qualite des tests, sans build qui echoue.
**Notes:** "Je ne veux pas de seuil a proprement parle. Je veux que ce soit un outil pour juger de la couverture et de la qualite des tests."

### Analyse statique Java

| Option | Description | Selected |
|--------|-------------|----------|
| SpotBugs | Bytecode analyzer, post-compilation, LGPL 2.1 | |
| Error Prone (Google) | Compile-time checker, javac plugin, Apache 2.0 | X |
| SonarQube self-hosted | Dashboard complet, necessite container Docker supplementaire | |

**User's choice:** Error Prone
**Notes:** L'utilisateur a demande une recherche comparative SpotBugs vs Error Prone. Apres presentation des tradeoffs (precision, faux positifs, integration, portfolio), choix d'Error Prone pour sa precision et son aspect moderne.

### Detection code mort

**User's choice:** Checkstyle (imports) + warnings compilateur. Pas d'outil dedie.
**Notes:** Decision differee jusqu'au choix SpotBugs/Error Prone. Comme Error Prone ne detecte pas le code mort nativement, approche minimaliste retenue.

---

## Scaffolding Frontend

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal fonctionnel | ng new + PrimeNG + Tailwind v4 + ESLint + Prettier. Page vide qui charge. | X |
| Structure avec layout | + routing + layout shell + theme PrimeNG personnalise | |

**User's choice:** Minimal fonctionnel
**Notes:** Routing, layout shell et theme ajoutes en Phase 2 quand necessaire.

---

## Claude's Discretion

- Configuration Docker Compose exacte
- Structure CI pipeline GitHub Actions
- Choix Husky vs lefthook
- Configuration Error Prone
- Nommage migrations Flyway

## Deferred Ideas

None
