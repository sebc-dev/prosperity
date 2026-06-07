"""Unit tests for `_consumption_filters` window optionality (S11.4 P11.4.1).

The single-source filter block (`budget.service.consumption._consumption_filters`)
gained optional `start`/`end` so the reclassement enumeration can sweep a
recurring budget's WHOLE history (no window bound, D4). These pure tests pin the
NUMBER and SHAPE of the predicates produced — no DB needed (the test tree is
outside the import-linter root, so importing the private helper is allowed).
"""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt
from uuid import uuid4

from backend.modules.budget.service.consumption import _consumption_filters

_SUBTREE = [uuid4()]
_ACCOUNTS = [uuid4()]


def test_without_window_omits_both_date_predicates() -> None:
    # No start/end (reclassement sweep): the two date predicates are dropped, the
    # five state/subtree/account/currency/override predicates remain.
    filters = _consumption_filters(subtree=_SUBTREE, accounts=_ACCOUNTS, currency="EUR")
    assert len(filters) == 5


def test_with_window_adds_both_date_predicates() -> None:
    # Full window (S08 consumption): the two date bounds are appended.
    filters = _consumption_filters(
        subtree=_SUBTREE,
        accounts=_ACCOUNTS,
        currency="EUR",
        start=dt.date(2026, 6, 1),
        end=dt.date(2026, 7, 1),
    )
    assert len(filters) == 7


def test_start_only_adds_one_predicate() -> None:
    # Each bound is independent: a lone `start` adds exactly one predicate.
    filters = _consumption_filters(
        subtree=_SUBTREE, accounts=_ACCOUNTS, currency="EUR", start=dt.date(2026, 6, 1)
    )
    assert len(filters) == 6


def test_before_keyset_appends_one_predicate() -> None:
    # The ordered-window `before` keyset is additive on top of the base five.
    filters = _consumption_filters(
        subtree=_SUBTREE,
        accounts=_ACCOUNTS,
        currency="EUR",
        before=(dt.date(2026, 6, 10), uuid4()),
    )
    assert len(filters) == 6
