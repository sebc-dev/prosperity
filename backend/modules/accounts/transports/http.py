"""HTTP transport for the accounts module (S03.2 — `/setup`).

Hosts the `/setup` bootstrap flow: lock-after-init (ADR 0010), creates
the first admin + initialises the household singleton in one DB
transaction. Re-callable until init completes; locked to 404 forever
after.

Placed here rather than in `auth/transports/` because the import-linter
layer graph (ADR 0005) puts `accounts` strictly above `auth`. A route
inside `auth` that touches `Household` would have to import from
`accounts.public`, which is forbidden downward. The reverse — accounts
calling `auth.public` — is legal and is the wiring this module relies
on.

Internal to the accounts module; cross-module callers (none today)
must go through `backend.modules.accounts.public`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.accounts.schemas import SetupRequest
from backend.modules.accounts.service.setup import (
    initialize_bootstrap,
    is_setup_open,
)
from backend.modules.auth.public import (
    TokenPair,
    issue_access_token,
    issue_refresh_token,
    sanitize_device_label,
)
from backend.shared.db import get_db

logger = logging.getLogger(__name__)

# OWASP ASVS V8.3.4 — token-bearing responses must not be cached. Also
# applied to the GET probe so a stale 200 cannot persist in a CDN /
# corp-proxy after init completes and `/setup` flips to 404.
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# Postgres SQLSTATEs that legitimately signal "another setup beat us".
# Anything else under DBAPIError indicates an application-level bug
# (NOT NULL miss, FK violation, etc.) and must bubble up as 500 — never
# be masked as "setup locked".
#
# 23505 unique_violation: PK on `household.id` AND the functional UNIQUE
# index `uq_users_email_lower` on `users.email` — Postgres emits the
# same SQLSTATE for both, which is fine because both mean "race lost".
#
# 23514 check_violation: defensive coverage of `ck_household_singleton`
# (unreachable when callers use the ORM default, but flagged here so a
# future raw-SQL path doesn't surface as 500).
#
# 40001 serialization_failure: under REPEATABLE READ isolation (cf.
# `backend.shared.db`), a true concurrent flush can abort the loser
# with 40001 *before* the UNIQUE check fires. Postgres raises this as
# `DBAPIError` (not `IntegrityError`), which is why the catch below is
# on the parent class. Same race-lost semantics as 23505.
_RACE_LOST_SQLSTATES = frozenset({"23505", "23514", "40001"})

router = APIRouter(tags=["setup"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/setup", status_code=status.HTTP_200_OK)
async def setup_form(
    response: Response,
    session: SessionDep,
) -> dict[str, str]:
    """Probe whether `/setup` is still open.

    Returns `{"status": "open"}` with 200 when the deployment has not
    yet been initialised; 404 once any user exists or the household
    singleton row has been inserted. The frontend uses this to decide
    whether to render the bootstrap form vs the login page.
    """
    response.headers.update(_NO_STORE_HEADERS)
    if not await is_setup_open(session):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"status": "open"}


@router.post("/setup", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def setup_submit(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Bootstrap the deployment: create the first admin + init household.

    Wrapped in a single `get_db` transaction — household INSERT, user
    INSERT, refresh-token INSERT all live or die together. The DB
    constraints (PK on `household.id`, UNIQUE on `lower(email)`)
    backstop the precheck race window. Any `DBAPIError` with a
    race-lost SQLSTATE (23505/23514/40001) collapses to 404; anything
    else re-raises so app-level bugs surface as 500.

    Returns a `TokenPair` so the new admin is logged in immediately —
    no second round-trip to `/auth/login` required.
    """
    response.headers.update(_NO_STORE_HEADERS)
    client_ip = request.client.host if request.client else None

    if not await is_setup_open(session):
        logger.warning(
            "setup_locked",
            extra={"reason": "precheck_locked", "client_ip": client_ip},
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    try:
        admin_id = await initialize_bootstrap(
            session,
            email=body.email,
            password=body.password.get_secret_value(),
            display_name=body.display_name,
            household_name=body.household_name,
        )
    except DBAPIError as exc:
        # SQLSTATE-based discrimination: only race-lost violations
        # collapse to 404. Anything else (NOT NULL, FK, unknown)
        # re-raises so an app-level bug surfaces as 500 instead of
        # being masked as "setup locked". `DBAPIError` is the parent
        # of `IntegrityError` (covers 23505/23514) and also catches
        # 40001 serialization_failure raised directly under REPEATABLE
        # READ before any UNIQUE check.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate not in _RACE_LOST_SQLSTATES:
            logger.error(
                "setup_unexpected_integrity",
                extra={"sqlstate": sqlstate, "client_ip": client_ip},
            )
            raise
        logger.warning(
            "setup_locked",
            extra={
                "reason": "race_lost",
                "sqlstate": sqlstate,
                "client_ip": client_ip,
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    # Auto-login: the refresh-token INSERT joins the same transaction
    # as the household + user INSERTs. A UNIQUE collision on
    # `token_hash` (astronomically improbable with 256-bit entropy) is
    # *not* in the race-lost branch above — it would bubble out of
    # `issue_refresh_token` as `IntegrityError` and surface as 500.
    # `get_db` rolls back the whole transaction on that path, so the
    # deployment is left vierge for a clean retry rather than half-
    # bootstrapped; 500 is the right signal for a true cryptographic
    # accident, distinct from the race-lost 404.
    device_label = sanitize_device_label(request.headers.get("user-agent"))
    access_token = issue_access_token(admin_id, settings=settings)
    refresh_token = await issue_refresh_token(
        session, admin_id, settings=settings, device_label=device_label
    )

    logger.info(
        "setup_completed",
        extra={
            "user_id": str(admin_id),
            "client_ip": client_ip,
            # Symmetry with `refresh_tokens.device_label` so the audit
            # log and the persisted column always agree.
            "device_label": device_label,
        },
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)
