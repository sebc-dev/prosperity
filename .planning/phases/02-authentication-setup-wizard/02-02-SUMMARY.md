---
phase: 02-authentication-setup-wizard
plan: 02
subsystem: auth
tags: [spring-security, csrf, spa, bcrypt, dto, userdetails]

# Dependency graph
requires:
  - phase: 02-01
    provides: User entity, Role enum, UserRepository, Flyway migration, session config
provides:
  - SecurityFilterChain with CSRF SPA mode and endpoint authorization
  - PasswordEncoder and AuthenticationManager beans
  - CustomUserDetailsService bridging UserRepository to Spring Security
  - SetupRequest, LoginRequest, UserResponse DTO records
affects: [02-03-auth-controller, 02-04-auth-tests, 02-06-angular-auth]

# Tech tracking
tech-stack:
  added: []
  patterns: [CSRF SPA mode for Angular, DelegatingPasswordEncoder, DaoAuthenticationProvider, Java records for DTOs]

key-files:
  created:
    - backend/src/main/java/com/prosperity/auth/SecurityConfig.java
    - backend/src/main/java/com/prosperity/auth/CustomUserDetailsService.java
    - backend/src/main/java/com/prosperity/auth/SetupRequest.java
    - backend/src/main/java/com/prosperity/auth/LoginRequest.java
    - backend/src/main/java/com/prosperity/auth/UserResponse.java
  modified: []

key-decisions:
  - "CSRF SPA mode with ignoringRequestMatchers for login/setup POST endpoints"
  - "DelegatingPasswordEncoder for future algorithm migration (bcrypt default)"
  - "GET /api/auth/me permitAll to allow session check without 302 redirect"

patterns-established:
  - "Java 21 records for DTOs with jakarta.validation annotations"
  - "Custom authenticationEntryPoint returning 401 instead of redirect for SPA"
  - "SESSION cookie deletion on logout (Spring Session JDBC naming)"

requirements-completed: [AUTH-02, AUTH-03, AUTH-05]

# Metrics
duration: 1min
completed: 2026-03-31
---

# Phase 02 Plan 02: Security Config and DTOs Summary

**Spring Security filter chain with CSRF SPA mode, auth DTOs with bean validation, and UserDetailsService bridging JPA to Spring Security**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-31T13:48:40Z
- **Completed:** 2026-03-31T13:49:50Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- SecurityFilterChain with CSRF SPA mode for Angular XSRF-TOKEN cookie compatibility
- Three DTO records (SetupRequest, LoginRequest, UserResponse) defining the auth API contract
- CustomUserDetailsService loading users by email from UserRepository
- PasswordEncoder (delegating/bcrypt) and AuthenticationManager beans ready for AuthController

## Task Commits

Each task was committed atomically:

1. **Task 1: Create DTO records for auth API contract** - `d496a66` (feat)
2. **Task 2: Create CustomUserDetailsService and SecurityConfig** - `5e26ef5` (feat)

## Files Created/Modified
- `backend/src/main/java/com/prosperity/auth/SetupRequest.java` - Setup wizard DTO with email, password (min 12, complexity), displayName validation
- `backend/src/main/java/com/prosperity/auth/LoginRequest.java` - Login DTO with email and password validation
- `backend/src/main/java/com/prosperity/auth/UserResponse.java` - Safe user response DTO (no password hash)
- `backend/src/main/java/com/prosperity/auth/CustomUserDetailsService.java` - Loads User by email, maps to Spring Security UserDetails
- `backend/src/main/java/com/prosperity/auth/SecurityConfig.java` - SecurityFilterChain, PasswordEncoder, AuthenticationManager beans

## Decisions Made
- CSRF SPA mode with `ignoringRequestMatchers` for login/setup POST endpoints (pre-auth endpoints cannot have CSRF token)
- `GET /api/auth/me` is `permitAll()` so the controller can return 401 JSON instead of Spring redirecting
- DelegatingPasswordEncoder chosen over direct BCryptPasswordEncoder for future algorithm migration
- Custom `authenticationEntryPoint` returns 401 instead of default 302 redirect (SPA pattern)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all code is fully wired to Spring Security infrastructure.

## Self-Check: PASSED

- All 5 created files exist on disk
- Both commit hashes (d496a66, 5e26ef5) found in git log

## Next Phase Readiness
- SecurityConfig, DTOs, and UserDetailsService are ready for AuthController (Plan 03)
- AuthenticationManager bean can be injected directly for programmatic login
- PasswordEncoder bean ready for password hashing in setup/registration

---
*Phase: 02-authentication-setup-wizard*
*Completed: 2026-03-31*
