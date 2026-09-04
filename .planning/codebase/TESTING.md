# Testing Patterns

**Analysis Date:** 2026-09-02

## Test Framework

### Backend

**Runner:** `pytest` 8.3+
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`
- Python path: `.` (root)
- Test paths: `tests/`
- Async mode: Auto (pytest-asyncio with session-scoped loop)

**Assertion Library:** Built-in `assert` statements

**Concurrency Tracking:** Special configuration for async + threaded code:
```toml
[tool.coverage.run]
concurrency = ["greenlet", "thread"]
```
This is required for SQLAlchemy async + FastAPI's threaded sync routes.

**Run Commands:**
```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest tests/integration/       # Specific tier
pytest -k test_auth_            # Filter by name pattern
pytest --cov                    # Coverage report (htmlcov/)
uv run pytest                   # Via UV (matches CI environment)
```

### Frontend

**Runner:** `vitest` 4.1+
- Config: `client/vite.config.ts` under `test` key
- Environment: `jsdom` (simulated browser)
- Test paths: `src/**/*.test.{ts,tsx}` + `tests/**/*.test.ts`
- Globals: `true` (describe, it, test, expect available without imports)

**Assertion Library:** `vitest` built-in (compatible with Jest)

**Run Commands:**
```bash
npm test                        # Run tests once
npm run test                    # Alias for above
vitest                          # Watch mode (interactive)
vitest run                      # Single run
vitest run --coverage           # Coverage report
vitest --ui                     # Browser UI (optional)
```

## Test File Organization

### Location

**Backend (Python):**
- All tests live in `tests/` (not co-located with source)
- Directory mirrors source structure:
  ```
  tests/
  ├── conftest.py              # Root fixtures (all modules share)
  ├── integration/
  │   ├── conftest.py          # Integration-specific fixtures
  │   ├── test_auth_*.py
  │   ├── test_accounts_*.py
  │   └── sync/
  │       └── conftest.py      # Sync-specific fixtures
  ├── e2e/
  │   └── test_*.py            # End-to-end (real Postgres, committed)
  └── unit/                     # (If used) unit tests
  ```

**Frontend (TypeScript):**
- Co-located with source:
  ```
  src/
  ├── components/
  │   ├── theme-toggle.tsx
  │   └── theme-toggle.test.tsx    # Alongside component
  ├── hooks/
  │   ├── useAuth.ts
  │   └── useAuth.test.tsx
  ├── lib/
  │   ├── utils.ts
  │   └── utils.test.ts
  └── pages/
      ├── auth-guard.tsx
      └── auth-guard.test.tsx
  
  tests/                          # Harness/integration tests
  ├── setup.ts                    # Global setup (MSW, stubs)
  ├── msw/                        # Mock Service Worker
  │   ├── handlers.ts
  │   └── server.ts
  └── auth.ts                     # Test auth helpers
  ```

### Naming

**Backend:**
- Pattern: `test_<feature>_<scenario>.py`
- Examples: `test_auth_rbac_dependencies.py`, `test_refresh_tokens_race.py`
- Descriptive — avoid generic `test_*.py`

**Frontend:**
- Pattern: Same name as source file + `.test.tsx` / `.test.ts`
- Examples: `useAuth.test.tsx`, `theme-toggle.test.tsx`, `utils.test.ts`

### Structure

**Backend (pytest):**
```python
"""Module docstring describing test scope.

Explains what feature is tested and any setup/isolation patterns.
"""

from __future__ import annotations

# Imports grouped: stdlib, third-party, local (ruff-isort order)
import logging
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import create_user, UserRole


async def test_user_creation_hashes_password(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """Plaintext password is hashed via Argon2id on creation."""
    user = await create_user(
        auth_schema,
        email="test@example.com",
        password="plaintext123",
        display_name="Test User",
        role=UserRole.MEMBER,
    )
    
    assert user.password_hash.startswith("$argon2")  # Argon2 hash format


async def test_duplicate_email_raises_integrity_error(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """UNIQUE constraint on lowercase email prevents duplicates."""
    user1 = await create_user(auth_schema, email="test@example.com", ...)
    
    with pytest.raises(IntegrityError):
        await create_user(auth_schema, email="TEST@example.com", ...)
```

**Frontend (vitest):**
```typescript
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'

import { ThemeToggle } from '@/components/theme-toggle'
import { ThemeProvider } from '@/app/theme-provider'

test('toggles dark mode on click', async () => {
  const user = userEvent.setup()
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
  
  expect(document.documentElement.classList.contains('dark')).toBe(true)
  
  await user.click(screen.getByRole('button', { name: /thème/i }))
  expect(document.documentElement.classList.contains('dark')).toBe(false)
})
```

## Test Structure

### Setup & Teardown

**Backend (pytest):**

```python
# Session-scoped fixtures (created once, reused per test)
@pytest_asyncio.fixture(scope="session")
async def postgres_container() -> Iterator[PostgresContainer]:
    """Docker container with Postgres, skipped if Docker unavailable."""
    ...

# Per-test fixtures (fresh for each test)
@pytest_asyncio.fixture(loop_scope="session")
async def auth_schema(db_session: AsyncSession) -> AsyncSession:
    """Create all tables on connection, rolled back after test."""
    conn = await db_session.connection()
    await conn.run_sync(Base.metadata.create_all)
    return db_session

# Autouse fixture (runs for every test)
@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:
    """Reset process-local cache before/after each test."""
    invalidate_household_cache()
    yield
    invalidate_household_cache()
```

Cleanup strategy:
- **Per-test:** Rollback outer transaction (savepoint mode in `db_session`)
- **Module-level:** Drop schema after module completes (if using `committed_engine`)
- **Autouse:** Cache resets, process-state cleanup

**Frontend (vitest):**

```typescript
// Global setup (tests/setup.ts)
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })  // MSW starts
})

afterEach(() => {
  tokenStore.set(null)                            // Reset auth state
  server.resetHandlers()                          // Purge custom handlers
  cleanup()                                       // Unmount Testing Library components
  document.documentElement.classList.remove('dark') // Reset theme
  localStorage.clear()                           // Clear storage
  stubMatchMedia()                                // Restore default media query
})

afterAll(() => {
  server.close()                                  // MSW stops
})
```

Cleanup strategy:
- **After each test:** Clear all state (tokens, DOM, storage, MSW handlers)
- **Per-test:** Setup with `render()` + auto cleanup
- **Mocking:** jsdom polyfills (matchMedia, scrollTo, Radix Popper APIs) set once in setup, reset per test

### Patterns

**Backend (assertion pattern):**

```python
async def test_admin_only_forbids_member(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    """RBAC guard blocks non-admin access."""
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    headers = {"Authorization": f"Bearer {issue_access_token(member.id, ...)}"}
    
    resp = await async_client.get("/test/admin-only", headers=headers)
    
    # Single assertion block (arrange-act-assert)
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Forbidden"}
```

**Frontend (Testing Library pattern):**

```typescript
test('persists theme to localStorage on toggle', async () => {
  const user = userEvent.setup()
  
  // Arrange
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
  
  // Act
  await user.click(screen.getByRole('button', { name: /thème/i }))
  
  // Assert
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
})
```

**Async testing pattern (both):**

Backend:
```python
async def test_token_expires(async_client: AsyncClient) -> None:
    await asyncio.sleep(1)  # Simulate time passing
    assert token.expires_at <= datetime.now(tz=UTC)
```

Frontend:
```typescript
test('debounce delays callback', async () => {
  const callback = vi.fn()
  renderHook(() => useDebounce(callback, 300))
  
  await waitFor(() => {
    expect(callback).toHaveBeenCalled()
  }, { timeout: 500 })
})
```

## Mocking

### Backend

**Framework:** `pytest` fixtures + SQLAlchemy session manipulation

**Database mocking:**
```python
# Real Postgres (testcontainers)
@pytest_asyncio.fixture(scope="session")
async def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer("postgres:17-alpine", driver="asyncpg")
    with container as started:
        yield started

# Transaction isolation (SAVEPOINT mode)
@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            session_factory = async_sessionmaker(
                bind=connection,
                join_transaction_mode="create_savepoint",  # Per-test rollback
            )
            async with session_factory() as session:
                yield session
        finally:
            await transaction.rollback()
```

**HTTP mocking:**
```python
# Use real FastAPI app with dependency override (not mocking HTTP)
@pytest.fixture
async def async_client(committed_sessionmaker) -> AsyncIterator[AsyncClient]:
    """Override get_db to use test session."""
    
    async def _override_get_db():
        async with committed_sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        yield client
    app.dependency_overrides.pop(get_db)
```

**What to mock:**
- Nothing — use real database (testcontainers)
- Nothing — use real FastAPI app

**What NOT to mock:**
- Database queries — use real Postgres in transaction
- HTTP layer — use ASGI transport to real app
- Auth tokens — generate real test tokens via `issue_access_token()`

### Frontend

**Framework:** `msw` (Mock Service Worker) + `vitest.mock()`

**HTTP mocking (MSW):**
```typescript
// tests/msw/server.ts
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)

// tests/msw/handlers.ts (default handlers)
export const handlers = [
  http.get('http://localhost:8000/auth/verify', () => 
    HttpResponse.json({ authenticated: false })
  ),
  http.post('http://localhost:8000/auth/login', () =>
    HttpResponse.json({ access_token: '...', refresh_token: '...' })
  ),
]

// Individual test override
test('login succeeds', async () => {
  server.use(
    http.post('http://localhost:8000/auth/login', () =>
      HttpResponse.json({ access_token: 'real-token' })
    ),
  )
  // ...
})
```

**Module mocking (vitest):**
```typescript
// Mock an entire module
vi.mock('@/lib/storage', () => ({
  storage: {
    getItem: vi.fn(),
    setItem: vi.fn(),
  },
}))

// Mock a specific function
const mockTokenStore = vi.spyOn(tokenStore, 'set')
```

**localStorage/sessionStorage mocking:**
```typescript
// jsdom provides native localStorage; just clear it
afterEach(() => {
  localStorage.clear()
})

// Or mock for specific test
test('persists to session storage', () => {
  const storage: Record<string, string> = {}
  vi.spyOn(global, 'sessionStorage', 'get').mockReturnValue({
    getItem: (key) => storage[key] ?? null,
    setItem: (key, value) => { storage[key] = value },
    // ... other methods
  } as any)
})
```

**DOM API mocking:**
```typescript
// Global stubs in setup (tests/setup.ts)
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.setPointerCapture = () => {}
  Element.prototype.releasePointerCapture = () => {}
  Element.prototype.scrollIntoView = () => {}
}

// Per-test override
test('matches dark mode preference', () => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: true,  // Simulate dark mode
    media: '',
    onchange: null,
    addEventListener: vi.fn(),
    // ...
  })
})
```

**What to mock:**
- Network requests (MSW)
- Module-level functions that are expensive or non-deterministic (vitest.mock)
- DOM APIs that jsdom doesn't implement (matchMedia, pointerCapture)

**What NOT to mock:**
- localStorage/sessionStorage — use real jsdom implementation
- React components from tested module — render the real component
- Custom hooks in the same file — test the hook, not a mock version

## Fixtures and Factories

### Test Data

**Backend (factory-boy):**
```python
# tests/factories/sqlalchemy.py
from factory import Factory
from factory.sqlalchemy import SQLAlchemyModelFactory

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = None  # Override per test
        sqlalchemy_session_persistence = 'flush'

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password_hash = "hashed_password"
    role = UserRole.MEMBER

# Usage
@pytest_asyncio.fixture
async def bound_user_factory(auth_schema: AsyncSession) -> UserMaker:
    """Factory bound to test session."""
    
    async def _make(
        email: str = "test@example.com",
        role: UserRole = UserRole.MEMBER,
    ) -> User:
        return await UserFactory(
            email=email,
            role=role,
        )  # Created in auth_schema via SessionLocal override
    
    return _make

# Test usage
admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
```

**Frontend (test helpers):**
```typescript
// tests/auth.ts
export function makeTestJwt(claims: Partial<JwtPayload>): string {
  const payload = {
    sub: 'user-123',
    exp: Math.floor(Date.now() / 1000) + 900,
    ...claims,
  }
  return jwt.sign(payload, 'test-secret')
}

export function seedAuth(tokens?: Partial<TokenPair>) {
  const defaultToken = makeTestJwt()
  tokenStore.set({
    accessToken: defaultToken,
    refreshToken: 'rt-token',
    ...tokens,
  })
}

// Test usage
seedAuth({ accessToken: makeTestJwt({ sub: 'admin-id' }) })
```

**Location:**
- Backend: `tests/factories/sqlalchemy.py` (centralized, imported as needed)
- Frontend: `tests/auth.ts`, `tests/render.tsx` (organized by concern)

## Coverage

### Requirements

**Backend:**
- Target: No explicit threshold enforced (configured but commented out)
- Measured: `backend/` source only (tests/ excluded)
- Concurrency: Configured for greenlet + thread (SQLAlchemy async + FastAPI sync)
- Command: `pytest --cov` → generates `htmlcov/` directory

**Frontend:**
- Target: No threshold enforced (configured but not activated)
- Measured: `src/components/business/**`, `src/components/layout/**`, `src/features/**` only
- Other directories (`lib/`, `hooks/`) out of scope (will be measured in future phase)
- Command: `npm test -- --coverage` → generates coverage report
- Config: `client/vite.config.ts` under `test.coverage`

### View Coverage

**Backend:**
```bash
pytest --cov
pytest --cov --cov-report=html  # Open htmlcov/index.html
```

**Frontend:**
```bash
vitest run --coverage
# Or via npm:
npm test -- --coverage
```

## Test Types

### Backend

**Unit Tests:**
- Scope: Individual functions/service methods in isolation
- Database: Real Postgres via testcontainers (not mocked)
- Examples: `test_hash_refresh_token()`, `test_email_normalization()`
- Fixtures: `auth_schema`, `db_session`

**Integration Tests:**
- Scope: Full HTTP request → service → database round-trip
- Database: Real Postgres, transaction per test (rollback isolation)
- Examples: `test_auth_rbac_dependencies.py`, `test_refresh_tokens_race.py`
- Fixtures: `async_client` (overridden `get_db`), `auth_schema`

**E2E Tests:**
- Scope: Black-box HTTP journey + real Postgres + committed transactions
- Database: Real Postgres, true commits (no savepoint rollback)
- Marked: `@pytest.mark.e2e`
- Fixtures: `committed_client`, `_clean_committed_db` (opt-in truncation)
- Examples: Account membership flows, share request races
- Note: Used for concurrency tests that cannot work under savepoint mode

### Frontend

**Component Tests:**
- Scope: Individual React component with real hooks
- Environment: jsdom
- MSW: Handles any HTTP calls
- Examples: `theme-toggle.test.tsx`, `sync-status-badge.test.tsx`
- Render: Via `render()` or `renderWithProviders()` helper

**Hook Tests:**
- Scope: Custom hooks in isolation (render via `renderHook()`)
- Environment: jsdom
- Mocking: PowerSync/Drizzle queries mocked if needed
- Examples: `useAuth.test.tsx`, `use-account-balance.test.tsx`

**Route/Integration Tests:**
- Scope: Full app boot (AuthProvider → Router) on a specific route
- Environment: jsdom
- Router: Real memory history, real guards
- MSW: Intercepts all API calls
- Examples: `routes.test.tsx`, `auth-guard.test.tsx`
- Pattern: Use `renderWithProviders({ route: '/accounts', auth: 'authenticated' })`

**Utility Tests:**
- Scope: Pure functions (no React)
- Examples: `utils.test.ts`, `nav-items.test.ts`
- No setup required

## Common Patterns

### Async Testing

**Backend:**
```python
async def test_token_rotation_is_atomic(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """Rotation issues new token + revokes parent in one statement."""
    user = await bound_user_factory(...)
    parent_token = await issue_refresh_token(auth_schema, user.id, settings=settings)
    
    # Simulate concurrent rotate
    user_id, new_token = await rotate(auth_schema, parent_token, settings=settings)
    
    assert user_id == user.id
    # Parent is now revoked (automatic via rotate)
    with pytest.raises(RevokedRefreshTokenError):
        await verify_readonly(auth_schema, parent_token, settings=settings)
```

**Frontend:**
```typescript
test('auto-refresh happens on background tab focus', async () => {
  render(<App />)
  
  // Simulate tab going idle then refocusing
  window.dispatchEvent(new Event('focus'))
  
  // Wait for refresh to fire
  await waitFor(() => {
    expect(tokenStore.get()?.accessToken).toBeDefined()
  }, { timeout: 1000 })
})
```

### Error Testing

**Backend:**
```python
def test_admin_only_rejects_anonymous_with_401(
    async_client: AsyncClient,
) -> None:
    """No credentials → 401."""
    resp = await async_client.get("/test/admin-only")
    assert resp.status_code == 401

def test_duplicate_email_raises_integrity_error(
    auth_schema: AsyncSession,
) -> None:
    """UNIQUE constraint blocks duplicates."""
    user1 = await create_user(auth_schema, email="test@example.com", ...)
    
    with pytest.raises(IntegrityError):
        await create_user(auth_schema, email="test@example.com", ...)
```

**Frontend:**
```typescript
test('login handles 401 gracefully', async () => {
  server.use(
    http.post('http://localhost:8000/auth/login', () =>
      HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })
    ),
  )
  
  const { login } = useAuth()
  await expect(login('a@b.c', 'wrong')).rejects.toThrow()
  expect(tokenStore.get()).toBeNull()
})
```

### Parametrized Testing

**Backend (pytest):**
```python
@pytest.mark.parametrize(
    "status_code,expected_error",
    [
        (401, "Unauthorized"),
        (403, "Forbidden"),
        (404, "Not Found"),
    ],
)
async def test_http_error_responses(
    async_client: AsyncClient,
    status_code: int,
    expected_error: str,
) -> None:
    # Single test function, multiple cases
    pass
```

**Frontend (vitest):**
```typescript
test.each([
  ['dark', true],
  ['light', false],
])('sets theme class %s (dark=%p)', (theme, isDark) => {
  setTheme(theme)
  expect(document.documentElement.classList.contains('dark')).toBe(isDark)
})
```

---

*Testing analysis: 2026-09-02*
