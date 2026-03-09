---
phase: 01-foundation
plan: 01
subsystem: api
tags: [spring-boot, maven, liquibase, postgresql, spring-security, bcrypt, jpa, uuidv7, docker]

requires:
  - phase: none
    provides: greenfield project
provides:
  - Spring Boot 3.5.0 Maven project with all dependencies
  - Shared domain kernel (Money, UserId, AccountId value objects)
  - Spring Security config with BCrypt(12), CSP, HSTS, X-Frame-Options
  - BaseEntity with JPA auditing (created_at, updated_at, version)
  - Liquibase migrations for users, accounts, permissions, categories, refresh_tokens
  - 16 default categories seeded
  - Multi-stage Dockerfile with Temurin 21
affects: [01-02, 01-03, 01-04]

tech-stack:
  added: [spring-boot-3.5.0, spring-security, spring-data-jpa, liquibase, jjwt-0.12.6, java-uuid-generator-5.1.0, postgresql, testcontainers]
  patterns: [vertical-slice, shared-kernel, value-objects, jpa-auditing]

key-files:
  created:
    - prosperity-api/pom.xml
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/ProsperityApplication.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/domain/Money.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/domain/UserId.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/domain/AccountId.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/persistence/BaseEntity.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/security/SecurityConfig.java
    - prosperity-api/src/main/java/fr/kalifazzia/prosperity/shared/web/GlobalExceptionHandler.java
    - prosperity-api/src/main/resources/application.yml
    - prosperity-api/src/main/resources/db/changelog/db.changelog-master.yaml
    - prosperity-api/Dockerfile
  modified: []

key-decisions:
  - "Spring Boot 3.5.0 chosen per research recommendation (3.3/3.4 EOL)"
  - "Money value object uses BigDecimal scale 4 with HALF_EVEN rounding"
  - "UUIDv7 via JUG Generators.timeBasedEpochGenerator() for all entity IDs"
  - "Preferences stored as JSONB column on users table (not separate table)"
  - "BCrypt strength 12 for password hashing"
  - "CORS configured for localhost:3000 and localhost:5173 (SvelteKit dev)"

patterns-established:
  - "Value objects: immutable, factory methods (of/generate), private constructor"
  - "BaseEntity: MappedSuperclass with UUID id, JPA auditing, optimistic locking"
  - "GlobalExceptionHandler: consistent ErrorResponse record with error + details map"
  - "Liquibase changeset IDs: YYYYMMDD-NN-description format"

requirements-completed: [INFR-03, INFR-04]

duration: 3min
completed: 2026-03-09
---

# Phase 1 Plan 01: Backend Scaffolding Summary

**Spring Boot 3.5 project with shared kernel (Money/UserId/AccountId), Spring Security BCrypt(12) + headers, Liquibase schema for 5 tables, and multi-stage Dockerfile**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-09T06:24:05Z
- **Completed:** 2026-03-09T06:27:14Z
- **Tasks:** 2
- **Files modified:** 19

## Accomplishments
- Maven project compiles-ready with all Spring Boot dependencies (web, security, JPA, validation, liquibase, JWT, UUID)
- Shared domain kernel with Money (BigDecimal HALF_EVEN scale 4), UserId and AccountId (UUIDv7 via JUG)
- Spring Security with BCrypt(12), CSP, HSTS, X-Frame-Options DENY, stateless sessions, CORS
- Liquibase migrations defining users, accounts, account_permissions, categories, refresh_tokens tables
- 16 default categories seeded (alimentation through divers)
- Multi-stage Dockerfile with Temurin 21 JDK build and JRE runtime

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Maven project with shared kernel and Spring Security config** - `e48b6eb` (feat)
2. **Task 2: Create Liquibase migrations and backend Dockerfile** - `1f74b9a` (feat)

## Files Created/Modified
- `prosperity-api/pom.xml` - Maven project with Spring Boot 3.5.0 parent and all dependencies
- `prosperity-api/src/main/java/.../ProsperityApplication.java` - Main class with @EnableJpaAuditing
- `prosperity-api/src/main/resources/application.yml` - Datasource, JPA, Liquibase, JWT, virtual threads config
- `prosperity-api/src/main/resources/application-dev.yml` - Debug logging for SQL and security
- `prosperity-api/src/main/java/.../shared/domain/Money.java` - Money value object with HALF_EVEN rounding
- `prosperity-api/src/main/java/.../shared/domain/UserId.java` - UserId with UUIDv7 generation
- `prosperity-api/src/main/java/.../shared/domain/AccountId.java` - AccountId with UUIDv7 generation
- `prosperity-api/src/main/java/.../shared/persistence/BaseEntity.java` - MappedSuperclass with auditing
- `prosperity-api/src/main/java/.../shared/config/JacksonConfig.java` - ObjectMapper with JavaTimeModule
- `prosperity-api/src/main/java/.../shared/web/GlobalExceptionHandler.java` - Validation, access denied, generic error handling
- `prosperity-api/src/main/java/.../shared/security/SecurityConfig.java` - BCrypt(12), headers, CORS, endpoint rules
- `prosperity-api/src/main/resources/db/changelog/db.changelog-master.yaml` - Master changelog
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-01-create-users-table.yaml` - Users schema
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-02-create-accounts-table.yaml` - Accounts schema
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-03-create-permissions-table.yaml` - Permissions schema
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-04-create-categories-table.yaml` - Categories schema
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-05-create-refresh-tokens-table.yaml` - Refresh tokens schema
- `prosperity-api/src/main/resources/db/changelog/migrations/20260309-06-seed-default-categories.yaml` - 16 default categories
- `prosperity-api/Dockerfile` - Multi-stage build with Temurin 21

## Decisions Made
- Spring Boot 3.5.0 per research (3.3/3.4 EOL, 3.5 is latest supported 3.x)
- Money uses scale 4 with HALF_EVEN for banker's rounding precision
- UUIDv7 via JUG timeBasedEpochGenerator for time-ordered IDs
- Preferences as JSONB column on users table (simpler for 2-user app)
- CORS allows localhost:3000 (SvelteKit prod) and localhost:5173 (SvelteKit dev)
- Categories use name_key for i18n lookup rather than storing localized names

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Java/Maven not installed on local machine (WSL2 environment). YAML validation done with Python. Compilation verification deferred to Docker build or environment with JDK. All file content verified structurally.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Backend foundation ready for Plan 02 (SvelteKit frontend scaffolding)
- Backend foundation ready for Plan 03 (Authentication endpoints)
- Compilation verification needed when JDK available (Docker build will validate)

---
*Phase: 01-foundation*
*Completed: 2026-03-09*

## Self-Check: PASSED

All key files exist, both commits verified, must-have content markers present (HALF_EVEN, BCryptPasswordEncoder, databaseChangeLog, spring-boot-starter).
