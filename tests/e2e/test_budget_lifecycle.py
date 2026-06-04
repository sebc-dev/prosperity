"""E2E Parcours 4 — Budget lifecycle, covers E06+E07+E08 (réconciliation ADR 0017).

Black-box HTTP chain of the budget value, possible only since E08.5 (a confirmable
expense consumes a budget): a member creates an account → enters an expense in
canonical form B (funding account leg + classification categorised leg) → confirms
it through the real flow (draft→planned→confirmed) → the PARENT budget's
consumption rises (hierarchical resolution) → the 80 % threshold is crossed (HTTP
consumption + side-channel alert) → the drill-down lists the contributing leg → and
a SHARED budget does not leak to a non-contributor (404).

Per §6.2 (Stratégie de tests): interim anticipation of the Playwright E15 journey
(like Onboarding/Invitation/Category). Per-endpoint contracts (401-anonymous,
pagination, schemas) stay delegated to integration; here we assert the state
TRANSITIONS and the PROPAGATION (REST → service → consumption).

Wiring (S08.5.3 §B). The threshold detector subscribes in `main.py`'s `lifespan`,
which httpx's `ASGITransport` does NOT run under `committed_client`. So the autouse
fixture below re-subscribes the real detector on the async channel (gabarit the
integration `_wire_threshold_detector`) — without it `TransactionConfirmedEvent`
has no subscriber and no alert is ever written. `test_detector_wiring_is_load_bearing`
pins that this wiring is load-bearing.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.modules.budget.public import on_transaction_confirmed
from backend.modules.transactions.events import TransactionConfirmedEvent
from backend.shared.events import clear_subscribers, subscribe_async
from tests.e2e._helpers import (
    auth_headers,
    bootstrap_admin,
    confirm_transaction,
    create_budget,
    create_category,
    create_personal_account,
    create_shared_account,
    create_transaction,
    fetch_threshold_alerts,
    onboard_member,
    user_id_by_email,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

MEMBER_EMAIL = "budget-member@example.com"
MEMBER_PASSWORD = "member-password-123"
THIRD_EMAIL = "budget-third@example.com"
THIRD_PASSWORD = "third-password-123"


@pytest.fixture(autouse=True)
def _wire_threshold_detector_e2e() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-subscribe the detector on the bus (S08.5.3 §B).

    The `lifespan` does not run under `ASGITransport` (committed_client), so
    `TransactionConfirmedEvent` would have no subscriber and no alert would be
    written. Mirrors the integration tier's `_wire_threshold_detector`;
    `subscribe_async` is idempotent. Cleared before AND after (process-global bus).
    """
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, on_transaction_confirmed)
    yield
    clear_subscribers()


def _today() -> date:
    # Anchor on the server's UTC clock (S08.5.3 review — determinism). The tx date
    # defaults to `datetime.now(UTC).date()` and the threshold detector resolves
    # its window with the same UTC clock, while the consumption endpoint defaults
    # to the *local* `date.today()`. Computing the budget window AND the read
    # `as_of` here in UTC (and passing `as_of` explicitly to the value reads) keeps
    # all three clocks aligned, so the window can't straddle the UTC midnight
    # boundary on a CI runner in a negative timezone (→ tx out of window → flake).
    return datetime.now(UTC).date()


def _first_of_current_month() -> str:
    return _today().replace(day=1).isoformat()


async def test_budget_lifecycle(  # noqa: PLR0915 — E2E journey is deliberately long
    committed_client, committed_sessionmaker
) -> None:
    client = committed_client
    admin_access, _refresh, admin_email = await bootstrap_admin(client)
    member_access = await onboard_member(client, admin_access, MEMBER_EMAIL, MEMBER_PASSWORD)
    third_access = await onboard_member(client, admin_access, THIRD_EMAIL, THIRD_PASSWORD)
    admin_id = str(await user_id_by_email(committed_sessionmaker, admin_email))
    member_id = str(await user_id_by_email(committed_sessionmaker, MEMBER_EMAIL))
    third_id = str(await user_id_by_email(committed_sessionmaker, THIRD_EMAIL))

    # 1. Category tree (E06, D9): budget on the parent, expense on the child.
    parent = await create_category(client, admin_access, name="Maison")
    child = await create_category(client, admin_access, name="Énergie", parent_id=parent["id"])

    # 2. Personal account (E05).
    acc = await create_personal_account(client, admin_access, name="Perso")

    # 3. Budget on the PARENT (E08): 100 € over the current month.
    period_start = _first_of_current_month()
    as_of = _today().isoformat()  # UTC, shared by the tx date and the value reads
    budget = await create_budget(
        client,
        admin_access,
        category_id=parent["id"],
        period_start=period_start,
        amount_cents=10000,
        contributor_ids=[admin_id],
        scope="personal",
    )

    # 4. Expense in form B on the CHILD category (E07, D12): both legs on the SAME
    #    account → is_transfer False → the classification leg must be categorised.
    #    The date is pinned to `as_of` (UTC) so the expense always lands inside the
    #    budget window the detector and the reads observe.
    tx = await create_transaction(
        client,
        admin_access,
        acc["id"],
        date=as_of,
        splits=[
            {"account_id": acc["id"], "amount_cents": -8100, "currency": "EUR"},
            {
                "account_id": acc["id"],
                "amount_cents": 8100,
                "currency": "EUR",
                "category_id": child["id"],
            },
        ],
    )
    assert tx["state"] == "draft"

    # 5. Confirm through the real flow (draft → planned → confirmed).
    confirmed = await confirm_transaction(client, admin_access, tx["id"])
    assert confirmed["state"] == "confirmed"

    # 6. Hierarchical consumption over HTTP: the child leg resolves UP to the
    #    parent budget; the funding NULL leg is excluded. 8100 / 10000 = 0.81 (raw
    #    ratio, non arrondi) → pin the exact value, not just the ≥ 0.80 band.
    cons = (
        await client.get(
            f"/budgets/{budget['id']}/consumption",
            params={"as_of": as_of},
            headers=auth_headers(admin_access),
        )
    ).json()
    assert cons["consumed_cents"] == 8100
    assert cons["splits_count"] == 1
    assert Decimal(str(cons["percent"])) == Decimal("0.81")

    # 7. Threshold crossed (side-channel, D8): the §B autouse-wired detector wrote
    #    the durable alert row for the 80 % crossing (the lifespan does NOT run
    #    under ASGITransport — see the module docstring).
    assert await fetch_threshold_alerts(committed_sessionmaker, budget_id=budget["id"]) == [80]

    # 8. Drill-down over HTTP: exactly the classification leg (the funding NULL leg
    #    is out of the subtree, so it never appears).
    drill = (
        await client.get(
            f"/budgets/{budget['id']}/contributing-splits",
            params={"as_of": as_of},
            headers=auth_headers(admin_access),
        )
    ).json()
    assert len(drill["items"]) == 1
    assert drill["items"][0]["category_id"] == child["id"]
    assert drill["items"][0]["amount_cents"] == 8100

    # 9. RBAC shared non-leak (D10). A `shared` budget needs ≥ 2 contributors, each
    #    a member of a common account → a THIRD user C makes B a member of the
    #    common account but NOT a contributor of the budget.
    shared = await create_shared_account(
        client,
        admin_access,
        name="Commun",
        members=[
            {"user_id": admin_id, "default_share_ratio": "0.34"},
            {"user_id": member_id, "default_share_ratio": "0.33"},
            {"user_id": third_id, "default_share_ratio": "0.33"},
        ],
    )
    assert shared["id"]  # the common account stood up (precondition for the budget)
    shared_budget = await create_budget(
        client,
        admin_access,
        category_id=parent["id"],
        period_start=period_start,
        amount_cents=20000,
        contributor_ids=[admin_id, third_id],  # B is a member of the account, NOT a contributor
        scope="shared",
    )

    member_headers = auth_headers(member_access)
    # B (non-contributor) gets a uniform 404 on consumption AND drill-down…
    assert (
        await client.get(f"/budgets/{shared_budget['id']}/consumption", headers=member_headers)
    ).status_code == 404
    assert (
        await client.get(
            f"/budgets/{shared_budget['id']}/contributing-splits", headers=member_headers
        )
    ).status_code == 404
    # …including with a structurally-valid cursor AND a malformed one: the 404
    # precedes the cursor decode, so neither leaks a page nor differentiates a 422.
    valid_cursor = base64.urlsafe_b64encode(f"{period_start}|{uuid4()}".encode()).decode()
    assert (
        await client.get(
            f"/budgets/{shared_budget['id']}/contributing-splits",
            params={"cursor": valid_cursor},
            headers=member_headers,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/budgets/{shared_budget['id']}/contributing-splits",
            params={"cursor": "not-a-valid-cursor!!"},
            headers=member_headers,
        )
    ).status_code == 404
    # Positive controls: A (creator/contributor) and C (contributor) both see it.
    assert (
        await client.get(f"/budgets/{shared_budget['id']}", headers=auth_headers(admin_access))
    ).status_code == 200
    assert (
        await client.get(
            f"/budgets/{shared_budget['id']}/consumption", headers=auth_headers(third_access)
        )
    ).status_code == 200

    # 10. Personal cross-user non-leak (§G): A's PERSONAL budget is invisible to B
    #     on every read route (get_visible_budget is the only guard for both scopes).
    for suffix in ("", "/consumption", "/contributing-splits"):
        assert (
            await client.get(f"/budgets/{budget['id']}{suffix}", headers=member_headers)
        ).status_code == 404


async def test_detector_wiring_is_load_bearing(committed_client, committed_sessionmaker) -> None:
    # Guard (S08.5.3 §B): DELIBERATELY unwire the detector, then drive a real
    # crossing over HTTP. Consumption (read-time) still rises, but with no async
    # subscriber NO alert row is written — so a future lifespan/wiring regression
    # fails THIS test instead of silently passing the journey for the wrong reason.
    client = committed_client
    admin_access, _refresh, email = await bootstrap_admin(client)
    admin_id = str(await user_id_by_email(committed_sessionmaker, email))
    as_of = _today().isoformat()  # UTC, shared by the tx date and the value read
    parent = await create_category(client, admin_access, name="Maison")
    acc = await create_personal_account(client, admin_access, name="Perso")
    budget = await create_budget(
        client,
        admin_access,
        category_id=parent["id"],
        period_start=_first_of_current_month(),
        amount_cents=10000,
        contributor_ids=[admin_id],
        scope="personal",
    )
    tx = await create_transaction(
        client,
        admin_access,
        acc["id"],
        date=as_of,
        splits=[
            {"account_id": acc["id"], "amount_cents": -8100, "currency": "EUR"},
            {
                "account_id": acc["id"],
                "amount_cents": 8100,
                "currency": "EUR",
                "category_id": parent["id"],
            },
        ],
    )

    clear_subscribers()  # drop the autouse wiring → no detector on the bus
    await confirm_transaction(client, admin_access, tx["id"])

    cons = (
        await client.get(
            f"/budgets/{budget['id']}/consumption",
            params={"as_of": as_of},
            headers=auth_headers(admin_access),
        )
    ).json()
    assert cons["consumed_cents"] == 8100  # consumption is read-time, still rises
    # …but no detector ran → no durable alert (proves the wiring is load-bearing).
    assert await fetch_threshold_alerts(committed_sessionmaker, budget_id=budget["id"]) == []
