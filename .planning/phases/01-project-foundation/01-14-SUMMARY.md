---
phase: 01-project-foundation
plan: 14
subsystem: infra
tags: [jacoco, coverage, maven, quality-gates]

requires:
  - phase: 01-project-foundation
    provides: JaCoCo plugin base config (report-only)
provides:
  - JaCoCo coverage threshold enforcement (INFR-08)
  - Build fails when instruction coverage < 70% or branch coverage < 50%
affects: [all-backend-plans]

tech-stack:
  added: []
  patterns: [jacoco-check-enforcement]

key-files:
  created: []
  modified: [backend/pom.xml]

key-decisions:
  - "INFR-08 requirement overrides D-08 decision: coverage thresholds now enforced (not report-only)"
  - "70% instruction / 50% branch thresholds: moderate to avoid blocking on JPA entity boilerplate"

patterns-established:
  - "JaCoCo BUNDLE-level enforcement: project-wide coverage check, not per-class"

requirements-completed: [INFR-08]

duration: 1min
completed: 2026-03-29
---

# Phase 01 Plan 14: JaCoCo Coverage Enforcement Summary

**JaCoCo check goal added to pom.xml enforcing 70% instruction / 50% branch coverage minimums on ./mvnw verify**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-29T12:15:13Z
- **Completed:** 2026-03-29T12:16:06Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added JaCoCo `check` execution bound to verify phase with BUNDLE-level coverage rules
- 70% instruction coverage minimum and 50% branch coverage minimum enforced
- Closes INFR-08 gap: `./mvnw verify` now fails build when coverage drops below thresholds

## Task Commits

Each task was committed atomically:

1. **Task 1: Add JaCoCo check execution with coverage threshold to pom.xml** - `b4c5350` (feat)

## Files Created/Modified
- `backend/pom.xml` - Added JaCoCo check execution with coverage threshold rules; updated comment to reference INFR-08

## Decisions Made
- INFR-08 requirement takes precedence over CONTEXT.md decision D-08 ("JaCoCo en mode reporting uniquement"). REQUIREMENTS.md explicitly mandates build failure on coverage threshold breach. VERIFICATION.md confirmed this as a gap.
- Set moderate thresholds (70% instruction, 50% branch) to avoid blocking builds on JPA entity boilerplate branches while still enforcing meaningful coverage.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None.

## Next Phase Readiness
- All Phase 01 quality gate infrastructure is now complete
- JaCoCo enforces coverage minimums alongside Checkstyle, Spotless, and OWASP dependency-check

---
*Phase: 01-project-foundation*
*Completed: 2026-03-29*
