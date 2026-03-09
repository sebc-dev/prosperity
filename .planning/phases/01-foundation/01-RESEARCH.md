# Phase 1: Foundation - Research

**Researched:** 2026-03-09
**Domain:** Full-stack greenfield setup (Spring Boot + SvelteKit + PostgreSQL + Docker), JWT auth, bank accounts CRUD, user preferences
**Confidence:** HIGH

## Summary

Phase 1 is a greenfield setup covering three pillars: infrastructure (Docker Compose, CI/CD, HTTPS), authentication (JWT + refresh tokens with httpOnly cookies, BFF pattern), and core domain (bank accounts with personal/shared visibility, user profiles and preferences). The architecture is fully documented in `docs/architecture.md` with Vertical Slice backend and SvelteKit BFF frontend.

The stack is mature and well-documented. Spring Boot 3.5.x is the current supported version (3.3 is EOL, 3.4 is EOL as of Dec 2025). SvelteKit 2 with Svelte 5 runes is stable. Tailwind CSS 4 simplifies setup via a Vite plugin (no config file needed). Paraglide JS 2.0 is the recommended i18n library for SvelteKit (tree-shakable, compiler-based, officially referenced in Svelte CLI docs). Liquibase with YAML changelogs is the migration tool.

**Primary recommendation:** Use Spring Boot 3.5.x (latest patch), SvelteKit 2 + Svelte 5, Tailwind CSS 4 via Vite plugin, Paraglide JS 2.0 for i18n, and `java-uuid-generator` (JUG) 5.x for UUIDv7. Structure backend as vertical slices per `docs/architecture.md`. Implement BFF pattern in SvelteKit `hooks.server.ts` for auth proxying.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Wizard au premier lancement : page /setup demande email, nom, mot de passe pour creer le compte Admin
- /setup verrouillee automatiquement des qu'un admin existe (redirect vers /login)
- Apres le wizard, redirect vers Settings pour configurer l'app
- L'admin cree le compte Standard depuis Settings > Utilisateurs (email + nom + mot de passe temporaire, change au premier login)
- Page login centree minimaliste : logo + champs email/password + bouton, fond neutre, style Linear/Vercel
- Pas de checkbox "Se souvenir de moi" -- toujours connecte, refresh token 30 jours
- Expiration de session : redirect silencieux vers /login avec toast discret "Session expiree"
- Interface bilingue FR/EN avec systeme i18n des le depart (selecteur de langue dans les preferences)
- Formulaire complet : nom, banque, type (Personnel/Partage), devise, solde initial, couleur
- Affichage en cards colorees groupees "Mes comptes" / "Comptes partages"
- Double solde (reel + projete) affiche des la Phase 1, meme si projete = reel tant qu'il n'y a pas de transactions
- Les deux utilisateurs (Admin et Standard) peuvent creer des comptes (personnels et partages)
- Settings avec sidebar gauche : Profil, Preferences, Securite, Utilisateurs (admin seulement)
- Preferences Phase 1 : theme (clair/sombre/systeme), devise par defaut, langue (FR/EN), categories favorites
- Categories de transactions predefinies par defaut + possibilite d'ajouter des categories custom
- Section Securite : changement de mot de passe uniquement (ancien + nouveau + confirmation)

### Claude's Discretion
- Design system (spacing, typography, composants UI)
- Choix de la librairie i18n SvelteKit
- Set exact de categories predefinies
- Structure des migrations Liquibase
- Skeletons de chargement et etats d'erreur
- Layout responsive mobile des Settings (sidebar -> menu deroulant ?)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | User can log in with email and password | JWT auth flow with Spring Security, login form action in SvelteKit, BFF cookie proxying |
| AUTH-02 | User session persists via JWT + Refresh Tokens with automatic rotation | httpOnly cookie storage, 15min access / 30-day refresh, silent refresh in hooks.server.ts |
| AUTH-03 | Two roles enforced: Admin and Standard | SystemRole enum, @PreAuthorize, route guards in hooks.server.ts and +layout.server.ts |
| AUTH-04 | User can update profile (display name) | User feature slice with UserController PATCH, Settings/Profile page |
| AUTH-05 | User can set preferences (theme, currency, favorites) | UserPreferences entity or JSONB column, Svelte 5 runes store for client-side reactivity |
| ACCT-01 | User can create bank accounts as Personal or Shared | Account feature slice with AccountType enum, form action for creation |
| ACCT-02 | Personal accounts visible only to owner | Permission-based filtering in AccountRepository query, owner_id check |
| ACCT-03 | Shared accounts accessible by both users | Auto-grant READ/WRITE permissions to both users on SHARED account creation |
| INFR-01 | Docker Compose deployment (PostgreSQL + Spring Boot API + SvelteKit web) | Multi-stage Docker builds, docker-compose.yml with profiles dev/prod |
| INFR-02 | CI/CD pipeline: build, tests, lint on push | GitHub Actions workflow, Checkstyle, ESLint, Prettier, svelte-check |
| INFR-03 | Security headers (CSP, HSTS, X-Frame-Options), HTTPS via Caddy | Caddy reverse proxy config, Spring Security headers config |
| INFR-04 | Passwords bcrypted (12 rounds), OWASP Top 10 compliance | BCryptPasswordEncoder(12), Bean Validation, parameterized queries |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Boot | 3.5.x (latest patch) | Backend framework | Current supported version; 3.3 and 3.4 are EOL |
| Spring Security | 6.x (via Boot 3.5) | Authentication, authorization | Built-in JWT filter chain, @PreAuthorize, BCrypt |
| Spring Data JPA | 3.x (via Boot 3.5) | ORM / Repository pattern | Standard for JPA with Spring Boot |
| PostgreSQL | 16 | Database | As specified in architecture doc |
| Liquibase | 4.x (via Boot starter) | Database migrations | YAML changelogs, Spring Boot auto-run integration |
| SvelteKit | 2.x | Frontend framework + BFF | File-based routing, SSR, form actions, server hooks |
| Svelte | 5.x | UI reactivity | Runes ($state, $derived, $effect), fine-grained reactivity |
| Tailwind CSS | 4.x | Styling | Vite plugin (no config file), @theme directive in CSS |
| TypeScript | 5.x | Frontend type safety | Standard for SvelteKit projects |
| Java | 21 LTS | Backend language | Records, sealed classes, virtual threads, pattern matching |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Paraglide JS | 2.x (@inlang/paraglide-js) | i18n (FR/EN) | All user-facing strings; compiler-based, tree-shakable |
| java-uuid-generator (JUG) | 5.x | UUIDv7 generation | All entity IDs — client-generated for future offline support |
| jjwt (io.jsonwebtoken) | 0.12.x | JWT creation/parsing | Access token (15min) and refresh token (30 days) |
| Docker + Docker Compose | latest | Containerization | Dev and prod deployment |
| Caddy | 2.x | Reverse proxy + HTTPS | Existing on server, auto-TLS with Let's Encrypt |
| Vite | 6.x (via SvelteKit) | Build tool | Dev server, HMR, production builds |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Paraglide JS | svelte-i18n | svelte-i18n is more established but runtime-based (larger bundle); Paraglide compiles to functions (tree-shakable), officially referenced in Svelte CLI docs |
| Paraglide JS | sveltekit-i18n | Zero deps but smaller community; Paraglide has better Svelte 5 support |
| jjwt | nimbus-jose-jwt | Both work; jjwt has simpler API for symmetric key JWT |
| JUG | uuid-creator | Both support UUIDv7; JUG has broader adoption and maintained by Jackson creator |
| Liquibase YAML | Liquibase SQL | SQL is more explicit but YAML provides cross-DB portability and built-in rollback support |

**Installation (Backend - Maven):**
```xml
<!-- Spring Boot parent 3.5.x -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-api</artifactId>
    <version>0.12.6</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.uuid</groupId>
    <artifactId>java-uuid-generator</artifactId>
    <version>5.1.0</version>
</dependency>
```

**Installation (Frontend - npm):**
```bash
npm create svelte@latest prosperity-web  # SvelteKit skeleton
npm install -D @tailwindcss/vite tailwindcss
npm install @inlang/paraglide-js
```

## Architecture Patterns

### Recommended Project Structure (Monorepo)

```
prosperity/
├── prosperity-api/                    # Spring Boot backend
│   ├── src/main/java/fr/kalifazzia/prosperity/
│   │   ├── shared/                    # Kernel: domain/, security/, persistence/, web/, config/
│   │   ├── auth/                      # Login, refresh, JWT
│   │   ├── user/                      # User CRUD, profile, preferences
│   │   └── account/                   # Bank accounts, permissions
│   ├── src/main/resources/
│   │   ├── db/changelog/              # Liquibase YAML migrations
│   │   └── application.yml
│   ├── Dockerfile                     # Multi-stage build
│   └── pom.xml
├── prosperity-web/                    # SvelteKit frontend
│   ├── src/
│   │   ├── routes/
│   │   │   ├── (auth)/login/          # Login page (no nav layout)
│   │   │   ├── (auth)/setup/          # First-run wizard
│   │   │   ├── (app)/                 # Authenticated layout group
│   │   │   │   ├── accounts/          # Account list + creation
│   │   │   │   └── settings/          # Profile, Preferences, Security, Users
│   │   │   └── +layout.svelte
│   │   ├── lib/
│   │   │   ├── api/client.ts          # Fetch wrapper (calls Spring Boot from server)
│   │   │   ├── components/ui/         # Button, Card, Input, Badge, etc.
│   │   │   ├── stores/                # auth.svelte.ts, preferences.svelte.ts
│   │   │   └── i18n/                  # Paraglide messages (FR/EN)
│   │   ├── hooks.server.ts            # Auth guard, JWT cookie proxying
│   │   └── app.css                    # @import "tailwindcss"
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── docker-compose.dev.yml
├── Caddyfile                          # Reverse proxy config (prod)
└── .github/workflows/ci.yml
```

### Pattern 1: BFF Authentication Flow

**What:** Browser never talks to Spring Boot directly. SvelteKit server-side handles JWT cookies.
**When to use:** All authenticated API calls.

```typescript
// hooks.server.ts — auth guard + cookie forwarding
import { redirect, type Handle } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';

const PUBLIC_PATHS = ['/login', '/setup'];

const authGuard: Handle = async ({ event, resolve }) => {
    const accessToken = event.cookies.get('access_token');
    const isPublic = PUBLIC_PATHS.some(p => event.url.pathname.startsWith(p));

    if (!accessToken && !isPublic) {
        redirect(303, '/login');
    }

    if (accessToken) {
        // Attach user info to event.locals for downstream use
        event.locals.accessToken = accessToken;
    }

    return resolve(event);
};

const tokenRefresh: Handle = async ({ event, resolve }) => {
    const accessToken = event.cookies.get('access_token');
    const refreshToken = event.cookies.get('refresh_token');

    if (!accessToken && refreshToken) {
        // Silent refresh: call Spring Boot /api/auth/refresh
        const res = await fetch('http://api:8080/api/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refreshToken })
        });
        if (res.ok) {
            const data = await res.json();
            event.cookies.set('access_token', data.accessToken, {
                path: '/', httpOnly: true, secure: true, sameSite: 'lax',
                maxAge: 60 * 15 // 15 minutes
            });
            event.cookies.set('refresh_token', data.refreshToken, {
                path: '/', httpOnly: true, secure: true, sameSite: 'lax',
                maxAge: 60 * 60 * 24 * 30 // 30 days
            });
            event.locals.accessToken = data.accessToken;
        } else {
            // Refresh failed — clear cookies, redirect to login
            event.cookies.delete('access_token', { path: '/' });
            event.cookies.delete('refresh_token', { path: '/' });
            if (!PUBLIC_PATHS.some(p => event.url.pathname.startsWith(p))) {
                redirect(303, '/login');
            }
        }
    }

    return resolve(event);
};

export const handle = sequence(tokenRefresh, authGuard);
```

### Pattern 2: Vertical Slice Feature (Backend)

**What:** Each feature (auth, user, account) is a self-contained package with controller, service, repository, entity, DTOs.
**When to use:** Every backend feature.

```java
// account/AccountService.java
@Service
@Transactional
public class AccountService {

    private final AccountRepository accountRepository;
    private final PermissionRepository permissionRepository;

    // Personal: only owner can see
    // Shared: both users get READ+WRITE permissions
    public AccountDto createAccount(CreateAccountRequest request, UserId currentUser) {
        var account = new Account(
            UuidCreator.getTimeOrderedEpoch(), // UUIDv7
            request.name(),
            request.bankName(),
            request.accountType(),
            currentUser,
            request.currency(),
            request.initialBalance(),
            request.color()
        );
        account = accountRepository.save(account);

        // Auto-grant permissions
        grantPermission(account.getId(), currentUser, PermissionLevel.MANAGE);
        if (request.accountType() == AccountType.SHARED) {
            // Grant READ+WRITE to the other user
            var otherUser = userRepository.findOtherUser(currentUser);
            grantPermission(account.getId(), otherUser.getId(), PermissionLevel.WRITE);
        }

        return AccountDto.from(account);
    }
}
```

### Pattern 3: SvelteKit Form Actions for Mutations

**What:** Server-side form handling with progressive enhancement.
**When to use:** All data mutations (create account, update profile, login).

```typescript
// routes/(app)/accounts/new/+page.server.ts
import { fail, redirect } from '@sveltejs/kit';
import type { Actions } from './$types';
import { apiClient } from '$lib/api/client';

export const actions: Actions = {
    default: async ({ request, locals, cookies }) => {
        const form = await request.formData();
        const name = form.get('name') as string;
        const bankName = form.get('bankName') as string;
        const accountType = form.get('accountType') as string;
        // ... validation

        if (!name) return fail(400, { error: 'name_required', name });

        const res = await apiClient(locals.accessToken).post('/api/accounts', {
            name, bankName, accountType,
            currency: form.get('currency'),
            initialBalance: parseFloat(form.get('initialBalance') as string),
            color: form.get('color')
        });

        if (!res.ok) {
            const err = await res.json();
            return fail(res.status, { error: err.message });
        }

        redirect(303, '/accounts');
    }
};
```

### Pattern 4: Svelte 5 Runes Store for Theme/Preferences

**What:** Reactive client-side state using Svelte 5 class-based stores with $state/$derived.
**When to use:** Theme toggle, locale, user preferences synced with server.

```typescript
// lib/stores/preferences.svelte.ts
class PreferencesStore {
    theme = $state<'light' | 'dark' | 'system'>('system');
    locale = $state<'fr' | 'en'>('fr');
    defaultCurrency = $state('EUR');

    resolvedTheme = $derived(() => {
        if (this.theme === 'system') {
            return typeof window !== 'undefined'
                && window.matchMedia('(prefers-color-scheme: dark)').matches
                ? 'dark' : 'light';
        }
        return this.theme;
    });

    setTheme(theme: 'light' | 'dark' | 'system') {
        this.theme = theme;
        if (typeof document !== 'undefined') {
            document.documentElement.classList.toggle('dark', this.resolvedTheme === 'dark');
        }
    }
}

export const preferences = new PreferencesStore();
```

### Pattern 5: Setup Wizard with Route Lock

**What:** /setup route that creates the first Admin user, locked once an admin exists.
**When to use:** First application launch only.

```typescript
// routes/(auth)/setup/+page.server.ts
import { redirect } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
    // Check if any admin exists
    const res = await fetch('http://api:8080/api/setup/status');
    const { adminExists } = await res.json();
    if (adminExists) redirect(303, '/login');
    return {};
};

export const actions: Actions = {
    default: async ({ request, fetch, cookies }) => {
        const form = await request.formData();
        const res = await fetch('http://api:8080/api/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: form.get('email'),
                displayName: form.get('displayName'),
                password: form.get('password')
            })
        });
        if (!res.ok) return fail(400, { error: 'Setup failed' });

        // Auto-login the admin after setup
        const loginRes = await res.json();
        cookies.set('access_token', loginRes.accessToken, { /* ... */ });
        cookies.set('refresh_token', loginRes.refreshToken, { /* ... */ });
        redirect(303, '/settings');
    }
};
```

### Anti-Patterns to Avoid

- **Calling Spring Boot from browser JavaScript:** Always proxy through SvelteKit server. Never expose the API URL to the client.
- **Storing JWT in localStorage:** Use httpOnly cookies only. The BFF pattern prevents XSS token theft.
- **Cross-feature imports in backend:** Features must not import from each other. Use Spring events or inject repositories for read-only access.
- **Using Hibernate DDL auto:** Always use Liquibase for schema changes. Set `spring.jpa.hibernate.ddl-auto=validate`.
- **Svelte 4 reactive syntax ($:):** Use Svelte 5 runes ($state, $derived, $effect) exclusively.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT creation/validation | Custom token string manipulation | jjwt library | Signature verification, expiry checks, claim parsing are error-prone |
| Password hashing | Custom hash functions | BCryptPasswordEncoder(12) | Timing attacks, salt handling, round counting are tricky |
| i18n message resolution | Custom key-value store | Paraglide JS | Plural forms, interpolation, tree-shaking, compile-time type safety |
| UUID v7 generation | Manual timestamp + random bytes | JUG or uuid-creator | RFC 9562 compliance, monotonic ordering within same millisecond |
| Database migrations | Manual ALTER TABLE scripts | Liquibase | Rollback, changeset tracking, team coordination |
| Form validation | Custom validation logic | Bean Validation (backend) + SvelteKit form actions (frontend) | Consistent error handling, i18n messages |
| Dark mode FOUC prevention | Custom JS injection | Tailwind CSS dark: variant + inline script in app.html | Flash of wrong theme on page load |
| Security headers | Manual response header setting | Spring Security headers config + Caddy | CSP is complex to get right; missing headers = vulnerabilities |

**Key insight:** Phase 1 has many foundational pieces. Using battle-tested libraries for auth, crypto, and i18n prevents security vulnerabilities and saves weeks of debugging.

## Common Pitfalls

### Pitfall 1: FOUC (Flash of Unstyled Content) on Dark Mode

**What goes wrong:** Page loads with light theme, then flashes to dark when JS hydrates.
**Why it happens:** Theme preference stored in cookie/localStorage isn't read before first paint.
**How to avoid:** Add an inline `<script>` in `app.html` (before body) that reads the cookie/localStorage and applies the `dark` class to `<html>` synchronously. Do NOT rely on Svelte component lifecycle for this.
**Warning signs:** Users report a white flash on page load when using dark mode.

### Pitfall 2: Cookie Domain Mismatch in Docker

**What goes wrong:** Cookies set by SvelteKit are not sent to Spring Boot, or vice versa.
**Why it happens:** In Docker, services run on different hostnames (e.g., `web:3000`, `api:8080`). Cookies are domain-scoped.
**How to avoid:** In the BFF pattern, cookies are between browser and SvelteKit ONLY. SvelteKit server-side code forwards the JWT as a Bearer header to Spring Boot. Never set cookies from Spring Boot responses directly.
**Warning signs:** 401 errors on API calls despite successful login.

### Pitfall 3: Liquibase Changeset ID Conflicts

**What goes wrong:** Multiple changesets with same ID cause migration failures.
**Why it happens:** Using sequential numbers (1, 2, 3) without namespacing.
**How to avoid:** Use format: `YYYYMMDD-NN-description` (e.g., `20260309-01-create-users-table`). One schema change per changeset. Use a master changelog that includes feature-specific changelogs.
**Warning signs:** `Validation Failed: N changeset(s) already applied` errors.

### Pitfall 4: Setup Wizard Race Condition

**What goes wrong:** Two users simultaneously access /setup and both create admin accounts.
**Why it happens:** No database-level uniqueness constraint or lock on admin creation.
**How to avoid:** Use a database constraint (CHECK that only one ADMIN role exists) or use `SELECT ... FOR UPDATE` in the setup service. The API endpoint should be idempotent.
**Warning signs:** Two admin accounts in the database.

### Pitfall 5: SvelteKit Load Function vs Form Action Confusion

**What goes wrong:** Developers put mutation logic in `+page.ts` load functions or data loading in form actions.
**Why it happens:** Unclear separation between data loading and mutations in SvelteKit.
**How to avoid:** `+page.ts` / `+page.server.ts` `load` = GET data. `+page.server.ts` `actions` = POST/mutations. Load functions run on navigation; actions run on form submission.
**Warning signs:** Data mutations happening on page navigation, or pages not loading data on first visit.

### Pitfall 6: Virtual Threads + Synchronized Blocks

**What goes wrong:** Virtual threads get pinned to platform threads when entering `synchronized` blocks.
**Why it happens:** JVM limitation with virtual threads and monitor-based synchronization.
**How to avoid:** Use `ReentrantLock` instead of `synchronized`. Most Spring Boot code doesn't use `synchronized` directly, but some JDBC drivers do. PostgreSQL JDBC driver (42.7+) has fixed most pinning issues.
**Warning signs:** Unexpected thread starvation under concurrent requests.

## Code Examples

### Liquibase Master Changelog Structure

```yaml
# src/main/resources/db/changelog/db.changelog-master.yaml
databaseChangeLog:
  - include:
      file: db/changelog/migrations/20260309-01-create-users-table.yaml
  - include:
      file: db/changelog/migrations/20260309-02-create-accounts-table.yaml
  - include:
      file: db/changelog/migrations/20260309-03-create-permissions-table.yaml
  - include:
      file: db/changelog/migrations/20260309-04-create-categories-table.yaml
  - include:
      file: db/changelog/migrations/20260309-05-create-audit-log-table.yaml
  - include:
      file: db/changelog/migrations/20260309-06-create-refresh-tokens-table.yaml
  - include:
      file: db/changelog/migrations/20260309-07-seed-default-categories.yaml
```

### Single Migration Changeset Example

```yaml
# db/changelog/migrations/20260309-01-create-users-table.yaml
databaseChangeLog:
  - changeSet:
      id: 20260309-01-create-users-table
      author: prosperity
      changes:
        - createTable:
            tableName: users
            columns:
              - column:
                  name: id
                  type: uuid
                  constraints:
                    primaryKey: true
              - column:
                  name: email
                  type: varchar(255)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: password_hash
                  type: varchar(255)
                  constraints:
                    nullable: false
              - column:
                  name: display_name
                  type: varchar(255)
                  constraints:
                    nullable: false
              - column:
                  name: system_role
                  type: varchar(50)
                  constraints:
                    nullable: false
              - column:
                  name: preferences
                  type: jsonb
                  defaultValue: '{}'
              - column:
                  name: force_password_change
                  type: boolean
                  defaultValueBoolean: false
              - column:
                  name: created_at
                  type: timestamp
                  constraints:
                    nullable: false
              - column:
                  name: updated_at
                  type: timestamp
                  constraints:
                    nullable: false
              - column:
                  name: version
                  type: bigint
                  defaultValueNumeric: 0
```

### Docker Compose (Dev Profile)

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: prosperity
      POSTGRES_USER: prosperity
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prosperity"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: ./prosperity-api
      dockerfile: Dockerfile
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/prosperity
      SPRING_DATASOURCE_USERNAME: prosperity
      SPRING_DATASOURCE_PASSWORD: ${DB_PASSWORD}
      JWT_SECRET: ${JWT_SECRET}
      SPRING_THREADS_VIRTUAL_ENABLED: "true"
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8080:8080"

  web:
    build:
      context: ./prosperity-web
      dockerfile: Dockerfile
    environment:
      API_URL: http://api:8080
      ORIGIN: https://prosperity.example.com
    depends_on:
      - api
    ports:
      - "3000:3000"

volumes:
  pgdata:
```

### Paraglide JS Setup

```typescript
// vite.config.ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { paraglide } from '@inlang/paraglide-js';

export default defineConfig({
    plugins: [
        tailwindcss(),
        paraglide({
            project: './project.inlang',
            outdir: './src/lib/i18n'
        }),
        sveltekit()
    ]
});
```

```json
// messages/fr.json
{
    "login_title": "Connexion",
    "login_email": "Adresse email",
    "login_password": "Mot de passe",
    "login_submit": "Se connecter",
    "session_expired": "Session expiree, veuillez vous reconnecter",
    "accounts_title": "Mes comptes",
    "accounts_shared": "Comptes partages",
    "accounts_personal": "Mes comptes personnels"
}
```

### FOUC Prevention Script (app.html)

```html
<!-- src/app.html -->
<!doctype html>
<html lang="fr">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script>
        // Prevent FOUC: apply dark class before paint
        (function() {
            try {
                var theme = document.cookie.match(/theme=(\w+)/)?.[1] || 'system';
                var isDark = theme === 'dark' ||
                    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                if (isDark) document.documentElement.classList.add('dark');
            } catch(e) {}
        })();
    </script>
    %sveltekit.head%
</head>
<body data-sveltekit-preload-data="hover">
    <div style="display: contents">%sveltekit.body%</div>
</body>
</html>
```

### Default Categories Seed Data

Recommended predefined categories for Phase 1 (Claude's discretion):

```yaml
# Essentials
- Alimentation / Groceries
- Logement / Housing
- Transport / Transportation
- Sante / Health
- Assurance / Insurance
# Lifestyle
- Loisirs / Entertainment
- Restaurants / Dining Out
- Shopping
- Abonnements / Subscriptions
- Sport & Fitness
# Financial
- Epargne / Savings
- Revenus / Income
- Remboursement / Reimbursement
# Other
- Cadeaux / Gifts
- Education
- Divers / Miscellaneous
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Spring Boot 3.3 | Spring Boot 3.5.x (or 4.0.x) | 3.3 EOL mid-2025, 3.4 EOL Dec 2025 | Must use 3.5.x; architecture doc says "3.3+" but that's outdated |
| Tailwind CSS 3 config file | Tailwind CSS 4 Vite plugin + @theme in CSS | Jan 2025 | No tailwind.config.ts needed, simpler setup |
| @inlang/paraglide-sveltekit adapter | @inlang/paraglide-js Vite plugin | Paraglide 2.0 (2025) | Framework-agnostic, no SvelteKit-specific package needed |
| Svelte 4 ($: reactive) | Svelte 5 runes ($state, $derived) | Late 2024 | All components must use runes syntax |
| typesafe-i18n | Paraglide JS | typesafe-i18n deprecated | Paraglide is the spiritual successor |

**Deprecated/outdated:**
- Spring Boot 3.3: EOL. Use 3.5.x
- Svelte 4 reactivity ($: labels): Use Svelte 5 runes exclusively
- @inlang/paraglide-sveltekit: Replaced by @inlang/paraglide-js (framework-agnostic Vite plugin)
- tailwind.config.js: Not needed with Tailwind CSS 4

## Open Questions

1. **Spring Boot 3.5 vs 4.0?**
   - What we know: Boot 3.5 OSS support ends June 2026. Boot 4.0 is available (LTS). Architecture doc says "3.3+".
   - What's unclear: Whether to start with 3.5 (safer, more documentation) or go straight to 4.0 (longer support).
   - Recommendation: Start with Spring Boot 3.5.x. It's the last 3.x, well-documented, and migration to 4.0 can happen later. The STATE.md blocker mentions this.

2. **User preferences storage: JSONB column vs separate table?**
   - What we know: Preferences include theme, locale, currency, favorite categories. Architecture doc shows no dedicated preferences table.
   - What's unclear: Whether to add a `preferences JSONB` column on `users` table or create a `user_preferences` table.
   - Recommendation: Use a `preferences JSONB` column on the `users` table. For 2 users with simple key-value preferences, a separate table is over-engineering. The JSONB column allows flexible schema without migrations for new preferences.

3. **Account table needs additional columns for Phase 1 context decisions**
   - What we know: Context says accounts need: name, bank name, type, currency, initial balance, color. Architecture SQL schema has name, account_type, owner_id, institution_name but NOT currency, initial_balance, or color.
   - What's unclear: Schema needs extension.
   - Recommendation: Add `currency VARCHAR(3)`, `initial_balance DECIMAL(19,4)`, `color VARCHAR(7)` to the accounts table in Liquibase migrations.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (backend) | JUnit 5 + Testcontainers (via Spring Boot Test) |
| Framework (frontend) | Vitest + @testing-library/svelte |
| Config file (backend) | `pom.xml` (spring-boot-starter-test) -- Wave 0 |
| Config file (frontend) | `vite.config.ts` + `vitest.config.ts` -- Wave 0 |
| Quick run command (backend) | `cd prosperity-api && mvn test -pl . -Dtest=AuthServiceTest,AccountServiceTest -q` |
| Quick run command (frontend) | `cd prosperity-web && npx vitest run --reporter=verbose` |
| Full suite command | `cd prosperity-api && mvn verify -q && cd ../prosperity-web && npx vitest run` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Login with email/password returns JWT | integration | `mvn test -Dtest=AuthControllerTest#loginSuccess` | Wave 0 |
| AUTH-01 | Login with wrong password returns 401 | integration | `mvn test -Dtest=AuthControllerTest#loginFailure` | Wave 0 |
| AUTH-02 | Refresh token returns new access token | integration | `mvn test -Dtest=AuthControllerTest#refreshToken` | Wave 0 |
| AUTH-02 | Expired refresh token returns 401 | integration | `mvn test -Dtest=AuthControllerTest#expiredRefresh` | Wave 0 |
| AUTH-03 | Admin role can access /api/admin endpoints | integration | `mvn test -Dtest=AuthorizationTest#adminAccess` | Wave 0 |
| AUTH-03 | Standard role cannot access admin endpoints | integration | `mvn test -Dtest=AuthorizationTest#standardDenied` | Wave 0 |
| AUTH-04 | Update display name | unit | `mvn test -Dtest=UserServiceTest#updateProfile` | Wave 0 |
| AUTH-05 | Set preferences (theme, currency) | unit | `mvn test -Dtest=UserServiceTest#updatePreferences` | Wave 0 |
| ACCT-01 | Create personal account | integration | `mvn test -Dtest=AccountControllerTest#createPersonal` | Wave 0 |
| ACCT-01 | Create shared account | integration | `mvn test -Dtest=AccountControllerTest#createShared` | Wave 0 |
| ACCT-02 | Personal account not visible to other user | integration | `mvn test -Dtest=AccountControllerTest#personalVisibility` | Wave 0 |
| ACCT-03 | Shared account visible to both users | integration | `mvn test -Dtest=AccountControllerTest#sharedVisibility` | Wave 0 |
| INFR-01 | Docker Compose starts all services | smoke | `docker compose up -d && curl http://localhost:8080/actuator/health` | Wave 0 |
| INFR-02 | CI pipeline runs on push | manual-only | Check GitHub Actions workflow file exists | Wave 0 |
| INFR-03 | Security headers present in responses | integration | `mvn test -Dtest=SecurityHeadersTest` | Wave 0 |
| INFR-04 | Passwords stored as bcrypt hashes | unit | `mvn test -Dtest=UserServiceTest#passwordBcrypted` | Wave 0 |

### Sampling Rate

- **Per task commit:** Backend: `mvn test -q` / Frontend: `npx vitest run`
- **Per wave merge:** Full suite: `mvn verify && npx vitest run`
- **Phase gate:** Full suite green + Docker Compose smoke test before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `prosperity-api/pom.xml` -- Maven project with spring-boot-starter-test, Testcontainers PostgreSQL
- [ ] `prosperity-api/src/test/java/.../auth/AuthControllerTest.java` -- covers AUTH-01, AUTH-02
- [ ] `prosperity-api/src/test/java/.../auth/AuthorizationTest.java` -- covers AUTH-03
- [ ] `prosperity-api/src/test/java/.../user/UserServiceTest.java` -- covers AUTH-04, AUTH-05, INFR-04
- [ ] `prosperity-api/src/test/java/.../account/AccountControllerTest.java` -- covers ACCT-01, ACCT-02, ACCT-03
- [ ] `prosperity-api/src/test/java/.../SecurityHeadersTest.java` -- covers INFR-03
- [ ] `prosperity-web/vitest.config.ts` -- Vitest configuration
- [ ] `prosperity-web/src/routes/(auth)/login/login.test.ts` -- Login page component test

## Sources

### Primary (HIGH confidence)
- `docs/architecture.md` -- Full backend and frontend architecture, DB schema, conventions
- `docs/prd.md` -- Product requirements, tech stack, quality tools
- `.planning/phases/01-foundation/01-CONTEXT.md` -- User decisions for Phase 1
- `.planning/REQUIREMENTS.md` -- Requirement IDs and descriptions
- [Spring Boot Support Policy](https://spring.io/support-policy/) -- EOL dates for 3.3, 3.4, 3.5
- [Spring Boot endoflife.date](https://endoflife.date/spring-boot) -- Version support timelines
- [Tailwind CSS SvelteKit Guide](https://tailwindcss.com/docs/guides/sveltekit) -- Official Vite plugin setup
- [Paraglide Svelte CLI Docs](https://svelte.dev/docs/cli/paraglide) -- Official Svelte integration reference
- [SvelteKit Docs - Web Standards](https://kit.svelte.dev/docs/web-standards) -- Fetch, cookies in server context

### Secondary (MEDIUM confidence)
- [Paraglide JS - Sveltekit | inlang](https://inlang.com/m/dxnzrydw/paraglide-sveltekit-i18n/) -- Paraglide 2.0 setup guide
- [SvelteKit Paraglide 2.0 Migration Guide](https://dropanote.de/en/blog/20250506-paraglide-migration-2-0-sveltekit/) -- Paraglide 2.0 changes
- [Tailwind CSS v4 SvelteKit Vite Plugin Setup](https://dev.to/fedor-pasynkov/setting-up-tailwind-css-v4-in-sveltekit-the-vite-plugin-way-a-guide-based-on-real-issues-380n) -- Real-world setup issues
- [java-uuid-generator GitHub](https://github.com/cowtowncoder/java-uuid-generator) -- JUG 5.x with UUIDv7 support
- [SvelteKit route protection discussion](https://github.com/sveltejs/kit/discussions/3911) -- hooks.server.ts auth guard patterns
- [SvelteKit cookie handling with external APIs](https://github.com/sveltejs/kit/discussions/5172) -- BFF cookie forwarding

### Tertiary (LOW confidence)
- Spring Boot 4.0 migration path -- Not yet researched in depth; flagged for future phase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries are documented in architecture doc and verified current
- Architecture: HIGH -- Detailed architecture doc exists with code examples and conventions
- Pitfalls: HIGH -- Well-known patterns (BFF cookies, FOUC, Liquibase IDs) from multiple sources
- i18n choice (Paraglide): MEDIUM -- Referenced in official Svelte docs but Paraglide 2.0 is relatively new
- Spring Boot version: MEDIUM -- Architecture doc says 3.3+ but 3.3 is EOL; recommending 3.5.x

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (30 days -- mature stack, stable libraries)
