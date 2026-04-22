# Phase 06 — Deferred Items

Out-of-scope discoveries found during plan execution. Not fixed here; filed for future cleanup.

## Pre-existing lint errors (observed during Plan 07 execution, 2026-04-22)

Confirmed present **before** Plan 07 began (verified by stashing Plan 07 changes and re-running `pnpm lint`).

- `frontend/src/app/transactions/transaction-dialog.ts:135` — `@typescript-eslint/no-inferrable-types` (string literal trivially inferred)
- `frontend/src/app/transactions/transactions.spec.ts:11` — `@typescript-eslint/no-unused-vars` (`makeTransaction` assigned but never used)
- `frontend/src/app/transactions/transactions.ts:237` — `@typescript-eslint/no-inferrable-types` (string literal trivially inferred)

These originated in Phase 5 (transactions) and are **out of scope** for Plan 07 (envelope frontend infrastructure) per the executor scope-boundary rule. Two of them are auto-fixable with `eslint --fix`. Recommended cleanup: a Phase 5 follow-up quick task or a broader lint-hygiene sweep.
