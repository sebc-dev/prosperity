# Phase 2: Authentication & Setup Wizard - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Secure access to the application: first-launch admin creation via setup wizard, login/logout with session persistence, CSRF protection, and Angular layout shell. Rate limiting, multi-user invitation, and password reset are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Setup Wizard
- **D-01:** Wizard collects admin-only info: email, password, display name. No app config (currency, household name) — those belong in a future settings phase.
- **D-02:** First-launch detection via `COUNT(*) = 0` on users table. No separate flag table.
- **D-03:** After admin creation, redirect to login page (no auto-login). Clear separation between setup and auth flows.
- **D-04:** Setup endpoint must be locked once an admin exists — 409 Conflict if users already in DB.

### Session & Security
- **D-05:** 30-minute idle timeout. Session expires after 30 min of inactivity.
- **D-06:** Spring Session JDBC — sessions stored in PostgreSQL. Survives server restarts.
- **D-07:** BFF cookie flow: httpOnly session cookie, no JWT client-side. Spring Security 7 CookieCsrfTokenRepository for Angular XSRF-TOKEN compatibility.
- **D-08:** No "remember me" in this phase — single session duration policy.

### Auth Pages (UI)
- **D-09:** Login and setup pages are full-screen centered, outside the layout shell. Clean, professional pattern.
- **D-10:** Minimal layout shell for authenticated pages: header with app title + logout button. Sidebar prepared (empty) for future phases.
- **D-11:** Post-login redirects to /dashboard with placeholder: "Bienvenue [display_name]" inside the layout shell. Validates end-to-end auth flow.

### Error Responses
- **D-12:** Generic error message on login failure: "Identifiants invalides" — no distinction between wrong email and wrong password. Prevents user enumeration.
- **D-13:** No rate limiting or account lockout in this phase. Self-hosted app, not publicly exposed. Deferred to backlog.
- **D-14:** Password validation at creation: OWASP rules — min 12 chars, at least 1 uppercase, 1 digit, 1 special character. Enforced both backend (validation) and frontend (real-time feedback).

### Claude's Discretion
- Password hashing algorithm choice (bcrypt recommended by Spring Security default)
- Exact CSRF token exchange mechanism details (Spring Security 7 defaults)
- Loading states and transition animations
- Exact Tailwind/PrimeNG styling for login/setup forms
- Angular route guard implementation details

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. The setup wizard should feel minimal and professional (single-page form, not a multi-step wizard). Login page should be clean and finance-app appropriate.

</specifics>

<canonical_refs>
## Canonical References

### Architecture & patterns
- `docs/adr/0002-architecture-layered.md` — Layered by feature architecture, auth/ package location
- `.planning/PROJECT.md` §Technology Stack — Spring Security 7 BFF cookie flow, CookieCsrfTokenRepository

### Database schema
- `backend/src/main/resources/db/migration/V001__create_users.sql` — Existing users table (email, password_hash, display_name, role)

### Prior phase context
- `.planning/phases/01-project-foundation/01-CONTEXT.md` — D-15: layout shell deferred to Phase 2

### Testing principles
- `.claude/rules/testing-principles.md` — AAA structure, FIRST properties, test doubles rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `User` entity (`auth/User.java`): JPA entity with email, passwordHash, displayName, Role enum — ready to use
- `Role` enum (`auth/Role.java`): USER and ADMIN roles already defined
- `UserRepository` (`auth/UserRepository.java`): `findByEmail(String)` query method exists

### Established Patterns
- Layered by feature: `com.prosperity.auth` package for all auth-related code
- JPA entities with UUID primary keys, TIMESTAMPTZ for dates
- Flyway migrations: sequential V00X numbering
- Frontend: Angular standalone components, PrimeNG + Tailwind CSS v4
- No existing routing — `app.routes.ts` has empty routes array

### Integration Points
- Spring Security filter chain — new configuration needed (no security config exists yet)
- Spring Session JDBC — new dependency + auto-configured tables
- Angular HttpClient — interceptor for 401 handling and CSRF token
- Angular Router — guards for authenticated/unauthenticated routes
- `application.yml` — session and security configuration additions

</code_context>

<deferred>
## Deferred Ideas

- Rate limiting / account lockout — backlog, add when app is exposed publicly
- "Remember me" extended sessions — future enhancement
- App configuration wizard (currency, household name) — future settings phase
- Password reset flow — separate phase
- Multi-user invitation — separate phase

</deferred>

---

*Phase: 02-authentication-setup-wizard*
*Context gathered: 2026-03-29*
