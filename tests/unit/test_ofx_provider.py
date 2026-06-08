"""Unit tests for `backend.modules.banking.providers.ofx` (S12.2, P12.2.1→4).

Pure unit tier — no DB, no event loop blocking. Covers: base parse + size guard
(D12), deterministic encoding detection across BOM/UTF-8/cp1252/UTF-16 (D4),
defensive exception wrapping — "jamais d'exception brute" (D10), XXE/entity
non-regression (D13), and the bi-format SGML 1.x ↔ XML 2.x mapping equivalence
(core of the story). Fixtures are 100% synthetic (no real bank PII).
"""

# Ce module teste des helpers privés (`_detect_encoding`, `OFXProvider._map`)
# qu'on veut épingler directement → on neutralise reportPrivateUsage (gabarit
# test_consumption_filters.py / test_overflow_materializer_unit.py).
# pyright: reportPrivateUsage=false

from __future__ import annotations

import codecs
import datetime as dt
import pathlib
from types import SimpleNamespace

import pytest
from ofxparse import OfxParser, OfxParserException

from backend.modules.banking.domain import (
    BankingProviderError,
    EncodingDetectionError,
    IncompatibleAccountError,
    ProviderUnavailableError,
)
from backend.modules.banking.providers import ofx as ofx_mod
from backend.modules.banking.providers.ofx import (
    MAX_OFX_BYTES,
    OFXProvider,
    _detect_encoding,
    parse_ofx,
)

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "ofx"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ---------------------------------------------------------------------------
# Base parse + size guard (P12.2.1)
# ---------------------------------------------------------------------------


async def test_parse_minimal_ofx() -> None:
    parsed = await OFXProvider().parse(_read("pel_2025_2026.ofx"))
    assert parsed.accounts == ("PEL-0000-9999",)
    assert len(parsed.transactions) == 2
    assert parsed.encoding_confidence == "high"
    first = parsed.transactions[0]
    assert isinstance(first.amount_cents, int)
    assert isinstance(first.date, dt.date)


async def test_parse_ofx_convenience_wrapper() -> None:
    parsed = await parse_ofx(_read("pel_2025_2026.ofx"))
    assert parsed.accounts == ("PEL-0000-9999",)


async def test_size_guard_rejects_oversize_without_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La garde précède tout décodage / to_thread : _detect_encoding ne doit pas être appelé.
    called = False

    def _boom(_blob: bytes) -> None:
        nonlocal called
        called = True
        raise AssertionError("decoding must not happen past the size guard")

    monkeypatch.setattr(ofx_mod, "_detect_encoding", _boom)
    with pytest.raises(IncompatibleAccountError):
        await OFXProvider().parse(b"x" * (MAX_OFX_BYTES + 1))
    assert called is False


# ---------------------------------------------------------------------------
# Encoding detection (P12.2.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "confidence"),
    [
        ("pel_2025_2026.ofx", "high"),  # UTF-8 BOM
        ("boursorama_export_2026.ofx", "high"),  # UTF-8 no BOM
        ("libelles_accentues_windows_1252.ofx", "low"),  # cp1252 fallback
        ("encoding_utf16.ofx", "high"),  # UTF-16 LE BOM
    ],
)
async def test_encoding_confidence_per_fixture(fixture: str, confidence: str) -> None:
    parsed = await OFXProvider().parse(_read(fixture))
    assert parsed.encoding_confidence == confidence


def test_detect_encoding_utf16_be_inline() -> None:
    # Demi-branche BOM_UTF16_BE (les fixtures fichier ne couvrent que LE).
    text, confidence = _detect_encoding(codecs.BOM_UTF16_BE + "héllo".encode("utf-16-be"))
    assert confidence == "high"
    assert text.endswith("héllo")


def test_detect_encoding_is_deterministic() -> None:
    blob = _read("libelles_accentues_windows_1252.ofx")
    assert _detect_encoding(blob) == _detect_encoding(blob)


async def test_cp1252_labels_decoded_without_mojibake() -> None:
    parsed = await OFXProvider().parse(_read("libelles_accentues_windows_1252.ofx"))
    payees = {t.payee for t in parsed.transactions}
    descriptions = {t.description for t in parsed.transactions}
    assert "Café Été" in payees
    assert "Déjeuner çà et là" in descriptions
    # Pas de mojibake : aucune séquence de double-encodage UTF-8-vu-comme-latin1.
    assert all("Ã" not in t.payee and "Ã" not in t.description for t in parsed.transactions)


def test_detect_encoding_undecodable_raises_typed() -> None:
    # Octet 0x81 : invalide en UTF-8 ET non assigné en cp1252 → EncodingDetectionError.
    with pytest.raises(EncodingDetectionError):
        _detect_encoding(b"\x81\x81\x81")


async def test_empty_file_raises_banking_error() -> None:
    # b"" décode en "" (high) puis OfxParser.parse("") échoue → filet typé.
    with pytest.raises(BankingProviderError):
        await OFXProvider().parse(b"")


# ---------------------------------------------------------------------------
# Defensive wrapping — "jamais d'exception brute qui fuit" (P12.2.3, D10)
# ---------------------------------------------------------------------------


async def test_corrupt_input_raises_incompatible_not_native() -> None:
    with pytest.raises(IncompatibleAccountError):
        await OFXProvider().parse(b"not an ofx file at all")


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        (OfxParserException("bad ofx"), IncompatibleAccountError),
        (OSError("disk gone"), ProviderUnavailableError),
        (ValueError("boom"), IncompatibleAccountError),  # filet except Exception
        (AttributeError("nope"), IncompatibleAccountError),  # filet except Exception
    ],
)
async def test_native_exceptions_wrapped_with_cause(
    monkeypatch: pytest.MonkeyPatch,
    native: Exception,
    expected: type[BankingProviderError],
) -> None:
    def _raise(_stream: object) -> None:
        raise native

    monkeypatch.setattr(OfxParser, "parse", staticmethod(_raise))
    with pytest.raises(expected) as exc_info:
        await OFXProvider().parse(_read("pel_2025_2026.ofx"))
    assert exc_info.value.__cause__ is native  # PII reste dans __cause__, jamais re-typée


async def test_encoding_error_propagates_not_swallowed_by_net() -> None:
    # EncodingDetectionError est levée AVANT le try → non avalée par `except Exception`.
    with pytest.raises(EncodingDetectionError):
        await OFXProvider().parse(b"\x81\x81\x81")


async def test_xxe_external_entity_not_resolved() -> None:
    # D13 : ofxparse parse via html.parser (pas lxml) → l'entité &xxe; n'est PAS résolue.
    parsed = await OFXProvider().parse(_read("xxe_attempt.ofx"))
    for t in parsed.transactions:
        assert "root:" not in t.payee
        assert "root:" not in t.description
        assert "/etc/passwd" not in t.description


# ---------------------------------------------------------------------------
# Bi-format mapping equivalence SGML 1.x ↔ XML 2.x (P12.2.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "external_ref", "debit"),
    [
        # XML 2.x — premier txn = débit Streaming.
        (
            "boursorama_export_2026.ofx",
            "BOURSO-0000-1111",
            SimpleNamespace(
                date=dt.date(2026, 1, 12),
                amount_cents=-2999,
                payee="Abonnement Streaming",
                description="Prelevement mensuel",
                fitid="BRS-2026-0001",
            ),
        ),
        # SGML 1.x — premier txn = débit Livret A.
        (
            "livret_a_2026_q1.ofx",
            "LIVRETA-2222-3333",
            SimpleNamespace(
                date=dt.date(2026, 1, 18),
                amount_cents=-7540,
                payee="Retrait Été",
                description="Virement vers compte courant",
                fitid="LIVA-2026-0001",
            ),
        ),
    ],
)
async def test_biformat_mapping(fixture: str, external_ref: str, debit: SimpleNamespace) -> None:
    parsed = await OFXProvider().parse(_read(fixture))
    assert parsed.accounts == (external_ref,)
    t = parsed.transactions[0]
    assert t.external_ref == external_ref
    assert t.date == debit.date
    assert t.amount_cents == debit.amount_cents
    assert t.amount_cents < 0  # symétrie de signe : un débit est négatif (bi-format)
    assert isinstance(t.amount_cents, int)
    assert t.currency == "EUR"
    assert t.payee == debit.payee
    assert t.description == debit.description
    assert t.fitid == debit.fitid  # présent (non None) sur les deux formats


# ---------------------------------------------------------------------------
# _map None-coalescing (couvre `or ""` / `.strip()`) — D7
# ---------------------------------------------------------------------------


def test_map_coalesces_none_payee_and_memo() -> None:
    t = SimpleNamespace(
        date=SimpleNamespace(date=lambda: dt.date(2026, 1, 1)),
        amount=__import__("decimal").Decimal("10.00"),
        payee=None,
        memo=None,
        id="FIT-X",
    )
    mapped = OFXProvider._map("ACC", "", t)
    assert mapped.payee == ""
    assert mapped.description == ""
    assert mapped.currency == "EUR"  # `"" or "EUR"` → EUR


# ---------------------------------------------------------------------------
# Garde-fou D1 — OFXProvider n'est PAS un BankingProvider (parser statique)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["list_accounts", "fetch_transactions", "consent_status"])
def test_ofx_provider_exposes_no_pull_methods(method: str) -> None:
    # Épingle « parser statique ≠ Protocol pull-only ». À renforcer en `not isinstance`
    # quand le Protocol BankingProvider existera (epic Enable Banking).
    assert not hasattr(OFXProvider(), method)
