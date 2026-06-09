"""Integration tests for `POST /imports/ofx/preview` (S12.4, P12.4.1).

Drives the preview route over httpx (`async_client`, savepoint mode — the route
is read-only, D10, so no real commit is needed). Covers the route PLUMBING only:
the access gate (D7), the parse-error mapping (D12), and the size cap (D13). The
exhaustive 5-criteria matrix stays at the service tier (`test_analyze_import.py`,
#178) — here we never re-test parsing, and `/preview` uses non-injectable
`date.today()` so the date-window cases would be flaky.

The load-bearing security assertion (INV-S12.3-PREVIEW-ACCESS): a ref linked to
*another* user's account is **byte-identical** to a not-linked ref (both 422
`account_not_linked`), so the preview is never an existence oracle.

Fixtures: `boursorama_export_2026.ofx` is high-confidence + EUR + within-window →
auto-validatable; `libelles_accentues_windows_1252.ofx` is cp1252-fallback → low
confidence. "Not linked" is obtained by *not* calling `link` (no dedicated fixture).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.banking.service.external_refs import link
from backend.transports import imports_http

_settings = get_settings()
_OFX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ofx"

# External refs carried by the fixtures (account.number in the OFX).
_BOURSO_REF = "BOURSO-0000-1111"  # boursorama_export_2026.ofx — high conf, EUR
_CP1252_REF = "CP1252-4444-5555"  # libelles_accentues_windows_1252.ofx — low conf

pytestmark = pytest.mark.usefixtures("household_singleton")


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _read_ofx(name: str) -> bytes:
    return (_OFX_DIR / name).read_bytes()


def _files(name: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, _read_ofx(name), "application/octet-stream")}


async def _make_user(session: AsyncSession, *, role: UserRole = UserRole.MEMBER) -> UUID:
    user = User(
        email=f"{uuid4().hex}@example.com",
        password_hash="x" * 60,
        display_name="importer",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user.id


async def _make_account(session: AsyncSession, owner_id: UUID) -> UUID:
    account = Account(name="Courant", type=AccountType.COURANT, currency="EUR", owner_id=owner_id)
    session.add(account)
    await session.flush()
    return account.id


async def test_preview_auto_validatable_200(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)
    await link(
        household_singleton,
        external_ref=_BOURSO_REF,
        internal_account_id=account_id,
        provider="ofx",
    )

    resp = await async_client.post(
        "/imports/ofx/preview", files=_files("boursorama_export_2026.ofx"), headers=_bearer(user_id)
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auto_validatable"] is True
    assert body["criteria"]["all_met"] is True
    assert body["encoding_confidence"] == "high"
    # `account_not_linked` is NEVER exposed in a 200 (D7): a returned preview ⟺
    # all accounts linked & accessible.
    assert "account_not_linked" not in body


async def test_preview_low_encoding_blocks_criterion(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)
    await link(
        household_singleton,
        external_ref=_CP1252_REF,
        internal_account_id=account_id,
        provider="ofx",
    )

    resp = await async_client.post(
        "/imports/ofx/preview",
        files=_files("libelles_accentues_windows_1252.ofx"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["encoding_confidence"] == "low"
    assert body["criteria"]["encoding_high_confidence"] is False
    assert body["auto_validatable"] is False


async def test_preview_account_not_linked_422(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    # Ref is NEVER linked → 422 typed `account_not_linked`.
    user_id = await _make_user(household_singleton)
    await _make_account(household_singleton, user_id)

    resp = await async_client.post(
        "/imports/ofx/preview", files=_files("boursorama_export_2026.ofx"), headers=_bearer(user_id)
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "account_not_linked"


async def test_preview_linked_but_inaccessible_is_indistinguishable_422(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    # Ref linked to ANOTHER user's personal account → must be byte-identical to
    # the not-linked case (non-disclosure, INV-S12.3-PREVIEW-ACCESS).
    other_id = await _make_user(household_singleton)
    other_account = await _make_account(household_singleton, other_id)
    await link(
        household_singleton,
        external_ref=_BOURSO_REF,
        internal_account_id=other_account,
        provider="ofx",
    )
    caller_id = await _make_user(household_singleton)
    await _make_account(household_singleton, caller_id)

    resp = await async_client.post(
        "/imports/ofx/preview",
        files=_files("boursorama_export_2026.ofx"),
        headers=_bearer(caller_id),
    )

    assert resp.status_code == 422, resp.text
    # Byte-identical body to the pure not-linked case.
    assert resp.json() == {
        "detail": {
            "code": "account_not_linked",
            "message": "Le compte du fichier OFX n'est lié à aucun compte interne accessible.",
        }
    }


async def test_preview_malformed_ofx_422(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)

    resp = await async_client.post(
        "/imports/ofx/preview",
        files={"file": ("garbage.ofx", b"garbage", "application/octet-stream")},
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    # Close-form `{code, message}` exactly — never `str(exc)` (C-SEC-1).
    assert resp.json()["detail"] == {
        "code": "unprocessable_ofx",
        "message": "Fichier OFX illisible ou incompatible.",
    }


async def test_preview_payload_too_large_413(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the cap so a tiny upload trips it: `Content-Length` > cap → 413
    # BEFORE `parse_ofx` is ever reached (D13). Monkeypatching the cap avoids
    # allocating a real 26 Mo payload.
    monkeypatch.setattr(imports_http, "MAX_REQUEST_BYTES", 4)

    def _fail_parse(*_a: object, **_k: object) -> object:
        raise AssertionError("parse_ofx must not be reached when the size cap fires")

    monkeypatch.setattr(imports_http, "parse_ofx", _fail_parse)
    user_id = await _make_user(household_singleton)

    resp = await async_client.post(
        "/imports/ofx/preview", files=_files("boursorama_export_2026.ofx"), headers=_bearer(user_id)
    )

    assert resp.status_code == 413, resp.text
    assert resp.json()["detail"]["code"] == "payload_too_large"


async def test_preview_anonymous_401(async_client: AsyncClient) -> None:
    # No Authorization header → 401 (auth rejects before the route body runs).
    resp = await async_client.post(
        "/imports/ofx/preview",
        files={"file": ("x.ofx", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 401, resp.text
