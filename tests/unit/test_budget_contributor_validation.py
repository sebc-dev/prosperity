"""Unit tests for `budget.domain.validate_contributor_count` (S08.4, P08.4.1).

The pure count/shape half of the contributor invariant (CONTEXT.md §Budget):
`personal ⇒ exactly its owner`, `shared ⇒ ≥ 2 distinct contributors`, any other
scope → fail-closed. The DB-backed "each shared contributor is a member of a
common account" check lives at the service (`budget_crud`), tested in the
integration tier.

**Example-based, deliberately not Hypothesis.** `validate_contributor_count` is
pure and takes `(scope, set of UUIDs, created_by)` — a *formal* property-based
candidate, but its logic is a 3-way branch with **no quantifiable invariant**
(no commutativity / idempotence / monotonicity to exercise): a property would be
either tautological or a mere re-enumeration of these cases. Contrast with
`compute_period_window` (P08.2.1), which *does* carry real invariants and so has
a Hypothesis property. No DB → `unit` tier.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.modules.budget.domain import (
    BudgetContributorError,
    BudgetError,
    validate_contributor_count,
)


def test_personal_with_owner_only_ok() -> None:
    owner = uuid4()
    validate_contributor_count(scope="personal", contributor_ids=[owner], created_by=owner)


def test_personal_with_extra_contributor_rejected() -> None:
    owner = uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(
            scope="personal", contributor_ids=[owner, uuid4()], created_by=owner
        )


def test_personal_with_non_owner_rejected() -> None:
    owner = uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(scope="personal", contributor_ids=[uuid4()], created_by=owner)


def test_personal_with_empty_rejected() -> None:
    owner = uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(scope="personal", contributor_ids=[], created_by=owner)


def test_shared_with_two_ok() -> None:
    owner, other = uuid4(), uuid4()
    validate_contributor_count(scope="shared", contributor_ids=[owner, other], created_by=owner)


def test_shared_with_one_rejected() -> None:
    owner = uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(scope="shared", contributor_ids=[owner], created_by=owner)


def test_shared_with_duplicate_rejected() -> None:
    a, b = uuid4(), uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(scope="shared", contributor_ids=[a, a, b], created_by=a)


def test_unknown_scope_fail_closed() -> None:
    # Covers the `else` branch — never a dead branch.
    owner = uuid4()
    with pytest.raises(BudgetContributorError):
        validate_contributor_count(scope="weird", contributor_ids=[owner], created_by=owner)


def test_contributor_error_is_budget_error() -> None:
    assert issubclass(BudgetContributorError, BudgetError)
