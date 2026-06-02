"""Read model for the transactions module (S07.5).

The lifecycle service (S07.4) is mutation-only; reads are a distinct
responsibility, so they live here rather than in `lifecycle.py`. `get_transaction`
loads one aggregate (or `None`), `list_transactions` (P07.5.4) returns a
cursor-paginated page. Both rebuild the pure `domain.Transaction` via the
**validating** constructor (`_to_domain`), so a row that drifted out of an
invariant in the DB raises on read (defense-in-depth, gabarit `lifecycle._to_domain`).

The mapper is re-implemented here rather than imported from `lifecycle` (D11):
that keeps it module-internal and avoids a `queries → lifecycle` coupling on a
private symbol (a shared `_mapper.py` would be over-engineering for two readers —
to reconsider if a third appears).

`get_transaction` returns `None` (not an exception) for an unknown id so the
route boundary can collapse "unknown" and "inaccessible" into one uniform 404
(non-disclosure, F03/D4) — no tx-id enumeration oracle.

Internal to the transactions module; cross-module callers go through
`backend.modules.transactions.public`. No cross-module import (the household
membership filter is applied at the route boundary, S07.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.shared.money import Money


def _to_domain(tx: TxModel, splits: Sequence[SplitModel]) -> domain.Transaction:
    """Build the domain aggregate via the VALIDATING constructor (D11).

    Loading through the constructor (not `model_construct`) re-checks the
    invariant on read — a `confirmed` row that became unbalanced in the DB raises
    here, the wanted defense-in-depth signal. Mirrors `lifecycle._to_domain` (kept
    a separate copy on purpose, D11: no `queries → lifecycle` private coupling).
    """
    return domain.Transaction(
        id=tx.id,
        account_id=tx.account_id,
        date=tx.date,
        state=domain.TransactionState(tx.state),
        payee=tx.payee,
        created_by=tx.created_by,
        splits=tuple(
            domain.Split(
                account_id=s.account_id,
                category_id=s.category_id,
                amount=Money(s.amount_cents, s.currency),  # type: ignore[arg-type]
            )
            for s in splits
        ),
        category_id=tx.category_id,
        description=tx.description,
        tags=tuple(tx.tags),
        debt_generation_override=tx.debt_generation_override,  # type: ignore[arg-type]
        share_request_id=tx.share_request_id,
    )


async def get_transaction(session: AsyncSession, *, tx_id: UUID) -> domain.Transaction | None:
    """Load the aggregate for `tx_id`, or `None` if it does not exist (D11).

    `None` (not `TransactionNotFoundError`) lets the route boundary merge
    unknown + inaccessible into a single uniform 404 (D4). Splits are ordered by
    `id` for a deterministic aggregate shape (gabarit `lifecycle._load_aggregate`).
    """
    tx = await session.get(TxModel, tx_id)
    if tx is None:
        return None
    splits = (
        (
            await session.execute(
                select(SplitModel).where(SplitModel.transaction_id == tx_id).order_by(SplitModel.id)
            )
        )
        .scalars()
        .all()
    )
    return _to_domain(tx, list(splits))
