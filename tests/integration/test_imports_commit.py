"""Integration tests for `POST /imports/ofx/commit` (S12.4, P12.4.3).

The commit is the only route that **creates `Transaction`s**, so every test that
creates or inspects rows runs under `committed_client` + `committed_sessionmaker`
(real commits, distinct session) — `async_client`'s savepoint mode hides commits
from sibling sessions and never fires `after_commit`, which would make the
atomicity proof a false positive (D14). `async_client` is reserved for the pure
401/404/422/413 mappings that short-circuit before any write.

Load-bearing invariants:
- one `draft` per non-duplicate line, single `funding` leg, `category_id` NULL —
  never `planned`/`confirmed`, never a "Sans catégorie" category (D6);
- idempotence via `UNIQUE(import_hash)`: a re-commit creates nothing (D9);
- atomicity: a mid-loop failure rolls back the WHOLE import (`get_db`, D10);
- the currency gate rejects a foreign-currency file globally (D6b);
- `user_overrides` is accepted but a no-op (D11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.banking.models import ImportedTransaction
from backend.modules.banking.service.external_refs import link
from backend.modules.budget.models import Category
from backend.modules.transactions.models import Split, Transaction
from backend.transports import imports_http

_settings = get_settings()
_OFX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ofx"
_BOURSO_REF = "BOURSO-0000-1111"  # boursorama_export_2026.ofx — 2 lines, EUR, high conf
_BOURSO_AMOUNTS = {-2999, 210000}

pytestmark = pytest.mark.usefixtures("_clean_committed_db")

SessionMaker = async_sessionmaker[AsyncSession]


@pytest.fixture(autouse=True)
def _reset_household_cache():  # pyright: ignore[reportUnusedFunction]
    # `get_household` caches the singleton process-locally; reset around every
    # test so the currency gate reads the freshly-seeded household, not a stale
    # cross-test cache.
    invalidate_household_cache()
    yield
    invalidate_household_cache()


# ---------------------------------------------------------------------------
# Synthetic OFX generator (foreign currency / multi-account / intra-file dup).
# Real fixtures cover the happy path; these edge files do not exist on disk.
# ---------------------------------------------------------------------------

_HEADER = (
    "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\nENCODING:USASCII\n"
    "CHARSET:1252\nCOMPRESSION:NONE\nOLDFILEUID:NONE\nNEWFILEUID:NONE\n"
)


def _stmt(acctid: str, currency: str, txns: list[tuple[str, str, str]], *, bankid: str) -> str:
    body = "".join(
        f"<STMTTRN>\n<TRNTYPE>DEBIT<DTPOSTED>{date}<TRNAMT>{amount}\n"
        f"<FITID>{fitid}<NAME>Op<MEMO>Op\n</STMTTRN>\n"
        for (date, amount, fitid) in txns
    )
    return (
        "<STMTTRNRS>\n<TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n<STMTRS>\n"
        f"<CURDEF>{currency}\n"
        f"<BANKACCTFROM><BANKID>{bankid}<ACCTID>{acctid}<ACCTTYPE>CHECKING</BANKACCTFROM>\n"
        "<BANKTRANLIST>\n<DTSTART>20260101<DTEND>20260331\n"
        f"{body}</BANKTRANLIST>\n"
        "<LEDGERBAL><BALAMT>0.00<DTASOF>20260331</LEDGERBAL>\n</STMTRS></STMTTRNRS>\n"
    )


def _ofx(stmts: list[str]) -> bytes:
    inner = "".join(stmts)
    return (
        _HEADER + "\n<OFX>\n<SIGNONMSGSRSV1><SONRS>\n<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        "<DTSERVER>20260401120000<LANGUAGE>FRA\n</SONRS></SIGNONMSGSRSV1>\n"
        f"<BANKMSGSRSV1>{inner}</BANKMSGSRSV1></OFX>\n"
    ).encode("cp1252")


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _real_files(name: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, (_OFX_DIR / name).read_bytes(), "application/octet-stream")}


def _bytes_files(payload: bytes) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("synthetic.ofx", payload, "application/octet-stream")}


async def _seed_linked(
    sm: SessionMaker, *, linked_refs: tuple[str, ...] = (_BOURSO_REF,)
) -> tuple[UUID, UUID]:
    """Seed household + owner + a personal account, link `linked_refs` to it, commit.

    Returns `(user_id, account_id)`. The account is owned by the user → accessible.
    """
    async with sm() as session:
        session.add(Household(name="H", base_currency="EUR", initialized_at=datetime.now(tz=UTC)))
        user = User(
            email=f"{uuid4().hex}@example.com",
            password_hash="x" * 60,
            display_name="importer",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        account = Account(
            name="Courant", type=AccountType.COURANT, currency="EUR", owner_id=user.id
        )
        session.add(account)
        await session.flush()
        for ref in linked_refs:
            await link(session, external_ref=ref, internal_account_id=account.id, provider="ofx")
        await session.commit()
        return user.id, account.id


async def _count(sm: SessionMaker, model: type, **filters: object) -> int:
    async with sm() as session:
        stmt = select(func.count()).select_from(model)
        for col, val in filters.items():
            stmt = stmt.where(getattr(model, col) == val)
        return (await session.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Happy path + idempotence
# ---------------------------------------------------------------------------


async def test_commit_creates_one_draft_per_line(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await _seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 2, "skipped_duplicates": 0}

    async with committed_sessionmaker() as session:
        txs = (
            (await session.execute(select(Transaction).where(Transaction.account_id == account_id)))
            .scalars()
            .all()
        )
        assert len(txs) == 2
        assert {t.state for t in txs} == {"draft"}

        splits = (await session.execute(select(Split))).scalars().all()
        assert len(splits) == 2
        assert all(s.category_id is None for s in splits)
        assert all(s.account_id == account_id for s in splits)
        assert all(s.currency == "EUR" for s in splits)
        assert {s.amount_cents for s in splits} == _BOURSO_AMOUNTS

    imported = await _count(committed_sessionmaker, ImportedTransaction, account_id=account_id)
    assert imported == 2
    assert await _count(committed_sessionmaker, ImportedTransaction, source="ofx") == 2


async def test_commit_never_planned_or_confirmed(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await _seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )
    assert resp.status_code == 200, resp.text

    async with committed_sessionmaker() as session:
        states = (await session.execute(select(Transaction.state))).scalars().all()
    assert states and set(states) == {"draft"}
    # No category was ever fabricated ("Sans catégorie" banned, D6).
    assert await _count(committed_sessionmaker, Category) == 0


async def test_recommit_is_idempotent(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await _seed_linked(committed_sessionmaker)
    body = {
        "data": {"internal_account_id": str(account_id)},
        "files": _real_files("boursorama_export_2026.ofx"),
        "headers": _bearer(user_id),
    }

    first = await committed_client.post("/imports/ofx/commit", **body)
    assert first.json() == {"created": 2, "skipped_duplicates": 0}

    second = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"created": 0, "skipped_duplicates": 2}

    # No new rows from the re-commit (distinct session).
    assert await _count(committed_sessionmaker, Transaction) == 2
    assert await _count(committed_sessionmaker, ImportedTransaction) == 2


async def test_commit_intra_file_duplicate_skipped(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Two lines with identical (date, amount, label) → identical import_hash. The
    # `seen` set skips the second WITHIN the same transaction (no IntegrityError).
    ref = "DUP-ACC-1"
    user_id, account_id = await _seed_linked(committed_sessionmaker, linked_refs=(ref,))
    payload = _ofx(
        [
            _stmt(
                ref,
                "EUR",
                [("20260118", "-10.00", "FIT-A"), ("20260118", "-10.00", "FIT-B")],
                bankid="30002",
            )
        ]
    )

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_bytes_files(payload),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 1, "skipped_duplicates": 1}
    assert await _count(committed_sessionmaker, Transaction) == 1
    assert await _count(committed_sessionmaker, ImportedTransaction) == 1


async def test_commit_atomic_rollback_on_midloop_failure(
    committed_client: AsyncClient,
    committed_sessionmaker: SessionMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fail `record_imported` on the 2nd call: line 1 fully flushed, line 2 half
    # written → the exception propagates and `get_db` rolls back the WHOLE import.
    user_id, account_id = await _seed_linked(committed_sessionmaker)
    real_record = imports_http.record_imported
    calls = {"n": 0}

    async def _flaky(session: AsyncSession, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated mid-loop failure")
        await real_record(session, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(imports_http, "record_imported", _flaky)

    with pytest.raises(RuntimeError):
        await committed_client.post(
            "/imports/ofx/commit",
            data={"internal_account_id": str(account_id)},
            files=_real_files("boursorama_export_2026.ofx"),
            headers=_bearer(user_id),
        )

    # Atomicity: nothing persisted at all (proves the `get_db` rollback, D10).
    assert await _count(committed_sessionmaker, Transaction) == 0
    assert await _count(committed_sessionmaker, Split) == 0
    assert await _count(committed_sessionmaker, ImportedTransaction) == 0


async def test_commit_then_preview_reports_duplicates(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Cross-layer lock (D5): the commit's journalled hashes are exactly what a
    # subsequent preview counts as duplicates.
    user_id, account_id = await _seed_linked(committed_sessionmaker)
    commit = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )
    assert commit.json()["created"] == 2

    preview = await committed_client.post(
        "/imports/ofx/preview",
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["duplicate_count"] == 2
    assert body["criteria"]["no_duplicates"] is False


# ---------------------------------------------------------------------------
# Gates (new edge cases)
# ---------------------------------------------------------------------------


async def test_commit_foreign_currency_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    ref = "USD-ACC-1"
    user_id, account_id = await _seed_linked(committed_sessionmaker, linked_refs=(ref,))
    payload = _ofx([_stmt(ref, "USD", [("20260118", "-75.40", "FIT-1")], bankid="30002")])

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_bytes_files(payload),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "currency_mismatch"
    assert await _count(committed_sessionmaker, Transaction) == 0


async def test_commit_multi_account_file_rejected_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # File carries two refs; only ACC-A is linked to the target account → the
    # unlinked ACC-B trips the per-ref gate (D8b). Nothing created.
    user_id, account_id = await _seed_linked(committed_sessionmaker, linked_refs=("ACC-A",))
    payload = _ofx(
        [
            _stmt("ACC-A", "EUR", [("20260118", "-10.00", "A1")], bankid="111"),
            _stmt("ACC-B", "EUR", [("20260119", "-20.00", "B1")], bankid="222"),
        ]
    )

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_bytes_files(payload),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "account_not_linked"
    assert await _count(committed_sessionmaker, Transaction) == 0


async def test_commit_user_overrides_is_noop(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await _seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id), "user_overrides": "category=Courses"},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    # Identical to a commit without overrides; no category fabricated (D11).
    assert resp.json() == {"created": 2, "skipped_duplicates": 0}
    assert await _count(committed_sessionmaker, Category) == 0


async def test_commit_inaccessible_account_404(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Target account owned by another user → 404 (non-disclosure, D8a). The file's
    # ref is linked to that foreign account, but the caller can't reach it.
    _other_id, other_account = await _seed_linked(committed_sessionmaker)
    async with committed_sessionmaker() as session:
        caller = User(
            email=f"{uuid4().hex}@example.com",
            password_hash="x" * 60,
            display_name="caller",
            role=UserRole.MEMBER,
        )
        session.add(caller)
        await session.commit()
        caller_id = caller.id

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(other_account)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(caller_id),
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"
    assert await _count(committed_sessionmaker, Transaction) == 0


async def test_commit_unlinked_ref_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Account accessible but the file's ref was never linked to it → 422 (D8b).
    user_id, account_id = await _seed_linked(committed_sessionmaker, linked_refs=())

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "account_not_linked"
    assert await _count(committed_sessionmaker, Transaction) == 0


async def test_commit_malformed_ofx_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await _seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_bytes_files(b"garbage"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == {
        "code": "unprocessable_ofx",
        "message": "Fichier OFX illisible ou incompatible.",
    }
    assert await _count(committed_sessionmaker, Transaction) == 0


async def test_commit_payload_too_large_413(
    committed_client: AsyncClient,
    committed_sessionmaker: SessionMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imports_http, "MAX_REQUEST_BYTES", 4)
    user_id, account_id = await _seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=_real_files("boursorama_export_2026.ofx"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 413, resp.text
    assert resp.json()["detail"]["code"] == "payload_too_large"


async def test_commit_anonymous_401(committed_client: AsyncClient) -> None:
    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(uuid4())},
        files=_bytes_files(b"x"),
    )
    assert resp.status_code == 401, resp.text
