"""Dump the FastAPI OpenAPI schema to a file WITHOUT starting a server.

Source of truth for the frontend typed client (`client/src/lib/api`). The
schema is produced via `app.openapi()` so the frontend codegen never needs a
running backend (its CI has no Python venv). `app.openapi()` is pure — the
lifespan (`bootstrap_initial_admin_from_env`, event wiring) only runs at uvicorn
startup, not at import — so this export touches neither the DB nor the network.

Invocation (from the repo root, `backend.scripts` is a package):

    python -m backend.scripts.dump_openapi client/openapi.json

Re-run after any route/schema change; the frontend's `npm run gen:api:check`
then fails if the committed types drift. `sort_keys=True` + `indent=2` keep the
output deterministic so the idempotence diff is not noised by key ordering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.main import app  # import absolu (convention repo, cf. purge_sync_request_log)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("client/openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":  # pragma: no cover
    main()
