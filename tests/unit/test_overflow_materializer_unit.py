"""Unit tests for the pure helper of the overflow materializer (S11.3 P11.3.2).

`_classification_total_and_categories` operates on the domain `Transaction`
(not the DB), so its leg-summation logic is unit-testable WITHOUT testcontainers
(review Tests Mineur). The effectful handlers (upsert/prune, resolver, void) are
covered in `tests/integration/test_overflow_materializer.py`.

Tests may import `transactions.domain` (the test tree is outside the import-linter
root package) to build the aggregate the handler duck-types via its Protocol.
"""
# pyright: reportPrivateUsage=false
# (deliberately tests the private pure helper `_classification_total_and_categories`)

from __future__ import annotations

import datetime as dt
from uuid import uuid4

from backend.modules.debts.service.overflow_materializer import (
    _classification_total_and_categories,
)
from backend.modules.transactions.domain import Split, Transaction, TransactionState
from backend.shared.money import Money


def _tx(*splits: Split) -> Transaction:
    # DRAFT state bypasses the confirmed-only zero-sum validator, so a test can
    # focus on the classification summation without balancing the legs.
    return Transaction(
        id=uuid4(),
        account_id=uuid4(),
        date=dt.date(2026, 6, 1),
        state=TransactionState.DRAFT,
        created_by=uuid4(),
        splits=splits,
    )


def test_transfer_yields_zero_and_empty() -> None:
    # A transfer (two funding legs, no classification) → (Money 0, ∅).
    acc_a, acc_b = uuid4(), uuid4()
    tx = _tx(
        Split(account_id=acc_a, category_id=None, amount=Money(-5000, "EUR"), leg_role="funding"),
        Split(account_id=acc_b, category_id=None, amount=Money(5000, "EUR"), leg_role="funding"),
    )
    total, categories = _classification_total_and_categories(tx)
    assert total.amount_cents == 0
    assert categories == set()


def test_multi_classification_legs_sum_and_collect_categories() -> None:
    # Two classification legs → summed amount + the set of their category ids;
    # the funding leg is excluded from both the total and the category set.
    acc = uuid4()
    cat1, cat2 = uuid4(), uuid4()
    tx = _tx(
        Split(account_id=acc, category_id=None, amount=Money(-3000, "EUR"), leg_role="funding"),
        Split(
            account_id=acc, category_id=cat1, amount=Money(1000, "EUR"), leg_role="classification"
        ),
        Split(
            account_id=acc, category_id=cat2, amount=Money(2000, "EUR"), leg_role="classification"
        ),
    )
    total, categories = _classification_total_and_categories(tx)
    assert total == Money(3000, "EUR")
    assert categories == {cat1, cat2}


def test_single_classification_leg() -> None:
    acc, cat = uuid4(), uuid4()
    tx = _tx(
        Split(account_id=acc, category_id=None, amount=Money(-7500, "EUR"), leg_role="funding"),
        Split(
            account_id=acc, category_id=cat, amount=Money(7500, "EUR"), leg_role="classification"
        ),
    )
    total, categories = _classification_total_and_categories(tx)
    assert total == Money(7500, "EUR")
    assert categories == {cat}
