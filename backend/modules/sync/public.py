"""Public surface of the sync module — re-exports for cross-module use.

Seul module de `backend.modules.sync` importable par les pairs. `sync` siège au
sommet du graphe directionnel (ADR 0005, contrat 1, juste sous `mcp`) : il peut
consommer le `public.py` de tous les modules métier, mais reste *public-surface-
only* — le contrat `2-sync` interdit aux pairs d'atteindre
`sync.{schemas,models,service,handlers,domain}`. Les re-exports ci-dessous sont
**intra-module** (`sync.public → sync.schemas`, le contrat bride les *pairs*, pas
`public` lui-même) — aucune exception import-linter requise.

Surface : l'enveloppe batch PowerSync (`BatchUpload`/`Mutation`/`MutationOp`/
`WriteError`/`WriteResult`), le contrat wire du write upload handler (ADR 0014).
"""

from __future__ import annotations

from backend.modules.sync.schemas import (
    BatchUpload,
    Mutation,
    MutationOp,
    WriteError,
    WriteResult,
)

__all__ = [
    "BatchUpload",
    "Mutation",
    "MutationOp",
    "WriteError",
    "WriteResult",
]
