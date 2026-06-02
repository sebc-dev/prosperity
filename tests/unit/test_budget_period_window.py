"""Unit tests for `compute_period_window` (S08.2, P08.2.1).

`compute_period_window` is pure (no session/DB/clock). Two layers
(Stratégie de tests §4.1/§4.2):

* example-based — the calendar cases that pin behaviour (monthly/quarterly/
  yearly, mid-month anchor with window flip, Jan-31 → Feb clamp, as_of before
  the anchor);
* property-based (Hypothesis, `max_examples=200 ≥ 100`) — the structural
  invariants: `start ≤ as_of < end`, adjacent windows contiguous & disjoint,
  idempotence inside a window, `start < end`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import get_args

import hypothesis.strategies as st
from hypothesis import given, settings

from backend.modules.budget.domain import PeriodKind, compute_period_window

_KINDS: tuple[PeriodKind, ...] = ("monthly", "quarterly", "yearly")


def test_kinds_match_period_kind_literal() -> None:
    # Garde-fou anti-dérive : la stratégie Hypothesis (`_KINDS`) doit couvrir
    # exactement le type public `PeriodKind`. Un genre supporté par le Literal
    # mais absent de `_MONTHS_PER_PERIOD` ferait `KeyError` dans les properties
    # ci-dessous (qui échantillonnent `_KINDS`) → drift transitivement attrapé.
    assert set(_KINDS) == set(get_args(PeriodKind))


# Bound the date strategy so the linear window search stays cheap while still
# covering several periods either side of the anchor.
_period_kinds = st.sampled_from(_KINDS)
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


# ---------------------------------------------------------------------------
# Example-based
# ---------------------------------------------------------------------------


def test_monthly_window_anchored_first() -> None:
    assert compute_period_window("monthly", date(2026, 6, 1), date(2026, 6, 15)) == (
        date(2026, 6, 1),
        date(2026, 7, 1),
    )


def test_monthly_window_anchored_mid_month() -> None:
    # Ancré le 15 : as_of=20 reste dans la fenêtre courante…
    assert compute_period_window("monthly", date(2026, 6, 15), date(2026, 6, 20)) == (
        date(2026, 6, 15),
        date(2026, 7, 15),
    )
    # …as_of=10 bascule sur la fenêtre précédente.
    assert compute_period_window("monthly", date(2026, 6, 15), date(2026, 6, 10)) == (
        date(2026, 5, 15),
        date(2026, 6, 15),
    )


def test_monthly_window_anchor_31_clamps_february() -> None:
    # Ancre le 31 → fév clampé à 28 (2026 non bissextile) ; contiguïté préservée.
    assert compute_period_window("monthly", date(2026, 1, 31), date(2026, 2, 10)) == (
        date(2026, 1, 31),
        date(2026, 2, 28),
    )
    assert compute_period_window("monthly", date(2026, 1, 31), date(2026, 3, 15)) == (
        date(2026, 2, 28),
        date(2026, 3, 31),
    )


def test_monthly_window_anchor_31_clamps_leap_february() -> None:
    # Ancre le 31 → fév 2024 (bissextile) clampé à 29 ; contiguïté préservée
    # malgré le clamp variable (28 vs 29 selon l'année).
    assert compute_period_window("monthly", date(2024, 1, 31), date(2024, 2, 15)) == (
        date(2024, 1, 31),
        date(2024, 2, 29),
    )
    assert compute_period_window("monthly", date(2024, 1, 31), date(2024, 3, 5)) == (
        date(2024, 2, 29),
        date(2024, 3, 31),
    )


def test_quarterly_window() -> None:
    assert compute_period_window("quarterly", date(2026, 1, 1), date(2026, 5, 10)) == (
        date(2026, 4, 1),
        date(2026, 7, 1),
    )


def test_quarterly_window_spanning_year() -> None:
    # Trimestre ancré le 1er nov 2025 : as_of en fév 2026 → fenêtre à cheval sur
    # l'année [2026-02-01, 2026-05-01).
    assert compute_period_window("quarterly", date(2025, 11, 1), date(2026, 2, 10)) == (
        date(2026, 2, 1),
        date(2026, 5, 1),
    )


def test_yearly_window() -> None:
    assert compute_period_window("yearly", date(2026, 1, 1), date(2027, 3, 1)) == (
        date(2027, 1, 1),
        date(2028, 1, 1),
    )


def test_yearly_window_anchored_mid_year_spans_two_calendar_years() -> None:
    # Annuel ancré le 1er juil : la fenêtre couvre [juil N, juil N+1).
    assert compute_period_window("yearly", date(2026, 7, 1), date(2027, 2, 1)) == (
        date(2026, 7, 1),
        date(2027, 7, 1),
    )


def test_as_of_equals_start_is_in_window() -> None:
    # Borne basse inclusive : as_of == period_start → start == period_start.
    start, end = compute_period_window("monthly", date(2026, 6, 1), date(2026, 6, 1))
    assert start == date(2026, 6, 1)
    assert end == date(2026, 7, 1)


def test_as_of_before_anchor_walks_back() -> None:
    # Branche `k -= 1` : as_of strictement avant l'ancre → fenêtre antérieure.
    assert compute_period_window("monthly", date(2026, 6, 15), date(2026, 1, 5)) == (
        date(2025, 12, 15),
        date(2026, 1, 15),
    )


def test_quarterly_window_before_anchor() -> None:
    assert compute_period_window("quarterly", date(2026, 1, 1), date(2025, 11, 20)) == (
        date(2025, 10, 1),
        date(2026, 1, 1),
    )


# ---------------------------------------------------------------------------
# Property-based (Hypothesis)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(kind=_period_kinds, period_start=_dates, as_of=_dates)
def test_property_as_of_within_window(kind: PeriodKind, period_start: date, as_of: date) -> None:
    start, end = compute_period_window(kind, period_start, as_of)
    assert start <= as_of < end


@settings(max_examples=200)
@given(kind=_period_kinds, period_start=_dates, as_of=_dates)
def test_property_end_strictly_after_start(
    kind: PeriodKind, period_start: date, as_of: date
) -> None:
    start, end = compute_period_window(kind, period_start, as_of)
    assert start < end


@settings(max_examples=200)
@given(kind=_period_kinds, period_start=_dates, as_of=_dates)
def test_property_adjacent_windows_contiguous_and_disjoint(
    kind: PeriodKind, period_start: date, as_of: date
) -> None:
    _start, end = compute_period_window(kind, period_start, as_of)
    # `end` (exclusive) appartient à la fenêtre suivante : sa fenêtre commence
    # exactement à `end` (contiguïté) → les deux intervalles sont disjoints.
    next_start, next_end = compute_period_window(kind, period_start, end)
    assert next_start == end
    assert end < next_end  # la fenêtre suivante est non vide
    # Disjonction : [start, end) ∩ [next_start, next_end) = ∅.
    assert end <= next_start


@settings(max_examples=200)
@given(kind=_period_kinds, period_start=_dates, as_of=_dates, data=st.data())
def test_property_idempotent_within_window(
    kind: PeriodKind, period_start: date, as_of: date, data: st.DataObject
) -> None:
    start, end = compute_period_window(kind, period_start, as_of)
    span_days = (end - start).days
    # Tout autre `as_of'` dans [start, end) retombe sur la même fenêtre.
    offset = data.draw(st.integers(min_value=0, max_value=span_days - 1))
    as_of_prime = start + timedelta(days=offset)
    assert compute_period_window(kind, period_start, as_of_prime) == (start, end)
