"""Unit tests for `sanitize_device_label` (story S02.4)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from backend.modules.auth.schemas import DEVICE_LABEL_MAX, sanitize_device_label


@given(st.text())
def test_sanitize_invariants(s: str) -> None:
    """For any input, output is None or a bounded ASCII-printable string."""
    out = sanitize_device_label(s)
    assert out is None or (
        len(out) <= DEVICE_LABEL_MAX
        and all(0x20 <= ord(c) <= 0x7E for c in out)
        and out == out.strip()
    )


@given(st.text())
def test_sanitize_is_idempotent(s: str) -> None:
    """sanitize(sanitize(x)) == sanitize(x) — guards against drift if strip/
    truncate ever reintroduce non-printable chars or trailing whitespace."""
    once = sanitize_device_label(s)
    twice = sanitize_device_label(once)
    assert once == twice


def test_sanitize_returns_none_for_none() -> None:
    assert sanitize_device_label(None) is None


def test_sanitize_returns_none_for_empty_string() -> None:
    assert sanitize_device_label("") is None


def test_sanitize_returns_none_when_only_whitespace() -> None:
    assert sanitize_device_label("   \t  ") is None


def test_sanitize_returns_none_when_only_control_chars() -> None:
    # All chars < 0x20 -> stripped -> empty -> None.
    assert sanitize_device_label("\x00\x01\x02") is None


def test_sanitize_passes_through_typical_user_agent() -> None:
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    assert sanitize_device_label(ua) == ua


def test_sanitize_strips_bidi_override() -> None:
    bidi = "\u202e"  # LEFT-TO-RIGHT OVERRIDE
    raw = f"Mozilla/5.0 {bidi}moz"
    out = sanitize_device_label(raw)
    assert out is not None
    assert bidi not in out
    assert out == "Mozilla/5.0 moz"


def test_sanitize_strips_zero_width_joiner() -> None:
    zwj = "\u200d"  # ZERO WIDTH JOINER
    raw = f"iPhone{zwj}OS/17"
    out = sanitize_device_label(raw)
    assert out is not None
    assert zwj not in out
    assert out == "iPhoneOS/17"


def test_sanitize_strips_cyrillic_homoglyphs() -> None:
    # Cyrillic small letter a (U+0430) is outside the ASCII printable range
    # and would otherwise be stored looking identical to Latin 'a'.
    cyrillic_a = "\u0430"
    raw = f"Firefox/1{cyrillic_a}0"
    out = sanitize_device_label(raw)
    assert out is not None
    assert cyrillic_a not in out
    assert out == "Firefox/10"


def test_sanitize_truncates_to_120_chars() -> None:
    raw = "A" * 500
    out = sanitize_device_label(raw)
    assert out is not None
    assert len(out) == DEVICE_LABEL_MAX
