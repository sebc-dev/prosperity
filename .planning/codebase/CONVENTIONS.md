# Coding Conventions

**Analysis Date:** 2026-09-02

## Naming Patterns

### Files

**Backend (Python):**
- Modules: `snake_case.py` (e.g., `refresh_tokens.py`, `users.py`)
- Private/internal modules: Leading underscore `_password.py`, `_debts_helpers.py`
- Test files: `test_*.py` (e.g., `test_auth_rbac_dependencies.py`)
- Pattern: Descriptive, multi-word names use underscore separation

**Frontend (TypeScript/TSX):**
- Components: `kebab-case.tsx` (e.g., `theme-toggle.tsx`, `sync-status-badge.tsx`)
- Component exports within file: PascalCase (e.g., `export function ThemeToggle()`)
- Hooks: Mixed convention — newer hooks use kebab-case filenames (e.g., `use-account-balance.ts`) but some legacy hooks use camelCase (e.g., `useAuth.ts`)
  - **Guidance for new code:** Prefer kebab-case filenames with camelCase exports
- Utilities: `kebab-case.ts` (e.g., `token-store.ts`, `session.ts`)
- Test files: Same base name + `.test.tsx` or `.test.ts` (e.g., `theme-toggle.test.tsx`)
- Generated files: Not linted (e.g., `routeTree.gen.ts`, `schema.d.ts`)

### Functions & Methods

**Backend:**
- Functions: `snake_case` (e.g., `create_user()`, `verify_readonly()`, `hash_refresh_token()`)
- Async functions: Same convention, `async def snake_case()` (e.g., `async def issue()`)
- Private functions: Leading underscore `_function_name()` (e.g., `_docker_available()`)
- Class methods: Snake case, public/private by leading underscore

**Frontend:**
- React components: PascalCase (e.g., `ThemeToggle`, `AppLayout`, `SyncStatusBadge`)
- Hooks: camelCase (e.g., `useAuth()`, `useAccountBalance()`, `usePowerSync()`)
- Utility functions: camelCase (e.g., `cn()`, `decodeSub()`)
- Event handlers: `handle*` or `on*` pattern (e.g., `handleClick()`, `onToggle()`)
- Private/internal functions: Prefixed with underscore (e.g., `_docker_available()`)
- Factory functions in tests: `*Maker` pattern (e.g., `UserMaker = Callable[..., Awaitable[User]]`)

### Variables

**Backend:**
- Variables: `snake_case` (e.g., `token_hash`, `user_id`, `refresh_token_ttl_seconds`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `_TOKEN_ENTROPY_BYTES = 32`, `_EXPECTED_403_BODY`)
- Type aliases: PascalCase (e.g., `UserMaker = Callable[...]`)

**Frontend:**
- Variables: `camelCase` (e.g., `isAuthenticated`, `userId`, `matches`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `THEME_STORAGE_KEY`, `_EXPECTED_403_BODY`)
- Component props: PascalCase types, camelCase prop names (e.g., `interface ThemeToggleProps { theme: 'light' | 'dark' }`)

### Types

**Backend (Pydantic/SQLAlchemy):**
- Models: PascalCase (e.g., `User`, `RefreshToken`, `Household`)
- Exception classes: PascalCase ending in `Error` (e.g., `InvalidRefreshTokenError`, `RoleError`, `RevokedRefreshTokenError`)
- Enums: PascalCase (e.g., `UserRole`)
- Schemas/DTOs: PascalCase (e.g., `SetupRequest`, `TokenPair`)

**Frontend (TypeScript):**
- Types/interfaces: PascalCase (e.g., `RenderOptions`, `User`, `TokenPair`)
- Union types: Clear and explicit (e.g., `'authenticated' | 'none'`)
- Type utilities: Rarely used, when needed use descriptive names

## Code Style

### Formatting

**Backend (Python):**
- Tool: `ruff format`
- Line length: 100 characters
- Quotes: Double quotes (`"string"`)
- Indent: Spaces (4-space default, set in pyproject.toml)
- Trailing commas: Enabled

**Frontend (TypeScript/TSX):**
- Tool: `prettier`
- Line length: 100 characters
- Quotes: Single quotes (`'string'`)
- Semicolons: No (semi: false)
- Trailing commas: All positions
- Indent: Spaces (2-space default, Prettier sets this)
- Config: `client/.prettierrc`

### Linting

**Backend:**
- Tool: `ruff check`
- Config: `pyproject.toml` under `[tool.ruff.lint]`
- Active rules: E, F, I, UP, B, PL (see pyproject.toml for details)
- Import organization: Sorted by `ruff-isort` (rule I)
- Per-file ignores: Tests allow `PLR2004` (magic numbers)
- Type checking: `pyright` in strict mode on backend/ (standard on tests/ to avoid third-party stubs drowning signal)

**Frontend:**
- Tool: `eslint` v9 with `typescript-eslint`
- Config: `client/eslint.config.js`
- Active configs: Recommended JS + TypeScript type-checked
- React plugins: `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- Type checking: `projectService: true` (inline TypeScript checking)
- Exceptions:
  - Shadcn/ui components (`src/components/ui/`) have `react-refresh/only-export-components` disabled (some files mix component + utility exports)
  - Config files (`.js`) have type checking disabled
- Pre-commit hook verifies: `eslint . && prettier --check .`

## Import Organization

### Backend (Python)

**Order (enforced by ruff-isort):**
1. `__future__` imports (e.g., `from __future__ import annotations`)
2. Standard library (e.g., `import os`, `from datetime import datetime`)
3. Third-party (e.g., `from sqlalchemy import select`)
4. Local/first-party (`known-first-party = ["backend"]`)
   - Intra-module: `from backend.shared.db import get_db`
   - Sibling service: `from backend.modules.auth.public import User`

**Path aliases:**
- None — use full relative paths (`from backend.modules.auth.public import ...`)
- Import architecture enforced by `import-linter` contract (see `.importlinter` for cross-module rules)

### Frontend (TypeScript)

**Order (enforced by prettier + eslint):**
1. React/framework imports (e.g., `import { render } from '@testing-library/react'`)
2. Third-party libraries (e.g., `import { http, HttpResponse } from 'msw'`)
3. Local imports via aliases (e.g., `import { useAuth } from '@/hooks/useAuth'`)

**Path aliases (tsconfig.json):**
- `@/*` → `src/*` (main source code)
- `@tests/*` → `tests/*` (test utilities)
- Use these consistently; avoid relative `../../../` paths

**Type imports:**
- Separate type imports from value imports where it matters for performance (optional but common):
  ```typescript
  import type { ReactNode } from 'react'
  import { useEffect } from 'react'
  ```

## Error Handling

### Backend (Python)

**Custom Exceptions:**
- Define exception hierarchies for each domain (e.g., `backend/modules/auth/service/refresh_tokens.py`):
  ```python
  class InvalidRefreshTokenError(Exception):
      """Raised when a refresh token fails verification (unknown, expired, revoked)."""

  class ExpiredRefreshTokenError(InvalidRefreshTokenError):
      """Raised when the token's `expires_at` is in the past."""
  ```
- Use clear class names ending in `Error`
- Include docstrings explaining when/why raised
- Inherit from standard Python exceptions or domain-specific base classes

**Error Propagation:**
- FastAPI routes let exceptions bubble up to middleware (logging/formatting handled by framework)
- Async functions use `try/except` for context cleanup (e.g., rollback in `get_db`):
  ```python
  async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
      async with sessionmaker() as session:
          try:
              yield session
              await session.commit()
          except Exception:
              await session.rollback()
              raise
  ```
- `session.flush()` is called inside helper functions (not route-level) to surface integrity errors immediately at the call site (e.g., in `create_user()`)

**Validation:**
- Input validation happens at the route level (Pydantic schemas)
- Security gates (`is_setup_open()`, role checks) enforce authorization at route entry
- Database constraints (UNIQUE indexes, FKs) catch race conditions and back up application logic

**Hidden parameters:** `hide_parameters=True` on SQLAlchemy engine to prevent accidental leaking of secrets (passwords, tokens) in exception strings

### Frontend (TypeScript)

**Error Boundaries:**
- Not heavily used; component-level error handling preferred
- Async operations (API calls, storage) wrapped in try/catch at the hook level

**Hook Error Handling:**
- Hooks return state + methods; errors stored as `error` property when applicable
- Failed API calls logged but not thrown (prevent component unmount)
- Example: `useQuery()` from `@powersync/react` returns `{ data, error, isLoading, status }`

**Validation:**
- API schema validated via OpenAPI types (generated at build time into `src/lib/api/schema.d.ts`)
- Form input validated via Zod (if used) or Pydantic on backend
- Empty/null states handled explicitly (avoid throwing)

**Logging errors:**
- Never log raw error objects; use `.message` or `.toString()`
- Avoid logging sensitive data (tokens, passwords) even in error traces
- Use `console.error()` for debugging; production errors sent to monitoring service (not visible here)

## Logging

### Backend (Python)

**Framework:** Standard `logging` module

**Pattern:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info("User created", extra={"user_id": str(user.id)})
logger.warning("Refresh token expired", extra={"user_id": str(user_id)})
logger.error("Database error", exc_info=True)  # includes stack trace
```

**Guidelines:**
- Module logger: `logger = logging.getLogger(__name__)` at module scope
- One logger per module (no cross-module logger sharing)
- Use `extra={}` dict for structured data (user_id, attempt_count, etc.)
- Never log `str(exc)` if it may contain secrets — use `exc_info=True` for stack traces instead
- Log level: INFO for business events (user signup), WARNING for recoverable errors, ERROR for unrecoverable

### Frontend (TypeScript)

**Framework:** `console` (browser DevTools)

**Pattern:**
```typescript
console.log('Theme toggled', { newTheme: 'light', userId })
console.warn('Sync failed', { reason })
console.error('Network timeout')
```

**Guidelines:**
- Minimal logging — frontend logs are not persisted
- Log route transitions, major state changes, API failures
- Never log tokens, passwords, or sensitive auth data
- Tests may produce console warnings if DOM APIs aren't mocked correctly (expected during setup)

## Comments

### When to Comment

**Backend:**
- Function docstrings: Always, using Google/NumPy style with Args/Raises/Returns
  ```python
  def verify_readonly(session: AsyncSession, raw_token: str, *, settings: Settings) -> UUID:
      """Return the `user_id` bound to `raw_token` if it is still usable.

      Raises:
          RevokedRefreshTokenError: token row exists but `revoked_at` is set.
          ExpiredRefreshTokenError: token row exists and `expires_at <= now`.
          InvalidRefreshTokenError: no token row matches the supplied value.
      """
  ```
- Complex algorithm: Explain the "why" (e.g., why REPEATABLE READ, why specific SQL structure)
- ADR/design decisions: Reference story/ADR number (e.g., "cf. ADR 0015 — replay-vs-rotate race window")
- Non-obvious invariants: Explain contract (e.g., "Does **not** commit — caller owns transaction")

**Frontend:**
- Component behavior: Explain non-obvious UX (e.g., test helper setup, why a mock is needed)
- Test setup: Document what a fixture does and why (see `tests/setup.ts` for examples)
- Workarounds: Explain browser API limitations being worked around (e.g., jsdom matchMedia stub)

### JSDoc/TSDoc

**Backend (Python):**
- All public functions use triple-quoted docstrings
- Use `:param name:`, `:returns:`, `:raises:` tags sparingly (Google style preferred)
- Type hints in signature, not docstring

**Frontend (TypeScript):**
- Optional for private functions
- Use for public component exports (rarely needed, TypeScript types are self-documenting)
- Example:
  ```typescript
  /**
   * Rendu de test partagé.
   * - avec `route` : monte le VRAI arbre de boot
   * - sans `route` : rend `ui` isolément
   */
  export function renderWithProviders(ui: ReactNode, options?: RenderOptions) { ... }
  ```

## Function Design

### Size

**Backend:**
- Average function: 10-30 lines
- Service functions (domain logic): 20-60 lines
- Helpers under 15 lines preferred
- Extract to separate functions if logic repeats or readability drops

**Frontend:**
- React components: 30-80 lines (including JSX)
- Hooks: 10-40 lines
- Keep render logic compact; extract sub-components for complexity

### Parameters

**Backend:**
- Keyword-only parameters (`*,`) after required positional args when there are multiple options:
  ```python
  def create_user(
      session: AsyncSession,
      *,
      email: str,
      password: str,
      display_name: str,
      role: UserRole,
  ) -> User:
  ```
- Settings passed kw-only to keep helpers testable without cache clearing

**Frontend:**
- Props objects over multiple parameters:
  ```typescript
  interface RenderOptions {
    route?: string
    auth?: 'authenticated' | 'none'
  }
  function renderWithProviders(ui: ReactNode, options: RenderOptions = {}) { ... }
  ```
- Destructuring in function signature for clarity

### Return Values

**Backend:**
- Single value or tuple of related values (e.g., `tuple[UUID, str]` for user_id + new_token)
- Exceptions for errors (no nil return for failure)
- **Consistency:** If a service function can fail, raise exception (don't return Optional)

**Frontend:**
- React components: JSX.Element
- Hooks: Object or tuple with named properties
  ```typescript
  return { isAuthenticated, userId, login, logout, refresh }
  return { data, isLoading, error, status }
  ```
- Null returns acceptable for optional data (e.g., `result.data[0]?.balanceCents ?? 0`)

## Module Design

### Exports

**Backend:**
- `public.py` re-exports cross-module API (see `backend/modules/auth/public.py` for pattern)
- Intra-module files (service, models, transports) not imported cross-module
- Use `__all__` list in public modules to signal stable API
- Example structure:
  ```
  backend/modules/auth/
  ├── public.py          # Cross-module surface (ONLY import this)
  ├── models.py          # Tables + enums (imported only via public.py)
  ├── service/
  │   ├── users.py       # Internal: create_user, any_user_exists
  │   ├── jwt.py         # Internal: token logic
  │   └── ...
  └── transports/
      ├── dependencies.py # FastAPI deps (re-exported via public.py)
      └── ...
  ```

**Frontend:**
- No explicit public/private separation (TypeScript/ESM default is public)
- Convention: Avoid importing from deeply nested paths; use `@/` aliases
- Barrel files (`index.ts`) optional; used for grouping related exports
- Re-exports in feature directories:
  ```typescript
  // features/accounts/index.ts
  export { useAccounts } from './use-accounts'
  export { AccountList } from './account-list'
  ```

### Barrel Files

**Backend:**
- `__init__.py` is typically empty (Python convention)
- Re-exports live in `public.py`

**Frontend:**
- Used in `lib/api/`, `hooks/` to group utilities
- Optional in `components/` (components often imported by full path)
- Example:
  ```typescript
  // src/lib/auth/index.ts
  export { login, logout, refresh } from './session'
  export { tokenStore } from './token-store'
  ```

---

*Convention analysis: 2026-09-02*
