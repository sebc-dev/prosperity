"""Shared building blocks for the E2E API user journeys.

Plain `async` functions (not fixtures, D9): a journey is an ordered
sequence of HTTP calls, and inline helper calls keep that order explicit
and the per-test statement count under ruff's `PLR0915` ceiling (D10).

The audit helpers read `admin_audit_logs` through a side-channel DB query
(D3): there is no audit-read endpoint yet, so the trail is verified
directly against the `committed_sessionmaker`. Replace with an HTTP call
once such an endpoint exists.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.auth.models import AdminAuditLog, User
from backend.modules.budget.models import BudgetThresholdAlert

# Default admin credentials reused across journeys. The password is ≥12
# chars (SetupRequest / OWASP ASVS V2.1.*); journeys that re-login against
# the admin must use this exact value.
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def bootstrap_admin(
    client: AsyncClient,
    *,
    email: str = ADMIN_EMAIL,
    password: str = ADMIN_PASSWORD,
    display_name: str = "Admin",
    household_name: str = "Foyer Test",
) -> tuple[str, str, str]:
    """POST /setup → (access, refresh, email).

    Creates the first admin + household and locks `/setup` (404 after).
    Asserts 200 — a failure here is a broken precondition for the calling
    journey, not the behaviour under test.
    """
    resp = await client.post(
        "/setup",
        json={
            "email": email,
            "password": password,
            "display_name": display_name,
            "household_name": household_name,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["access_token"], body["refresh_token"], email


async def create_invitation(client: AsyncClient, admin_access: str, email: str) -> dict[str, Any]:
    """POST /invitations (Bearer admin) → full body.

    Returns `{id, email, expires_at, token, accept_url}`; the raw token is
    captured from the body (D4), never scraped from logs. Asserts 201.
    """
    resp = await client.post(
        "/invitations",
        json={"email": email},
        headers=auth_headers(admin_access),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def onboard_member(client: AsyncClient, admin_access: str, email: str, password: str) -> str:
    """invitation → accept → the member's access token (Parcours 1, condensed).

    Reuses the golden onboarding path so an accounts journey can stand up a
    second authenticated user without re-asserting the per-step invitation
    contracts (already covered by `test_onboarding_multi_user`). Returns the
    member's access token.
    """
    inv = await create_invitation(client, admin_access, email)
    accept = await client.post(
        "/accept-invite",
        json={"token": inv["token"], "password": password, "display_name": email.split("@", 1)[0]},
    )
    assert accept.status_code == 200, accept.text
    return accept.json()["access_token"]


async def fetch_audit_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> list[tuple[str, object, object]]:
    """Side-channel (D3): `[(action, actor_user_id, target_user_id), …]`.

    Ordered by `created_at`. The order is strict because every audited
    action lives in its own HTTP transaction → its own Postgres `now()`
    (D11). If two audited actions ever share one transaction, add a
    tie-breaker here.
    """
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(
                    AdminAuditLog.action,
                    AdminAuditLog.actor_user_id,
                    AdminAuditLog.target_user_id,
                ).order_by(AdminAuditLog.created_at)
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def user_id_by_email(
    sessionmaker: async_sessionmaker[AsyncSession], email: str
) -> object | None:
    """Side-channel (D3): resolve a user's id by email, or None if absent."""
    async with sessionmaker() as session:
        return (
            await session.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()


async def create_category(
    client: AsyncClient,
    access: str,
    *,
    name: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """POST /categories (Bearer) → full CategoryResponse body. Asserts 201.

    Omits `parent_id` when None so the `extra="forbid"` schema sees only what the
    caller meant to set. Multi-usage (the A/B/C tree + the member's tree); the
    single-use GET / PATCH /parent / DELETE calls stay inline in the journey so
    each state transition reads in place. `color`/`icon` are left to their
    server defaults — no journey asserts them (those contracts are integration's).
    """
    body: dict[str, Any] = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = await client.post("/categories", json=body, headers=auth_headers(access))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def fetch_audit_by_action(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    action: str,
) -> list[tuple[object, object, dict[str, Any] | None]]:
    """Side-channel (D3): `[(actor_user_id, target_user_id, event_metadata), …]`
    for the rows whose `action` matches, ordered by `created_at`.

    `fetch_audit_rows` is a *global, unfiltered* projection of `(action, actor,
    target)` — relied on by Parcours 1/2. A category journey instead needs to
    isolate its own `category_moved` rows (an `onboard_member` call interleaves
    `invite_sent` / `invite_accepted` rows), and to read the JSONB `metadata`
    column (Python attr `event_metadata`) holding `category_id` / `from_parent_id`
    / `to_parent_id`. Filtering by action keeps the oracle robust to those
    interleaved rows; projecting actor+target+metadata together lets one call
    assert both *who* moved and *what* moved.
    """
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(
                    AdminAuditLog.actor_user_id,
                    AdminAuditLog.target_user_id,
                    AdminAuditLog.event_metadata,
                )
                .where(AdminAuditLog.action == action)
                .order_by(AdminAuditLog.created_at)
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


# --- Budget lifecycle (S08.5.3) ---------------------------------------------
#
# Plain `async` helpers for the budget E2E journey (D11): create an account, a
# transaction in canonical form B, confirm it through the real flow, create a
# budget, and read the threshold alerts. `leg_role` is NEVER in a create payload
# (server-authoritative, derived from `category_id` — ADR 0017 / S08.5.1), so the
# journey produces a confirmable consuming expense through the real client flow.


async def create_personal_account(
    client: AsyncClient,
    access: str,
    *,
    name: str,
    type: str = "courant",
    currency: str = "EUR",
) -> dict[str, Any]:
    """POST /accounts/personal (Bearer) → AccountResponse. owner = caller. Asserts 201."""
    resp = await client.post(
        "/accounts/personal",
        json={"name": name, "type": type, "currency": currency},
        headers=auth_headers(access),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_shared_account(  # noqa: PLR0913 — keyword-only HTTP helper
    client: AsyncClient,
    access: str,
    *,
    name: str,
    members: list[dict[str, Any]],
    type: str = "courant",
    currency: str = "EUR",
) -> dict[str, Any]:
    """POST /accounts/shared (Bearer). `members` = [{user_id, default_share_ratio}]
    (≥ 2, Σ parts == 1). Asserts 201."""
    resp = await client.post(
        "/accounts/shared",
        json={"name": name, "type": type, "currency": currency, "members": members},
        headers=auth_headers(access),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_transaction(
    client: AsyncClient,
    access: str,
    account_id: str,
    *,
    splits: list[dict[str, Any]],
    date: str | None = None,
) -> dict[str, Any]:
    """POST /accounts/{account_id}/transactions (Bearer) → draft TransactionResponse.

    `splits` = [{account_id, amount_cents, currency, category_id?}] ; `leg_role`
    is NOT exposed (server-authoritative, derived from `category_id` at INSERT —
    ADR 0017 / S08.5.1). Asserts 201.
    """
    body: dict[str, Any] = {"splits": splits}
    if date is not None:
        body["date"] = date
    resp = await client.post(
        f"/accounts/{account_id}/transactions", json=body, headers=auth_headers(access)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def confirm_transaction(client: AsyncClient, access: str, tx_id: str) -> dict[str, Any]:
    """draft → planned → confirmed (Bearer). A draft is not directly confirmable
    (E07): chains POST /plan then POST /confirm. Asserts 200 at each step."""
    planned = await client.post(f"/transactions/{tx_id}/plan", headers=auth_headers(access))
    assert planned.status_code == 200, planned.text
    confirmed = await client.post(f"/transactions/{tx_id}/confirm", headers=auth_headers(access))
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


async def create_budget(  # noqa: PLR0913 — keyword-only HTTP helper
    client: AsyncClient,
    access: str,
    *,
    category_id: str,
    period_start: str,
    amount_cents: int,
    contributor_ids: list[str],
    scope: str = "personal",
    period_kind: str = "monthly",
) -> dict[str, Any]:
    """POST /budgets (Bearer) → BudgetResponse. `currency`/`created_by` server-derived.
    Asserts 201."""
    resp = await client.post(
        "/budgets",
        json={
            "category_id": category_id,
            "period_kind": period_kind,
            "period_start": period_start,
            "amount_cents": amount_cents,
            "scope": scope,
            "contributor_ids": contributor_ids,
        },
        headers=auth_headers(access),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def fetch_threshold_alerts(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    budget_id: str,
) -> list[int]:
    """Side-channel (D8): the sorted `[threshold_pct, …]` of a budget's alerts.

    No HTTP endpoint exposes the threshold alerts in V1 (notification = SSE/E14);
    we read `budget_threshold_alerts` directly, gabarit `fetch_audit_*`. Replace
    with an HTTP call once such an endpoint exists.
    """
    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(BudgetThresholdAlert.threshold_pct)
                    .where(BudgetThresholdAlert.budget_id == UUID(budget_id))
                    .order_by(BudgetThresholdAlert.threshold_pct)
                )
            )
            .scalars()
            .all()
        )
    return [int(r) for r in rows]
