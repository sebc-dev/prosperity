"""Unit tests for `backend.shared.bank_labels` (S12.3, P12.3.2).

Pure unit tier — no DB. Pins the canonical `normalize_label` (shared with the
future `reconciliation` `MatchScorer`, CONTEXT.md §MatchScorer) and the
deterministic `import_hash` (sha256 composite, FITID never used). The
serialisation format is PERSISTED in `imported_transactions.import_hash`, so a
known-vector test locks it: any format change must fail loudly (it would
silently break dedup over history otherwise).
"""

from __future__ import annotations

import datetime as dt
import re
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from backend.shared.bank_labels import import_hash, normalize_label

_UUID = UUID("00000000-0000-0000-0000-000000000001")
_DATE = dt.date(2026, 1, 2)

# ---------------------------------------------------------------------------
# normalize_label — example-based
# ---------------------------------------------------------------------------


def test_strip_and_lowercase() -> None:
    assert normalize_label("  CARREFOUR  ") == "carrefour"


def test_strips_each_prefix() -> None:
    assert normalize_label("PRLV SEPA EDF") == "edf"
    assert normalize_label("CB FNAC") == "fnac"
    assert normalize_label("VIR Salaire") == "salaire"
    assert normalize_label("PAIEMENT Amazon") == "amazon"
    assert normalize_label("VIR SEPA Loyer") == "loyer"


def test_prefix_order_longest_first() -> None:
    # The longest prefix must win in the same iteration: "VIR SEPA" collapses to
    # "" (not "sepa"). A future reordering of `_BANK_PREFIXES` that let "vir"
    # match first would silently break the dedup → this test would fail loudly.
    assert normalize_label("VIR SEPA") == ""
    assert normalize_label("PRLV SEPA") == ""


def test_strips_stacked_prefixes() -> None:
    assert normalize_label("VIR SEPA CB Truc") == "truc"
    assert normalize_label("PRLV PRLV SEPA EDF") == "edf"


def test_strips_iso_dates() -> None:
    assert normalize_label("CB 2026-01-15 RESTO") == "resto"


def test_collapses_whitespace() -> None:
    assert normalize_label("a\t b\n c") == "a b c"


def test_prefix_substring_not_stripped() -> None:
    # Word boundary: "cbtest" is not the "cb " prefix → left untouched.
    assert normalize_label("cbtest") == "cbtest"


def test_normalize_label_empty() -> None:
    assert normalize_label("") == ""
    assert normalize_label("   ") == ""
    assert normalize_label("PRLV SEPA") == ""  # prefix-only ⇒ empty label


def test_strips_control_chars() -> None:
    # All C0/DEL removed, not just the `\s`-covered whitespace — guarantees the
    # `\x1f` hash separator can never appear in a normalized label.
    assert normalize_label("a\x1fb") == "a b"
    assert normalize_label("a\x00b") == "a b"
    assert normalize_label("a\x7fb") == "a b"


# ---------------------------------------------------------------------------
# normalize_label — property-based (Hypothesis, strategy §4.2)
# ---------------------------------------------------------------------------


@given(st.text())
def test_property_idempotent(x: str) -> None:
    once = normalize_label(x)
    assert normalize_label(once) == once


@given(st.text())
def test_property_no_control_chars(x: str) -> None:
    # st.text() generates control chars / surrogates; the output must contain no
    # C0/DEL (hence never `\x1f`) and no double whitespace — injection-safety of
    # the hash separator, independent of CPython's `\s` behaviour.
    out = normalize_label(x)
    assert not re.search(r"[\x00-\x1f\x7f]", out)
    assert "  " not in out
    assert out == out.strip()


# ---------------------------------------------------------------------------
# import_hash — example + property-based
# ---------------------------------------------------------------------------


def test_known_vector() -> None:
    # Serialisation lock (D2): the format is persisted; any change breaks this.
    assert import_hash(_UUID, _DATE, -1234, "carrefour") == (
        "dc6937db88eb234deb9bf220e81a93bc7851c5a2a54cf282255c04d573709c13"
    )


def test_format_is_64_hex_lower() -> None:
    h = import_hash(_UUID, _DATE, 100, "anything")
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_property_deterministic() -> None:
    a = import_hash(_UUID, _DATE, -1234, "carrefour")
    b = import_hash(_UUID, _DATE, -1234, "carrefour")
    assert a == b


@given(
    a1=st.uuids(),
    a2=st.uuids(),
    d=st.dates(),
    c=st.integers(min_value=-(10**9), max_value=10**9),
    label=st.text(),
)
def test_property_sensitive_to_account(a1: UUID, a2: UUID, d: dt.date, c: int, label: str) -> None:
    if a1 != a2:
        assert import_hash(a1, d, c, label) != import_hash(a2, d, c, label)


@given(
    a=st.uuids(),
    d1=st.dates(),
    d2=st.dates(),
    c=st.integers(min_value=-(10**9), max_value=10**9),
    label=st.text(),
)
def test_property_sensitive_to_date(a: UUID, d1: dt.date, d2: dt.date, c: int, label: str) -> None:
    if d1 != d2:
        assert import_hash(a, d1, c, label) != import_hash(a, d2, c, label)


@given(
    a=st.uuids(),
    d=st.dates(),
    c1=st.integers(min_value=-(10**9), max_value=10**9),
    c2=st.integers(min_value=-(10**9), max_value=10**9),
    label=st.text(),
)
def test_property_sensitive_to_amount(a: UUID, d: dt.date, c1: int, c2: int, label: str) -> None:
    if c1 != c2:
        assert import_hash(a, d, c1, label) != import_hash(a, d, c2, label)


@given(
    a=st.uuids(),
    d=st.dates(),
    c=st.integers(min_value=-(10**9), max_value=10**9),
    l1=st.text(),
    l2=st.text(),
)
def test_property_sensitive_to_label(a: UUID, d: dt.date, c: int, l1: str, l2: str) -> None:
    # `\x1f`-joined serialisation differs as soon as any field differs — a strong
    # deterministic invariant that avoids reasoning about sha256 collisions.
    if l1 != l2:
        assert import_hash(a, d, c, l1) != import_hash(a, d, c, l2)


def test_dedup_equivalence() -> None:
    # Business dedup invariant: two labels equivalent after normalization
    # deliberately collide.
    assert import_hash(_UUID, _DATE, 500, normalize_label("PRLV SEPA EDF")) == import_hash(
        _UUID, _DATE, 500, normalize_label("  edf  ")
    )
