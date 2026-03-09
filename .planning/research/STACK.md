# Stack Research

**Domain:** Self-hosted personal finance web app for couples
**Researched:** 2026-03-09
**Confidence:** MEDIUM-HIGH (core stack verified, some library versions need validation at install time)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Java | 21 LTS | Runtime | Non-negotiable constraint. Virtual threads, records, sealed classes, pattern matching. Latest LTS with broad ecosystem support. |
| Spring Boot | 3.5.11 | Backend framework | Latest stable 3.5.x (Feb 2026). Use 3.5 over 4.0 -- Boot 4.0 requires Jakarta EE 11, Jackson 3.x, and modular starters which add migration complexity with no benefit for a greenfield learning project targeting Java 21. Boot 3.5 has first-class Java 21 support including virtual threads. EOL 2026-06-30, giving 3+ months runway, and migration to 4.0 is straightforward when ready. |
| PostgreSQL | 16 | Database | Non-negotiable constraint. Mature, excellent JSONB support for conflict_data/alert_thresholds, robust indexing. |
| Svelte | 5.53+ | UI framework | Non-negotiable constraint. Runes ($state, $derived, $effect) replace stores, fine-grained reactivity, smaller bundles. |
| SvelteKit | 2.53+ | App framework | Non-negotiable constraint. File-based routing, SSR, form actions, load functions. Excellent PWA story. |
| TypeScript | 5.7+ | Type safety | Non-negotiable constraint. Strict mode for financial data integrity. |
| Tailwind CSS | 4.2 | Styling | Non-negotiable constraint. CSS-native config in v4 (no tailwind.config.js needed), 5x faster builds, @property support, cascade layers. Breaking change from v3 -- use v4 from the start. |

### Backend Libraries

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| spring-boot-starter-web | 3.5.11 | REST API | Core Spring MVC with embedded Tomcat. Virtual threads via `spring.threads.virtual.enabled=true`. | HIGH |
| spring-boot-starter-data-jpa | 3.5.11 | Persistence | Hibernate 6.6+ with Java records support, optimistic locking via @Version. | HIGH |
| spring-boot-starter-security | 3.5.11 | Security | Spring Security 6.4+. Use built-in OAuth2 Resource Server JWT support (NimbusJwtDecoder/NimbusJwtEncoder) for decoding; JJWT for token generation. | HIGH |
| spring-boot-starter-validation | 3.5.11 | Input validation | Jakarta Bean Validation 3.0. Records + @Valid for request DTOs. | HIGH |
| spring-boot-starter-actuator | 3.5.11 | Monitoring | Health checks, metrics endpoints. Custom Plaid health indicator. | HIGH |
| spring-boot-starter-cache | 3.5.11 | Caching | ConcurrentMapCacheManager for 2-user scenario. No Redis needed at MVP. | HIGH |
| jjwt-api / jjwt-impl / jjwt-jackson | 0.12.6 | JWT creation | Mature JWT library. Use 0.12.6 (stable) over 0.13.0 (newer but less battle-tested). jjwt-impl and jjwt-jackson as runtime scope. Spring Security's Nimbus handles decoding, JJWT handles generation. | MEDIUM |
| plaid-java | 39.1.0 | Banking integration | Official Plaid SDK. Uses Retrofit/OkHttp under the hood. Frequent releases (API-version-driven). Pin to latest at project start. | MEDIUM |
| liquibase-core | 4.33.0 | DB migrations | Managed by Spring Boot BOM. Use YAML changelogs. Avoid versions 4.31.0 (Snowflake CVE) and ensure compatibility with Boot 3.5.9+ (earlier had regression). | HIGH |
| jackson-databind | (managed) | JSON serialization | Managed by Spring Boot BOM (Jackson 2.18+). Configure JavaTimeModule for LocalDate/Instant. Do NOT upgrade to Jackson 3.x -- that's Boot 4.0 territory. | HIGH |
| springdoc-openapi-starter-webmvc-ui | 2.8+ | API documentation | OpenAPI 3.1 spec generation + Swagger UI. Use springdoc (not springfox -- springfox is dead). | MEDIUM |

### Frontend Libraries

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| shadcn-svelte | 1.0.9+ | UI component system | CLI-generated components using Bits UI + Tailwind v4. You own the code (copy-paste model), full control over styling. Best fit for Tailwind + Svelte 5. Includes form components, dialogs, dropdowns, tables, toasts. | HIGH |
| bits-ui | 2.15+ | Headless primitives | Underlying library for shadcn-svelte. Svelte 5 native, accessible, unstyled. Auto-installed by shadcn-svelte CLI. | HIGH |
| layerchart | next (2.x) | Charts/visualizations | Svelte 5 native, composable SVG primitives, D3-powered. Area, Bar, Pie, time-series. Install via `layerchart@next` for Svelte 5 support. Best Svelte-native charting option for financial dashboards. | MEDIUM |
| d3-scale | 4.0+ | Scale calculations | Required peer dependency for LayerChart. Only import what you need (tree-shakeable). | HIGH |
| @vite-pwa/sveltekit | 0.7+ | PWA support | Zero-config PWA plugin for SvelteKit. Workbox-powered service worker generation. Handles manifest, icons, cache strategies. | MEDIUM |
| dexie | 4.0+ | IndexedDB wrapper | Best IndexedDB library for offline-first. liveQuery() for reactive Svelte stores. Structured schema for transactions/sync queue. Svelte 5 compatible via liveQuery integration. | MEDIUM |
| mode-watcher | 0.5+ | Theme switching | Light/dark mode with system detection. Used by shadcn-svelte. | HIGH |
| svelte-sonner | 0.3+ | Toast notifications | Svelte 5 port of Sonner. Used by shadcn-svelte for notifications. Budget alerts, sync status. | HIGH |
| @lucide/svelte | latest | Icons | Tree-shakeable SVG icons. Used by shadcn-svelte. Replaces lucide-svelte (deprecated). | HIGH |
| formsnap | 2.0+ | Form handling | Superforms + shadcn-svelte integration. Type-safe form validation with Zod. | MEDIUM |
| sveltekit-superforms | 2.0+ | Server-side forms | Type-safe form actions with validation. Works with SvelteKit load/actions pattern. | MEDIUM |
| zod | 3.24+ | Schema validation | Runtime type validation for forms. Shared validation between client and server-side. | HIGH |

### Database Extensions (PostgreSQL)

| Extension | Purpose | Why Recommended | Confidence |
|-----------|---------|-----------------|------------|
| pgcrypto | Encryption functions | AES-256 encryption for Plaid tokens at rest. Built-in, trusted extension. Enable with `CREATE EXTENSION pgcrypto`. Can use `pgp_sym_encrypt`/`pgp_sym_decrypt` for token storage. | HIGH |
| pg_trgm | Fuzzy text search | Trigram-based similarity search for transaction descriptions, merchant name matching during deduplication. | MEDIUM |
| uuid-ossp | UUID generation | Generate UUIDs server-side if needed. Alternative: use Java UUID.randomUUID() (preferred for this project). | LOW (optional) |

### Development & Testing Tools

| Tool | Version | Purpose | Notes | Confidence |
|------|---------|---------|-------|------------|
| Vitest | 4.0+ | Frontend unit/component tests | SvelteKit's recommended test runner. Vite-native, fast. Use with @testing-library/svelte. | HIGH |
| @testing-library/svelte | 5.0+ | Component testing | DOM testing utilities. Renders Svelte components for assertions. | HIGH |
| axe-core | 4.10+ | Accessibility testing | WCAG 2.2 AA automated audits. Integrate via vitest-axe. | HIGH |
| Playwright | 1.58+ | E2E testing | Cross-browser E2E tests. Login flows, transaction entry, dashboard. Use @playwright/test. | HIGH |
| Testcontainers | 2.0+ | Integration testing | Spin up real PostgreSQL in Docker for backend tests. Use Spring Boot's @ServiceConnection (no annotations needed). Breaking: v2 renamed modules with testcontainers- prefix. | HIGH |
| JUnit 5 | 5.11+ | Backend unit testing | Managed by Spring Boot BOM. Use @ParameterizedTest for financial calculations. | HIGH |
| Mockito | 5.14+ | Mocking | Managed by Spring Boot BOM. Mock Plaid API, external services. | HIGH |
| ArchUnit | 1.4.1 | Architecture enforcement | Test vertical slice isolation: features don't import each other, only shared/. JUnit 5 integration. | HIGH |
| SpotBugs | 4.8+ | Static analysis | Bytecode analysis for bug patterns. Maven plugin. | MEDIUM |
| PIT (pitest) | 1.17+ | Mutation testing | Verify test quality. Target > 70% mutation kill rate. Maven plugin. | MEDIUM |

### Build & Quality Tools

| Tool | Purpose | Notes | Confidence |
|------|---------|-------|------------|
| Maven 3.9+ | Backend build | Use Maven Wrapper (mvnw). Multi-module not needed for MVP -- single module with vertical slices. | HIGH |
| pnpm 9+ | Frontend package manager | Faster, stricter than npm. Workspace support for monorepo. | HIGH |
| Checkstyle | Java code style | Google style or custom. Maven plugin. | HIGH |
| ESLint 9+ | JS/TS linting | Flat config format. svelte-eslint-parser for .svelte files. | HIGH |
| Prettier 3+ | Code formatting | With prettier-plugin-svelte and prettier-plugin-tailwindcss. | HIGH |
| svelte-check | Type checking | Full TypeScript validation for Svelte files. Run in CI. | HIGH |
| husky 9+ | Git hooks | Pre-commit: lint-staged for frontend formatting. | HIGH |
| lint-staged 15+ | Staged file processing | Run Prettier/ESLint only on staged files. | HIGH |

### Infrastructure

| Technology | Version | Purpose | Notes | Confidence |
|------------|---------|---------|-------|------------|
| Docker | 24+ | Containerization | Multi-stage builds. backend (Eclipse Temurin 21-jre), frontend (Node 22-alpine + nginx), db (postgres:16-alpine). | HIGH |
| Docker Compose | 2.20+ | Orchestration | Profiles: dev (hot-reload), prod (optimized images). | HIGH |
| Caddy | 2.8+ | Reverse proxy | Already on server. Automatic HTTPS via Let's Encrypt. Caddyfile config. | HIGH |
| GitHub Actions | - | CI/CD | Progressive pipeline: build+test+lint first, SonarQube/SpotBugs/PIT added later. | HIGH |
| SonarQube | 10+ (Community) | Code quality | Quality gate: 80% coverage on new code, A ratings. Docker deployment. | MEDIUM |

## Version Decision: Spring Boot 3.5 vs 4.0

**Recommendation: Start with Spring Boot 3.5.11.**

| Factor | Boot 3.5.x | Boot 4.0.x |
|--------|-----------|-----------|
| Java baseline | 17 (supports 21 natively) | 17 (supports 25) |
| Jakarta EE | 10 | 11 (breaking changes) |
| Jackson | 2.x | 3.x (breaking changes) |
| Module system | Traditional starters | New modular starters |
| Maturity | 11 patch releases, battle-tested | 3 patch releases, newer |
| EOL | 2026-06-30 | 2027-11 (est.) |
| Migration risk | None (greenfield) | Higher complexity for learning project |

**Rationale:** The project is a learning exercise. Boot 3.5 is stable, well-documented with abundant tutorials, and fully supports Java 21 features (virtual threads, records, sealed classes). Boot 4.0's breaking changes (Jakarta EE 11, Jackson 3.x, modular starters) add friction without meaningful benefit. Plan to migrate to 4.0 after MVP when the codebase is stable and Boot 4.0 has more patch releases.

## Version Decision: Tailwind v3 vs v4

**Recommendation: Use Tailwind CSS v4.2 from the start.**

shadcn-svelte@1.0+ requires Tailwind v4. Since this is greenfield, there is no migration burden. Tailwind v4 is CSS-native (no JS config file), faster, and the ecosystem has adopted it.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| shadcn-svelte + Bits UI | Flowbite-Svelte | If you want more pre-built components out of the box with less customization control. Flowbite is heavier and less Svelte 5 native. |
| shadcn-svelte + Bits UI | Skeleton UI | If you want a full design system with Figma kit. More opinionated, harder to customize deeply. |
| LayerChart | Chart.js (direct) | If you need a quick chart without Svelte integration. svelte-chartjs wrapper is unmaintained for Svelte 5. Direct Chart.js integration is possible but loses Svelte reactivity. |
| LayerChart | Apache ECharts | If you need extremely complex visualizations (not needed for MVP). Heavier, not Svelte-native. |
| Dexie | idb-keyval | If you only need simple key-value storage. Dexie is better for structured data (transactions, sync queues) with querying and live queries. |
| JJWT | Nimbus JOSE only | If you want to use only Spring Security's built-in JWT support. JJWT has a more fluent API for token creation. Either works. |
| Liquibase | Flyway | If you prefer SQL-only migrations. Liquibase offers YAML/XML changelogs with rollback support. Spring Boot supports both equally. Personal preference. |
| pnpm | npm | If you want zero extra setup. pnpm is faster and stricter about dependency hoisting which prevents phantom dependencies. |
| Maven | Gradle | If you prefer Groovy/Kotlin DSL. Maven is more common in Spring Boot tutorials and has better Spring Boot BOM support. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| svelte-chartjs | Unmaintained, no Svelte 5 support | LayerChart (Svelte 5 native) |
| lucide-svelte | Deprecated in favor of @lucide/svelte | @lucide/svelte |
| Melt UI | Superseded by Bits UI (same author, Bits UI is the evolution) | Bits UI (via shadcn-svelte) |
| springfox | Dead project, no Spring Boot 3 support | springdoc-openapi |
| Spring Boot 4.0 (at start) | Jakarta EE 11 + Jackson 3.x breaking changes, limited tutorials, 3 months old | Spring Boot 3.5.11 |
| Redis | Unnecessary for 2 users. Adds infra complexity. | Spring ConcurrentMapCacheManager |
| React / Next.js | Not the chosen stack. Svelte 5 has better DX for this scale. | Svelte 5 + SvelteKit 2 |
| Zustand / TanStack Query | React patterns. Svelte 5 runes ($state, $derived) replace external state management. | Svelte 5 runes |
| Lombok | Java 21 records eliminate most Lombok use cases. Records for DTOs, sealed interfaces for types. | Java 21 records |
| Jackson 3.x | Only needed for Boot 4.0. Incompatible with Boot 3.5. | Jackson 2.18+ (managed by Boot BOM) |
| Testcontainers 1.x | Replaced by 2.0 with renamed modules and improved Spring Boot integration. | Testcontainers 2.0+ |

## Stack Patterns by Variant

**For JWT Authentication:**
- Use Spring Security's built-in OAuth2 Resource Server for JWT validation (NimbusJwtDecoder)
- Use JJWT (0.12.6) for JWT creation with a fluent builder API
- Store JWT in HttpOnly cookies (not localStorage) to prevent XSS
- Refresh tokens with rotation stored in PostgreSQL

**For Plaid Integration:**
- Wrap plaid-java SDK in a dedicated Spring `@Service`
- Encrypt access tokens with AES-256 using pgcrypto at the DB level OR Java-side encryption with Spring's `Encryptors.standard()`
- Use `@Scheduled` for periodic sync, `@Async` with virtual threads for webhook processing
- Circuit breaker pattern: fallback to manual entry when Plaid is down

**For PWA Offline-First:**
- @vite-pwa/sveltekit for service worker generation and manifest
- Dexie for structured IndexedDB storage (transactions, sync queue)
- Cache-first for static assets, network-first for API calls
- Background Sync API for deferred transaction submission
- Version-stamped sync protocol for conflict detection

**For Financial Calculations:**
- Always use `BigDecimal` in Java (never double/float for money)
- DECIMAL(19,4) in PostgreSQL for amounts
- Money value object in shared/domain/ with currency-aware arithmetic
- Rounding: HALF_UP for display, HALF_EVEN (banker's rounding) for internal calculations

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Spring Boot 3.5.11 | Java 21 LTS | Virtual threads via config flag |
| Spring Boot 3.5.11 | Liquibase 4.33 | Managed by BOM; override if needed |
| Spring Boot 3.5.11 | Testcontainers 2.0+ | @ServiceConnection auto-config |
| Spring Boot 3.5.11 | Hibernate 6.6+ | Managed by BOM |
| Svelte 5.53+ | SvelteKit 2.53+ | Peer dependency |
| Svelte 5.53+ | Tailwind CSS 4.2 | Via @tailwindcss/vite plugin |
| shadcn-svelte 1.0+ | Bits UI 2.x | Auto-installed dependency |
| shadcn-svelte 1.0+ | Tailwind CSS 4.x | Required (v3 not supported) |
| LayerChart next (2.x) | Svelte 5 | Must use @next tag on npm |
| LayerChart next | d3-scale 4+ | Required peer dependency |
| @vite-pwa/sveltekit 0.7+ | SvelteKit 2.x | Supported |
| Dexie 4.0+ | Svelte 5 | liveQuery works but needs wrapper for Svelte 5 reactivity |
| Vitest 4.0+ | Vite 6+ | SvelteKit uses Vite under the hood |
| Playwright 1.58+ | All browsers | Standalone, no Vite dependency |

## Installation

### Backend (pom.xml)

```xml
<!-- Parent -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.11</version>
</parent>

<properties>
    <java.version>21</java.version>
    <jjwt.version>0.12.6</jjwt.version>
    <plaid-java.version>39.1.0</plaid-java.version>
    <archunit.version>1.4.1</archunit.version>
    <springdoc.version>2.8.5</springdoc.version>
</properties>

<dependencies>
    <!-- Core -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>

    <!-- Database -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
    </dependency>

    <!-- JWT -->
    <dependency>
        <groupId>io.jsonwebtoken</groupId>
        <artifactId>jjwt-api</artifactId>
        <version>${jjwt.version}</version>
    </dependency>
    <dependency>
        <groupId>io.jsonwebtoken</groupId>
        <artifactId>jjwt-impl</artifactId>
        <version>${jjwt.version}</version>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>io.jsonwebtoken</groupId>
        <artifactId>jjwt-jackson</artifactId>
        <version>${jjwt.version}</version>
        <scope>runtime</scope>
    </dependency>

    <!-- Plaid -->
    <dependency>
        <groupId>com.plaid</groupId>
        <artifactId>plaid-java</artifactId>
        <version>${plaid-java.version}</version>
    </dependency>

    <!-- API Docs -->
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>

    <!-- Test -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>com.tngtech.archunit</groupId>
        <artifactId>archunit-junit5</artifactId>
        <version>${archunit.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### Frontend (package.json dependencies)

```bash
# Core (installed via create-svelte)
# svelte, @sveltejs/kit, vite, typescript already included

# Tailwind CSS v4
pnpm add -D @tailwindcss/vite tailwindcss

# UI Components (shadcn-svelte installs bits-ui, lucide, etc.)
pnpm dlx shadcn-svelte@latest init

# Charts
pnpm add layerchart@next d3-scale

# PWA
pnpm add -D @vite-pwa/sveltekit

# Offline storage
pnpm add dexie

# Forms
pnpm add sveltekit-superforms zod formsnap

# Testing
pnpm add -D vitest @testing-library/svelte jsdom axe-core vitest-axe
pnpm add -D @playwright/test

# Quality
pnpm add -D eslint prettier prettier-plugin-svelte prettier-plugin-tailwindcss
pnpm add -D svelte-check
pnpm add -D husky lint-staged
```

## Sources

- [Spring Boot releases](https://github.com/spring-projects/spring-boot/releases) -- Boot 3.5.11 / 4.0.3 version confirmation (HIGH)
- [Spring Boot EOL dates](https://endoflife.date/spring-boot) -- Support lifecycle (HIGH)
- [Spring Boot 4.0 migration guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) -- Breaking changes analysis (HIGH)
- [shadcn-svelte](https://shadcn-svelte.com/) -- v1.0.9, Svelte 5 + Tailwind v4 support (HIGH)
- [Bits UI](https://bits-ui.com/) -- v2.15+, Svelte 5 headless components (HIGH)
- [LayerChart](https://next.layerchart.com/) -- Svelte 5 charting, @next tag (MEDIUM)
- [@vite-pwa/sveltekit](https://github.com/vite-pwa/sveltekit) -- PWA plugin for SvelteKit (MEDIUM)
- [Dexie.js Svelte docs](https://dexie.org/docs/Tutorial/Svelte) -- v4.0 Svelte integration (MEDIUM)
- [plaid-java Maven Central](https://mvnrepository.com/artifact/com.plaid/plaid-java) -- v39.1.0 (MEDIUM)
- [JJWT GitHub](https://github.com/jwtk/jjwt) -- v0.12.6 / v0.13.0 (HIGH)
- [ArchUnit](https://www.archunit.org/) -- v1.4.1 (HIGH)
- [Testcontainers releases](https://github.com/testcontainers/testcontainers-java/releases) -- v2.0+ (MEDIUM)
- [Vitest npm](https://www.npmjs.com/package/vitest) -- v4.0.18 (MEDIUM)
- [Playwright releases](https://github.com/microsoft/playwright/releases) -- v1.58.2 (HIGH)
- [Tailwind CSS v4](https://tailwindcss.com/blog/tailwindcss-v4) -- v4.2 features (HIGH)
- [Svelte npm](https://www.npmjs.com/package/svelte) -- v5.53.7 (HIGH)
- [SvelteKit npm](https://www.npmjs.com/package/@sveltejs/kit) -- v2.53.4 (HIGH)
- [PostgreSQL pgcrypto docs](https://www.postgresql.org/docs/current/pgcrypto.html) -- Extension capabilities (HIGH)
- [Liquibase releases](https://github.com/liquibase/liquibase/releases) -- v4.33.0 (MEDIUM)
- [Spring Security JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) -- Built-in Nimbus support (HIGH)

---
*Stack research for: Self-hosted personal finance web app (Java 21 / Spring Boot / Svelte 5)*
*Researched: 2026-03-09*
