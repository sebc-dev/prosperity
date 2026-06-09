"""Unit tests for the pure date-window helper of `banking.service.import_ofx` (S12.3).

`_shift_years` is the ±3-year boundary arithmetic of criterion ③. Pure (no DB),
so test it directly — the only subtle case is the leap-day clamp (29 Feb → 28
when the target year is not a leap year), which the integration tier's
`reference_date`-driven boundary tests do not reach.
"""

# Teste le helper privé `_shift_years` directement → on neutralise
# reportPrivateUsage (gabarit test_ofx_provider.py / test_consumption_filters.py).
# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt

from backend.modules.banking.service.import_ofx import _shift_years


def test_shift_years_leap_day_clamps_to_28() -> None:
    # 2027 / 2021 are not leap years → 29 Feb clamps to 28.
    assert _shift_years(dt.date(2024, 2, 29), 3) == dt.date(2027, 2, 28)
    assert _shift_years(dt.date(2024, 2, 29), -3) == dt.date(2021, 2, 28)


def test_shift_years_leap_to_leap_keeps_29() -> None:
    # 2028 IS a leap year → 29 Feb is preserved.
    assert _shift_years(dt.date(2024, 2, 29), 4) == dt.date(2028, 2, 29)


def test_shift_years_ordinary_date() -> None:
    assert _shift_years(dt.date(2026, 6, 9), 3) == dt.date(2029, 6, 9)
    assert _shift_years(dt.date(2026, 6, 9), -3) == dt.date(2023, 6, 9)
