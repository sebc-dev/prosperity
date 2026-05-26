"""Guard against forgetting to add a new module to `.importlinter`.

`contract:2` (and its sibling `contract:2-auth`) enforce that no module
imports another module's internals. As long as the source list is
manually enumerated (a forced workaround for grimp's
shared-descendants rule, see `.importlinter` notes), adding a directory
under `backend/modules/` without also editing those contracts silently
exempts it from the policy.

This test parses `.importlinter` and asserts that every dir under
`backend/modules/` appears in `contract:2.source_modules` or
`contract:2-auth.source_modules`. Failure means: edit those two
sections before opening the PR.
"""

from __future__ import annotations

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTLINTER = REPO_ROOT / ".importlinter"
MODULES_ROOT = REPO_ROOT / "backend" / "modules"


def _parse_modules(value: str) -> set[str]:
    return {line.strip() for line in value.splitlines() if line.strip()}


def test_every_module_under_backend_modules_is_a_contract2_source() -> None:
    cfg = configparser.ConfigParser()
    cfg.read(IMPORTLINTER)

    covered = _parse_modules(cfg["importlinter:contract:2"]["source_modules"]) | _parse_modules(
        cfg["importlinter:contract:2-auth"]["source_modules"]
    )

    on_disk = {
        f"backend.modules.{path.name}"
        for path in MODULES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }

    missing = on_disk - covered
    assert not missing, (
        "Modules under backend/modules/ not declared in contract:2 or "
        "contract:2-auth source_modules — they would be exempt from the "
        f"cross-module import policy. Add them: {sorted(missing)}"
    )
