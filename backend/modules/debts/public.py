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
"""

from __future__ import annotations

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
    "DuplicateActiveShareRequestError",
    "RequestedFromNotMemberError",
    "SelfShareError",
    "ShareRequestError",
    "ShareRequestNotFoundError",
    "SourceAccountNotShareableError",
    "SourceTransactionNotConfirmedError",
    "SourceTransactionNotFoundError",
    "create_share_request",
    "revoke_share_request",
]
