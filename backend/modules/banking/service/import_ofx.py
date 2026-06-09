"""Service d'analyse d'import OFX (S12.3.3) — preview + dedup, READ-ONLY.

`analyze_import` produit une `ImportPreview` à partir d'un `ParsedOFX` :
résout chaque réf de compte du fichier vers un compte interne
(`find_internal_account`), calcule le hash composite de chaque tx via
`compute_import_hash` (source UNIQUE du hash, réutilisée par le commit S12.4.3),
compte les doublons (lookup dans `imported_transactions`), évalue les 5 critères F04.

⚠️ N'ÉCRIT RIEN (D10) : aucun add/flush/commit ; la création de `Transaction`
+ l'insert `imported_transactions` sont au commit (S12.4, composition root).

⚠️ INV-S12.3-PREVIEW-ACCESS (D13) : `account_not_linked` et `duplicate_count`
sont calculés sur des `internal_account_id` BRUTS (résolus depuis un fichier
importé), NON filtrés par accessibilité. L'`ImportPreview` est donc un ORACLE
potentiel (existence d'un lien / d'une ligne sur un compte). L'appelant (route
S12.4) DOIT, avant exposition, refuser tout `external_ref` résolvant vers un
`internal_account_id ∉ accessible_account_ids(user_id)`, et rendre « lié-mais-
inaccessible » INDISTINGUABLE de « non-lié » (non-disclosure). Pendant exact de
l'INV-S12.1-ACCESS sur `find_internal_account`.

⚠️ Précondition de volume (D14) : la borne de taille (nb de tx / nb de comptes
distincts) est garantie par l'appelant (`MAX_OFX_BYTES` / cap `Content-Length`,
S12.2/S12.4). Le service fait un `find_internal_account` séquentiel par réf
distincte et itère sur N tx — il ne s'auto-borne pas (critère ⑤ est informatif).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.banking.domain import (
    AutoValidationCriteria,
    BankTransaction,
    ImportPreview,
    ParsedOFX,
)
from backend.modules.banking.models import ImportedTransaction
from backend.modules.banking.service.external_refs import find_internal_account
from backend.shared.bank_labels import import_hash, normalize_label

_AMOUNT_CAP_CENTS = 1_000_000  # 10 000 € (④)
_MAX_TX = 50  # ⑤ : strict <
_WINDOW_YEARS = 3  # ③ : ±3 ans


def _bank_label(tx: BankTransaction) -> str:
    return tx.description or tx.payee  # D8 (repli payee si description vide)


async def known_import_hashes(session: AsyncSession, hashes: Sequence[str]) -> set[str]:
    """Sous-ensemble de `hashes` déjà journalisés dans `imported_transactions`.

    SOURCE UNIQUE de la requête de dedup (S12.4 D9) : `analyze_import` (preview)
    ET le commit (composition root) l'appellent → un seul `SELECT ... IN` partagé.
    Court-circuite sur `hashes` vide (`IN ()` est invalide en SQL) → `set()`.
    Read-only ; ne dépend pas de l'accessibilité (INV-S12.3-PREVIEW-ACCESS : la
    route gate en amont).
    """
    if not hashes:  # ⚠️ IN () invalide — court-circuit avant la requête
        return set()
    rows = await session.execute(
        select(ImportedTransaction.import_hash).where(ImportedTransaction.import_hash.in_(hashes))
    )
    return set(rows.scalars())


async def record_imported(
    session: AsyncSession, *, account_id: UUID, import_hash: str, source: str = "ofx"
) -> None:
    """Journalise une ligne importée dans `imported_transactions` (idempotence).

    Primitive d'écriture triviale propriété de `banking` (le journal lui
    appartient, comme `link` possède `bank_account_external_refs`) : le composition
    root S12.4 l'appelle au lieu de toucher `banking.models`. Flush-only — pas de
    commit (`get_db` possède la frontière, ADR 0015). L'UNIQUE `import_hash` est le
    backstop d'idempotence (une vraie course → `IntegrityError` → rollback total).
    """
    session.add(ImportedTransaction(account_id=account_id, import_hash=import_hash, source=source))
    await session.flush()  # flush-only (ADR 0015) ; no commit


def compute_import_hash(internal_account_id: UUID, tx: BankTransaction) -> str:
    """Hash de dedup canonique d'une `BankTransaction` sur un compte INTERNE.

    SOURCE UNIQUE du hash (D8) : `analyze_import` (S12.3, lookup) ET le commit
    S12.4.3 (insert `imported_transactions`) l'appellent → l'invariant « deux
    lignes équivalentes → même hash » tient de bout en bout. Encapsule le choix
    du champ libellé (`description` sinon `payee`) + la normalisation ; verrouillé
    par le vecteur connu (P12.3.2) et un test cross-S12.4. Re-exportée par
    `banking.public` (réutilisable au composition root). FITID JAMAIS utilisé
    (doctrine F04).
    """
    return import_hash(
        internal_account_id, tx.date, tx.amount_cents, normalize_label(_bank_label(tx))
    )


def _shift_years(d: dt.date, years: int) -> dt.date:
    """Décale `d` de `years` ; clampe le 29 février → 28 si l'année cible n'est
    pas bissextile. Fonction pure testable unitairement."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 fév → année non bissextile
        return d.replace(year=d.year + years, day=28)


async def analyze_import(
    session: AsyncSession,
    parsed_ofx: ParsedOFX,
    *,
    provider: str = "ofx",
    reference_date: dt.date | None = None,
) -> ImportPreview:
    """Analyse un `ParsedOFX` → `ImportPreview` (read-only, F04). Cf. docstring module.

    ⚠️ N'écrit rien (D10). ⚠️ INV-S12.3-PREVIEW-ACCESS (D13) : la route DOIT
    gater l'accessibilité avant exposition. ⚠️ Volume borné par l'appelant (D14).
    """
    ref_date = reference_date or dt.date.today()
    txns = parsed_ofx.transactions

    # 1) Résolution external_ref → interne (par réf distincte). D5.
    ref_to_internal: dict[str, UUID | None] = {
        ref: await find_internal_account(session, external_ref=ref, provider=provider)
        for ref in parsed_ofx.accounts
    }
    account_not_linked = any(v is None for v in ref_to_internal.values())

    # 2) Hash par tx liée + lookup dedup (un seul SELECT, D11).
    #    compute_import_hash = source UNIQUE du hash, partagée avec le commit S12.4.3 (D8).
    hashes = [
        compute_import_hash(internal, tx)
        for tx in txns
        if (internal := ref_to_internal.get(tx.external_ref)) is not None
    ]
    known = await known_import_hashes(session, hashes)
    duplicate_count = sum(1 for h in hashes if h in known)

    # 3) Agrégats (sur TOUTES les tx du fichier — le non-lien n'affecte que le hashing).
    tx_count = len(txns)
    dates = [tx.date for tx in txns]
    amount_max_cents = max((abs(tx.amount_cents) for tx in txns), default=0)
    lower, upper = _shift_years(ref_date, -_WINDOW_YEARS), _shift_years(ref_date, _WINDOW_YEARS)

    # 4) Critères F04 (D6).
    criteria = AutoValidationCriteria(
        no_duplicates=duplicate_count == 0,
        encoding_high_confidence=parsed_ofx.encoding_confidence == "high",
        within_date_window=all(lower <= d <= upper for d in dates),
        amounts_within_cap=amount_max_cents <= _AMOUNT_CAP_CENTS,
        volume_under_limit=tx_count < _MAX_TX,
    )
    return ImportPreview(
        tx_count=tx_count,
        duplicate_count=duplicate_count,
        encoding_confidence=parsed_ofx.encoding_confidence,
        date_min=min(dates, default=None),
        date_max=max(dates, default=None),
        amount_max_cents=amount_max_cents,
        criteria=criteria,
        account_not_linked=account_not_linked,
    )
