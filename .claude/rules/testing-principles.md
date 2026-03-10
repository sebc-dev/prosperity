# Testing Principles

## Fundamentals

- Test **observable behavior**, never internal implementation
- Validation test: "If I refactor the implementation without changing functionality, does this test still pass?" If not → rewrite
- Verification hierarchy: output-based (returns) > state-based (state) > communication-based (mocks)
- One test = one logical concept

## AAA Structure (Mandatory)

Every test follows Arrange-Act-Assert with blank line separation:

```
// Arrange — set up SUT and data
//
// Act — ONE SINGLE line of execution
//
// Assert — verify observable behavior
```

Act section must be **one line**. Multiple lines = testing more than one behavior → split.

## Naming

Format: `scenario_description_and_expected_result` in natural language.
- Good: `delivery_with_past_date_is_invalid`, `cart_applies_discount_when_total_exceeds_threshold`
- Bad: `testIsDeliveryValid`, `test1`, `itWorks`

The name must describe the scenario **without reading the test code**.

## Test Case Selection (EP + BVA)

For each feature, systematically test:
1. **Happy path** — nominal case
2. **Boundary values** — limit values (e.g., 17, 18, 19 for threshold 18)
3. **Errors** — invalid inputs, null/undefined/empty
4. **Edge cases** — empty collections, empty strings, zero, negatives

Isolate invalid partitions (one per test) to identify failure cause precisely.

## Test Doubles — Minimal Usage

```
Dummy  → Fills a parameter, never used
Stub   → Pre-programmed responses (simulates inputs)
Fake   → Simplified implementation (in-memory DB)
Mock   → Outgoing behavior verification (LAST RESORT)
```

Rules:
- Mock **only** unmanaged out-of-process dependencies (external APIs, SMTP, message bus)
- Use real collaborators for internal dependencies
- Prefer fakes over mocks when possible
- **> 2-3 doubles in a test = refactoring signal for the SUT**
- "Only mock types that you own" → wrap third-party libs in adapters

## FIRST Properties

- **Fast**: < 100ms per test; zero real network/filesystem calls
- **Isolated**: runnable alone, in any order; zero shared mutable state
- **Repeatable**: deterministic; injectable clock, random with fixed seed
- **Self-validating**: explicit assertions, never manual verification
- **Timely**: written at development time

## Coverage

- **Negative** indicator: low coverage = certainly under-tested
- **Never** a target: high coverage ≠ well tested
- Google benchmarks: 60% acceptable, 75% good, 90% exemplary
- Never write assertion-less tests to inflate coverage

## Code Classification (Khorikov)

| | Few collaborators | Many collaborators |
|---|---|---|
| **High complexity** | DOMAIN → unit test (priority) | OVERCOMPLICATED → refactor first |
| **Low complexity** | TRIVIAL → don't test | CONTROLLERS → integration tests |

Don't test: trivial getters/setters, code without conditional logic, wrappers without transformation.

## Anti-patterns (Forbidden)

| Anti-pattern | Detection | Correction |
|---|---|---|
| **The Liar** | `expect` absent or trivial | Verify a concrete observable behavior |
| **The Mockery** | More mocks than assertions | Reduce doubles, use real collaborators |
| **The Inspector** | Reflection, cast, `as any` | Test via public API only |
| **The Giant** | Test > 50 lines | Split into focused tests (1 concept = 1 test) |
| **Fragile Test** | Breaks on refactoring without bug | Assert on outputs and observable side effects |
| **The Nitpicker** | `toEqual` on full object/JSON | Assert only on relevant fields |
| **Free Ride** | Unrelated assertion added to existing test | Create a new test for each behavior |
| **Flaky** | `sleep`, `Date.now()`, network | Injectable clock, fixed seed, zero real I/O |

## Checklists

### Before Validating a Test

- Name describes scenario AND expected result
- AAA structure with Act on a single line
- Assertions verify observable behavior (not implementation)
- Test survives internal SUT refactoring
- Boundary values and error cases covered
- Test is deterministic and independent
- Number of doubles ≤ 2-3
- No temporal sleep/wait
- No access to private members

### Anti-flakiness

- Injectable clock (no direct Date.now() / new Date())
- Zero real network calls
- Zero real filesystem access (or abstracted)
- Zero shared mutable state between tests
- Random with fixed seed
- Assertions independent of collection order
- No sleep/setTimeout in tests

## Test Data

- Use **Test Data Builder** pattern with sensible defaults
- Specify **only** fields relevant to tested behavior
- Fresh fixtures by default; never shared mutable state between tests
- Readable labels for each parameter set in parameterized tests
- Never mix success and error paths in a single parameterized test

## DAMP > DRY in Tests

- **Scenarios** (what-to): inline, descriptive, explicit in each test → DAMP
- **Mechanisms** (how-to): builders, factories, custom assertions → DRY
- Never extract `beforeEach` that obscures test intent
- Each test must be understandable in isolation

## When to Delete a Test

1. Feature removed or obsolete
2. Coupled to implementation (breaks on every refactoring)
3. Duplicated by a broader-scope test
4. Not traceable to a business requirement
5. Permanently `@Ignored`/skipped (dead test)
6. Irreparably flaky
