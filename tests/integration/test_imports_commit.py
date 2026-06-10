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

Plumbing (`bearer`, real/synthetic OFX payloads) lives in `_imports_helpers`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User, UserRole
from backend.modules.banking.models import ImportedTransaction
from backend.modules.budget.models import Category
from backend.modules.transactions.models import Split, Transaction
from backend.transports import imports_http
from tests.integration._imports_helpers import (
    BOURSO_AMOUNTS,
    SessionMaker,
    bearer,
    bytes_files,
    count_rows,
    files,
    ofx,
    seed_linked,
    stmt,
)

pytestmark = pytest.mark.usefixtures("_clean_committed_db")


# The process-local `get_household` cache is reset around every integration test
# by the autouse `_reset_household_cache` fixture in `tests/integration/conftest.py`
# (hoisted there in S12.5 so the e2e tier's currency-gate path is protected too).


# ---------------------------------------------------------------------------
# Happy path + idempotence
# ---------------------------------------------------------------------------


async def test_commit_creates_one_draft_per_line(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
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
        assert {s.amount_cents for s in splits} == BOURSO_AMOUNTS

    imported = await count_rows(committed_sessionmaker, ImportedTransaction, account_id=account_id)
    assert imported == 2
    assert await count_rows(committed_sessionmaker, ImportedTransaction, source="ofx") == 2


async def test_commit_never_planned_or_confirmed(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )
    assert resp.status_code == 200, resp.text

    async with committed_sessionmaker() as session:
        states = (await session.execute(select(Transaction.state))).scalars().all()
    assert states and set(states) == {"draft"}
    # No category was ever fabricated ("Sans catégorie" banned, D6).
    assert await count_rows(committed_sessionmaker, Category) == 0


async def test_recommit_is_idempotent(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker)

    first = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )
    assert first.json() == {"created": 2, "skipped_duplicates": 0}

    second = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"created": 0, "skipped_duplicates": 2}

    # No new rows from the re-commit (distinct session).
    assert await count_rows(committed_sessionmaker, Transaction) == 2
    assert await count_rows(committed_sessionmaker, ImportedTransaction) == 2


async def test_commit_intra_file_duplicate_skipped(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Two lines with identical (date, amount, label) → identical import_hash. The
    # `seen` set skips the second WITHIN the same transaction (no IntegrityError).
    ref = "DUP-ACC-1"
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(ref,))
    payload = ofx(
        [
            stmt(
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
        files=bytes_files(payload),
        headers=bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 1, "skipped_duplicates": 1}
    assert await count_rows(committed_sessionmaker, Transaction) == 1
    assert await count_rows(committed_sessionmaker, ImportedTransaction) == 1


async def test_commit_atomic_rollback_on_midloop_failure(
    committed_client: AsyncClient,
    committed_sessionmaker: SessionMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fail `record_imported` on the 2nd call: line 1 fully flushed, line 2 half
    # written → the exception propagates and `get_db` rolls back the WHOLE import.
    user_id, account_id = await seed_linked(committed_sessionmaker)
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
            files=files("boursorama_export_2026.ofx"),
            headers=bearer(user_id),
        )

    # Atomicity: nothing persisted at all (proves the `get_db` rollback, D10).
    assert await count_rows(committed_sessionmaker, Transaction) == 0
    assert await count_rows(committed_sessionmaker, Split) == 0
    assert await count_rows(committed_sessionmaker, ImportedTransaction) == 0


async def test_commit_then_preview_reports_duplicates(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Cross-layer lock (D5): the commit's journalled hashes are exactly what a
    # subsequent preview counts as duplicates.
    user_id, account_id = await seed_linked(committed_sessionmaker)
    commit = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )
    assert commit.json()["created"] == 2

    preview = await committed_client.post(
        "/imports/ofx/preview",
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
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
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(ref,))
    payload = ofx([stmt(ref, "USD", [("20260118", "-75.40", "FIT-1")], bankid="30002")])

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=bytes_files(payload),
        headers=bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "currency_mismatch"
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_multi_account_file_rejected_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # File carries two refs; only ACC-A is linked to the target account → the
    # unlinked ACC-B trips the per-ref gate (D8b). Nothing created.
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=("ACC-A",))
    payload = ofx(
        [
            stmt("ACC-A", "EUR", [("20260118", "-10.00", "A1")], bankid="111"),
            stmt("ACC-B", "EUR", [("20260119", "-20.00", "B1")], bankid="222"),
        ]
    )

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=bytes_files(payload),
        headers=bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "account_not_linked"
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_user_overrides_is_noop(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id), "user_overrides": "category=Courses"},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    # Identical to a commit without overrides; no category fabricated (D11).
    assert resp.json() == {"created": 2, "skipped_duplicates": 0}
    assert await count_rows(committed_sessionmaker, Category) == 0


async def test_commit_inaccessible_account_404(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Target account owned by another user → 404 (non-disclosure, D8a). The file's
    # ref is linked to that foreign account, but the caller can't reach it.
    _other_id, other_account = await seed_linked(committed_sessionmaker)
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
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(caller_id),
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_unlinked_ref_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Account accessible but the file's ref was never linked to it → 422 (D8b).
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=())

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "account_not_linked"
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_malformed_ofx_422(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=bytes_files(b"garbage"),
        headers=bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == {
        "code": "unprocessable_ofx",
        "message": "Fichier OFX illisible ou incompatible.",
    }
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_payload_too_large_413(
    committed_client: AsyncClient,
    committed_sessionmaker: SessionMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cap tripped → 413 BEFORE the body is read/parsed (D13). Stub `parse_ofx` to
    # prove the short-circuit on the WRITE route too (parity with `/preview`), and
    # assert nothing was written.
    monkeypatch.setattr(imports_http, "MAX_REQUEST_BYTES", 4)

    def _fail_parse(*_a: object, **_k: object) -> object:
        raise AssertionError("parse_ofx must not be reached when the size cap fires")

    monkeypatch.setattr(imports_http, "parse_ofx", _fail_parse)
    user_id, account_id = await seed_linked(committed_sessionmaker)

    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files("boursorama_export_2026.ofx"),
        headers=bearer(user_id),
    )

    assert resp.status_code == 413, resp.text
    assert resp.json()["detail"]["code"] == "payload_too_large"
    assert await count_rows(committed_sessionmaker, Transaction) == 0


async def test_commit_anonymous_401(committed_client: AsyncClient) -> None:
    resp = await committed_client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(uuid4())},
        files=bytes_files(b"x"),
    )
    assert resp.status_code == 401, resp.text
