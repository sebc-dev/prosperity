"""Guard against forgetting to add a new module to `.importlinter`.

`contract:2` (and its module-specific siblings `contract:2-auth`,
`contract:2-accounts`, …) enforce that no module imports another
module's internals. As long as the source list is manually enumerated
(a forced workaround for grimp's shared-descendants rule, see
`.importlinter` notes), adding a directory under `backend/modules/`
without also editing those contracts silently exempts it from the policy.

This test parses `.importlinter` and asserts that every dir under
`backend/modules/` appears in `contract:2.source_modules` or one of the
per-module `contract:2-*` sources. Failure means: edit the relevant
section before opening the PR.
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

    contract2_sections = [
        section
        for section in cfg.sections()
        if section == "importlinter:contract:2" or section.startswith("importlinter:contract:2-")
    ]
    covered: set[str] = set()
    for section in contract2_sections:
        covered |= _parse_modules(cfg[section]["source_modules"])

    on_disk = {
        f"backend.modules.{path.name}"
        for path in MODULES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }

    missing = on_disk - covered
    assert not missing, (
        "Modules under backend/modules/ not declared in contract:2 or any "
        "contract:2-* source_modules — they would be exempt from the "
        f"cross-module import policy. Add them: {sorted(missing)}"
    )


def test_every_module_is_a_contract6_source() -> None:
    """Contract 6 (`backend.transports` consumer-only) must list EVERY module.

    The composition root sits above every module and is never consumed — so each
    `backend.modules.*` (plus `backend.shared`) must be a `source_modules` entry,
    otherwise a future `backend.modules.X → backend.transports` arc would pass
    silently (transports is outside `backend/modules/`, so the contract-2 coverage
    test above cannot catch it). Assert coverage, not just existence (D3).
    """
    cfg = configparser.ConfigParser()
    cfg.read(IMPORTLINTER)

    section = "importlinter:contract:6"
    assert section in cfg.sections(), "contract:6 (transports consumer-only) is missing"

    sources = _parse_modules(cfg[section]["source_modules"])
    forbidden = _parse_modules(cfg[section]["forbidden_modules"])
    assert forbidden == {"backend.transports"}, (
        f"contract:6 must forbid exactly backend.transports, got {sorted(forbidden)}"
    )

    on_disk = {
        f"backend.modules.{path.name}"
        for path in MODULES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }
    missing = on_disk - sources
    assert not missing, (
        "Modules under backend/modules/ not declared in contract:6 source_modules "
        "— a future import of backend.transports from them would be invisible. "
        f"Add them: {sorted(missing)}"
    )
    assert "backend.shared" in sources, (
        "contract:6 must list backend.shared as a source_module (shared must not "
        "import backend.transports either)"
    )
    # Symmetric guard: no source_modules entry may name a backend.modules.* that
    # no longer exists on disk (a typo or a deleted module would silently weaken
    # the contract). `backend.shared` is the one legitimate non-module source.
    stale = sources - on_disk - {"backend.shared"}
    assert not stale, (
        "contract:6 source_modules names backend.modules.* entries with no "
        f"matching directory under backend/modules/ — remove or fix them: {sorted(stale)}"
    )
