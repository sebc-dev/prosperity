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


def test_sync_public_reexports_batch_schemas() -> None:
    """`sync.public.__all__` re-exports the five batch schemas plus `process_batch`
    (S13.3) and each name IS the underlying object (no shadow copies) — P13.2.3 /
    P13.3.1."""
    public = importlib.import_module("backend.modules.sync.public")
    schemas = importlib.import_module("backend.modules.sync.schemas")
    dispatcher = importlib.import_module("backend.modules.sync.service.dispatcher")

    assert public.__all__ == [
        "BatchUpload",
        "Mutation",
        "MutationOp",
        "WriteError",
        "WriteResult",
        "process_batch",
    ]
    assert public.BatchUpload is schemas.BatchUpload
    assert public.Mutation is schemas.Mutation
    assert public.MutationOp is schemas.MutationOp
    assert public.WriteError is schemas.WriteError
    assert public.WriteResult is schemas.WriteResult
    assert public.process_batch is dispatcher.process_batch
