# Prosperity

Self-hosted personal finance app for a household. See [`CONTEXT.md`](CONTEXT.md) for the domain model and [`docs/roadmap/`](docs/roadmap/) for the MVP plan.

## Stack (one-line justifications)

| Layer | Choice | Why |
|---|---|---|
| Language / runtime | Python 3.13 | Strict typing + Pydantic v2 ergonomy; matches FastAPI's audience |
| Web framework | FastAPI + Uvicorn | Async-first HTTP; native Pydantic models; trivial OpenAPI |
| DB | Postgres 17 + SQLAlchemy 2 async + Alembic | Server is the source of truth for derived projections (debts, balances) — see [ADR 0002](docs/adr/0002-debts-as-server-projection.md) |
| Architecture | 7-level directional import graph | Enforced by `import-linter` — see [ADR 0005](docs/adr/0005-directional-import-graph.md) |
| Sync | PowerSync buckets | Per-household isolation — see [ADR 0003](docs/adr/0003-powersync-bucket-design.md) and [ADR 0014](docs/adr/0014-sync-module-and-write-upload-handler.md) |
| Package manager | `uv` | Locked, reproducible installs (`uv.lock`) without an editable install (`tool.uv.package = false`) |
| Quality gates | `ruff`, `pyright` (strict), `import-linter`, `pytest` + `hypothesis` + `testcontainers` | See [`docs/Stratégie de tests.md`](docs/Strat%C3%A9gie%20de%20tests.md) |

## Setup

```sh
uv sync                       # install runtime + dev deps from uv.lock
uv run pre-commit install     # enable git hooks (ruff, pyright, import-linter, pytest)
```

## Common commands

The project ships no `Makefile`; commands are uv invocations. Aliases below mirror the typical `make <target>` shape.

| Target | Command |
|---|---|
| `dev` | `uv run uvicorn backend.main:app --reload` |
| `test` | `uv run pytest` (add `--cov` for coverage) |
| `lint` | `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports` |
| `migrate` | `uv run alembic upgrade head` |
| `migrate-new` | `uv run alembic revision -m "<message>"` |
| `pre-commit` | `uv run pre-commit run --all-files` |

## CI

GitHub Actions, mirroring [Stratégie de tests §9](docs/Strat%C3%A9gie%20de%20tests.md#9-pipelinecicd):

- [`.github/workflows/push.yml`](.github/workflows/push.yml) — runs on every push / PR, target < 5 min: `backend-lint`, `backend-unit`, `backend-integration`, `backend-sync` (placeholder), `backend-migrations`.
- [`.github/workflows/nightly.yml`](.github/workflows/nightly.yml) — daily cron + `workflow_dispatch`: property tests with `HYPOTHESIS_PROFILE=nightly` (500 examples), `pip-audit`, full-suite coverage upload, plus Playwright and Enable Banking niveau C placeholders.
