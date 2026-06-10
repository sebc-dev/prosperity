"""Helpers d'intégration partagés du parcours d'import OFX (S12.4 + S12.5).

Factorisés depuis `test_imports_routes_preview.py` / `_routes_link.py` /
`_commit.py` (review S12.4) : `bearer`, lecture/empaquetage des fixtures OFX, et
le générateur OFX SGML synthétique (fichiers devise étrangère / multi-comptes /
doublon intra-fichier, absents du dépôt). S12.5 y remonte `_seed_linked`/`_count`
(jadis locaux à `test_imports_commit.py`) + les constantes refs/montants des 6
fixtures canoniques, consommées aussi par `test_ofx_fixtures_e2e.py`. Module NON
collecté (pas de préfixe `test_`, précédent `_debts_helpers.py` /
`tests/e2e/_helpers.py`), hors `root_package` import-linter. Un seul exemplaire à
maintenir au lieu de copies inter-fichiers de tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.banking.public import link

_settings = get_settings()
_OFX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ofx"

SessionMaker = async_sessionmaker[AsyncSession]

# External refs (account.number) carried by the real canonical fixtures, with the
# cent-amounts each one commits (euros×100, débit négatif). Source unique pour les
# tests de route S12.4 et le tier bout-en-bout S12.5.
BOURSO_REF = "BOURSO-0000-1111"  # boursorama_export_2026.ofx — 2.x XML, EUR, high conf
BOURSO_AMOUNTS = {-2999, 210000}  # -29.99 / +2100.00
CP1252_REF = "CP1252-4444-5555"  # libelles_accentues_windows_1252.ofx — 1.x SGML cp1252, low conf
LIVRET_A_REF = "LIVRETA-2222-3333"  # livret_a_2026_q1.ofx — 1.x SGML cp1252, 2 tx
LIVRET_A_AMOUNTS = {-7540, 1233}  # -75.40 / +12.33
PEL_REF = "PEL-0000-9999"  # pel_2025_2026.ofx — 1.x SGML UTF-8 BOM, 2 tx, high conf
PEL_AMOUNTS = {22500, 5712}  # +225.00 / +57.12
SG_FITID_REF = "SG-1111-2222"  # fitid_unstable_societe_generale.ofx — 2 STMTTRN ≡ métier
NOT_LINKED_REF = "NOTLINKED-0000-0000"  # account_not_yet_linked.ofx — jamais liée


def bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def read_ofx(name: str) -> bytes:
    return (_OFX_DIR / name).read_bytes()


def files(name: str) -> dict[str, tuple[str, bytes, str]]:
    """Multipart payload from a real fixture file under `tests/fixtures/ofx/`."""
    return {"file": (name, read_ofx(name), "application/octet-stream")}


def bytes_files(
    payload: bytes, *, name: str = "synthetic.ofx"
) -> dict[str, tuple[str, bytes, str]]:
    """Multipart payload from raw bytes (synthetic OFX or malformed input)."""
    return {"file": (name, payload, "application/octet-stream")}


# ---------------------------------------------------------------------------
# Synthetic OFX SGML generator (foreign currency / multi-account / intra-file
# dup). Real fixtures cover the happy path; these edge files do not exist on disk.
# ---------------------------------------------------------------------------

_HEADER = (
    "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\nENCODING:USASCII\n"
    "CHARSET:1252\nCOMPRESSION:NONE\nOLDFILEUID:NONE\nNEWFILEUID:NONE\n"
)


def stmt(acctid: str, currency: str, txns: list[tuple[str, str, str]], *, bankid: str) -> str:
    """One `<STMTTRNRS>` block: `txns` = list of `(date, amount, fitid)`."""
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


def ofx(stmts: list[str]) -> bytes:
    """Wrap `stmts` into a full cp1252-encoded OFX document."""
    inner = "".join(stmts)
    return (
        _HEADER + "\n<OFX>\n<SIGNONMSGSRSV1><SONRS>\n<STATUS><CODE>0<SEVERITY>INFO</STATUS>\n"
        "<DTSERVER>20260401120000<LANGUAGE>FRA\n</SONRS></SIGNONMSGSRSV1>\n"
        f"<BANKMSGSRSV1>{inner}</BANKMSGSRSV1></OFX>\n"
    ).encode("cp1252")


# ---------------------------------------------------------------------------
# Real-commit seeding (commit/idempotence/dedup tests run on `committed_*`).
# Hoisted from `test_imports_commit.py` (review S12.5) so the e2e tier consumes
# them without importing a `test_`-prefixed (collected) module.
# ---------------------------------------------------------------------------


async def seed_linked(
    sm: SessionMaker, *, linked_refs: tuple[str, ...] = (BOURSO_REF,)
) -> tuple[UUID, UUID]:
    """Seed household + owner + a personal account, link `linked_refs` to it, commit.

    Returns `(user_id, account_id)`. The account is owned by the user → accessible.
    The household is `initialized_at`-stamped so the commit currency gate does not
    short-circuit on `household_not_initialized`.
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


async def count_rows(sm: SessionMaker, model: type, **filters: object) -> int:
    """Count rows of `model` matching `filters`, in a fresh committed session."""
    async with sm() as session:
        stmt_ = select(func.count()).select_from(model)
        for col, val in filters.items():
            stmt_ = stmt_.where(getattr(model, col) == val)
        return (await session.execute(stmt_)).scalar_one()


async def commit_fixture(
    client: AsyncClient, *, account_id: UUID, user_id: UUID, name: str
) -> dict[str, int]:
    """POST a real fixture to `/imports/ofx/commit`, assert 200, return the JSON body.

    Shared by the commit/idempotence/dedup tests that all run the same
    upload→assert-200→read-`{created, skipped_duplicates}` shape.
    """
    resp = await client.post(
        "/imports/ofx/commit",
        data={"internal_account_id": str(account_id)},
        files=files(name),
        headers=bearer(user_id),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
