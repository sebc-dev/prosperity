# Phase 1: Project Foundation - Research

**Researched:** 2026-03-28
**Domain:** Spring Boot 4.0.x + Angular 21 project scaffolding, quality gates, CI pipeline
**Confidence:** HIGH

## Summary

Phase 1 bootstraps the entire Prosperity project from scratch: Spring Boot 4.0.x backend with domain model, Angular 21 frontend shell, Docker Compose infrastructure, Flyway migrations, and a comprehensive quality gate pipeline. The codebase is currently empty (only docs exist), so all scaffolding must be created.

The primary technical risks are: (1) Error Prone requires specific JVM flags for Java 21 via `.mvn/jvm.config`, (2) Spotless Maven Plugin is the standard way to integrate google-java-format (no standalone Maven plugin exists), and (3) the OWASP dependency-check plugin can be slow on first run (downloads NVD database). The frontend scaffolding is straightforward -- `ng new` + PrimeNG + Tailwind v4 is well-documented.

**Primary recommendation:** Use Spotless Maven Plugin for google-java-format integration, Lefthook for pre-commit hooks (language-agnostic, faster, single YAML config), and bind all quality gates to Maven `verify` phase so `./mvnw verify` runs everything.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Architecture layered par feature (Controller/Service/Repository), pas d'hexagonal. Package-by-feature : account/, transaction/, envelope/, banking/, auth/, admin/, shared/. Voir ADR-0002.
- **D-02:** Module Maven unique. ArchUnit valide les regles de dependance entre packages (pas d'import circulaire, banking/ abstrait via interface).
- **D-03:** Abstraction strategique uniquement sur le connecteur bancaire (interface BankConnector). Pas de ports/adapters generalises.
- **D-04:** Entites JPA completes en Phase 1 : Account, Transaction, Envelope, User, Category, avec tous les champs et relations.
- **D-05:** Value Objects : Money (BigDecimal, precision 2, pas de floating-point), TransactionState (enum : MANUAL_UNMATCHED, IMPORTED_UNMATCHED, MATCHED).
- **D-06:** Repositories Spring Data JPA pour chaque entite. Migrations Flyway completes pour le schema initial.
- **D-07:** Tests unitaires sur les regles metier : Money n'accepte pas de floating-point, Transaction states valides, Envelope rollover/overspend.
- **D-08:** JaCoCo en mode reporting uniquement, pas de seuil bloquant. Outil de visibilite, pas de gate.
- **D-09:** Error Prone (Google) pour l'analyse statique Java. Compile-time checker, Apache 2.0, peu de faux positifs.
- **D-10:** Checkstyle pour le lint Java (imports inutilises, conventions). google-java-format pour le formatage.
- **D-11:** Detection code mort : Checkstyle (imports) + warnings compilateur. Pas d'outil dedie supplementaire.
- **D-12:** OWASP dependency-check pour le scan de securite des dependances.
- **D-13:** Pre-commit hooks (Husky ou lefthook) : lint + format checks avant chaque commit.
- **D-14:** Angular minimal fonctionnel : ng new + PrimeNG 21.x + Tailwind v4 + tailwindcss-primeui + ESLint + Prettier. Page d'accueil vide qui charge.
- **D-15:** Pas de routing, layout shell ou theme personnalise en Phase 1. Ajoutes en Phase 2 (auth) quand necessaire.

### Claude's Discretion
- Configuration Docker Compose exacte (volumes, networks, healthchecks)
- Structure CI pipeline GitHub Actions (nombre de jobs, parallelisation)
- Choix entre Husky et lefthook pour les pre-commit hooks
- Configuration exacte Error Prone (quels checks activer)
- Nommage des migrations Flyway

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFR-02 | Docker Compose fonctionnel (Caddy + Spring Boot + PostgreSQL) | Docker Compose v2 with 3 services, Caddy 2.11.x config, healthchecks |
| INFR-04 | Linting : Checkstyle pour Java, ESLint pour Angular, execution locale et CI | Checkstyle 13.3.0 via maven-checkstyle-plugin 3.6.0, @angular-eslint/schematics |
| INFR-05 | Formatage automatique : google-java-format pour Java, Prettier pour frontend | Spotless Maven Plugin 2.43.x + google-java-format 1.35.0, Prettier via pnpm |
| INFR-06 | Analyse statique integree avec quality gate locale et CI | Error Prone 2.48.0 as compile-time checker (replaces SonarQube per D-09) |
| INFR-07 | Detection de code mort (Java + Angular) integree au pipeline CI | Checkstyle unused imports + `-Xlint:all` compiler warnings (per D-11) |
| INFR-08 | Couverture de tests (reporting) | JaCoCo 0.8.15 in report-only mode (per D-08, overrides INFR-08 threshold text) |
| INFR-09 | Scan de securite des dependances (OWASP dependency-check) | OWASP dependency-check 12.2.0 Maven plugin |
| INFR-10 | Pre-commit hooks executant lint, format, et checks avant chaque commit | Lefthook recommended (language-agnostic, parallel, single YAML) |
</phase_requirements>

## Requirement Conflict Note

**INFR-08 vs D-08:** The requirement INFR-08 says "couverture de tests enforcee avec seuils minimum (echec build si non atteint)" but user decision D-08 explicitly says "JaCoCo en mode reporting uniquement, pas de seuil bloquant." **The user decision D-08 takes precedence.** JaCoCo generates reports but does NOT fail the build on coverage thresholds.

## Standard Stack

### Core (Backend)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Boot Starter Parent | 4.0.5 | Parent POM, dependency management | Latest stable Spring Boot 4.0.x |
| spring-boot-starter-web | 4.0.5 (via parent) | REST API | Embedded Tomcat, Spring MVC |
| spring-boot-starter-data-jpa | 4.0.5 (via parent) | ORM | Hibernate 7, Spring Data JPA 4.0.x |
| spring-boot-starter-validation | 4.0.5 (via parent) | Bean validation | Jakarta Validation |
| spring-boot-starter-actuator | 4.0.5 (via parent) | Health endpoint | /api/health for Docker healthchecks |
| Flyway | 11.x (via Boot) | DB migrations | Auto-configured by Boot, Apache 2.0 |
| PostgreSQL JDBC | 42.x (via Boot) | DB driver | Managed by Boot BOM |

### Core (Frontend)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Angular CLI | 21.x | Project scaffold | `ng new` creates standalone component app |
| PrimeNG | 21.x | UI components | Finance-oriented components |
| Tailwind CSS | v4 | Utility CSS | Native Angular CLI integration |
| tailwindcss-primeui | latest | PrimeNG + Tailwind bridge | Official PrimeTek plugin, CSS version for Tailwind v4 |

### Quality Gate Tools
| Tool | Version | Purpose | Integration |
|------|---------|---------|-------------|
| Error Prone | 2.48.0 | Static analysis (compile-time) | maven-compiler-plugin annotationProcessorPaths |
| Checkstyle | 13.3.0 | Java lint (conventions, unused imports) | maven-checkstyle-plugin 3.6.0 with runtime override |
| Spotless | 2.43.x | google-java-format enforcement | spotless-maven-plugin, `check` goal bound to verify |
| google-java-format | 1.35.0 | Java code formatting | Via Spotless plugin |
| JaCoCo | 0.8.15 | Coverage reporting (no threshold) | jacoco-maven-plugin, prepare-agent + report goals |
| OWASP dependency-check | 12.2.0 | Dependency vulnerability scan | dependency-check-maven, bound to verify |
| ESLint | via @angular-eslint | Angular lint | `ng lint` / `pnpm lint` |
| Prettier | latest | Frontend formatting | `pnpm format:check` |
| Lefthook | latest (npm) | Pre-commit hooks | lefthook.yml at project root |

### Infrastructure
| Tool | Version | Purpose |
|------|---------|---------|
| Docker Compose | v2 | 3 services: db, backend, caddy |
| PostgreSQL | 17-alpine | Database container |
| Caddy | 2.11.x | Reverse proxy, HTTPS auto |
| Temurin JDK | 21 | Backend runtime |
| Node.js | 22 LTS | Frontend tooling |

### Test Libraries (via spring-boot-starter-test)
| Library | Version | Purpose |
|---------|---------|---------|
| JUnit 5/6 | via Boot | Test framework |
| AssertJ | 3.x via Boot | Fluent assertions |
| ArchUnit | 1.x | Architecture rule tests |

## Architecture Patterns

### Recommended Project Structure
```
prosperity/
  backend/                        # OR root-level Maven project
    .mvn/
      jvm.config                  # Error Prone JVM flags for Java 21
    src/
      main/
        java/com/prosperity/
          ProsperityApplication.java
          account/
            Account.java          # JPA entity
            AccountRepository.java
          transaction/
            Transaction.java
            TransactionRepository.java
          envelope/
            Envelope.java
            EnvelopeRepository.java
          category/
            Category.java
            CategoryRepository.java
          auth/
            User.java
            UserRepository.java
          banking/
            BankConnector.java    # Interface (abstraction strategique)
            BankTransaction.java
          shared/
            Money.java            # Value Object (BigDecimal)
            TransactionState.java # Enum
            config/
        resources/
          application.yml
          db/migration/
            V001__create_users.sql
            V002__create_bank_accounts.sql
            V003__create_account_access.sql
            V004__create_categories.sql
            V005__create_transactions.sql
            V006__create_envelopes.sql
      test/
        java/com/prosperity/
          shared/
            MoneyTest.java
            TransactionStateTest.java
          envelope/
            EnvelopeTest.java
          architecture/
            ArchitectureTest.java
    pom.xml
    mvnw / mvnw.cmd
  frontend/                       # Angular project
    src/
      app/
        app.component.ts
        app.config.ts
      styles.css                  # Tailwind + PrimeNG imports
    angular.json
    package.json
    .eslintrc.json
    .prettierrc
  docker-compose.yml
  Caddyfile
  lefthook.yml
  .github/
    workflows/
      ci.yml
```

### Pattern 1: Money Value Object
**What:** Immutable value object wrapping BigDecimal with fixed precision 2, EUR only.
**When to use:** All monetary amounts in the domain layer.
**Example:**
```java
// Money.java in shared/
public record Money(BigDecimal amount) {
    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        if (amount.scale() > 2) {
            throw new IllegalArgumentException("Money precision cannot exceed 2 decimal places");
        }
        amount = amount.setScale(2, RoundingMode.HALF_UP);
    }

    public static Money of(String value) {
        return new Money(new BigDecimal(value));
    }

    public static Money ofCents(long cents) {
        return new Money(BigDecimal.valueOf(cents, 2));
    }

    // REJECT floating-point: no of(double) factory method
    // DB mapping: amount stored as BIGINT cents, converted via AttributeConverter

    public Money add(Money other) {
        return new Money(this.amount.add(other.amount));
    }

    public Money subtract(Money other) {
        return new Money(this.amount.subtract(other.amount));
    }

    public long toCents() {
        return amount.movePointRight(2).longValueExact();
    }
}
```

### Pattern 2: JPA Entity with Value Object
**What:** JPA entities use `@Convert` for Money fields to store as BIGINT cents in DB.
**Example:**
```java
@Entity
@Table(name = "bank_accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(name = "account_type", nullable = false, length = 20)
    @Enumerated(EnumType.STRING)
    private AccountType accountType; // PERSONAL, SHARED

    @Column(name = "balance_cents", nullable = false)
    @Convert(converter = MoneyConverter.class)
    private Money balance;

    // ... timestamps, relations
}
```

### Pattern 3: Flyway Migration Naming
**What:** Versioned SQL migrations with zero-padded version numbers.
**Convention:** `V{NNN}__{description}.sql` in `src/main/resources/db/migration/`
**Example:** `V001__create_users.sql`, `V002__create_bank_accounts.sql`

### Anti-Patterns to Avoid
- **Floating-point Money:** Never use `double` or `float` for monetary amounts. Money value object enforces BigDecimal.
- **Hexagonal ports for single-impl:** Do NOT create port interfaces for repositories or controllers. Only BankConnector gets an interface (D-03).
- **Lombok on entities:** Use Java 21 records for DTOs/VOs, manual getters/setters for JPA entities (project convention: no Lombok).
- **Liquibase:** Explicitly forbidden. Use Flyway only (FSL license issue).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Java code formatting | Custom Maven exec plugin calling gjf | Spotless Maven Plugin + google-java-format | Spotless handles classpath, JVM args, and provides `check`/`apply` goals natively |
| Dependency vulnerability scan | Script parsing CVE databases | OWASP dependency-check Maven plugin | Maintained NVD integration, false-positive suppression, CVSS scoring |
| Pre-commit hooks | Custom .git/hooks scripts | Lefthook (via npm) | Parallel execution, YAML config, handles both Java and JS toolchains |
| Coverage reporting | Manual JaCoCo setup | spring-boot-starter-test + JaCoCo plugin | Boot auto-configures test infrastructure; JaCoCo `prepare-agent` + `report` is 10 lines of XML |
| Health endpoint | Custom /api/health controller | spring-boot-starter-actuator | Auto-configured, includes DB health, customizable |

## Common Pitfalls

### Pitfall 1: Error Prone Requires .mvn/jvm.config on Java 21
**What goes wrong:** Compilation fails with "cannot access internal API" errors when Error Prone tries to hook into javac.
**Why it happens:** Java 16+ enforces strong encapsulation of JDK internals. Error Prone needs `--add-exports` and `--add-opens` flags.
**How to avoid:** Create `.mvn/jvm.config` with the required flags before first build.
**Warning signs:** `IllegalAccessError` or `InaccessibleObjectException` during compilation.

### Pitfall 2: Spotless google-java-format Default Version Is Stale
**What goes wrong:** Spotless ships with an older default google-java-format (e.g., 1.28.0) that may not support latest Java features.
**Why it happens:** Spotless bundles a default version; it does not auto-update.
**How to avoid:** Explicitly set `<version>1.35.0</version>` in the Spotless `<googleJavaFormat>` config.
**Warning signs:** Formatting differences between IDE and CI.

### Pitfall 3: OWASP dependency-check First Run Is Very Slow
**What goes wrong:** First `mvn verify` takes 5-10+ minutes downloading the NVD database.
**Why it happens:** OWASP dependency-check downloads the full NVD JSON feed on first execution.
**How to avoid:** In CI, cache the `~/.dependency-check/` directory. Locally, run `mvn dependency-check:update-only` once. Consider setting `failBuildOnCVSS` threshold to avoid blocking on low-severity issues initially.
**Warning signs:** CI timeouts on first run.

### Pitfall 4: Checkstyle Default Config in Plugin vs Custom
**What goes wrong:** Using the plugin's default Checkstyle 9.3 instead of the latest 13.3.0 leads to missing checks and Java 21 parsing issues.
**Why it happens:** maven-checkstyle-plugin 3.6.0 defaults to Checkstyle 9.3 internally.
**How to avoid:** Override the Checkstyle version in the plugin dependency:
```xml
<plugin>
  <artifactId>maven-checkstyle-plugin</artifactId>
  <version>3.6.0</version>
  <dependencies>
    <dependency>
      <groupId>com.puppycrawl.tools</groupId>
      <artifactId>checkstyle</artifactId>
      <version>13.3.0</version>
    </dependency>
  </dependencies>
</plugin>
```
**Warning signs:** False positives or parsing errors on Java 21 syntax.

### Pitfall 5: Docker Not Available in WSL2
**What goes wrong:** `docker compose up -d` fails because Docker is not installed in this WSL2 environment.
**Why it happens:** Docker Desktop WSL2 integration is not enabled.
**How to avoid:** Ensure Docker Desktop is running on Windows and WSL2 integration is enabled for this distro. Alternatively, install Docker Engine directly in WSL2.
**Warning signs:** "command not found: docker" error.

### Pitfall 6: PrimeNG Tailwind v4 Requires CSS Plugin, Not JS Plugin
**What goes wrong:** PrimeNG styles don't apply or conflict with Tailwind.
**Why it happens:** `tailwindcss-primeui` has two versions: CSS version (for Tailwind v4) and JS version (for Tailwind v3). Using the wrong one breaks styling.
**How to avoid:** Import in `styles.css` after the Tailwind import: `@import "tailwindcss-primeui";` (CSS version, not `plugin()` in config).
**Warning signs:** PrimeNG components render unstyled or with broken layout.

### Pitfall 7: Node.js Version Mismatch
**What goes wrong:** Angular CLI 21 fails to start.
**Why it happens:** Environment has Node.js 24.14.0 but Angular 21 minimum is Node.js 22 LTS. Node 24 should be compatible but may cause warnings.
**How to avoid:** Verify Angular CLI works with the installed Node version. If issues arise, use `volta pin node@22` or nvm to set Node 22 LTS.
**Warning signs:** Angular CLI version warnings or startup errors.

## Code Examples

### Maven pom.xml Quality Gate Configuration (key plugins)
```xml
<!-- Error Prone via maven-compiler-plugin -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>21</release>
        <compilerArgs>
            <arg>-XDcompilePolicy=simple</arg>
            <arg>--should-stop=ifError=FLOW</arg>
            <arg>-Xplugin:ErrorProne</arg>
            <arg>-XDaddTypeAnnotationsToSymbol=true</arg>
            <arg>-Xlint:all</arg>
        </compilerArgs>
        <annotationProcessorPaths>
            <path>
                <groupId>com.google.errorprone</groupId>
                <artifactId>error_prone_core</artifactId>
                <version>2.48.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>

<!-- Spotless for google-java-format -->
<plugin>
    <groupId>com.diffplug.spotless</groupId>
    <artifactId>spotless-maven-plugin</artifactId>
    <version>2.43.0</version>
    <configuration>
        <java>
            <googleJavaFormat>
                <version>1.35.0</version>
                <style>GOOGLE</style>
            </googleJavaFormat>
        </java>
    </configuration>
    <executions>
        <execution>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- Checkstyle with runtime version override -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <dependencies>
        <dependency>
            <groupId>com.puppycrawl.tools</groupId>
            <artifactId>checkstyle</artifactId>
            <version>13.3.0</version>
        </dependency>
    </dependencies>
    <configuration>
        <configLocation>checkstyle.xml</configLocation>
        <consoleOutput>true</consoleOutput>
        <failsOnError>true</failsOnError>
    </configuration>
    <executions>
        <execution>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- JaCoCo report only (NO check goal, per D-08) -->
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.15</version>
    <executions>
        <execution>
            <goals><goal>prepare-agent</goal></goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>verify</phase>
            <goals><goal>report</goal></goals>
        </execution>
    </executions>
</plugin>

<!-- OWASP dependency-check -->
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>12.2.0</version>
    <executions>
        <execution>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
    <configuration>
        <failBuildOnCVSS>7</failBuildOnCVSS>
    </configuration>
</plugin>
```

### .mvn/jvm.config (Required for Error Prone on Java 21)
```
--add-exports jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.file=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.main=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.model=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.parser=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED
--add-opens jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED
--add-opens jdk.compiler/com.sun.tools.javac.comp=ALL-UNNAMED
```

### lefthook.yml
```yaml
pre-commit:
  parallel: true
  commands:
    java-format:
      glob: "*.java"
      run: ./mvnw spotless:check -q
    java-lint:
      glob: "*.java"
      run: ./mvnw checkstyle:check -q
    frontend-lint:
      root: "frontend/"
      glob: "*.{ts,html}"
      run: pnpm lint
    frontend-format:
      root: "frontend/"
      glob: "*.{ts,html,css,json}"
      run: pnpm format:check
```

### Docker Compose (docker-compose.yml)
```yaml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: prosperity
      POSTGRES_USER: prosperity
      POSTGRES_PASSWORD: prosperity
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prosperity"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8080:8080"
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/prosperity
      SPRING_DATASOURCE_USERNAME: prosperity
      SPRING_DATASOURCE_PASSWORD: prosperity
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/actuator/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  caddy:
    image: caddy:2.11-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      backend:
        condition: service_healthy

volumes:
  pgdata:
  caddy_data:
  caddy_config:
```

### Caddyfile
```
:80 {
    handle /api/* {
        reverse_proxy backend:8080
    }
    handle {
        root * /srv
        try_files {path} /index.html
        file_server
    }
}
```

### GitHub Actions CI (ci.yml)
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: 21
          cache: maven
      - name: Build & verify
        run: ./mvnw verify -B
      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: jacoco-report
          path: target/site/jacoco/

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - uses: pnpm/action-setup@v4
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
        working-directory: frontend
      - name: Lint
        run: pnpm lint
        working-directory: frontend
      - name: Format check
        run: pnpm format:check
        working-directory: frontend
      - name: Build
        run: pnpm build
        working-directory: frontend
```

### Frontend styles.css
```css
@import "tailwindcss";
@import "tailwindcss-primeui";
```

### application.yml
```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/prosperity
    username: prosperity
    password: prosperity
  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
  flyway:
    enabled: true
    locations: classpath:db/migration

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: always
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Liquibase 5.0 | Flyway 11.x | Oct 2025 (FSL license change) | CRITICAL: Liquibase 5.0 FSL license violates project open source constraint |
| Spring Boot 3.x | Spring Boot 4.0.x | Nov 2025 | JSpecify null-safety, Spring Framework 7, Hibernate 7 |
| Zone.js Angular | Zoneless Angular 21 | 2025-2026 | Signals-based, standalone components by default |
| Tailwind v3 (JS config) | Tailwind v4 (CSS-based) | 2025 | CSS-native config, no tailwind.config.js needed |
| Maven Checkstyle 9.x default | Override to Checkstyle 13.3.0 | Ongoing | Plugin bundles old version, must override for Java 21 support |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Java (Temurin) | Backend | Yes | 21.0.10 | -- |
| Node.js | Frontend | Yes | 24.14.0 | May need volta/nvm for 22 LTS if issues arise |
| pnpm | Frontend | Yes | 10.32.1 | -- |
| Git | VCS | Yes | 2.43.0 | -- |
| GitHub CLI | CI/PR | Yes | 2.45.0 | -- |
| Docker | Infrastructure | **NO** | -- | Enable Docker Desktop WSL2 integration or install Docker Engine in WSL2 |
| Maven | Backend | No (use mvnw) | -- | Maven Wrapper (mvnw) bundled with project |
| Angular CLI | Frontend | No (global) | -- | Use `npx @angular/cli` or `pnpm dlx @angular/cli` |
| Lefthook | Pre-commit hooks | No | -- | Install via `pnpm add -D lefthook` at root |

**Missing dependencies with no fallback:**
- Docker/Docker Compose: Required for INFR-02. Must be installed or enabled via Docker Desktop WSL2 integration before `docker compose up -d` can work.

**Missing dependencies with fallback:**
- Maven: Maven Wrapper (mvnw) will be generated by Spring Initializr -- no global install needed.
- Angular CLI: Use npx/pnpm dlx for `ng new`, then local node_modules/.bin/ng.
- Node.js 24 vs 22: Angular 21 should work with Node 24 (forward compatible), but if issues arise, pin Node 22 LTS via volta.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | JUnit 5 (via spring-boot-starter-test) + AssertJ + ArchUnit |
| Config file | None -- Wave 0 setup (pom.xml test dependencies) |
| Quick run command | `./mvnw test -pl .` |
| Full suite command | `./mvnw verify` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-02 | Docker Compose starts all 3 services | manual / smoke | `docker compose up -d && curl http://localhost:8080/actuator/health` | N/A (manual) |
| INFR-04 | Checkstyle fails on violations | unit (build) | `./mvnw checkstyle:check` | Wave 0 |
| INFR-05 | Spotless fails on format violations | unit (build) | `./mvnw spotless:check` | Wave 0 |
| INFR-06 | Error Prone catches bugs at compile | unit (build) | `./mvnw compile` (Error Prone runs during compilation) | Wave 0 |
| INFR-07 | Dead code detected (unused imports, -Xlint) | unit (build) | `./mvnw compile` (-Xlint:all in compiler args) | Wave 0 |
| INFR-08 | JaCoCo report generated | unit (build) | `./mvnw verify` then check target/site/jacoco/index.html | Wave 0 |
| INFR-09 | OWASP scan runs | unit (build) | `./mvnw dependency-check:check` | Wave 0 |
| INFR-10 | Pre-commit hooks block bad code | manual | `git commit` with intentional violation | N/A (manual) |
| D-05 | Money rejects floating-point, enforces precision | unit | `./mvnw test -Dtest=MoneyTest` | Wave 0 |
| D-05 | TransactionState enum values correct | unit | `./mvnw test -Dtest=TransactionStateTest` | Wave 0 |
| D-07 | Envelope rollover/overspend rules | unit | `./mvnw test -Dtest=EnvelopeTest` | Wave 0 |
| D-02 | ArchUnit: no circular deps, banking abstract | unit | `./mvnw test -Dtest=ArchitectureTest` | Wave 0 |
| D-14 | Angular SPA loads in browser | smoke | `pnpm dev` then check browser | N/A (manual) |

### Sampling Rate
- **Per task commit:** `./mvnw test -q` (quick unit tests)
- **Per wave merge:** `./mvnw verify` (full quality gates)
- **Phase gate:** Full suite green + `pnpm lint && pnpm format:check && pnpm build` before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pom.xml` -- all test dependencies (JUnit, AssertJ, ArchUnit), quality gate plugins
- [ ] `src/test/java/com/prosperity/shared/MoneyTest.java` -- covers D-05
- [ ] `src/test/java/com/prosperity/shared/TransactionStateTest.java` -- covers D-05
- [ ] `src/test/java/com/prosperity/envelope/EnvelopeTest.java` -- covers D-07
- [ ] `src/test/java/com/prosperity/architecture/ArchitectureTest.java` -- covers D-02
- [ ] `checkstyle.xml` -- Checkstyle configuration file
- [ ] `.mvn/jvm.config` -- Error Prone JVM flags

## Open Questions

1. **DB schema: `balance_cents BIGINT` vs Money(BigDecimal)**
   - What we know: DB stores cents as BIGINT, domain uses Money(BigDecimal). A JPA AttributeConverter bridges them.
   - What's unclear: The existing database.md still references Liquibase and `balance_cents`. This is consistent with the approach (cents in DB, BigDecimal in Java) but database.md needs updating.
   - Recommendation: Implement MoneyConverter (AttributeConverter<Money, Long>) to map between BigDecimal and BIGINT cents.

2. **Docker availability in this WSL2 environment**
   - What we know: Docker is not installed/configured in this WSL2 distro.
   - What's unclear: Whether Docker Desktop is installed on the Windows host.
   - Recommendation: Document Docker setup as a prerequisite. The docker-compose.yml and Dockerfiles can be written and tested once Docker is available.

3. **Checkstyle configuration file scope**
   - What we know: Checkstyle needs a config XML (google_checks.xml or custom).
   - What's unclear: Whether to use Google's checks directly or customize.
   - Recommendation: Start with Google's `google_checks.xml` (ships with Checkstyle), customize only where it conflicts with google-java-format or project needs.

## Project Constraints (from CLAUDE.md)

- Open source: all dependencies must be MIT or Apache 2.0
- Self-hosted: no paid cloud services (except Plaid)
- CI/lint tooling must be mature (no bleeding edge without tool support)
- Bank connector behind abstract interface (Plaid interchangeable)
- Java 21 LTS (Checkstyle incompatible with Java 25)
- Spring Boot 4.0.x (Boot 3.5 end-of-OSS June 2026)
- No Lombok (Java 21 records + manual code)
- Montants en centimes (BIGINT/long) in DB, BigDecimal in domain
- Flyway 11.x (NOT Liquibase -- FSL license)

## Sources

### Primary (HIGH confidence)
- [Error Prone installation docs](https://errorprone.info/docs/installation) -- Maven config, JVM flags for Java 21
- [Spotless Maven Plugin README](https://github.com/diffplug/spotless/blob/main/plugin-maven/README.md) -- google-java-format integration
- [Flyway naming convention](https://documentation.red-gate.com/fd/) -- V{version}__{description}.sql
- [Spring Boot 4.0 release](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/) -- confirmed version 4.0.5 latest
- [Tailwind CSS Angular guide](https://tailwindcss.com/docs/installation/framework-guides/angular) -- native CLI integration

### Secondary (MEDIUM confidence)
- [Error Prone 2.48.0](https://mvnrepository.com/artifact/com.google.errorprone/error_prone_core) -- latest version confirmed Feb 2026
- [google-java-format 1.35.0](https://github.com/google/google-java-format/releases) -- latest version
- [OWASP dependency-check 12.2.0](https://mvnrepository.com/artifact/org.owasp/dependency-check-maven) -- latest Jan 2026
- [Checkstyle 13.3.0](https://checkstyle.sourceforge.io/) -- latest Feb 2026
- [JaCoCo 0.8.15](https://github.com/jacoco/jacoco/releases) -- latest Mar 2026
- [maven-checkstyle-plugin 3.6.0](https://mvnrepository.com/artifact/org.apache.maven.plugins/maven-checkstyle-plugin) -- latest version
- [Spotless Maven Plugin 2.43.0](https://github.com/diffplug/spotless/blob/main/plugin-maven/CHANGES.md) -- version confirmed
- [Lefthook vs Husky comparison 2026](https://www.edopedia.com/blog/lefthook-vs-husky/) -- Lefthook recommended for polyglot/monorepo

### Tertiary (LOW confidence)
- Spotless default google-java-format version (1.28.0) -- from search results, needs verification against actual plugin release notes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified via search, Boot 4.0.5 confirmed
- Architecture: HIGH -- follows locked decisions D-01 through D-15, canonical docs read
- Quality gates: HIGH -- Error Prone, Checkstyle, Spotless, OWASP all verified with current versions
- Pitfalls: HIGH -- Error Prone JVM config confirmed via official docs, OWASP slow first run well-documented
- Environment: MEDIUM -- Docker unavailability confirmed, Node.js 24 vs 22 compatibility unverified

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable stack, 30-day window)

---
*Phase: 01-project-foundation*
*Research completed: 2026-03-28*
