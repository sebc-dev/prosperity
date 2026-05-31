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
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.accounts.domain import (
    AccountValidationError,
    CurrencyMismatchError,
    DuplicateMemberError,
    MemberShare,
    NonPositiveShareRatioError,
    OwnershipShapeError,
    ShareRatioSumError,
    TooFewMembersError,
)
from backend.modules.accounts.models import Account
from backend.modules.accounts.schemas import (
    AccountCreatePersonal,
    AccountCreateShared,
    AccountResponse,
    SetupRequest,
)
from backend.modules.accounts.service.accounts import (
    create_personal,
    create_shared,
)
from backend.modules.accounts.service.setup import (
    initialize_bootstrap,
    is_setup_open,
)
from backend.modules.auth.public import (
    TokenPair,
    User,
    get_current_user,
    issue_access_token,
    issue_refresh_token,
    sanitize_device_label,
)
from backend.shared.db import get_db
from backend.shared.http import client_ip_for

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
    client_ip = client_ip_for(request, settings)

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


# --- Account CRUD routes (S05.3) --------------------------------------------
#
# A second router on this module, `prefix="/accounts"`, hosting the F03-
# watertight CRUD. Every handler is guarded by `get_current_user`
# (authentication) and NEVER by `require_admin`/`require_member`: the
# watertightness is a per-resource filter in the service (`_accessible`), not
# an RBAC gate — the admin is deliberately not exempt (D2, glossary F03).
# Mapping `require_admin` here would invert the invariant.
#
# An inaccessible / archived / unknown account is a uniform 404 (never 403),
# so a non-member — admin included — cannot probe an account's existence (D4).

accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])

CurrentUser = Annotated[User, Depends(get_current_user)]

# 422 body when a shared account lists a `user_id` with no matching user row
# (FK 23503). Generic on purpose — it does not echo the offending id.
_UNKNOWN_MEMBER_DETAIL = "A referenced member does not exist."

# Curated 422 details per domain error class (C-SEC-1): we never echo
# `str(exc)`, which would leak the household base currency
# (`CurrencyMismatchError`) and internal sums (`ShareRatioSumError`) — a
# non-issue under the V1 EUR lock, but a real disclosure once V2 is
# multi-currency. The precise `str(exc)` is logged server-side instead.
_VALIDATION_DETAILS: dict[type[AccountValidationError], str] = {
    CurrencyMismatchError: "Account currency must match the household base currency.",
    OwnershipShapeError: "Invalid account ownership shape.",
    TooFewMembersError: "A shared account needs at least two members.",
    ShareRatioSumError: "Member share ratios must sum to 1.",
    NonPositiveShareRatioError: "Each member share ratio must be strictly positive.",
    DuplicateMemberError: "A user cannot be listed twice in a shared account.",
}
_DEFAULT_VALIDATION_DETAIL = "Account creation rejected."


def _validation_detail(exc: AccountValidationError) -> str:
    return _VALIDATION_DETAILS.get(type(exc), _DEFAULT_VALIDATION_DETAIL)


@accounts_router.post(
    "/personal",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_account(
    body: AccountCreatePersonal,
    user: CurrentUser,
    session: SessionDep,
) -> Account:
    """Create the caller's personal account; `owner_id` is the token's user (D3).

    `owner_id` is taken from `get_current_user`, never the body — a stray
    `owner_id` in the payload was already dropped by the schema. Domain
    rejections (currency mismatch, ownership shape) map to a curated 422
    (C-SEC-1), never a 500.
    """
    try:
        return await create_personal(
            session,
            owner_id=user.id,
            name=body.name,
            type=body.type,
            currency=body.currency,
        )
    except AccountValidationError as exc:
        logger.info("account_create_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_validation_detail(exc)
        ) from exc


@accounts_router.post(
    "/shared",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shared_account(
    body: AccountCreateShared,
    user: CurrentUser,
    session: SessionDep,
) -> Account:
    """Create a shared account with its members (≥ 2, quote-parts Σ == 1).

    Domain rejections (Σ ≠ 1, duplicate member, ratio ≤ 0, < 2 members,
    currency mismatch) → curated 422 (C-SEC-1). A member `user_id` with no
    matching user trips `fk_account_members_user_id_users` at flush; we catch
    only `IntegrityError`/SQLSTATE 23503 → 422 (C-ARCH-1) — narrower than
    `/setup`'s `DBAPIError` because account creation has no business race, so
    a concurrent 40001 may surface as 500 (no corruption, no disclosure). Any
    other SQLSTATE (e.g. 23505, pre-empted by `DuplicateMemberError`) is a
    real bug → re-raise → 500.
    """
    members = [MemberShare(user_id=m.user_id, ratio=m.default_share_ratio) for m in body.members]
    try:
        return await create_shared(
            session,
            members=members,
            name=body.name,
            type=body.type,
            currency=body.currency,
        )
    except AccountValidationError as exc:
        logger.info("account_create_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_validation_detail(exc)
        ) from exc
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23503":
            logger.info("account_create_rejected", extra={"error": "unknown_member"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNKNOWN_MEMBER_DETAIL
            ) from exc
        logger.error(
            "account_create_unexpected_integrity",
            extra={"sqlstate": getattr(exc.orig, "sqlstate", None)},
        )
        raise
