"""Public surface of the debts module — re-exports for cross-module use.

This module is the only one in `backend.modules.debts` that other modules may
import from (contract `2-debts`; `debts.{service,models,domain,...}` are listed
in peers' `forbidden_modules`). The re-exports below are all intra-module.

Exposes the share-request service entry points (`create_share_request`,
`revoke_share_request`) and their typed error taxonomy, so a caller — and the
route boundary (`debts.transports.http`) — can drive the act and map failures to
HTTP. The pure `DebtCalculator` family (`debts.domain`) is NOT re-exported here:
it is consumed only internally by the service; the boundary imports the
`DebtCalculationError` family from `debts.domain` directly (intra-module).

The S09.4 **read** surface (`list_debts_for_user`, `aggregate_by_counterparty`
and their DTOs `DebtWithContext`/`CounterpartyNet`/`DebtDirection`) is re-exported
too: the dashboard routes consume it via this surface, never `service.dashboard`
directly. All re-exports are intra-module (no new cross-module arc).

The S10.3 **remaining-balance** primitives (`compute_remaining`,
`list_open_debts_between` + the `OpenDebt` DTO + `DebtNotFoundError`) are
re-exported for reuse by `create_settlement` (S10.4) and E11 (overflow F10), per
the E10 roadmap note. The shared `_settled_subq` SQL helper stays PRIVATE (not
re-exported).
"""

from __future__ import annotations

from backend.modules.debts.service.dashboard import (
    CounterpartyNet,
    DebtDirection,
    DebtWithContext,
    aggregate_by_counterparty,
    list_debts_for_user,
)
from backend.modules.debts.service.remaining import (
    DebtNotFoundError,
    OpenDebt,
    compute_remaining,
    list_open_debts_between,
)
from backend.modules.debts.service.settlement import (
    CrossHouseholdError,
    LinkedTransactionNotAccessibleError,
    LinkedTransactionNotConfirmedError,
    LinkedTransactionNotTransferError,
    SettlementDebtNotAccessibleError,
    SettlementServiceError,
    create_settlement,
)
from backend.modules.debts.service.share_request import (
    DuplicateActiveShareRequestError,
    RequestedFromNotMemberError,
    SelfShareError,
    ShareRequestError,
    ShareRequestNotFoundError,
    SourceAccountNotShareableError,
    SourceTransactionNotConfirmedError,
    SourceTransactionNotFoundError,
    create_share_request,
    revoke_share_request,
)

__all__ = [
    "CounterpartyNet",
    "CrossHouseholdError",
    "DebtDirection",
    "DebtNotFoundError",
    "DebtWithContext",
    "DuplicateActiveShareRequestError",
    "LinkedTransactionNotAccessibleError",
    "LinkedTransactionNotConfirmedError",
    "LinkedTransactionNotTransferError",
    "OpenDebt",
    "RequestedFromNotMemberError",
    "SelfShareError",
    "SettlementDebtNotAccessibleError",
    "SettlementServiceError",
    "ShareRequestError",
    "ShareRequestNotFoundError",
    "SourceAccountNotShareableError",
    "SourceTransactionNotConfirmedError",
    "SourceTransactionNotFoundError",
    "aggregate_by_counterparty",
    "compute_remaining",
    "create_settlement",
    "create_share_request",
    "list_debts_for_user",
    "list_open_debts_between",
    "revoke_share_request",
]
