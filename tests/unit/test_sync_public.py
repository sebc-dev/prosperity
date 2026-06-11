"""Public surface of `backend.modules.sync` (S13.2).

P13.2.1 asserts the module + its internal packages are importable (the
scaffolding is wired and the `contract:2-sync` split keeps the lint green);
`test_sync_public_reexports_batch_schemas` (P13.2.3) pins the schema re-export.
"""

from __future__ import annotations

import importlib


def test_sync_public_importable() -> None:
    """`sync.public` imports cleanly (no eager peer-internal import)."""
    importlib.import_module("backend.modules.sync.public")


def test_sync_internal_packages_importable() -> None:
    """The scaffolding packages `service` / `handlers` + `domain` import."""
    importlib.import_module("backend.modules.sync.service")
    importlib.import_module("backend.modules.sync.handlers")
    importlib.import_module("backend.modules.sync.domain")
