# Phase 1: Project Foundation - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Environnement de developpement fonctionnel avec modele de domaine valide, quality gates completes, et pipeline CI. Scaffolding backend (Spring Boot 4.0.x) et frontend (Angular 21) avec Docker Compose operationnel.

</domain>

<decisions>
## Implementation Decisions

### Architecture & structure projet
- **D-01:** Architecture layered par feature (Controller/Service/Repository), pas d'hexagonal. Package-by-feature : account/, transaction/, envelope/, banking/, auth/, admin/, shared/. Voir ADR-0002.
- **D-02:** Module Maven unique. ArchUnit valide les regles de dependance entre packages (pas d'import circulaire, banking/ abstrait via interface).
- **D-03:** Abstraction strategique uniquement sur le connecteur bancaire (interface BankConnector). Pas de ports/adapters generalises.

### Modele de domaine
- **D-04:** Entites JPA completes en Phase 1 : Account, Transaction, Envelope, User, Category, avec tous les champs et relations.
- **D-05:** Value Objects : Money (BigDecimal, precision 2, pas de floating-point), TransactionState (enum : MANUAL_UNMATCHED, IMPORTED_UNMATCHED, MATCHED).
- **D-06:** Repositories Spring Data JPA pour chaque entite. Migrations Flyway completes pour le schema initial.
- **D-07:** Tests unitaires sur les regles metier : Money n'accepte pas de floating-point, Transaction states valides, Envelope rollover/overspend.

### Quality gates
- **D-08:** JaCoCo en mode reporting uniquement, pas de seuil bloquant. Outil de visibilite, pas de gate.
- **D-09:** Error Prone (Google) pour l'analyse statique Java. Compile-time checker, Apache 2.0, peu de faux positifs.
- **D-10:** Checkstyle pour le lint Java (imports inutilises, conventions). google-java-format pour le formatage.
- **D-11:** Detection code mort : Checkstyle (imports) + warnings compilateur. Pas d'outil dedie supplementaire.
- **D-12:** OWASP dependency-check pour le scan de securite des dependances.
- **D-13:** Pre-commit hooks (Husky ou lefthook) : lint + format checks avant chaque commit.

### Scaffolding frontend
- **D-14:** Angular minimal fonctionnel : ng new + PrimeNG 21.x + Tailwind v4 + tailwindcss-primeui + ESLint + Prettier. Page d'accueil vide qui charge.
- **D-15:** Pas de routing, layout shell ou theme personnalise en Phase 1. Ajoutes en Phase 2 (auth) quand necessaire.

### Claude's Discretion
- Configuration Docker Compose exacte (volumes, networks, healthchecks)
- Structure CI pipeline GitHub Actions (nombre de jobs, parallelisation)
- Choix entre Husky et lefthook pour les pre-commit hooks
- Configuration exacte Error Prone (quels checks activer)
- Nommage des migrations Flyway

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `docs/agent_docs/architecture.md` -- Structure backend package-by-feature, composants, flux de donnees
- `docs/adr/0001-initial-stack.md` -- Decisions stack technique (Java 21, Spring Boot 4.0.x, Flyway 11.x)
- `docs/adr/0002-architecture-layered.md` -- Decision architecture layered (remplacement hexagonal)

### Base de donnees
- `docs/agent_docs/database.md` -- Schema initial PostgreSQL, tables, relations

### Spec projet
- `SPEC.md` -- Fonctionnalites MVP, stack, contraintes

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Aucun code existant -- codebase vierge, Phase 1 est le scaffolding initial

### Established Patterns
- Aucun pattern etabli -- les patterns seront definis par Phase 1

### Integration Points
- Docker Compose : 3 services (db, backend, caddy)
- Caddy : reverse proxy /api/* vers Spring Boot :8080, fichiers statiques Angular
- Flyway : migrations au demarrage Spring Boot

</code_context>

<specifics>
## Specific Ideas

- Le projet est open source ET une vitrine technique (portfolio Java/Spring + IA). Les choix doivent etre credibles aux yeux de devs seniors.
- Error Prone choisi pour son aspect moderne et Google-level practices, pas juste pour la detection de bugs.
- JaCoCo sans seuil : outil de visibilite pour juger la qualite, pas une contrainte bloquante.

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 01-project-foundation*
*Context gathered: 2026-03-28*
