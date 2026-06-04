"""Unit tests for `backend.modules.debts.schemas` (S09.3 boundary validation).

Locks the `short_label` whitelist (review #144 security `Majeur`): a whitelist of
ASCII + printable Latin-1 must accept French accents while rejecting controls,
BiDi overrides, zero-width joiners, NBSP & every non-space `Zs`, SHY, and
non-Latin homoglyphs. Also pins `ratio` bounds and `extra="forbid"` (anti
`by_user_id` smuggling, D7). No DB needed — pure boundary validation.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.modules.debts.schemas import ShareRequestCreate


def _make(**overrides: object) -> ShareRequestCreate:
    body: dict[str, object] = {
        "requested_from": str(uuid4()),
        "ratio": "0.5",
        "short_label": "Diner",
    }
    body.update(overrides)
    return ShareRequestCreate.model_validate(body)


def test_accepts_french_accents() -> None:
    # Café (é U+00E9), dîner (î U+00EE), août (û U+00FB) — all printable Latin-1.
    # An em-dash (U+2014) would be rejected: the whitelist stops at Latin-1.
    label = "  " + "Café & dîner - août" + "  "
    sr = _make(short_label=label)
    assert sr.short_label == "Café & dîner - août"  # trimmed, accents kept


def test_ratio_bounds() -> None:
    assert _make(ratio="1").ratio == Decimal("1")
    for bad in ("0", "-0.1", "1.5"):
        with pytest.raises(ValidationError):
            _make(ratio=bad)


# Built with explicit codepoints so the source file carries no invisible /
# ambiguous characters — each is a vector the whitelist must reject. NBSP
# survives `.strip()`, so it reaches the whitelist rather than being trimmed.
_DISALLOWED_LABELS = [
    "with\nnewline",  # U+000A Cc control
    "with\x00null",  # U+0000 NUL
    "bidi" + chr(0x202E) + "override",  # BiDi RTL override (Cf)
    "zero" + chr(0x200B) + "width",  # zero-width space (Cf)
    "nbsp" + chr(0x00A0) + "here",  # NBSP (Zs, survives .strip())
    "soft" + chr(0x00AD) + "hyphen",  # SHY (Cf)
    chr(0x0430) + chr(0x0431) + chr(0x0432),  # Cyrillic homoglyphs (non-Latin)
]


@pytest.mark.parametrize("label", _DISALLOWED_LABELS)
def test_rejects_disallowed_characters(label: str) -> None:
    with pytest.raises(ValidationError):
        _make(short_label=label)


def test_rejects_blank_after_trim() -> None:
    with pytest.raises(ValidationError):
        _make(short_label="   ")


def test_rejects_too_long() -> None:
    with pytest.raises(ValidationError):
        _make(short_label="x" * 101)


def test_rejects_extra_fields() -> None:
    # `by_user_id`/`requested_by` must NEVER ride the body (D7, extra="forbid").
    with pytest.raises(ValidationError):
        _make(by_user_id=str(uuid4()))
    with pytest.raises(ValidationError):
        _make(requested_by=str(uuid4()))
