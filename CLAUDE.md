# Prosperity

App de gestion de finances personnelles (suivi, budgets enveloppes, multi-comptes) self-hosted pour un foyer.

## Commandes
- `./mvnw spring-boot:run` : Run backend
- `./mvnw test` : Tests backend
- `./mvnw verify` : Build + tests + checks
- `pnpm install` : Install frontend deps
- `pnpm dev` : Dev server frontend
- `pnpm build` : Build production frontend
- `pnpm test` : Tests frontend
- `pnpm lint` : Lint frontend
- `docker compose up -d` : Run full stack (Caddy + API + PostgreSQL)

## Stack
- Backend: Java 21 LTS (Temurin) + Spring Boot 4.0.x + Spring Security 7.0.x
- ORM: Spring Data JPA 4.0.x + Liquibase 5.0.x
- Database: PostgreSQL 17
- Frontend: Angular 21 + PrimeNG 21.x + Tailwind CSS v4 + ngx-echarts 21.x
- Runtime: Node.js 22 LTS + pnpm
- Infra: Docker Compose + Caddy 2.10.x
- Bank sync: Plaid API (EU/FR)

## Architecture
Hexagonale allegee (Domain / Application / Infrastructure) — API REST monolithique + SPA separee.

```
[Caddy :443] → /api/* → [Spring Boot :8080] → [PostgreSQL :5432]
                                             → [Plaid API]
             → /*     → [Angular SPA/PWA static]
```

## Contexte detaille
- Architecture : `docs/agent_docs/architecture.md`
- Database : `docs/agent_docs/database.md`
- Spec projet : `SPEC.md`
- Discovery : `docs/discovery.md`

## Contraintes critiques
- Open source : toutes les deps doivent etre MIT ou Apache 2.0
- Self-hosted : pas de services cloud payes (hors Plaid)
- Outillage CI/lint mature : pas de versions bleeding edge sans support outils
- Connecteur bancaire derriere une interface abstraite (Plaid interchangeable)

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Prosperity**

Application de gestion de finances personnelles self-hosted pour un foyer. Permet le suivi des comptes bancaires (personnels et communs), la categorisation des transactions, les budgets enveloppes et la synchronisation bancaire automatique via Plaid. Projet open source supportant N utilisateurs avec droits et comptes propres/communs.

**Core Value:** Un foyer peut suivre ses finances au quotidien (soldes, transactions, budgets enveloppes) sans effort manuel excessif, grace a la synchronisation bancaire automatique et une interface claire.

### Constraints

- **Open source** : toutes les dependances MIT ou Apache 2.0
- **Self-hosted** : pas de services cloud payes (hors Plaid)
- **Outillage CI/lint** : versions supportees par Checkstyle, SonarQube, etc. (pas de bleeding edge)
- **Java 21 LTS** : Checkstyle incompatible Java 25
- **Spring Boot 4.0.x** : Boot 3.5 fin OSS juin 2026
- **Connecteur bancaire abstrait** : Plaid interchangeable (interface, pas de couplage direct)
- **Timeline** : pas de deadline, projet personnel "when it's done"
- **Review** : decoupage atomique des phases pour permettre des reviews optimales a chaque etape
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Java (Temurin) | 21 LTS | Backend runtime | Support outillage complet (Checkstyle, SonarQube). Java 25 LTS existe mais Checkstyle incompatible. Support Temurin jusqu'en sept 2028. **HIGH confidence** |
| Spring Boot | 4.0.x (latest 4.0.5) | Backend framework | Sorti nov 2025, support OSS jusqu'en nov 2027. Boot 3.5 fin OSS juin 2026 -- migration forcee evitee. Modularisation complete, JSpecify null-safety. **HIGH confidence** |
| Spring Security | 7.0.x (via Boot 4.0) | Auth + CSRF + BFF | CookieCsrfTokenRepository integre nativement avec Angular (XSRF-TOKEN cookie). BFF cookie flow sans lib externe. **HIGH confidence** |
| Spring Data JPA | 4.0.x (via Boot 4.0) | ORM / DB access | Aligne automatiquement avec Boot 4.0. Hibernate 7 sous le capot. **HIGH confidence** |
| Flyway | 11.x (Apache 2.0) | Migrations DB | **Remplace Liquibase 5.0.** Liquibase 5.0 a change de licence vers FSL (Functional Source License) en oct 2025 -- n'est plus open source. Flyway Community reste Apache 2.0, integre nativement avec Spring Boot 4. **HIGH confidence -- CRITICAL** |
| PostgreSQL | 17 | Base de donnees | 18 mois en production, support jusqu'en nov 2029. Solide pour une app finance. **HIGH confidence** |
| Angular | 21.x | Frontend SPA/PWA | Derniere stable. Signals matures, standalone components par defaut, zoneless. **HIGH confidence** |
| PrimeNG | 21.x (latest 21.1.3) | Composants UI | p-table (tri, filtre, pagination), p-inputnumber (format monetaire), p-calendar, p-dialog. Meilleur ratio composants finance vs Angular Material. **HIGH confidence** |
| Tailwind CSS | v4 | CSS utility framework | Integration native via tailwindcss-primeui plugin. Layout Tailwind + composants PrimeNG styles. **HIGH confidence** |
| ngx-echarts | 21.0.0 | Graphiques | Wrapper Angular pour Apache ECharts. Candlestick, dataZoom, 30+ types de graphiques. Version alignee avec Angular 21. **HIGH confidence** |
| Caddy | 2.11.x (latest 2.11.1) | Reverse proxy | **Version mise a jour : 2.11.1** (pas 2.10.x). HTTPS auto, HTTP/3, ECH, post-quantum crypto. Rolling release, seule la derniere version est supportee. **HIGH confidence** |
| Node.js | 22 LTS | Frontend tooling | Requis par Angular 21. LTS active. **HIGH confidence** |
| pnpm | latest | Package manager | Default Angular 21. Rapide, deduplication stricte. **HIGH confidence** |
| Docker Compose | v2 | Conteneurisation | Self-hosted, simplifie le deploiement. 3 services : db, backend, caddy. **HIGH confidence** |
| Plaid API (EU/FR) | latest | Synchro bancaire | SG + Banque Populaire confirmees. SDK Java plaid-java 39.x. Interface abstraite pour interchangeabilite. **HIGH confidence** |
### Supporting Libraries -- Backend
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| plaid-java | 39.x (latest 39.1.0) | SDK Plaid officiel | Import transactions, connexion institutions bancaires. Maven Central. Apache 2.0. |
| MapStruct | 1.6.x | Mapping DTO/Entity | Mapping entre domain models, JPA entities et DTOs REST. Compile-time, zero reflexion. Apache 2.0. |
| springdoc-openapi | 2.8.x / 3.0.x | Documentation API | Genere OpenAPI 3.1 spec + Swagger UI. Supporte Spring Boot 4. Attention : version 3.0.0 a un bug connu avec API versioning. Utiliser 2.8.x en attendant fix. Apache 2.0. |
| Testcontainers | 2.x | Tests integration | Containers Docker pour PostgreSQL dans les tests. Supporte Spring Boot 4 nativement. Apache 2.0. |
| AssertJ | 3.x (via Boot) | Assertions tests | Fluent assertions, inclus dans spring-boot-starter-test. Apache 2.0. |
| JUnit | 5.x / 6.x (via Boot) | Framework tests | Inclus dans spring-boot-starter-test. Boot 4 supporte JUnit 5 et 6. EPL 2.0. |
| ArchUnit | 1.x | Tests architecture | Valider les regles hexagonales (domain ne depend pas d'infra). Apache 2.0. |
| Checkstyle | 10.x | Lint Java | Compatible Java 21 (parse up to Java 22). Integre Maven. LGPL 2.1. |
| Jackson | 2.x (via Boot) | JSON serialization | Inclus dans Boot. Serialization montants, dates. Apache 2.0. |
### Supporting Libraries -- Frontend
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tailwindcss-primeui | latest | Integration Tailwind v4 + PrimeNG | Plugin officiel PrimeTek. CSS version pour Tailwind v4. MIT. |
| Apache ECharts | 5.x | Moteur graphiques | Peer dependency de ngx-echarts. Tree-shakeable. Apache 2.0. |
| @angular/pwa | 21.x | PWA support | Ajoute service worker, manifest. Via `ng add @angular/pwa`. MIT. |
| @angular/cdk | 21.x | Utilities UI | Drag-drop, overlay, clipboard. Utilise par PrimeNG en interne. MIT. |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| Maven Wrapper (mvnw) | Build backend | Embarque dans le projet, pas d'install Maven requise |
| Checkstyle Maven Plugin | Lint Java | `mvn checkstyle:check` dans CI |
| JaCoCo | Code coverage | Genere rapports coverage, integrable SonarQube |
| SonarQube (optionnel) | Analyse statique | Version 2026.x pour Java 21. Self-hosted ou skip en v1 |
| Angular CLI | Build/serve frontend | `ng serve`, `ng build`, `ng test` via pnpm |
| ESLint | Lint Angular | `@angular-eslint/schematics` pour config Angular 21 |
| Prettier | Format code | Frontend only. Consistent formatting |
## Installation
### Backend (pom.xml)
### Frontend
# Core
# Dev dependencies
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Flyway 11.x (Apache 2.0) | Liquibase 5.0.x (FSL) | Jamais pour ce projet. Liquibase 5.0 n'est plus open source (FSL != Apache/MIT). Contrainte projet : deps MIT ou Apache 2.0 uniquement |
| Flyway 11.x | Liquibase 4.x (Apache 2.0) | Si besoin de rollback natif ou format YAML/XML. Mais Liquibase 4.x est en fin de vie, pas de patches securite |
| PrimeNG 21.x | Angular Material 21.x | Si le projet n'a pas besoin de composants finance riches (p-inputnumber monetaire, p-table avancee). Material domine le corpus AI mais manque de composants finance |
| ngx-echarts | ng2-charts (Chart.js) | Si seuls des graphiques simples (bar, line, pie) sont necessaires et que le poids du bundle est critique (~70 kB vs ~120-150 kB). Pas de candlestick, pas de dataZoom |
| Caddy 2.11.x | Nginx | Si besoin de performance brute ou config tres avancee. Mais complexite de config HTTPS manuelle, pas de HTTP/3 natif |
| Caddy 2.11.x | Traefik | Si l'infra est multi-services avec service discovery Docker. Overkill pour ce projet (3 containers fixes) |
| MapStruct | Records + manual mapping | Si le nombre de DTOs est tres faible (<5). MapStruct ajoute une dep mais elimine le code boilerplate de mapping |
| springdoc-openapi | Spring REST Docs | Si la doc API doit etre basee sur les tests. Plus lourd a maintenir, moins de DX pour un projet solo |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Liquibase 5.0.x | Licence FSL, pas open source. Viole la contrainte MIT/Apache 2.0 du projet | Flyway 11.x (Apache 2.0) |
| Liquibase 4.x | Fin de vie, plus de patches securite | Flyway 11.x |
| GoCardless/Nordigen | Ferme aux nouveaux inscrits depuis juillet 2025 | Plaid API |
| ngx-charts (Swimlane) | Pas de support Angular 21, maintenance en declin | ngx-echarts 21.0.0 |
| Spartan UI | Alpha, 1 mainteneur, corpus AI quasi nul | PrimeNG 21.x |
| Angular Material | Composants finance insuffisants : pas de currency input, table basique | PrimeNG 21.x |
| JSR 354 / Moneta (JavaMoney) | Over-engineering pour un projet mono-devise EUR. Montants en centimes (long) suffisent. Moneta ajoute complexite sans valeur pour ce use case | Montants en centimes (BIGINT/long) |
| Spring Cloud Gateway (BFF) | Overkill pour un monolithe. Spring Security 7 gere le BFF cookie flow nativement | Spring Security 7 CookieCsrfTokenRepository |
| Lombok | Debat permanent, masque le code genere. Java 21 records couvrent la majorite des cas (DTOs, value objects). Pour les entities JPA, constructeurs/getters manuels restent plus clairs | Java 21 records + code manuel |
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Spring Boot 4.0.5 | Java 17-25 | Java 17 minimum, Java 21 recommande pour Checkstyle |
| Spring Boot 4.0.x | Flyway 11.x | Auto-configured via spring-boot-starter |
| Spring Boot 4.0.x | Testcontainers 2.x | Support natif `@Testcontainers`, `@ServiceConnection` |
| Spring Boot 4.0.x | springdoc-openapi 2.8.x | Version 3.0.0 a un bug avec API versioning, rester sur 2.8.x |
| Angular 21 | ngx-echarts 21.0.0 | Versions alignees par convention |
| Angular 21 | PrimeNG 21.1.x | PrimeNG suit le cycle Angular |
| Angular 21 | Node.js 22 LTS | Minimum requis par Angular CLI 21 |
| PrimeNG 21.x | Tailwind CSS v4 | Via tailwindcss-primeui plugin (CSS version, pas JS version) |
| Caddy 2.11.x | HTTP/3, ECH | Rolling release, seule la derniere est supportee |
| plaid-java 39.x | Java 17+ | SDK genere depuis OpenAPI spec, mise a jour mensuelle |
## CRITICAL: Changement Liquibase vers Flyway
## Caddy Version Update
## Sources
- [Spring Boot 4.0.0 release announcement](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/) -- release date, features (HIGH confidence)
- [Spring Boot end-of-life dates](https://endoflife.date/spring-boot) -- support timelines (HIGH confidence)
- [Spring Security 7 CSRF docs](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) -- CookieCsrfTokenRepository, Angular integration (HIGH confidence)
- [Liquibase FSL license announcement](https://www.liquibase.com/blog/liquibase-community-for-the-future-fsl) -- licence change confirmed (HIGH confidence)
- [Liquibase 5.0 release notes](https://docs.liquibase.com/community/release-notes/5-0) -- FSL details (HIGH confidence)
- [Flyway licensing](https://documentation.red-gate.com/fd/flyway-open-source-277579296.html) -- Apache 2.0 confirmed (HIGH confidence)
- [Flyway GitHub](https://github.com/flyway/flyway) -- Apache 2.0 license (HIGH confidence)
- [PrimeNG releases](https://github.com/primefaces/primeng/releases) -- version 21.1.3, Angular 21 support (HIGH confidence)
- [ngx-echarts GitHub](https://github.com/xieziyu/ngx-echarts) -- version 21.0.0 for Angular 21 (HIGH confidence)
- [Caddy releases](https://github.com/caddyserver/caddy/releases) -- version 2.11.1 latest (HIGH confidence)
- [plaid-java on Maven Central](https://mvnrepository.com/artifact/com.plaid/plaid-java) -- version 39.1.0 (HIGH confidence)
- [Testcontainers 2.0 + Spring Boot 4](https://rieckpil.de/whats-new-for-testing-in-spring-boot-4-0-and-spring-framework-7/) -- testing changes (MEDIUM confidence)
- [springdoc-openapi GitHub](https://github.com/springdoc/springdoc-openapi) -- Spring Boot 4 support, bug with v3.0.0 (MEDIUM confidence)
- [MapStruct releases](https://github.com/mapstruct/mapstruct/releases) -- version 1.6.3 (MEDIUM confidence)
- [tailwindcss-primeui GitHub](https://github.com/primefaces/tailwindcss-primeui) -- Tailwind v4 support (MEDIUM confidence)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
