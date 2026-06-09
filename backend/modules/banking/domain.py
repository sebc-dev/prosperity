"""Contrat de données commun OFX / Enable Banking + taxonomie d'erreurs provider.

`domain.py` héberge le **contrat de données pur** (aucun ORM, aucun import
`backend.modules.*`) partagé par le parser OFX (S12.2) et le futur
`EnableBankingProvider` : le modèle `BankTransaction`, le résultat `ParsedOFX`,
l'alias `EncodingConfidence`, le helper de conversion `decimal_euros_to_cents`,
et la **hiérarchie d'exceptions `BankingProviderError`** (1ʳᵉ définition projet).

La séparation contrat-de-données (`domain.py`) / mécanique-OFX
(`providers/ofx.py`) suit le gabarit `transactions.{models,service}` : `public.py`
re-exporte librement le domaine (intra-module, sans exception import-linter) ;
seul `OFXProvider`/`parse_ofx` traverse `providers` (contrat import-linter 4).

⚠️ **Delta ADR 0009 (issue #177)** : `OFXProvider` est un parser fichier statique,
PAS une implémentation du Protocol pull-only `BankingProvider`. OFX et Enable
Banking ne partagent que `BankTransaction` et la base `BankingProviderError` ;
les erreurs réseau/consentement (`ConsentExpiredError`, `RateLimitedError`, …)
arriveront avec Enable Banking, pas ici.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

EncodingConfidence = Literal["high", "low"]
"""Confiance de la détection d'encoding. `low` (fallback cp1252) imposera la
preview obligatoire au boundary métier (critère F04, S12.3) — ici on ne produit
que le signal, dérivé des octets seuls (non contournable par un en-tête falsifié)."""


class BankTransaction(BaseModel):
    """Ligne bancaire normalisée — modèle COMMUN OFX / Enable Banking.

    `amount_cents` : centimes entiers (ADR 0008 — JAMAIS float/Decimal stocké ;
    un débit donne un montant négatif). `currency` : code ISO brut (`str`, PAS le
    `Literal` `Currency`) — un OFX peut porter un code hors `{EUR,USD,GBP,CHF}` ;
    la validation vs `household.base_currency` vit au boundary qui crée la
    `Transaction` (S12.4), pas dans le parser. `fitid` : conservé pour debug
    UNIQUEMENT, JAMAIS utilisé pour la dedup (FITID instable côté ASPSP FR — la
    dedup est un hash composite en S12.3, doctrine F04 / D8).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    external_ref: str  # compte du fichier (account.number)
    date: dt.date
    amount_cents: int
    currency: str
    payee: str
    description: str
    fitid: str | None = None  # debug only — jamais dans le hash de dedup


@dataclass(frozen=True, slots=True)
class ParsedOFX:
    """Résultat d'un parse OFX : comptes distincts, transactions, confiance encoding."""

    accounts: tuple[str, ...]  # external_refs distincts présents dans le fichier
    transactions: tuple[BankTransaction, ...]
    encoding_confidence: EncodingConfidence


class AutoValidationCriteria(BaseModel):
    """Les 5 critères F04 d'auto-validation (TOUS requis).

    Détail exposé pour que la preview puisse mettre en évidence le(s) critère(s)
    en échec. `all_met` est l'invariant central de la story (`auto_validatable`
    en dérive) ; verrouillé par un test exhaustif sur les 32 combinaisons.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    no_duplicates: bool  # ① aucun doublon (hash déjà connu)
    encoding_high_confidence: bool  # ② encoding_confidence == "high"
    within_date_window: bool  # ③ toutes les tx dans ±3 ans
    amounts_within_cap: bool  # ④ |montant| ≤ 10 000 €
    volume_under_limit: bool  # ⑤ < 50 tx

    @property
    def all_met(self) -> bool:
        return (
            self.no_duplicates
            and self.encoding_high_confidence
            and self.within_date_window
            and self.amounts_within_cap
            and self.volume_under_limit
        )


class ImportPreview(BaseModel):
    """Résultat read-only d'`analyze_import` (F04 preview hybride conditionnel).

    ⚠️ INV-S12.3-PREVIEW-ACCESS : `account_not_linked` et `duplicate_count` sont
    calculés sur des comptes internes BRUTS (résolus depuis un fichier importé),
    NON filtrés par accessibilité. Cet objet est donc un ORACLE potentiel ; la
    route S12.4 DOIT gater chaque `external_ref` sur `accessible_account_ids(
    user_id)` avant exposition et rendre « lié-inaccessible » indistinguable de
    « non-lié ». Cf. docstring `analyze_import` / `banking.public`.

    `auto_validatable` est INFORMATIF : la décision finale (auto-commit vs
    preview) appartient à la route/au client (F04) — `analyze_import` expose les
    critères, il ne décide pas. `account_not_linked` est ⊥ aux 5 critères.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    tx_count: int
    duplicate_count: int
    encoding_confidence: EncodingConfidence
    date_min: dt.date | None  # None si 0 tx
    date_max: dt.date | None
    amount_max_cents: int  # max(|amount_cents|), 0 si vide
    criteria: AutoValidationCriteria
    account_not_linked: bool  # ⊥ aux 5 critères ; la route → 422 si True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auto_validatable(self) -> bool:
        return self.criteria.all_met


def decimal_euros_to_cents(amount: Decimal) -> int:
    """`Decimal('-12.34') → -1234`. `ROUND_HALF_UP`, jamais de `float` (ADR 0008).

    Politique cents centralisée : multiplie par 100 puis quantize à l'entier en
    arrondi commercial (`Decimal('-0.005') → -1`, `Decimal('0.005') → 1`).
    """
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class BankingProviderError(Exception):
    """Base commune des erreurs provider banking (ADR 0009 ; 1ʳᵉ définition projet).

    Le boundary S12.4 catche d'un seul `except BankingProviderError` — aucune
    exception native `ofxparse`/`OSError` ne doit jamais fuiter au-delà du parser.
    """


class IncompatibleAccountError(BankingProviderError):
    """Fichier OFX illisible / incompatible / trop volumineux.

    Mappe `ofxparse.OfxParserException` et tout autre échec du bloc parsing, plus
    le dépassement de `MAX_OFX_BYTES` (garde DoS, D12).
    """


class ProviderUnavailableError(BankingProviderError):
    """Source inaccessible / lecture impossible (← `OSError`).

    Mapping défensif (taxonomie pull-provider ADR 0009) : non atteint sur le
    chemin purement mémoire du parser OFX (`io.StringIO`), mais exigé par l'AC
    #177 et testé via monkeypatch (D10).
    """


class EncodingDetectionError(BankingProviderError):
    """Octets OFX non décodables même en fallback cp1252.

    Extension propre à OFX (D6) — cohérente avec ADR 0009 (qui ne l'exclut pas) :
    le parser décode lui-même les octets avant de passer le texte à `ofxparse`.
    """
