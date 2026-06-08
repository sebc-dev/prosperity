"""`OFXProvider` — parser OFX fichier statique défensif (S12.2).

⚠️ **Delta ADR 0009 (issue #177)** : `OFXProvider` est un **parser fichier
statique synchrone**, PAS une implémentation du Protocol pull-only
`BankingProvider`. Aucune méthode `list_accounts`/`fetch_transactions`/
`consent_status` : pas de polling, pas de consentement, pas d'async réseau.
Il partage seulement `BankTransaction` et la base `BankingProviderError` avec le
futur `EnableBankingProvider`.

Le parser prend les octets bruts d'un fichier uploadé et produit un
`ParsedOFX(accounts, transactions, encoding_confidence)` :

- **encoding déterministe** (BOM-first → UTF-8 strict → fallback cp1252, D4) ;
- **toute défaillance traduite en exception typée** (`BankingProviderError`), jamais
  une exception native `ofxparse`/`OSError` (D10) ;
- parsing synchrone `ofxparse` exécuté **hors event loop** via `asyncio.to_thread`
  (D9), précédé d'une **garde de taille** synchrone `MAX_OFX_BYTES` (DoS, D12).
"""

from __future__ import annotations

import asyncio
import codecs
import io
from typing import Any

from ofxparse import OfxParser, OfxParserException

from backend.modules.banking.domain import (
    BankTransaction,
    EncodingConfidence,
    EncodingDetectionError,
    IncompatibleAccountError,
    ParsedOFX,
    ProviderUnavailableError,
    decimal_euros_to_cents,
)

MAX_OFX_BYTES = 25 * 1024 * 1024
"""25 MiB — garde DoS (D12). Le parser présuppose une entrée bornée et le vérifie :
sans borne, un upload de plusieurs centaines de Mo → plusieurs Go résidents/requête
(bytes + texte décodé + `StringIO` + arbre BeautifulSoup) et N uploads concurrents
saturent le `ThreadPoolExecutor` par défaut de `asyncio.to_thread`. Le boundary
route S12.4 pose un cap miroir sur `Content-Length` (défense en profondeur)."""


def _detect_encoding(blob: bytes) -> tuple[str, EncodingConfidence]:
    """Décode `blob` de façon **déterministe** : BOM-first → UTF-8 strict → cp1252 (D4).

    BOM (UTF-8 sig / UTF-16 LE-BE) ou UTF-8 strict → `'high'`. Fallback windows-1252
    (`cp1252`) → `'low'` (impose la preview obligatoire en S12.3). Octets indécodables
    même en cp1252 → `EncodingDetectionError`.

    Pas de `chardet` (heuristique probabiliste : tests/critères de preview non
    reproductibles). La détection ignore tout en-tête `CHARSET`/`<?xml encoding>`
    déclaré (attaquant-contrôlé) — on tranche au niveau octets, donc le signal
    `encoding_confidence` est non contournable (intégrité sécurité).
    """
    if blob.startswith(codecs.BOM_UTF8):
        return blob.decode("utf-8-sig"), "high"
    if blob.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return blob.decode("utf-16"), "high"  # `utf-16` lit le BOM (LE comme BE)
    try:
        return blob.decode("utf-8"), "high"
    except UnicodeDecodeError:
        pass
    try:
        return blob.decode("cp1252"), "low"  # fallback → confiance basse
    except UnicodeDecodeError as exc:
        raise EncodingDetectionError("octets OFX indécodables") from exc


class OFXProvider:
    """Parser OFX fichier statique (ADR 0009 delta : PAS un `BankingProvider`).

    `parse` est async et exécute `ofxparse` (synchrone) hors event loop via
    `asyncio.to_thread` (D9). La garde de taille (D12) s'exécute en amont,
    synchronement. Aucune méthode pull (`list_accounts`/...).
    """

    async def parse(self, file_bytes: bytes) -> ParsedOFX:
        if len(file_bytes) > MAX_OFX_BYTES:  # D12 — garde DoS, O(1), avant tout décodage
            raise IncompatibleAccountError("OFX trop volumineux")
        return await asyncio.to_thread(self._parse_sync, file_bytes)

    def _parse_sync(self, file_bytes: bytes) -> ParsedOFX:
        # `ofxparse` parse via `BeautifulSoup(fh, "html.parser")` (stdlib, PAS lxml) :
        # pas de résolution d'entités externes (XXE) ni d'expansion récursive
        # (billion-laughs). NE PAS introduire lxml / `features='lxml-xml'` sans
        # durcissement XML (`defusedxml`). Non-régression : test_ofx_provider (D13).
        text, confidence = _detect_encoding(file_bytes)  # EncodingDetectionError se propage
        try:
            # `ofxparse` n'expose pas de stubs : on confine l'arbre non typé derrière
            # `Any` (frontière unique) et n'en extrait que des primitifs typés via `_map`.
            ofx: Any = OfxParser.parse(io.StringIO(text))  # pyright: ignore[reportUnknownMemberType]
            accounts = tuple(str(acc.number) for acc in ofx.accounts)
            txns = tuple(
                self._map(str(acc.number), acc.statement.currency, t)
                for acc in ofx.accounts
                for t in acc.statement.transactions
            )
        except OfxParserException as exc:
            raise IncompatibleAccountError("OFX illisible") from exc
        except OSError as exc:  # mapping défensif (D10) ; non atteint en mémoire
            raise ProviderUnavailableError("lecture OFX impossible") from exc
        except Exception as exc:  # filet « jamais d'exception brute qui fuit » (D10)
            raise IncompatibleAccountError("OFX incompatible") from exc
        return ParsedOFX(
            accounts=accounts,
            transactions=txns,
            encoding_confidence=confidence,
        )

    @staticmethod
    def _map(external_ref: str, statement_currency: str, t: Any) -> BankTransaction:
        # `t` est un `ofxparse.Transaction` non typé (`Any`) : `t.amount` est un
        # `Decimal`, `t.date` un `datetime` ; `payee`/`memo`/`id` des `str` (defaults
        # `''`). `or ""` garde le cas `None` défensivement.
        return BankTransaction(
            external_ref=external_ref,
            date=t.date.date(),
            amount_cents=decimal_euros_to_cents(t.amount),
            currency=(str(statement_currency) or "EUR").upper(),  # str ISO brut (D7)
            payee=(t.payee or "").strip(),
            description=(t.memo or "").strip(),
            fitid=t.id,  # debug only (D8)
        )


async def parse_ofx(file_bytes: bytes) -> ParsedOFX:
    """Surface attendue par S12.4 (`banking.public.parse_ofx`)."""
    return await OFXProvider().parse(file_bytes)
