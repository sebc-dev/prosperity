"""Verrou de parité des registres du dispatcher PowerSync (S13.4).

Rend décidable, dans LES DEUX SENS, l'alignement entre :
- `HANDLERS` (table → sous-handler),
- `SUPPORTED_OPS` (table → ops déclarées gérées par le handler),
- `PERMISSION_CHECKS` (`(table, op)` → check d'auth étape 1).

Sans `SUPPORTED_OPS` (source de vérité déclarative), « tout `(table, op)` géré a un
check » n'est pas vérifiable (les ops vivent dans le corps du handler). Ce verrou
casse si une phase ajoute un handler/une op sans politique d'auth (faille
fail-open), ou un check orphelin (op non gérée) — DB-free, aucun container."""

from __future__ import annotations

from backend.modules.sync.schemas import MutationOp
from backend.modules.sync.service.dispatcher import (
    HANDLERS,
    PERMISSION_CHECKS,
    SUPPORTED_OPS,
)

_VALID_OPS: frozenset[MutationOp] = frozenset({"insert", "update", "delete"})


def test_handlers_and_supported_ops_cover_same_tables() -> None:
    """Garde anti-typo : exactement les mêmes tables des deux côtés."""
    assert set(HANDLERS) == set(SUPPORTED_OPS)


def test_supported_ops_are_valid_mutation_ops() -> None:
    """Chaque op déclarée appartient au vocabulaire wire `MutationOp`."""
    for table, ops in SUPPORTED_OPS.items():
        assert ops, f"{table} déclare un ensemble d'ops vide"
        assert ops <= _VALID_OPS, f"{table} déclare une op hors enum : {ops - _VALID_OPS}"


def test_every_supported_op_has_a_permission_check() -> None:
    """Sens 1 : toute op GÉRÉE par un handler a une politique d'auth (étape 1).

    `reconciliations` (placeholder V1, D-H) n'est PAS une exception : son check
    « membre actif » existe bien, il PASSE puis le handler renvoie
    `not_implemented_yet`. Aucune op gérée ne doit échapper à l'étape 1 (fail-closed)."""
    for table, ops in SUPPORTED_OPS.items():
        for op in ops:
            assert (table, op) in PERMISSION_CHECKS, f"({table}, {op}) géré sans check d'auth"


def test_every_permission_check_targets_a_supported_op() -> None:
    """Sens 2 : aucun check orphelin (porte sur une `(table, op)` que le handler ne gère pas)."""
    for table, op in PERMISSION_CHECKS:
        assert table in SUPPORTED_OPS, f"check pour une table sans handler : {table}"
        assert op in SUPPORTED_OPS[table], f"check pour une op non gérée : ({table}, {op})"
