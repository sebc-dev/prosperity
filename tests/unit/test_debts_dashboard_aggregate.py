"""Unit tests for `_aggregate_net` — the only PURE function S09.4 introduces.

`_aggregate_net(debts, viewer_id)` collapses a list of (already masked)
`DebtWithContext` into one signed `net_amount_cents` per counterparty, oriented
from the viewer's perspective: `+` when the counterparty owes the viewer, `−`
when the viewer owes the counterparty (D10). No DB — the function is pure.

Beyond the example-based cases, two structurally-loaded checks:

- `test_property_net_is_antisymmetric_by_viewer` (Hypothesis): the net A sees on
  B is exactly the opposite of the net B sees on A (and the counts match). This
  is the "antisymmetric debt matrix" invariant the test strategy lists for
  `debts`; the function is introduced here, so the invariant is locked here.
- `test_aggregate_net_raises_on_mixed_currency`: `Money` refuses cross-currency
  arithmetic (fail-safe ADR 0008). Mono-currency V1 is precisely when this guard
  is testable before multi-currency arrives.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from backend.modules.debts.service.dashboard import (
    CounterpartyNet,
    DebtWithContext,
    _aggregate_net,  # pyright: ignore[reportPrivateUsage]
)
from backend.shared.money import IncompatibleCurrencyError

_CREATED_AT = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def _debt(
    *,
    frm: UUID,
    to: UUID,
    amount_cents: int,
    currency: str = "EUR",
    remaining_cents: int | None = None,
) -> DebtWithContext:
    """A minimal `DebtWithContext` for the aggregate (masked fields irrelevant here).

    `remaining_cents` defaults to `amount_cents` (no settlement → remaining ==
    amount, S09.4 non-regression). Pass it explicitly to model a partially
    settled debt — the aggregate sums the REMAINING, not the initial amount (D6).
    """
    return DebtWithContext(
        debt_id=uuid4(),
        from_user_id=frm,
        to_user_id=to,
        amount_cents=amount_cents,
        currency=currency,
        origin="personal_share_request",
        requested_by=to,
        short_label="x",
        category_id=None,
        date=None,
        created_at=_CREATED_AT,
        source_transaction_id=None,
        account_id=None,
        remaining_cents=amount_cents if remaining_cents is None else remaining_cents,
    )


def _net_for(rows: list[CounterpartyNet], counterparty: UUID) -> int | None:
    for r in rows:
        if r.user_id == counterparty:
            return r.net_amount_cents
    return None


def test_net_positive_when_counterparty_owes_me() -> None:
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net([_debt(frm=bob, to=me, amount_cents=4000)], viewer_id=me)
    assert len(rows) == 1
    assert rows[0].user_id == bob
    assert rows[0].net_amount_cents == 4000
    assert rows[0].debts_count == 1
    assert rows[0].currency == "EUR"


def test_net_negative_when_i_owe() -> None:
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net([_debt(frm=me, to=bob, amount_cents=4000)], viewer_id=me)
    assert rows[0].user_id == bob
    assert rows[0].net_amount_cents == -4000
    assert rows[0].debts_count == 1


def test_net_offsets_two_directions() -> None:
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net(
        [
            _debt(frm=bob, to=me, amount_cents=4000),  # Bob me doit 40€
            _debt(frm=me, to=bob, amount_cents=1500),  # je dois 15€ à Bob
        ],
        viewer_id=me,
    )
    assert len(rows) == 1
    assert rows[0].user_id == bob
    assert rows[0].net_amount_cents == 2500
    assert rows[0].debts_count == 2


def test_net_uses_remaining_not_initial_amount() -> None:
    # D6: a partially settled debt contributes its REMAINING, not its initial
    # `amount_cents`. Bob owes Alice 40€ initially, 15€ already settled → net 25€.
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net(
        [_debt(frm=bob, to=me, amount_cents=4000, remaining_cents=1500)], viewer_id=me
    )
    assert len(rows) == 1
    assert rows[0].user_id == bob
    assert rows[0].net_amount_cents == 1500  # remaining, not the 4000 initial


def test_zero_remaining_debt_still_counts() -> None:
    # D7: a fully settled debt (remaining 0) contributes 0 to the net but still
    # increments `debts_count` (the dashboard is the complete register).
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net(
        [_debt(frm=bob, to=me, amount_cents=4000, remaining_cents=0)], viewer_id=me
    )
    assert len(rows) == 1
    assert rows[0].net_amount_cents == 0
    assert rows[0].debts_count == 1


def test_net_zero_on_exact_offset() -> None:
    # Exact compensation ("quitte") : la ligne de contrepartie est tout de même
    # émise avec net 0 et le `debts_count` complet — elle n'est PAS supprimée.
    me, bob = uuid4(), uuid4()
    rows = _aggregate_net(
        [
            _debt(frm=bob, to=me, amount_cents=4000),  # Bob me doit 40€
            _debt(frm=me, to=bob, amount_cents=4000),  # je dois 40€ à Bob
        ],
        viewer_id=me,
    )
    assert len(rows) == 1
    assert rows[0].user_id == bob
    assert rows[0].net_amount_cents == 0
    assert rows[0].debts_count == 2


def test_groups_by_distinct_counterparties() -> None:
    me, bob, carol = uuid4(), uuid4(), uuid4()
    rows = _aggregate_net(
        [
            _debt(frm=bob, to=me, amount_cents=1000),
            _debt(frm=me, to=carol, amount_cents=2000),
        ],
        viewer_id=me,
    )
    assert len(rows) == 2
    # Deterministic order: sorted by stringified user_id.
    assert [r.user_id for r in rows] == sorted([bob, carol], key=str)
    assert _net_for(rows, bob) == 1000
    assert _net_for(rows, carol) == -2000


def test_empty_when_no_debts() -> None:
    assert _aggregate_net([], viewer_id=uuid4()) == []


def test_aggregate_net_raises_on_mixed_currency() -> None:
    # Two debts on the SAME counterparty in distinct currencies → Money.__add__
    # raises IncompatibleCurrencyError (fail-safe ADR 0008). Mono-currency V1 is
    # the only window where this is verifiable.
    me, bob = uuid4(), uuid4()
    with pytest.raises(IncompatibleCurrencyError):
        _aggregate_net(
            [
                _debt(frm=bob, to=me, amount_cents=1000, currency="EUR"),
                _debt(frm=bob, to=me, amount_cents=1000, currency="USD"),
            ],
            viewer_id=me,
        )


# Two fixed users so every generated debt is on the SINGLE A↔B pair (so the
# antisymmetry comparison has a well-defined counterparty on each side).
_A = UUID("00000000-0000-0000-0000-0000000000aa")
_B = UUID("00000000-0000-0000-0000-0000000000bb")

# (a_is_creditor, remaining_cents): if True the debt is B→A (A is creditor), else
# A→B. `remaining_cents` spans NEGATIVE values (∈ [−10⁹, 10⁹]) to lock D2 at the
# unit level: `_aggregate_net` sums the remaining via `Money(-x)` which must not
# raise on a negative balance (no clamp — an over-settlement stays visible).
_debt_specs = st.lists(
    st.tuples(st.booleans(), st.integers(min_value=-(10**9), max_value=10**9)),
    max_size=20,
)


@given(specs=_debt_specs)
@example(specs=[(True, 4000), (False, 1500)])  # pins the concrete offset case (#3)
@example(specs=[(True, -2500)])  # pins a negative-remaining debt (D2)
def test_property_net_is_antisymmetric_by_viewer(specs: list[tuple[bool, int]]) -> None:
    """net(A sees B) == -net(B sees A), and the counts match (D10).

    Non-tautological: relates two independent calls with swapped viewers, not a
    restatement of the implementation. The aggregate sums `remaining_cents`, so
    the spec generates remaining balances (incl. negative — D2).
    """
    debts = [
        _debt(frm=_B, to=_A, amount_cents=abs(rem) + 1, remaining_cents=rem)
        if a_creditor
        else _debt(frm=_A, to=_B, amount_cents=abs(rem) + 1, remaining_cents=rem)
        for a_creditor, rem in specs
    ]
    from_a = _aggregate_net(debts, viewer_id=_A)
    from_b = _aggregate_net(debts, viewer_id=_B)

    net_a_on_b = _net_for(from_a, _B)
    net_b_on_a = _net_for(from_b, _A)

    if not specs:  # no debts → no counterparty line on either side
        assert net_a_on_b is None and net_b_on_a is None
        return

    assert net_a_on_b is not None and net_b_on_a is not None
    assert net_a_on_b == -net_b_on_a
    # debts_count is symmetric (same set of debts, same pair).
    count_a = next(r.debts_count for r in from_a if r.user_id == _B)
    count_b = next(r.debts_count for r in from_b if r.user_id == _A)
    assert count_a == count_b == len(specs)
