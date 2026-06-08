"""Service de mapping compte externe → compte interne (S12.1.2).

`find_internal_account` (lecture) et `link` (écriture flush-only) matérialisent
le mapping persistant `BankAccountExternalRef` (CONTEXT.md §Import OFX). Service
métier **ordinaire** : transaction-agnostic, **flush-only — jamais de commit**
(la frontière est `get_db`, ADR 0015). La dérogation commit-inside-service
d'ADR 0015 ne s'applique PAS (le critère « le client ne doit pas pouvoir défaire
l'effet de bord en provoquant l'exception » n'est pas rempli).

`link` ne crée **aucun compte** (AC #176) : la FK `internal_account_id →
accounts` garantit l'existence du compte. Le contrôle d'accessibilité du compte
interne est au boundary route (S12.4.2), hors scope ici.

Interne au module banking ; les consommateurs cross-module passent par
`banking.public`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.banking.models import BankAccountExternalRef

# Set OUVERT validé au boundary service (D1/D7) : 'ofx' en V1, 'enable_banking'
# plus tard (la colonne reste text, pas d'ENUM DB). Élargir cette frozenset au
# moment où Enable Banking arrive.
_VALID_PROVIDERS: frozenset[str] = frozenset({"ofx"})


class ExternalRefError(Exception):
    """Base des erreurs du service de mapping (taxonomie locale S12.1).

    PII-safe : la valeur sensible (`external_ref` = numéro de compte masqué) est
    portée par un **attribut nommé**, jamais interpolée dans le message par
    défaut — ainsi un `str(exc)` loggué par un handler/Sentry ne fuite pas la
    PII. Le boundary S12.4 NE DOIT PAS réfléchir `external_ref` dans la réponse
    HTTP.
    """


class UnknownProviderError(ExternalRefError):
    """`provider` hors du set autorisé V1 (D1)."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__("unknown provider")  # valeur en attribut, pas dans le message


class AccountAlreadyLinkedError(ExternalRefError):
    """`(external_ref, provider)` est déjà lié (D6) — rejet déterministe avant
    le backstop UNIQUE DB."""

    def __init__(self, external_ref: str, provider: str) -> None:
        # PII (numéro masqué) en attributs nommés, message générique.
        self.external_ref = external_ref
        self.provider = provider
        super().__init__("account already linked")


async def find_internal_account(
    session: AsyncSession, *, external_ref: str, provider: str
) -> UUID | None:
    """Compte interne lié à `(external_ref, provider)`, ou `None` si inconnu.

    Sélectionne uniquement `internal_account_id` (jamais la ligne ORM). `None`
    quand aucun mapping n'existe — le boundary import (S12.3/S12.4) en déduit
    « compte non lié » → 422 typé `account_not_linked`.

    ⚠️ INV-S12.1-ACCESS (D9) : l'`internal_account_id` retourné est BRUT et
    contexte-agnostique. Le boundary route (S12.4.2) DOIT le filtrer par
    `accessible_account_ids(user_id)` avant tout usage — `external_ref` provient
    d'un fichier importé, donc un id non filtré fuirait un compte non autorisé.
    """
    if provider not in _VALID_PROVIDERS:
        raise UnknownProviderError(provider)
    stmt = select(BankAccountExternalRef.internal_account_id).where(
        BankAccountExternalRef.external_ref == external_ref,
        BankAccountExternalRef.provider == provider,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def link(
    session: AsyncSession,
    *,
    external_ref: str,
    internal_account_id: UUID,
    provider: str,
) -> BankAccountExternalRef:
    """Lie `(external_ref, provider)` à un compte interne **existant**.

    Valide `provider` (D1), refuse un double-lien (D6 : pré-check + UNIQUE DB en
    backstop), INSERT + flush (PK surfacée ; pas de commit — `get_db` possède la
    frontière, ADR 0015). Ne crée aucun compte (la FK garantit l'existence ;
    sinon `IntegrityError` → rollback `get_db`).

    ⚠️ INV-S12.1-ACCESS (D9) : ne vérifie PAS l'accessibilité du
    `internal_account_id` (service contexte-agnostique) — le boundary route
    S12.4.2 doit refuser un compte interne inaccessible avant d'appeler `link`.

    Concurrence (D6) : sous `REPEATABLE READ` (engine global), le perdant d'une
    vraie course sur l'UNIQUE prend un `SerializationFailure` SQLSTATE `40001`
    (remonté en `DBAPIError`) → 500 **délibéré, pas un bug** (TOCTOU acceptable,
    foyer unique, précédent `invitations.py`/`share_request.py`) ; le chemin
    séquentiel lève le typé `AccountAlreadyLinkedError` avant tout `flush` (aucune
    transaction empoisonnée). Un futur test NE DOIT PAS attendre l'erreur typée
    sur le chemin concurrent.
    """
    if provider not in _VALID_PROVIDERS:
        raise UnknownProviderError(provider)
    existing = await find_internal_account(session, external_ref=external_ref, provider=provider)
    if existing is not None:
        raise AccountAlreadyLinkedError(external_ref, provider)
    ref = BankAccountExternalRef(
        external_ref=external_ref,
        internal_account_id=internal_account_id,
        provider=provider,
    )
    session.add(ref)
    await session.flush()  # surface PK ; no commit (get_db owns it, ADR 0015)
    return ref
