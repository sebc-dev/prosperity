"""Integration tests for `banking.service.import_ofx.analyze_import` (S12.3, P12.3.3).

`analyze_import` reads the DB (`imported_transactions` lookup + `find_internal_account`
resolution) → integration tier (testcontainers Postgres). Exercises: clean import
→ `auto_validatable`, the 5 F04 criteria violated in isolation, duplicate counting,
account-not-linked detection, the label-fallback / empty-label hashing contract,
the empty-file vacuity, and the read-only contract (D10). `ParsedOFX` is built in
memory — no file parsing here (that is S12.5). Gabarit `test_banking_external_refs`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.banking.domain import BankTransaction, ParsedOFX
from backend.modules.banking.models import ImportedTransaction
from backend.modules.banking.service.external_refs import link
from backend.modules.banking.service.import_ofx import analyze_import, compute_import_hash

# Every test inserts an `Account`, whose `household_id` FK requires the singleton
# `household` row (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")

_REF = "XXXX1"
_REF_DATE = dt.date(2026, 6, 9)


async def _make_account(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID:
    account = Account(
        name="Compte courant",
        type=AccountType.COURANT,
        currency="EUR",
        owner_id=owner_id,
    )
    session.add(account)
    await session.flush()
    return account.id


def _txn(
    *,
    external_ref: str = _REF,
    date: dt.date | None = None,
    amount_cents: int = -4250,
    payee: str = "Carrefour",
    description: str = "Courses",
) -> BankTransaction:
    return BankTransaction(
        external_ref=external_ref,
        date=date or _REF_DATE,
        amount_cents=amount_cents,
        currency="EUR",
        payee=payee,
        description=description,
    )


def _parsed(
    txns: tuple[BankTransaction, ...],
    *,
    encoding: str = "high",
    accounts: tuple[str, ...] = (_REF,),
) -> ParsedOFX:
    return ParsedOFX(accounts=accounts, transactions=txns, encoding_confidence=encoding)  # type: ignore[arg-type]


async def _linked_account(
    session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    *,
    ref: str = _REF,
) -> uuid.UUID:
    user = await user_factory()
    account_id = await _make_account(session, user.id)
    await link(session, external_ref=ref, internal_account_id=account_id, provider="ofx")
    return account_id


# ---------------------------------------------------------------------------
# Clean import + 5 criteria isolated
# ---------------------------------------------------------------------------


async def test_clean_import_auto_validatable(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    txns = (
        _txn(date=_REF_DATE, amount_cents=-4250, description="Courses"),
        _txn(date=_REF_DATE - dt.timedelta(days=1), amount_cents=1200, description="Remboursement"),
        _txn(date=_REF_DATE - dt.timedelta(days=2), amount_cents=-999, description="Café"),
    )
    preview = await analyze_import(auth_schema, _parsed(txns), reference_date=_REF_DATE)

    assert preview.auto_validatable is True
    assert preview.account_not_linked is False
    assert preview.duplicate_count == 0
    assert preview.tx_count == 3
    assert preview.date_min == _REF_DATE - dt.timedelta(days=2)
    assert preview.date_max == _REF_DATE
    c = preview.criteria
    assert (
        c.no_duplicates
        and c.encoding_high_confidence
        and c.within_date_window
        and c.amounts_within_cap
        and c.volume_under_limit
    )


async def test_low_encoding_blocks(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    preview = await analyze_import(
        auth_schema, _parsed((_txn(),), encoding="low"), reference_date=_REF_DATE
    )
    assert preview.criteria.encoding_high_confidence is False
    assert preview.auto_validatable is False
    # Other criteria remain True.
    assert preview.criteria.no_duplicates
    assert preview.criteria.within_date_window
    assert preview.criteria.amounts_within_cap
    assert preview.criteria.volume_under_limit


async def test_date_outside_window_blocks(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    old = _txn(date=dt.date(2022, 6, 9))  # ref - 4 years
    preview = await analyze_import(auth_schema, _parsed((old,)), reference_date=_REF_DATE)
    assert preview.criteria.within_date_window is False
    assert preview.auto_validatable is False


async def test_date_window_bounds_inclusive(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    lower = dt.date(2023, 6, 9)  # ref - 3 years
    upper = dt.date(2029, 6, 9)  # ref + 3 years
    on_bounds = (_txn(date=lower), _txn(date=upper))
    preview = await analyze_import(auth_schema, _parsed(on_bounds), reference_date=_REF_DATE)
    assert preview.criteria.within_date_window is True  # inclusive (D6)

    just_before = (_txn(date=lower - dt.timedelta(days=1)),)
    preview2 = await analyze_import(auth_schema, _parsed(just_before), reference_date=_REF_DATE)
    assert preview2.criteria.within_date_window is False


async def test_amount_cap_boundary(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    # Exactly 10 000 € as a debit (negative) → within cap (abs used).
    at_cap = await analyze_import(
        auth_schema, _parsed((_txn(amount_cents=-1_000_000),)), reference_date=_REF_DATE
    )
    assert at_cap.criteria.amounts_within_cap is True
    assert at_cap.amount_max_cents == 1_000_000

    over = await analyze_import(
        auth_schema, _parsed((_txn(amount_cents=-1_000_001),)), reference_date=_REF_DATE
    )
    assert over.criteria.amounts_within_cap is False


async def test_volume_limit_boundary(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)

    # 49 distinct tx (vary the day so hashes differ) → under limit; 50 → at limit.
    def _many(n: int) -> tuple[BankTransaction, ...]:
        return tuple(
            _txn(date=_REF_DATE - dt.timedelta(days=i), description=f"tx{i}") for i in range(n)
        )

    under = await analyze_import(auth_schema, _parsed(_many(49)), reference_date=_REF_DATE)
    assert under.tx_count == 49
    assert under.criteria.volume_under_limit is True

    at_limit = await analyze_import(auth_schema, _parsed(_many(50)), reference_date=_REF_DATE)
    assert at_limit.tx_count == 50
    assert at_limit.criteria.volume_under_limit is False


# ---------------------------------------------------------------------------
# Dedup counting (lookup against imported_transactions)
# ---------------------------------------------------------------------------


async def test_duplicate_detected(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    account_id = await _linked_account(auth_schema, bound_user_factory)
    tx = _txn(description="Courses")
    # Pre-insert the dedup-journal row for this exact tx (same hash source).
    auth_schema.add(
        ImportedTransaction(
            account_id=account_id,
            import_hash=compute_import_hash(account_id, tx),
            source="ofx",
        )
    )
    await auth_schema.flush()

    preview = await analyze_import(auth_schema, _parsed((tx,)), reference_date=_REF_DATE)
    assert preview.duplicate_count == 1
    assert preview.criteria.no_duplicates is False
    assert preview.auto_validatable is False


async def test_duplicate_count_multiple(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    account_id = await _linked_account(auth_schema, bound_user_factory)
    known = (_txn(description="A"), _txn(description="B"))
    fresh = _txn(description="C")
    for tx in known:
        auth_schema.add(
            ImportedTransaction(
                account_id=account_id,
                import_hash=compute_import_hash(account_id, tx),
                source="ofx",
            )
        )
    await auth_schema.flush()

    preview = await analyze_import(auth_schema, _parsed((*known, fresh)), reference_date=_REF_DATE)
    assert preview.duplicate_count == 2
    assert preview.tx_count == 3


# ---------------------------------------------------------------------------
# Account-not-linked detection
# ---------------------------------------------------------------------------


async def test_account_not_linked(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Ref never linked → account_not_linked; tx not hashed → duplicate_count=0,
    # but tx_count/aggregates STILL computed over all tx (review Tests n1).
    txns = (_txn(amount_cents=-5000), _txn(amount_cents=2000))
    preview = await analyze_import(auth_schema, _parsed(txns), reference_date=_REF_DATE)
    assert preview.account_not_linked is True
    assert preview.duplicate_count == 0
    assert preview.tx_count == 2
    assert preview.amount_max_cents == 5000
    assert preview.date_min == _REF_DATE
    assert preview.date_max == _REF_DATE


async def test_partial_link_multi_account(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Two distinct refs, one linked one not → account_not_linked (at least one
    # None, D5).
    await _linked_account(auth_schema, bound_user_factory, ref="LINKED")
    txns = (
        _txn(external_ref="LINKED"),
        _txn(external_ref="MISSING"),
    )
    preview = await analyze_import(
        auth_schema,
        _parsed(txns, accounts=("LINKED", "MISSING")),
        reference_date=_REF_DATE,
    )
    assert preview.account_not_linked is True
    assert preview.tx_count == 2


# ---------------------------------------------------------------------------
# Label fallback / empty label (review Tests Majeur M2)
# ---------------------------------------------------------------------------


async def test_label_fallback_description_empty(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    account_id = await _linked_account(auth_schema, bound_user_factory)
    tx = _txn(description="", payee="Boulangerie")
    # Hash falls back to payee (D8): equal to a hash computed from payee.
    expected = compute_import_hash(account_id, tx)
    auth_schema.add(ImportedTransaction(account_id=account_id, import_hash=expected, source="ofx"))
    await auth_schema.flush()

    preview = await analyze_import(auth_schema, _parsed((tx,)), reference_date=_REF_DATE)
    assert preview.duplicate_count == 1


async def test_empty_label_hashes(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    account_id = await _linked_account(auth_schema, bound_user_factory)
    # Both description and payee empty → hash over empty label; two such tx
    # (same account/date/amount) collide (assumed behaviour, D8).
    t1 = _txn(description="", payee="")
    t2 = _txn(description="", payee="")
    assert compute_import_hash(account_id, t1) == compute_import_hash(account_id, t2)
    preview = await analyze_import(auth_schema, _parsed((t1,)), reference_date=_REF_DATE)
    assert preview.tx_count == 1
    assert preview.duplicate_count == 0  # nothing pre-inserted


# ---------------------------------------------------------------------------
# Empty file + aggregates + read-only contract
# ---------------------------------------------------------------------------


async def test_empty_file(auth_schema: AsyncSession) -> None:
    preview = await analyze_import(auth_schema, _parsed((), accounts=()), reference_date=_REF_DATE)
    assert preview.tx_count == 0
    assert preview.date_min is None
    assert preview.date_max is None
    assert preview.amount_max_cents == 0
    assert preview.account_not_linked is False  # nothing to link
    assert preview.auto_validatable is True  # vacuity (documented)


async def test_aggregates(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    await _linked_account(auth_schema, bound_user_factory)
    # Dominant amount comes from a DEBIT → locks the abs() (review Tests n2).
    txns = (
        _txn(date=dt.date(2026, 1, 10), amount_cents=-9_999_99, description="gros débit"),
        _txn(date=dt.date(2026, 3, 5), amount_cents=500_00, description="crédit"),
    )
    preview = await analyze_import(auth_schema, _parsed(txns), reference_date=_REF_DATE)
    assert preview.amount_max_cents == 999_999
    assert preview.date_min == dt.date(2026, 1, 10)
    assert preview.date_max == dt.date(2026, 3, 5)


async def test_no_db_write(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Read-only contract (D10): the dedup-journal count is unchanged AND the
    # session holds no pending writes a `get_db` commit could flush. The
    # `transactions`-count assertion is deliberately NOT made: `analyze_import`
    # cannot import `transactions` (contract `banking ⊥ transactions`), so it
    # would be an always-green assertion (anti-pattern).
    account_id = await _linked_account(auth_schema, bound_user_factory)
    # Seed one dedup row so the lookup path is exercised, then flush it cleanly.
    auth_schema.add(ImportedTransaction(account_id=account_id, import_hash="f" * 64, source="ofx"))
    await auth_schema.flush()

    before = (
        await auth_schema.execute(select(func.count()).select_from(ImportedTransaction))
    ).scalar_one()

    await analyze_import(auth_schema, _parsed((_txn(),)), reference_date=_REF_DATE)

    assert not auth_schema.new
    assert not auth_schema.dirty
    assert not auth_schema.deleted
    after = (
        await auth_schema.execute(select(func.count()).select_from(ImportedTransaction))
    ).scalar_one()
    assert after == before
