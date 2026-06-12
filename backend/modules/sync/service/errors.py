"""Mapping exception domaine → `WriteError` typé (ADR 0014, étape 10 / P13.6.3).

`to_write_error` est la SOURCE UNIQUE de la table de correspondance : une exception
domaine CONNUE → un `WriteError` au code fermé (`WriteErrorCode`) ; une exception
INCONNUE → `None`, que le dispatcher traduit en re-raise → 500 (retry PowerSync,
D-H). On distingue ainsi l'erreur récupérable (le client purge la mutation et
poursuit) de l'erreur serveur (retry).

`sync` est au sommet du graphe (ADR 0005) : il importe les TYPES d'exception via les
`public.py` des modules métier (jamais leurs `*.domain`, contrat import-linter). On
réutilise les `.code` (`ClassVar`) des familles `transactions` qui sont DÉJÀ dans le
vocabulaire fermé (pas de duplication de chaîne) ; on collapse les familles de
validation des autres modules en `validation_error` ; les `*NotFoundError` en
`not_found` (uniforme, anti-oracle). `message` est STATIQUE par code — jamais
`str(exc)`/SQL/PII (review Sécu F2).
"""

from __future__ import annotations

from typing import cast

from backend.modules.accounts.public import AccountValidationError
from backend.modules.budget.public import BudgetError, CategoryError
from backend.modules.debts.public import (
    DebtCalculationError,
    DebtNotFoundError,
    SettlementServiceError,
    SettlementValidationError,
    ShareRequestError,
    ShareRequestNotFoundError,
)
from backend.modules.sync.schemas import WriteError, WriteErrorCode
from backend.modules.transactions.public import (
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    SplitNotFoundError,
    TransactionError,
    TransactionNotFoundError,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
)

# Message wire STATIQUE, partagé : la granularité exploitable vit dans `code`, jamais
# dans `message` (qui ne doit fuiter aucun détail interne — review Sécu F2).
_REJECTED = "The mutation was rejected."


def to_write_error(exc: Exception) -> WriteError | None:
    """Mappe une exception domaine CONNUE → `WriteError` typé ; `None` si inconnue.

    Ordre du `match` : du PLUS SPÉCIFIQUE au plus général (les `*NotFoundError` sont
    des sous-classes de leur base — ex. `TransactionNotFoundError(TransactionError)` —
    donc captés AVANT la branche base). `None` ⇒ erreur serveur → 500 (D-H).
    """
    match exc:
        case (
            TransactionNotFoundError()
            | SplitNotFoundError()
            | ShareRequestNotFoundError()
            | DebtNotFoundError()
        ):
            code: WriteErrorCode = "not_found"
        case (
            ImmutableFieldViolation()
            | InvalidStateTransitionError()
            | UnbalancedTransactionError()
            | UncategorizedExpenseError()
        ):
            # `.code` (ClassVar) est DÉJÀ dans le vocabulaire fermé — pas de duplication.
            code = cast("WriteErrorCode", exc.code)
        case (
            TransactionError()  # base + `MultipleFundingLegsError` → validation générique
            | AccountValidationError()
            | CategoryError()
            | BudgetError()
            | ShareRequestError()
            | SettlementValidationError()
            | SettlementServiceError()
            | DebtCalculationError()
        ):
            code = "validation_error"
        case _:
            return None  # inconnue → re-raise → 500 (retry PowerSync)
    return WriteError(code=code, message=_REJECTED)
