"""Helpers d'intégration partagés du parcours d'import OFX (S12.4).

Factorisés depuis `test_imports_routes_preview.py` / `_routes_link.py` /
`_commit.py` (review S12.4) : `bearer`, lecture/empaquetage des fixtures OFX, et
le générateur OFX SGML synthétique (fichiers devise étrangère / multi-comptes /
doublon intra-fichier, absents du dépôt). Module NON collecté (pas de préfixe
`test_`, précédent `_debts_helpers.py` / `tests/e2e/_helpers.py`), hors
`root_package` import-linter. Mêmes corps qu'avant, noms rendus publics — un seul
exemplaire à maintenir au lieu de trois copies.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from backend.config import get_settings
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()
_OFX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ofx"

# External refs (account.number) carried by the real fixtures.
BOURSO_REF = "BOURSO-0000-1111"  # boursorama_export_2026.ofx — 2 lines, EUR, high conf
BOURSO_AMOUNTS = {-2999, 210000}
CP1252_REF = "CP1252-4444-5555"  # libelles_accentues_windows_1252.ofx — low conf


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
