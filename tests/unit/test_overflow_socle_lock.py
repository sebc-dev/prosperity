"""Regression locks for the overflow F10 socle (S11.1, P11.1.1).

The socle (`debt_generation_override` editable post-`confirmed` + exclusion of
`force_full_debt` from the budget consumption counter) was shipped in E07/E08 —
S11.1 does NOT recreate it. These locks ATTACH it explicitly to the E11 overflow
mechanics: they break — with an F10-pointing message — if a refactor silently
drops one of the invariants. No production code here (CONTEXT.md
§debt_generation_override).

The behavioural counterparts already exist (`test_transactions_editable.py`,
`test_budget_consumption.py::test_force_full_debt_excluded`); these unit locks
are the FAST, F10-owned complement (no DB, immediate failure).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from backend.modules.budget.service.consumption import (
    _consumption_filters,  # pyright: ignore[reportPrivateUsage]
)
from backend.modules.transactions.domain import EDITABLE_AFTER_CONFIRMED


def test_override_is_editable_after_confirmed() -> None:
    # F10: the override MUST stay editable after `confirmed` to drive the overflow
    # (re-)materialisation (S11.3). The D14 lock
    # (`test_editable_set_matches_model_fields`) pins the WHOLE partition; this
    # test gives the TARGETED failure "override left the editable set → F10 edit
    # breaks".
    assert "debt_generation_override" in EDITABLE_AFTER_CONFIRMED


def test_consumption_filters_exclude_force_full_debt() -> None:
    # STRUCTURAL lock on the single source (`_consumption_filters`, shared by the
    # aggregate and the drill-down): a `force_full_debt` transaction is "out of
    # budget" (CONTEXT.md §debt_generation_override). We compile the clauses to
    # PostgreSQL SQL and look for the exclusion predicate — it breaks the moment a
    # refactor drops it, with no DB nor a confirmed transaction to set up.
    #
    # Dummy UUIDs (never persisted) keep us on the function's contractual path:
    # production short-circuits BEFORE calling `_consumption_filters` when
    # subtree/accounts are empty, so passing `[]` would render a degenerate
    # `IN ()`. The explicit `postgresql` dialect pins the `!=` rendering to the
    # real DB's.
    clauses = _consumption_filters(
        subtree=[uuid4()],
        accounts=[uuid4()],
        currency="EUR",
        start=date(2026, 1, 1),
        end=date(2026, 2, 1),
    )
    rendered = " ; ".join(
        str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for c in clauses
    )
    # Match the FULL fragment, operator INCLUDED: asserting the column and the
    # value tokens separately would also pass on an INVERTED predicate
    # (`= 'force_full_debt'`, the worst regression — counting ONLY the overridden
    # transactions instead of excluding them). `literal_binds` + the postgres
    # dialect render exactly this string.
    assert "debt_generation_override != 'force_full_debt'" in rendered
