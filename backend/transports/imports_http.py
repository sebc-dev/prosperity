"""HTTP transport for the OFX import flow (S12.4) — composition root.

Assembles the banking primitives (S12.1→S12.3: parse / analyze / link / log) and
the `transactions` aggregate (E07: `create_draft` + `add_split`) into one
user-facing flow that **creates the `Transaction`s**. It lives OUTSIDE
`backend.modules` on purpose: `commit` consumes `banking.public` AND
`transactions.public`, but those are peer modules (contract 1) forbidden from
importing each other — only the composition root, like `main.py`, may import all
`*.public` surfaces freely (D1). No new `ignore_imports` is needed (D2): the
composition root is the source of no contract.

Three routes (`imports_router`, prefix `/imports/ofx`):

- `POST /preview` (multipart) → `ImportPreviewOut`. A file whose account is not
  linked to an accessible internal account → **422 `account_not_linked`**
  (D7) — "linked-but-inaccessible" is byte-identical to "not linked"
  (non-disclosure, INV-S12.3-PREVIEW-ACCESS).
- `POST /link-account` (JSON) → creates a `BankAccountExternalRef` (D8 pre-check:
  internal account must be accessible → else 404).
- `POST /commit` (re-upload multipart) → one `draft` `Transaction` per
  non-duplicate line (single `funding` leg, `category_id` NULL — never
  `planned`/`confirmed`, D6), journalled in `imported_transactions`. Idempotent
  via `UNIQUE(import_hash)` (D9). No `commit()` here — `get_db` owns the boundary
  (ADR 0015), so the whole import is atomic (D10).

Security: parse errors map to a curated 422 (never `str(exc)`, C-SEC-1, D12); a
`Content-Length` cap rejects oversized uploads with 413 **before** reading the
body (D13); PII (`file_bytes`/`parsed`) is NEVER attached to a log or exception.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import (
    accessible_account_ids,
    account_is_accessible,
    get_household,
)
from backend.modules.auth.public import User, get_current_user
from backend.modules.banking.public import (
    AccountAlreadyLinkedError,
    BankingProviderError,
    ImportPreview,
    UnknownProviderError,
    analyze_import,
    compute_import_hash,
    find_internal_account,
    known_import_hashes,
    link,
    parse_ofx,
    record_imported,
)
from backend.modules.transactions.public import add_split, create_draft
from backend.shared.db import get_db

imports_router = APIRouter(prefix="/imports/ofx", tags=["imports"])

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]

_PROVIDER = "ofx"

# 25 Mo OFX (MAX_OFX_BYTES, ofx.py) + marge enveloppe multipart. Cap miroir amont
# de la garde en RAM (défense en profondeur, D13).
MAX_REQUEST_BYTES = 26 * 1024 * 1024

# Corps d'erreur de forme CLOSE `{"code", "message"}` — jamais d'`str(exc)` ni
# d'écho de PII (C-SEC-1, D12). "linked-but-inaccessible" et "not linked"
# partagent le MÊME corps (non-disclosure, D7).
_ACCOUNT_NOT_LINKED = {
    "code": "account_not_linked",
    "message": "Le compte du fichier OFX n'est lié à aucun compte interne accessible.",
}
_UNPROCESSABLE_OFX = {
    "code": "unprocessable_ofx",
    "message": "Fichier OFX illisible ou incompatible.",
}
_CURRENCY_MISMATCH = {
    "code": "currency_mismatch",
    "message": "Le fichier contient une devise différente de celle du foyer.",
}
_PAYLOAD_TOO_LARGE = {
    "code": "payload_too_large",
    "message": "Fichier trop volumineux.",
}
_NOT_FOUND = {
    "code": "account_not_found",
    "message": "Compte introuvable.",
}
_UNKNOWN_PROVIDER = {
    "code": "unknown_provider",
    "message": "Fournisseur d'import inconnu.",
}
_ALREADY_LINKED = {
    "code": "account_already_linked",
    "message": "Ce compte externe est déjà lié.",
}


def _enforce_size_cap(request: Request) -> None:
    """Reject an oversized (or unbounded) upload with 413 BEFORE reading the body.

    `Content-Length` absent ⇒ rejet (pas de stream non borné). Volontairement
    amont de la garde `MAX_OFX_BYTES` du parser (qui opère sur des bytes déjà en
    RAM) : ce cap pré-lecture est le rempart anti-DoS amont (D13, `ofx.py:44`).
    """
    raw = request.headers.get("content-length")
    if raw is None or not raw.isdigit() or int(raw) > MAX_REQUEST_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=_PAYLOAD_TOO_LARGE)


# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------


class AutoValidationCriteriaOut(BaseModel):
    """Les 5 critères F04 + leur conjonction (`all_met`), exposés au client."""

    no_duplicates: bool
    encoding_high_confidence: bool
    within_date_window: bool
    amounts_within_cap: bool
    volume_under_limit: bool
    all_met: bool


class ImportPreviewOut(BaseModel):
    """Corps de réponse `/preview`.

    ⚠️ `account_not_linked` n'est PAS exposé : la route le traduit TOUJOURS en 422
    (D7), donc un `ImportPreviewOut` renvoyé ⟺ tous les comptes liés & accessibles.
    """

    tx_count: int
    duplicate_count: int
    encoding_confidence: Literal["high", "low"]
    date_min: dt.date | None
    date_max: dt.date | None
    amount_max_cents: int
    criteria: AutoValidationCriteriaOut
    auto_validatable: bool

    @classmethod
    def from_domain(cls, p: ImportPreview) -> ImportPreviewOut:
        return cls(
            tx_count=p.tx_count,
            duplicate_count=p.duplicate_count,
            encoding_confidence=p.encoding_confidence,
            date_min=p.date_min,
            date_max=p.date_max,
            amount_max_cents=p.amount_max_cents,
            criteria=AutoValidationCriteriaOut(
                no_duplicates=p.criteria.no_duplicates,
                encoding_high_confidence=p.criteria.encoding_high_confidence,
                within_date_window=p.criteria.within_date_window,
                amounts_within_cap=p.criteria.amounts_within_cap,
                volume_under_limit=p.criteria.volume_under_limit,
                all_met=p.criteria.all_met,
            ),
            auto_validatable=p.auto_validatable,
        )


class LinkAccountIn(BaseModel):
    """Corps de `/link-account` : lier une réf externe à un compte interne."""

    external_ref: str
    internal_account_id: UUID
    provider: str = _PROVIDER


class LinkAccountOut(BaseModel):
    """Mapping créé (201)."""

    id: UUID
    external_ref: str
    internal_account_id: UUID
    provider: str


class ImportResultOut(BaseModel):
    """Résultat d'un `/commit` : lignes créées vs ignorées (doublons)."""

    created: int
    skipped_duplicates: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@imports_router.post("/preview", response_model=ImportPreviewOut)
async def preview_import(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> ImportPreviewOut:
    """Analyse un OFX uploadé → `ImportPreviewOut` (read-only, D10).

    Gate D7 : si UN SEUL `external_ref` du fichier est non-lié OU lié à un compte
    ∉ `accessible_account_ids(user)` → 422 `account_not_linked` (corps statique
    partagé, non-disclosure). Sinon → `analyze_import`. PII jamais loggée.
    """
    _enforce_size_cap(request)  # D13
    file_bytes = await file.read()
    try:
        parsed = await parse_ofx(file_bytes)
    except BankingProviderError as exc:  # D12 (inclut la garde de taille)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNPROCESSABLE_OFX
        ) from exc

    accessible = await accessible_account_ids(session, user_id=current_user.id)  # D7
    for ref in parsed.accounts:
        internal = await find_internal_account(session, external_ref=ref, provider=_PROVIDER)
        if internal is None or internal not in accessible:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_ACCOUNT_NOT_LINKED)

    preview = await analyze_import(session, parsed, provider=_PROVIDER)
    return ImportPreviewOut.from_domain(preview)


@imports_router.post(
    "/link-account", response_model=LinkAccountOut, status_code=status.HTTP_201_CREATED
)
async def link_account(
    session: SessionDep,
    current_user: CurrentUser,
    body: LinkAccountIn,
) -> LinkAccountOut:
    """Lie `(external_ref, provider)` à un compte interne accessible (D8).

    Gate accessibilité AVANT `link` (404 non-disclosure, admin non exempt, F03) :
    on ne révèle jamais l'existence d'un compte d'autrui. Puis `link` :
    double-lien → 409, provider inconnu → 422. Flush-only (ADR 0015).
    """
    if not await account_is_accessible(
        session, account_id=body.internal_account_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    try:
        ref = await link(
            session,
            external_ref=body.external_ref,
            internal_account_id=body.internal_account_id,
            provider=body.provider,
        )
    except AccountAlreadyLinkedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_ALREADY_LINKED) from exc
    except UnknownProviderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNKNOWN_PROVIDER) from exc
    return LinkAccountOut(
        id=ref.id,
        external_ref=ref.external_ref,
        internal_account_id=ref.internal_account_id,
        provider=ref.provider,
    )


@imports_router.post("/commit", response_model=ImportResultOut)
async def commit_import(  # noqa: PLR0913 — FastAPI route deps + form fields are a flat API
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
    internal_account_id: Annotated[UUID, Form()],
    user_overrides: Annotated[str | None, Form()] = None,  # D11 — accepté, no-op V1
) -> ImportResultOut:
    """Crée un `draft` par ligne non dupliquée + journalise son `import_hash`.

    Orchestration au composition root (D1). Gates : (a) compte cible accessible
    (404, D8a) ; (b) chaque réf du fichier liée à CE compte (422, D8b) ; (c) devise
    du fichier == devise du foyer (422, D6b). Dedup D9 : `known_import_hashes` +
    set `seen` intra-batch. Chaque ligne retenue → `create_draft` + `add_split`
    (jambe `funding`, reste `draft`, D6) + `record_imported`. AUCUN commit (D10) :
    `get_db` commite à la sortie ; une exception → rollback total (atomicité).
    `user_overrides` accepté mais ignoré (D11 — catégorisation manuelle). PII
    jamais loggée.
    """
    _enforce_size_cap(request)  # D13
    file_bytes = await file.read()
    try:
        parsed = await parse_ofx(file_bytes)
    except BankingProviderError as exc:  # D12
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNPROCESSABLE_OFX
        ) from exc

    # D8(a) — compte cible accessible (non-disclosure, admin non exempt).
    if not await account_is_accessible(
        session, account_id=internal_account_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    # D8(b) — chaque réf du fichier doit pointer CE compte (non lié = lié ailleurs).
    for ref in parsed.accounts:
        if (
            await find_internal_account(session, external_ref=ref, provider=_PROVIDER)
            != internal_account_id
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_ACCOUNT_NOT_LINKED)

    # D6b — gate devise : rejet GLOBAL si une ligne diffère de la devise du foyer.
    household = await get_household(session)
    if any(tx.currency != household.base_currency for tx in parsed.transactions):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_CURRENCY_MISMATCH)

    # D9 — idempotence : 1 SELECT préalable + set intra-batch ; UNIQUE = backstop.
    hashes = [compute_import_hash(internal_account_id, tx) for tx in parsed.transactions]  # D5
    known = await known_import_hashes(session, hashes)
    seen: set[str] = set()
    created = skipped = 0
    for tx, import_hash in zip(parsed.transactions, hashes, strict=True):
        if import_hash in known or import_hash in seen:
            skipped += 1
            continue
        seen.add(import_hash)
        draft = await create_draft(
            session, account_id=internal_account_id, by_user_id=current_user.id, date=tx.date
        )  # D6 — reste draft
        await add_split(
            session,
            tx_id=draft.id,
            account_id=internal_account_id,
            amount_cents=tx.amount_cents,
            currency=tx.currency,
        )  # jambe funding (category_id NULL)
        await record_imported(session, account_id=internal_account_id, import_hash=import_hash)
        created += 1

    return ImportResultOut(created=created, skipped_duplicates=skipped)
    # AUCUN commit (D10) — get_db commite à la sortie ; exception → rollback total.
