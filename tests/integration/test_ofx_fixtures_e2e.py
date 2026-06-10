"""End-to-end OFX import tests over the 6 canonical bank fixtures (S12.5, P12.5.2).

The black-box tier: drive the real HTTP routes (`/imports/ofx/{preview,link-account,
commit}`) over the **real anonymised exports** in `tests/fixtures/ofx/` and assert
concrete business values — exact cent-amounts per OFX flavour, accented labels
decoded down to the persisted artefact, FITID-agnostic dedup, the full
upload→preview→link→commit journey. This is the safety net that turns "works on my
file" into "works on the targeted FR banks' real exports".

Complementary to — never a re-run of — the S12.4 plumbing tests
(`test_imports_commit.py`/`_routes_preview.py`: access gate, parse-error, size cap,
401/404/413, atomic rollback, currency mismatch) and the S12.3 service matrix
(`test_analyze_import.py`: the 5 criteria boundary-by-boundary). Here we only assert
what the *assembly* over a real file proves.

Harness split (D7): writes (commit, journey, FITID) go through `committed_client` +
`committed_sessionmaker` (real commits, cross-session read-back); pure reads
(preview criteria) go through `async_client` (savepoint). The process-local
`get_household` cache is reset per test by the autouse `_reset_household_cache`
fixture in `conftest.py`.

Note on the date window: `within_date_window` depends on `date.today()` — not
injectable *via the HTTP boundary* (the route calls `analyze_import` without a
`reference_date`, so it falls back to today). Fixtures are dated 2026 Q1, inside the
±3-year window until ~2029; the auto-validatable assertion pins the four
clock-independent criteria explicitly and treats `within_date_window` as a
documented, time-bound expectation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.banking.models import ImportedTransaction
from backend.modules.banking.public import compute_import_hash, link, parse_ofx
from backend.modules.transactions.models import Split, Transaction
from tests.integration._imports_helpers import (
    BOURSO_AMOUNTS,
    BOURSO_REF,
    CP1252_REF,
    LIVRET_A_AMOUNTS,
    LIVRET_A_REF,
    NOT_LINKED_REF,
    PEL_AMOUNTS,
    PEL_REF,
    SG_FITID_REF,
    SessionMaker,
    bearer,
    bytes_files,
    commit_fixture,
    count_rows,
    files,
    ofx,
    read_ofx,
    seed_linked,
    stmt,
)

SeedAccount = Callable[..., Awaitable[tuple[UUID, UUID]]]

_CANONICAL_FIXTURES = (
    "livret_a_2026_q1.ofx",
    "pel_2025_2026.ofx",
    "boursorama_export_2026.ofx",
    "libelles_accentues_windows_1252.ofx",
    "fitid_unstable_societe_generale.ofx",
    "account_not_yet_linked.ofx",
)


# ---------------------------------------------------------------------------
# Fast parse lock — no DB, runs even without Docker.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _CANONICAL_FIXTURES)
async def test_all_canonical_fixtures_parse(name: str) -> None:
    """Each canonical fixture decodes and parses without raising — at least one
    account and one transaction surfaced. Guards against a malformed/empty fixture
    silently disabling a downstream assertion."""
    parsed = await parse_ofx(read_ofx(name))
    assert parsed.transactions
    assert parsed.accounts


# ---------------------------------------------------------------------------
# (a) Formats committed without loss — exact amounts per OFX flavour.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "ref", "amounts"),
    [
        ("livret_a_2026_q1.ofx", LIVRET_A_REF, LIVRET_A_AMOUNTS),  # 1.x SGML cp1252
        ("pel_2025_2026.ofx", PEL_REF, PEL_AMOUNTS),  # 1.x SGML UTF-8 BOM
        ("boursorama_export_2026.ofx", BOURSO_REF, BOURSO_AMOUNTS),  # 2.x XML
    ],
)
@pytest.mark.usefixtures("_clean_committed_db")
async def test_commit_format_amounts_exact(
    committed_client: AsyncClient,
    committed_sessionmaker: SessionMaker,
    name: str,
    ref: str,
    amounts: set[int],
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(ref,))

    result = await commit_fixture(
        committed_client, account_id=account_id, user_id=user_id, name=name
    )
    assert result == {"created": 2, "skipped_duplicates": 0}

    async with committed_sessionmaker() as session:
        splits = (await session.execute(select(Split))).scalars().all()
        states = (await session.execute(select(Transaction.state))).scalars().all()
    # Exact cent-amounts survive both the 1.x SGML and 2.x XML parse paths.
    assert {s.amount_cents for s in splits} == amounts
    # Single funding leg per line, never categorised → never planned/confirmed.
    assert all(s.category_id is None for s in splits)
    assert set(states) == {"draft"}


# ---------------------------------------------------------------------------
# (b) windows-1252 accented labels decoded end-to-end → persisted import_hash.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_committed_db")
async def test_accented_labels_decoded_to_import_hash(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(CP1252_REF,))
    parsed = await parse_ofx(read_ofx("libelles_accentues_windows_1252.ofx"))

    # 1) Decoded without mojibake at the parse tier (the hash's label is the MEMO).
    assert {tx.description for tx in parsed.transactions} == {
        "Déjeuner çà et là",
        "Règlement à la française",
    }

    # 2) Commit: the only DB artefact carrying the label is `import_hash` (the
    # commit persists no description). A mojibake decode would change `expected`
    # AND fail step 1 — so hash equality proves the byte→Unicode chain end-to-end.
    result = await commit_fixture(
        committed_client,
        account_id=account_id,
        user_id=user_id,
        name="libelles_accentues_windows_1252.ofx",
    )
    assert result["created"] == 2

    expected = {compute_import_hash(account_id, tx) for tx in parsed.transactions}
    async with committed_sessionmaker() as session:
        stored = set(
            (await session.execute(select(ImportedTransaction.import_hash))).scalars().all()
        )
    assert stored == expected


# ---------------------------------------------------------------------------
# (c) Unstable FITID → a single draft (dedup ignores FITID).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_committed_db")
async def test_fitid_instability_collapses_to_one_draft(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(SG_FITID_REF,))
    parsed = await parse_ofx(read_ofx("fitid_unstable_societe_generale.ofx"))

    # The load-bearing precondition: two business-identical movements that differ
    # ONLY by FITID. Without this, the test would not prove FITID-agnosticity.
    assert len({tx.fitid for tx in parsed.transactions}) == 2
    assert len({(tx.date, tx.amount_cents, tx.description) for tx in parsed.transactions}) == 1

    result = await commit_fixture(
        committed_client,
        account_id=account_id,
        user_id=user_id,
        name="fitid_unstable_societe_generale.ofx",
    )

    # Composite hash (account, date, amount, normalised label) collapses the two →
    # FITID is never part of the key.
    assert result == {"created": 1, "skipped_duplicates": 1}
    assert await count_rows(committed_sessionmaker, Transaction) == 1
    assert await count_rows(committed_sessionmaker, ImportedTransaction) == 1


@pytest.mark.usefixtures("_clean_committed_db")
async def test_fitid_unstable_recommit_idempotent(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(SG_FITID_REF,))
    commit = partial(
        commit_fixture,
        committed_client,
        account_id=account_id,
        user_id=user_id,
        name="fitid_unstable_societe_generale.ofx",
    )

    first = await commit()
    second = await commit()

    assert first == {"created": 1, "skipped_duplicates": 1}
    assert second == {"created": 0, "skipped_duplicates": 2}
    assert await count_rows(committed_sessionmaker, Transaction) == 1


# ---------------------------------------------------------------------------
# (d) Not-yet-linked account → 422, then the full upload→preview→link→commit journey.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_committed_db")
async def test_account_not_yet_linked_full_journey(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Account exists and is accessible, but the file's ref is linked to nothing.
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=())

    # 1) Preview rejects with the typed error demanding a mapping.
    preview = await committed_client.post(
        "/imports/ofx/preview",
        files=files("account_not_yet_linked.ofx"),
        headers=bearer(user_id),
    )
    assert preview.status_code == 422, preview.text
    assert preview.json()["detail"]["code"] == "account_not_linked"

    # 2) Establish the mapping (explicit user act — never auto-created).
    linked = await committed_client.post(
        "/imports/ofx/link-account",
        json={
            "external_ref": NOT_LINKED_REF,
            "internal_account_id": str(account_id),
            "provider": "ofx",
        },
        headers=bearer(user_id),
    )
    assert linked.status_code == 201, linked.text

    # 3) Preview now passes.
    preview2 = await committed_client.post(
        "/imports/ofx/preview",
        files=files("account_not_yet_linked.ofx"),
        headers=bearer(user_id),
    )
    assert preview2.status_code == 200, preview2.text

    # 4) Commit goes through — the import passes after linking.
    result = await commit_fixture(
        committed_client, account_id=account_id, user_id=user_id, name="account_not_yet_linked.ofx"
    )
    assert result == {"created": 1, "skipped_duplicates": 0}
    # The adversarial "ref of another member's account" branch of the gate is
    # covered byte-identically by `test_preview_linked_but_inaccessible_*` (S12.4).


# ---------------------------------------------------------------------------
# (e) Dedup at commit on a real fixture — re-commit creates nothing.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_committed_db")
async def test_recommit_real_fixture_zero_creation(
    committed_client: AsyncClient, committed_sessionmaker: SessionMaker
) -> None:
    # Locks the dedup on a cp1252 1.x SGML export (the S12.4 idempotence test uses
    # the 2.x XML boursorama file only).
    user_id, account_id = await seed_linked(committed_sessionmaker, linked_refs=(LIVRET_A_REF,))
    commit = partial(
        commit_fixture,
        committed_client,
        account_id=account_id,
        user_id=user_id,
        name="livret_a_2026_q1.ofx",
    )

    first = await commit()
    second = await commit()

    assert first == {"created": 2, "skipped_duplicates": 0}
    assert second == {"created": 0, "skipped_duplicates": 2}
    assert await count_rows(committed_sessionmaker, Transaction) == 2


# ---------------------------------------------------------------------------
# (f) Preview criteria validated on real / realistic exports.
# ---------------------------------------------------------------------------


async def test_preview_clean_export_auto_validatable(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    seed_personal_account: SeedAccount,
) -> None:
    user_id, account_id = await seed_personal_account()
    await link(
        household_singleton, external_ref=BOURSO_REF, internal_account_id=account_id, provider="ofx"
    )

    body = (
        await async_client.post(
            "/imports/ofx/preview",
            files=files("boursorama_export_2026.ofx"),
            headers=bearer(user_id),
        )
    ).json()

    c = body["criteria"]
    # Four clock-independent criteria pinned explicitly.
    assert c["no_duplicates"] is True
    assert c["encoding_high_confidence"] is True
    assert c["amounts_within_cap"] is True
    assert c["volume_under_limit"] is True
    # Time-bound: fixtures dated 2026 Q1 ⊂ ±3 years (holds until ~2029).
    assert c["within_date_window"] is True
    assert body["auto_validatable"] is True


async def test_preview_over_volume_requires_review(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    seed_personal_account: SeedAccount,
) -> None:
    user_id, account_id = await seed_personal_account()
    await link(
        household_singleton, external_ref="VOL-9999", internal_account_id=account_id, provider="ofx"
    )
    # 55 lines (> 50) — realistic large export, ASCII so encoding stays high.
    payload = ofx(
        [
            stmt(
                "VOL-9999",
                "EUR",
                [(f"202602{(i % 28) + 1:02d}", "-1.00", f"V{i}") for i in range(55)],
                bankid="30004",
            )
        ]
    )

    body = (
        await async_client.post(
            "/imports/ofx/preview", files=bytes_files(payload), headers=bearer(user_id)
        )
    ).json()

    assert body["criteria"]["volume_under_limit"] is False
    assert body["auto_validatable"] is False


async def test_preview_over_amount_requires_review(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    seed_personal_account: SeedAccount,
) -> None:
    user_id, account_id = await seed_personal_account()
    await link(
        household_singleton, external_ref="AMT-9999", internal_account_id=account_id, provider="ofx"
    )
    # One line at 15 000 € (> 10 000 € cap).
    payload = ofx([stmt("AMT-9999", "EUR", [("20260210", "-15000.00", "BIG")], bankid="30005")])

    body = (
        await async_client.post(
            "/imports/ofx/preview", files=bytes_files(payload), headers=bearer(user_id)
        )
    ).json()

    assert body["criteria"]["amounts_within_cap"] is False
    assert body["auto_validatable"] is False
