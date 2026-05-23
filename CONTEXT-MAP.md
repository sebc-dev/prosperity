# Context Map

This repo has two bounded contexts. Each has its own `CONTEXT.md` glossary and `docs/adr/` for context-specific decisions. System-wide ADRs (cross-context concerns) live at `/docs/adr/`.

| Context    | Expected path     | Scope                                                                       |
| ---------- | ----------------- | --------------------------------------------------------------------------- |
| `frontend` | `src/frontend/`   | User-facing application — UI, client-side state, routing, presentation.     |
| `backend`  | `src/backend/`    | Server-side application — API, persistence, domain logic, background work.  |

The `src/` paths are placeholders — update them when the stack lands (e.g. `apps/web/` + `apps/api/` for a Turborepo layout, or two separate top-level directories).

When a skill needs to consult the domain, it reads the `CONTEXT.md` for the relevant context (or both, if a change spans both). `/grill-with-docs` creates and grows these files lazily as terms get resolved — don't pre-populate them.
