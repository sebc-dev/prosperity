"""Unit tests for `_consumption_filters` window optionality (S11.4 P11.4.1).

The single-source filter block (`budget.service.consumption._consumption_filters`)
gained optional `start`/`end` so the reclassement enumeration can sweep a
recurring budget's WHOLE history (no window bound, D4). These pure tests pin the
**identity** of the predicates produced (which columns are bound, not merely how
many) — no DB needed (the test tree is outside the import-linter root, so
importing the private helper is allowed).

Asserting on *which* predicate is present (vs `len(...)`) is deliberate: a
regression that dropped `state == "confirmed"` and re-added a stray `date >=`
would keep the count identical yet silently change the meaning — exactly the
false-green the test strategy §12 warns against.
"""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy.sql.elements import ColumnElement

from backend.modules.budget.service.consumption import _consumption_filters

_SUBTREE = [uuid4()]
_ACCOUNTS = [uuid4()]

# The five window-independent predicates that define « un split compté » — always
# present whatever the date bounds (subtree, account, currency, confirmed, override).
_INVARIANTS = (
    "splits.category_id in",
    "splits.account_id in",
    "splits.currency =",
    "transactions.state =",
    "transactions.debt_generation_override !=",
)


def _sql(filters: Sequence[ColumnElement[bool]]) -> list[str]:
    """Compiled, lowercased SQL fragment of each predicate (stable string form)."""
    return [str(f).lower().strip() for f in filters]


def _has_invariants(sql: list[str]) -> bool:
    return all(any(inv in frag for frag in sql) for inv in _INVARIANTS)


def _has_start(sql: list[str]) -> bool:  # scalar lower bound `date >=`
    return any(frag.startswith("transactions.date >=") for frag in sql)


def _has_end(sql: list[str]) -> bool:  # scalar upper bound `date <` (NOT the tuple)
    return any(frag.startswith("transactions.date <") for frag in sql)


def _has_before(sql: list[str]) -> bool:  # keyset tuple `(date, id) < ...`
    return any("transactions.id" in frag and frag.startswith("(transactions.date") for frag in sql)


def test_without_window_omits_both_date_predicates() -> None:
    # No start/end (reclassement sweep): the two date predicates are dropped, the
    # five invariants remain — and ONLY them.
    sql = _sql(_consumption_filters(subtree=_SUBTREE, accounts=_ACCOUNTS, currency="EUR"))
    assert _has_invariants(sql)
    assert not _has_start(sql)
    assert not _has_end(sql)
    assert not _has_before(sql)
    assert len(sql) == 5  # nothing else snuck in


def test_with_window_adds_both_date_predicates() -> None:
    # Full window (S08 consumption): both date bounds appended, invariants intact.
    sql = _sql(
        _consumption_filters(
            subtree=_SUBTREE,
            accounts=_ACCOUNTS,
            currency="EUR",
            start=dt.date(2026, 6, 1),
            end=dt.date(2026, 7, 1),
        )
    )
    assert _has_invariants(sql)
    assert _has_start(sql) and _has_end(sql)
    assert not _has_before(sql)


def test_start_only_adds_lower_bound_only() -> None:
    # A lone `start` adds the lower bound and NOT the upper one (each bound is
    # independent — the count alone could not distinguish start from end).
    sql = _sql(
        _consumption_filters(
            subtree=_SUBTREE, accounts=_ACCOUNTS, currency="EUR", start=dt.date(2026, 6, 1)
        )
    )
    assert _has_invariants(sql)
    assert _has_start(sql)
    assert not _has_end(sql)


def test_end_only_adds_upper_bound_only() -> None:
    # Symmetric to the above — a lone `end` adds the upper bound and not the lower.
    sql = _sql(
        _consumption_filters(
            subtree=_SUBTREE, accounts=_ACCOUNTS, currency="EUR", end=dt.date(2026, 7, 1)
        )
    )
    assert _has_invariants(sql)
    assert _has_end(sql)
    assert not _has_start(sql)


def test_before_keyset_is_the_tuple_predicate_not_a_scalar_bound() -> None:
    # The ordered-window `before` keyset is the `(date, id)` tuple comparison —
    # distinct from a scalar `date <` bound (the distinction the old len()-only
    # test could not make).
    sql = _sql(
        _consumption_filters(
            subtree=_SUBTREE,
            accounts=_ACCOUNTS,
            currency="EUR",
            before=(dt.date(2026, 6, 10), uuid4()),
        )
    )
    assert _has_invariants(sql)
    assert _has_before(sql)
    assert not _has_start(sql)
    assert not _has_end(sql)
