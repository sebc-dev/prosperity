# Phase 2: Authentication & Setup Wizard - Research

**Researched:** 2026-03-30
**Domain:** Spring Security 7 session-based auth + Angular 21 SPA auth flow
**Confidence:** HIGH

## Summary

This phase implements first-launch admin setup, session-based authentication with httpOnly cookies, CSRF protection, and the Angular layout shell. The backend uses Spring Security 7 with Spring Session JDBC (PostgreSQL-backed sessions) and a custom REST controller for JSON-based login (not form-based). The frontend uses Angular 21 functional route guards, HTTP interceptors for CSRF/401 handling, and PrimeNG components per the approved UI spec.

The key architectural decision is using a **REST controller login endpoint** instead of Spring Security's built-in `formLogin()`. The `formLogin()` DSL expects form-encoded parameters and redirect-based flows, which are incompatible with a JSON SPA. Instead, we inject `AuthenticationManager` into a controller, authenticate programmatically, and save the `SecurityContext` to `HttpSessionSecurityContextRepository`. This is the standard BFF (Backend for Frontend) cookie pattern.

**Primary recommendation:** Use `spring-boot-starter-security` + `spring-session-jdbc` with Flyway-managed session tables, a custom `AuthController` for JSON login/logout/setup endpoints, and `.csrf((csrf) -> csrf.spa())` for automatic Angular XSRF-TOKEN integration.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Wizard collects admin-only info: email, password, display name. No app config (currency, household name) -- those belong in a future settings phase.
- **D-02:** First-launch detection via `COUNT(*) = 0` on users table. No separate flag table.
- **D-03:** After admin creation, redirect to login page (no auto-login). Clear separation between setup and auth flows.
- **D-04:** Setup endpoint must be locked once an admin exists -- 409 Conflict if users already in DB.
- **D-05:** 30-minute idle timeout. Session expires after 30 min of inactivity.
- **D-06:** Spring Session JDBC -- sessions stored in PostgreSQL. Survives server restarts.
- **D-07:** BFF cookie flow: httpOnly session cookie, no JWT client-side. Spring Security 7 CookieCsrfTokenRepository for Angular XSRF-TOKEN compatibility.
- **D-08:** No "remember me" in this phase -- single session duration policy.
- **D-09:** Login and setup pages are full-screen centered, outside the layout shell. Clean, professional pattern.
- **D-10:** Minimal layout shell for authenticated pages: header with app title + logout button. Sidebar prepared (empty) for future phases.
- **D-11:** Post-login redirects to /dashboard with placeholder: "Bienvenue [display_name]" inside the layout shell. Validates end-to-end auth flow.
- **D-12:** Generic error message on login failure: "Identifiants invalides" -- no distinction between wrong email and wrong password. Prevents user enumeration.
- **D-13:** No rate limiting or account lockout in this phase. Self-hosted app, not publicly exposed. Deferred to backlog.
- **D-14:** Password validation at creation: OWASP rules -- min 12 chars, at least 1 uppercase, 1 digit, 1 special character. Enforced both backend (validation) and frontend (real-time feedback).

### Claude's Discretion
- Password hashing algorithm choice (bcrypt recommended by Spring Security default)
- Exact CSRF token exchange mechanism details (Spring Security 7 defaults)
- Loading states and transition animations
- Exact Tailwind/PrimeNG styling for login/setup forms
- Angular route guard implementation details

### Deferred Ideas (OUT OF SCOPE)
- Rate limiting / account lockout -- backlog, add when app is exposed publicly
- "Remember me" extended sessions -- future enhancement
- App configuration wizard (currency, household name) -- future settings phase
- Password reset flow -- separate phase
- Multi-user invitation -- separate phase
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Premier lancement affiche un setup wizard pour creer le compte administrateur | Setup endpoint (`POST /api/auth/setup`) locked by D-02/D-04; Angular `/setup` route with `noAdminGuard`; backend `SetupService` with `userRepository.count() == 0` check |
| AUTH-02 | Utilisateur peut se connecter avec email et mot de passe (BFF cookie flow, cookies httpOnly) | Custom `AuthController` with `AuthenticationManager.authenticate()`, `HttpSessionSecurityContextRepository` saves context, Spring Session JDBC persists to PostgreSQL |
| AUTH-03 | Utilisateur peut se deconnecter depuis n'importe quelle page | `POST /api/auth/logout` endpoint + Spring Security `.logout()` config; Angular layout shell with logout button on every authenticated page |
| AUTH-04 | Session utilisateur persiste apres rafraichissement du navigateur | Spring Session JDBC stores session in PostgreSQL; `GET /api/auth/me` endpoint returns current user; Angular `APP_INITIALIZER` checks session on bootstrap |
| AUTH-05 | Protection CSRF active sur tous les endpoints mutatifs | `.csrf((csrf) -> csrf.spa())` configures CookieCsrfTokenRepository + BREACH protection; Angular `provideHttpClient(withXsrfConfiguration())` reads XSRF-TOKEN cookie automatically |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Open source:** All deps must be MIT or Apache 2.0 -- Spring Security (Apache 2.0), Spring Session (Apache 2.0) both compliant
- **Self-hosted:** No cloud auth services -- session-based auth with PostgreSQL is fully self-contained
- **Java 21 LTS:** Checkstyle compatible, no Java 25 features
- **Spring Boot 4.0.x:** Parent POM already at 4.0.5
- **Layered by feature:** All auth code in `com.prosperity.auth` package
- **No Lombok:** Use Java 21 records for DTOs, manual code for entities
- **google-java-format:** Enforced via Spotless plugin
- **Testing principles:** AAA structure, FIRST properties, test doubles rules from `.claude/rules/testing-principles.md`

## Standard Stack

### Core (New Dependencies for Phase 2)

| Library | Artifact | Purpose | Why Standard |
|---------|----------|---------|--------------|
| Spring Security 7.0.x | `spring-boot-starter-security` | Auth, CSRF, session management | Managed by Boot 4.0.5 parent. Apache 2.0. |
| Spring Session JDBC | `spring-session-jdbc` | PostgreSQL-backed sessions | Auto-configured by Boot when on classpath. Apache 2.0. |
| Spring Security Test | `spring-security-test` | MockMvc security testing | `@WithMockUser`, CSRF test support. Apache 2.0. Scope: test. |

### Already Present (from Phase 1)
| Library | Purpose |
|---------|---------|
| Spring Boot Starter Web | REST controllers |
| Spring Boot Starter Data JPA | User entity/repository |
| Spring Boot Starter Validation | Bean validation (password rules) |
| Flyway | Database migrations |
| PostgreSQL | Database driver |
| Angular 21 | Frontend SPA |
| PrimeNG 21.x | UI components |
| Tailwind CSS v4 | Styling |
| Vitest | Frontend testing |

### Frontend (No New Dependencies)
Angular's `@angular/common/http` already includes XSRF support. `@angular/router` provides guards. `@angular/forms` provides reactive forms. All already in `package.json`.

**Installation (backend only):**
```xml
<!-- Add to pom.xml dependencies -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-jdbc</artifactId>
</dependency>
<!-- Test scope -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

No version numbers needed -- managed by `spring-boot-starter-parent 4.0.5`.

## Architecture Patterns

### Backend Package Structure
```
com.prosperity.auth/
    User.java              # (exists) JPA entity
    Role.java              # (exists) Enum
    UserRepository.java    # (exists) Spring Data
    AuthController.java    # NEW: REST endpoints (login, logout, setup, me)
    AuthService.java       # NEW: Business logic (setup, current user)
    SetupRequest.java      # NEW: Record DTO for setup wizard
    LoginRequest.java      # NEW: Record DTO for login
    UserResponse.java      # NEW: Record DTO for API response (no password hash)
    SecurityConfig.java    # NEW: SecurityFilterChain bean
    CustomUserDetailsService.java # NEW: Loads User by email for Spring Security
```

### Frontend Structure
```
src/app/
    app.ts                 # (exists) Updated: router-outlet
    app.routes.ts          # (exists) Updated: route definitions
    app.config.ts          # (exists) Updated: provideHttpClient, withXsrfConfiguration
    auth/
        login.ts           # NEW: Login page component
        setup.ts           # NEW: Setup wizard component
        auth.service.ts    # NEW: AuthService (login, logout, setup, me)
        auth.guard.ts      # NEW: authGuard, unauthenticatedGuard, noAdminGuard
        auth.interceptor.ts# NEW: 401 handler interceptor
    layout/
        layout.ts          # NEW: Layout shell (header + sidebar + router-outlet)
        header.ts          # NEW: Header with app title + logout
        sidebar.ts         # NEW: Empty sidebar placeholder
    dashboard/
        dashboard.ts       # NEW: Placeholder dashboard
```

### Pattern 1: REST Controller Login (BFF Cookie Flow)

**What:** Custom REST controller that accepts JSON credentials, authenticates via `AuthenticationManager`, and saves the `SecurityContext` to the session.

**When to use:** When the frontend is a SPA that sends JSON, not form-encoded data. This is the standard BFF pattern for Spring Security + Angular.

**Why not formLogin():** Spring Security's `formLogin()` DSL expects `application/x-www-form-urlencoded` parameters and redirect-based flows. It cannot parse JSON request bodies without a custom filter. A controller is simpler and more explicit.

**Example:**
```java
// Source: Spring Security official docs - Persisting Authentication
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository =
        new HttpSessionSecurityContextRepository();

    @PostMapping("/login")
    public ResponseEntity<UserResponse> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest httpRequest,
            HttpServletResponse httpResponse) {
        var token = UsernamePasswordAuthenticationToken.unauthenticated(
            request.email(), request.password());
        var authentication = authenticationManager.authenticate(token);

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        securityContextRepository.saveContext(context, httpRequest, httpResponse);

        var user = (CustomUserDetails) authentication.getPrincipal();
        return ResponseEntity.ok(new UserResponse(user.displayName(), user.email()));
    }
}
```

### Pattern 2: Spring Security 7 `.csrf().spa()` for Angular

**What:** Single-line CSRF configuration that sets up `CookieCsrfTokenRepository` (XSRF-TOKEN cookie, httpOnly=false) with BREACH protection via `XorCsrfTokenRequestAttributeHandler` and deferred token loading.

**When to use:** Any SPA frontend (Angular, React, Vue) that reads the CSRF token from a cookie.

**Example:**
```java
// Source: Spring Security 7.0.x CSRF docs
@Bean
public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .csrf(csrf -> csrf.spa())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/auth/login", "/api/auth/setup", "/api/auth/status").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/auth/me").permitAll()
            .anyRequest().authenticated()
        )
        .logout(logout -> logout
            .logoutUrl("/api/auth/logout")
            .logoutSuccessHandler((req, res, auth) -> res.setStatus(200))
        )
        .sessionManagement(session -> session
            .maximumSessions(1)
        )
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint((req, res, authEx) ->
                res.sendError(HttpServletResponse.SC_UNAUTHORIZED))
        );
    return http.build();
}
```

### Pattern 3: Angular Functional Route Guards

**What:** Standalone functions (no class boilerplate) using `inject()` to access services. The modern Angular pattern since v15+.

**Example:**
```typescript
// Source: Angular official docs - Route Guards
import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';
import { map } from 'rxjs';

export const authGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  return authService.isAuthenticated$.pipe(
    map(isAuth => isAuth || router.createUrlTree(['/login']))
  );
};
```

### Pattern 4: Angular HTTP Interceptor for 401 Handling

**What:** Functional interceptor that catches 401 responses and redirects to login.

**Example:**
```typescript
// Source: Angular official docs - Interceptors
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  return next(req).pipe(
    catchError(error => {
      if (error.status === 401) {
        router.navigate(['/login']);
      }
      return throwError(() => error);
    })
  );
};
```

### Pattern 5: Spring Session JDBC Tables via Flyway

**What:** Manage Spring Session tables through Flyway instead of Spring's auto-initialization. This avoids conflicts with Flyway's schema validation and keeps all schema changes in one place.

**Why:** The project uses `spring.jpa.hibernate.ddl-auto=validate` and Flyway for all migrations. Spring Session's `initialize-schema=embedded` would bypass Flyway and cause validation confusion. A Flyway migration is the clean approach.

**Example:**
```sql
-- V008__create_spring_session_tables.sql
-- Source: org/springframework/session/jdbc/schema-postgresql.sql
CREATE TABLE SPRING_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT SPRING_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);

CREATE UNIQUE INDEX SPRING_SESSION_IX1 ON SPRING_SESSION (SESSION_ID);
CREATE INDEX SPRING_SESSION_IX2 ON SPRING_SESSION (EXPIRY_TIME);
CREATE INDEX SPRING_SESSION_IX3 ON SPRING_SESSION (PRINCIPAL_NAME);

CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BYTEA NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID) REFERENCES SPRING_SESSION(PRIMARY_ID) ON DELETE CASCADE
);
```

### Anti-Patterns to Avoid

- **formLogin() for SPA:** Expects form-encoded params and redirects. Use a custom REST controller instead.
- **JWT in browser storage:** Violates D-07. Use httpOnly session cookies.
- **Auto-login after setup:** Violates D-03. Redirect to login page after admin creation.
- **Checking `role = ADMIN` for first-launch:** Violates D-02. Use `userRepository.count() == 0`.
- **Spring Session `initialize-schema=always`:** Conflicts with Flyway. Use a Flyway migration for session tables.
- **Class-based route guards:** Deprecated pattern. Use `CanActivateFn` functional guards.
- **HttpClientXsrfModule:** Deprecated. Use `provideHttpClient(withXsrfConfiguration())`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom hashing | `BCryptPasswordEncoder` (Spring Security default) | Bcrypt handles salting, work factor. Spring Security default via `PasswordEncoderFactories.createDelegatingPasswordEncoder()` |
| Session management | Custom session table/logic | Spring Session JDBC | Handles expiry, cleanup cron, concurrent sessions, session fixation |
| CSRF token exchange | Manual token endpoint | `.csrf(csrf -> csrf.spa())` | Handles BREACH protection, deferred loading, cookie lifecycle automatically |
| XSRF header injection | Manual Angular interceptor | `withXsrfConfiguration()` | Angular's built-in XSRF interceptor reads XSRF-TOKEN cookie and sets X-XSRF-TOKEN header automatically |
| Session cookie config | Manual cookie settings | Spring Session + Spring Security defaults | httpOnly, secure, SameSite configured by framework |
| Auth entry point | Custom 401 filter | `.exceptionHandling()` with custom `AuthenticationEntryPoint` | Returns 401 JSON instead of redirect for SPA |

**Key insight:** Spring Security 7's `.csrf().spa()` is the single most important "don't hand-roll" item. It replaces ~30 lines of manual CSRF configuration with one method call and handles BREACH protection, which is easy to get wrong manually.

## Common Pitfalls

### Pitfall 1: SecurityContext Not Saved After Programmatic Login
**What goes wrong:** After `authenticationManager.authenticate()`, the session cookie is not set because the SecurityContext was not explicitly saved.
**Why it happens:** In Spring Security 7, `requireExplicitSave` is `true` by default. The SecurityContext is NOT automatically persisted to the session.
**How to avoid:** Always call `securityContextRepository.saveContext(context, request, response)` after setting the authentication in the controller.
**Warning signs:** Login returns 200 but subsequent requests return 401.

### Pitfall 2: CSRF Token Not Available on First Request
**What goes wrong:** Angular's first mutating request (e.g., POST /api/auth/login) fails with 403 because no XSRF-TOKEN cookie exists yet.
**Why it happens:** The CSRF cookie is only set after a GET request loads the SPA. If the SPA makes a POST before any GET to the backend, there's no token.
**How to avoid:** Exempt `/api/auth/login` and `/api/auth/setup` from CSRF protection via `.csrf(csrf -> csrf.spa().ignoringRequestMatchers("/api/auth/login", "/api/auth/setup"))` OR ensure a GET request (like `/api/auth/status`) fires before login. The `.spa()` config uses deferred tokens which helps, but login/setup should still be exempt since the user has no session yet.
**Warning signs:** 403 Forbidden on login POST with "CSRF token missing" in logs.

### Pitfall 3: Flyway + Spring Session Schema Conflict
**What goes wrong:** Spring Session's `initialize-schema` tries to create tables that Flyway already manages, or Flyway validation fails because tables were created outside its control.
**Why it happens:** Two systems trying to manage the same schema.
**How to avoid:** Set `spring.session.jdbc.initialize-schema=never` and create session tables via a Flyway migration.
**Warning signs:** Flyway validation errors on startup, or duplicate table creation attempts.

### Pitfall 4: Angular HttpClient Not Sending Cookies
**What goes wrong:** Angular's HttpClient doesn't include the session cookie in requests to the API.
**Why it happens:** In development, the Angular dev server runs on port 4200 and the API on port 8080 -- different origins. Cookies are not sent cross-origin by default.
**How to avoid:** Configure Angular's proxy (`proxy.conf.json`) to forward `/api/*` to the backend during development. In production, Caddy handles this at the reverse proxy level.
**Warning signs:** Authenticated requests return 401 despite successful login.

### Pitfall 5: Logout Not Clearing Session Cookie
**What goes wrong:** After logout, the browser still has the old session cookie and it gets resubmitted.
**Why it happens:** `invalidateHttpSession(true)` invalidates the server-side session but doesn't always clear the client cookie.
**How to avoid:** Configure `.logout()` with `deleteCookies("SESSION")` (Spring Session uses "SESSION" as the default cookie name, not "JSESSIONID").
**Warning signs:** After logout, refreshing the page shows stale auth state.

### Pitfall 6: Password Validation Mismatch Frontend/Backend
**What goes wrong:** Frontend allows passwords that backend rejects, or vice versa.
**Why it happens:** Regex patterns or rules defined in two places that drift apart.
**How to avoid:** Define the password validation rules as constants/utility shared within each layer. Backend is the source of truth -- frontend validation is UX convenience only.
**Warning signs:** Setup form submits successfully on frontend but returns 400 from backend.

## Code Examples

### DTO Records (Java 21)

```java
// No Lombok -- Java 21 records per CLAUDE.md
public record SetupRequest(
    @NotBlank @Email String email,
    @NotBlank @Size(min = 12) String password,
    @NotBlank @Size(min = 2, max = 100) String displayName
) {}

public record LoginRequest(
    @NotBlank @Email String email,
    @NotBlank String password
) {}

public record UserResponse(
    String displayName,
    String email,
    String role
) {}
```

### CustomUserDetailsService

```java
// Source: Spring Security docs - UserDetailsService
@Service
public class CustomUserDetailsService implements UserDetailsService {

    private final UserRepository userRepository;

    public CustomUserDetailsService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Override
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        var user = userRepository.findByEmail(email)
            .orElseThrow(() -> new UsernameNotFoundException("User not found"));
        return org.springframework.security.core.userdetails.User.builder()
            .username(user.getEmail())
            .password(user.getPasswordHash())
            .roles(user.getRole().name())
            .build();
    }
}
```

### PasswordEncoder Bean

```java
// Spring Security recommends DelegatingPasswordEncoder (bcrypt as default)
@Bean
public PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

### AuthenticationManager Bean

```java
// Required for programmatic authentication in the controller
@Bean
public AuthenticationManager authenticationManager(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {
    var provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return new ProviderManager(provider);
}
```

### Angular App Config with HttpClient + XSRF

```typescript
// Source: Angular docs - provideHttpClient, withXsrfConfiguration
import { provideHttpClient, withXsrfConfiguration, withInterceptors } from '@angular/common/http';
import { authInterceptor } from './auth/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(
      withXsrfConfiguration({ cookieName: 'XSRF-TOKEN', headerName: 'X-XSRF-TOKEN' }),
      withInterceptors([authInterceptor])
    ),
  ],
};
```

### Angular Auth Service

```typescript
import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, of } from 'rxjs';

interface UserResponse {
  displayName: string;
  email: string;
  role: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private currentUser = signal<UserResponse | null>(null);

  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  readonly user = computed(() => this.currentUser());

  constructor(private http: HttpClient) {}

  checkSession(): Observable<UserResponse | null> {
    return this.http.get<UserResponse>('/api/auth/me').pipe(
      tap(user => this.currentUser.set(user)),
      catchError(() => {
        this.currentUser.set(null);
        return of(null);
      })
    );
  }

  login(email: string, password: string): Observable<UserResponse> {
    return this.http.post<UserResponse>('/api/auth/login', { email, password }).pipe(
      tap(user => this.currentUser.set(user))
    );
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/auth/logout', {}).pipe(
      tap(() => this.currentUser.set(null))
    );
  }
}
```

### Application.yml Session Configuration

```yaml
spring:
  session:
    jdbc:
      initialize-schema: never  # Flyway manages schema
      table-name: SPRING_SESSION
  # Session timeout (D-05: 30 minutes)
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
        name: SESSION
```

### Angular Proxy Config (Development)

```json
// proxy.conf.json -- forward /api to Spring Boot in dev
{
  "/api": {
    "target": "http://localhost:8080",
    "secure": false
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `formLogin()` for SPA | Custom REST controller + `AuthenticationManager` | Spring Security 6+ | JSON login, no redirects |
| `HttpClientXsrfModule` | `provideHttpClient(withXsrfConfiguration())` | Angular 17+ | Standalone API, no NgModule |
| Class-based guards `CanActivate` | `CanActivateFn` functional guards | Angular 15.2+ | Less boilerplate, inject() |
| Manual CSRF cookie config | `.csrf(csrf -> csrf.spa())` | Spring Security 6.4+ | One-line SPA CSRF setup |
| `SecurityContextPersistenceFilter` | `SecurityContextHolderFilter` + explicit save | Spring Security 6+ | Must explicitly save context |
| `JSESSIONID` cookie | `SESSION` cookie (Spring Session) | Spring Session 1.x+ | Customizable session cookie |

## Open Questions

1. **Spring Session cleanup cron**
   - What we know: Spring Session JDBC has a cleanup cron for expired sessions (default: every minute)
   - What's unclear: Whether the default cron is appropriate or should be tuned for a low-traffic self-hosted app
   - Recommendation: Use the default. Low-traffic means low session count; cleanup overhead is negligible.

2. **`DelegatingPasswordEncoder` vs plain `BCryptPasswordEncoder`**
   - What we know: `DelegatingPasswordEncoder` prefixes hashes with `{bcrypt}` and allows future migration to different algorithms. Plain `BCryptPasswordEncoder` stores raw bcrypt hashes.
   - What's unclear: Whether the `{bcrypt}` prefix in the password_hash column is acceptable
   - Recommendation: Use `DelegatingPasswordEncoder` (Spring Security default). The prefix is a best practice that allows future algorithm migration without a database migration. The `password_hash` column is VARCHAR(255) which accommodates the prefix.

3. **Angular dev proxy configuration**
   - What we know: No `proxy.conf.json` exists yet. Angular dev server on :4200, API on :8080.
   - What's unclear: Whether the proxy should be configured in `angular.json` or as a separate file
   - Recommendation: Create `proxy.conf.json` and reference it in `angular.json` serve config with `"proxyConfig": "proxy.conf.json"`. This is the standard Angular pattern.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (backend) | JUnit 5 + AssertJ + Spring Boot Test (via `spring-boot-starter-test`) |
| Framework (frontend) | Vitest 4.x (via `@angular/build:unit-test`) |
| Config file (backend) | Maven Surefire (default) |
| Config file (frontend) | Vitest config embedded in Angular build |
| Quick run (backend) | `./mvnw test -pl backend -Dtest=AuthControllerTest` |
| Quick run (frontend) | `cd frontend && pnpm test` |
| Full suite | `./mvnw verify && cd frontend && pnpm test` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Setup wizard creates admin | integration | `./mvnw test -Dtest=AuthControllerTest#setup*` | Wave 0 |
| AUTH-01 | Setup locked after admin exists (409) | integration | `./mvnw test -Dtest=AuthControllerTest#setup*already*` | Wave 0 |
| AUTH-02 | Login with valid credentials returns 200 + cookie | integration | `./mvnw test -Dtest=AuthControllerTest#login*` | Wave 0 |
| AUTH-02 | Login with bad credentials returns 401 | integration | `./mvnw test -Dtest=AuthControllerTest#login*invalid*` | Wave 0 |
| AUTH-03 | Logout invalidates session | integration | `./mvnw test -Dtest=AuthControllerTest#logout*` | Wave 0 |
| AUTH-04 | GET /me returns user when authenticated | integration | `./mvnw test -Dtest=AuthControllerTest#me*` | Wave 0 |
| AUTH-05 | POST without CSRF token returns 403 | integration | `./mvnw test -Dtest=SecurityConfigTest#csrf*` | Wave 0 |
| AUTH-01 | Password validation rules enforced | unit | `./mvnw test -Dtest=AuthServiceTest#setup*password*` | Wave 0 |
| AUTH-02 | Angular login form submits and redirects | unit (Vitest) | `pnpm test -- --reporter=verbose` | Wave 0 |

### Sampling Rate
- **Per task commit:** `./mvnw test -Dtest=AuthControllerTest,AuthServiceTest,SecurityConfigTest`
- **Per wave merge:** `./mvnw verify && cd frontend && pnpm test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `AuthControllerTest.java` -- integration tests for login/logout/setup/me endpoints (MockMvc + `@SpringBootTest`)
- [ ] `AuthServiceTest.java` -- unit tests for setup logic, password validation
- [ ] `SecurityConfigTest.java` -- CSRF enforcement, unauthenticated access returns 401
- [ ] `CustomUserDetailsServiceTest.java` -- user loading, not-found case
- [ ] Frontend: `auth.service.spec.ts` -- login/logout/checkSession
- [ ] Frontend: `auth.guard.spec.ts` -- guard redirect logic
- [ ] `spring-security-test` dependency needed in pom.xml

## Sources

### Primary (HIGH confidence)
- [Spring Security 7.0.x CSRF docs](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) -- `.csrf().spa()` config, CookieCsrfTokenRepository, BREACH protection
- [Spring Security 7.0.x Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) -- session fixation, concurrent sessions, timeout
- [Spring Security 7.0.x Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html) -- `requireExplicitSave`, SecurityContextRepository
- [Spring Session JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html) -- PostgreSQL schema, auto-config, cleanup cron
- [Spring Session Boot JDBC Guide](https://docs.spring.io/spring-session/reference/guides/boot-jdbc.html) -- Maven dependency, application properties
- [Angular Route Guards](https://angular.dev/guide/routing/route-guards) -- `CanActivateFn`, functional guards
- [Angular HTTP Interceptors](https://angular.dev/guide/http/interceptors) -- `HttpInterceptorFn`, `withInterceptors`
- [Angular withXsrfConfiguration](https://angular.dev/api/common/http/withXsrfConfiguration) -- XSRF cookie/header config
- [Angular provideHttpClient](https://angular.dev/api/common/http/provideHttpClient) -- standalone HttpClient providers
- [CookieCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/csrf/CookieCsrfTokenRepository.html) -- XSRF-TOKEN cookie, X-XSRF-TOKEN header

### Secondary (MEDIUM confidence)
- [Spring Security Logout docs](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) -- logout handlers, cookie clearing
- [Baeldung Spring Session JDBC](https://www.baeldung.com/spring-session-jdbc) -- practical setup examples
- [Spring Security Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html) -- DelegatingPasswordEncoder, BCrypt

### Tertiary (LOW confidence)
- [Spring Security issue #10966](https://github.com/spring-projects/spring-security/issues/10966) -- JSON login not natively supported by formLogin, confirming custom controller approach

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Spring Security 7 + Spring Session JDBC are well-documented, managed by Boot 4.0.5 parent
- Architecture: HIGH -- BFF cookie pattern is the documented approach for SPA + Spring Security. Custom controller login is the standard workaround for JSON login.
- Pitfalls: HIGH -- All pitfalls identified from official docs and known issues. CSRF `.spa()` pitfall and explicit context save are the most critical.

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable ecosystem, no breaking changes expected)
