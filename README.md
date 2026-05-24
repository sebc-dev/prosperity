# Prosperity

Self-hosted personal finance app for a household. Backend in Python 3.13 (FastAPI + SQLAlchemy 2 async). See `CONTEXT.md` and `docs/roadmap/` for architecture and the MVP plan.

## Setup

```sh
uv sync                       # install runtime + dev deps from uv.lock
uv run pre-commit install     # enable git hooks (ruff, pyright, pytest)
```

## Quality gates

```sh
uv run ruff check .           # lint
uv run ruff format --check .  # format check
uv run pyright                # strict type check
uv run pytest                 # tests (add --cov for coverage)
uv run pre-commit run --all-files
```
