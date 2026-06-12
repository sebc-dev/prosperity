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

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
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
                # Mapped[str] → LegRole (gabarit debt_generation_override) ;
                # valeur autoritative du SGBD, le mapper ne re-dérive pas.
                leg_role=s.leg_role,  # type: ignore[arg-type]
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


async def list_split_ids(session: AsyncSession, *, tx_id: UUID) -> set[UUID]:
    """Les `id` (générés serveur, `uuid4`) des splits de `tx_id` — set, sans ordre.

    Exposé pour le write upload handler (S13.6 / P13.6.2) : `domain.Split` est un
    value object SANS `id` (l'identité de l'agrégat est la `Transaction`), donc
    l'ack d'un `splits/insert` ne peut PAS lire l'id du split neuf depuis l'agrégat
    rendu par `add_split`. Le handler diffe `list_split_ids` avant/après l'ajout
    pour isoler l'id à reporter au client (`server_values`)."""
    return set(
        (
            await session.execute(
                select(SplitModel.id).where(SplitModel.transaction_id == tx_id)
            )
        )
        .scalars()
        .all()
    )


async def list_transactions(  # noqa: PLR0913 — flat, keyword-only filter surface
    session: AsyncSession,
    *,
    account_ids: set[UUID],
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    state: domain.TransactionState | None = None,
    after: tuple[dt.date, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[domain.Transaction], tuple[dt.date, UUID] | None]:
    """A page of transactions over `account_ids`, + the next cursor or `None` (D12).

    `account_ids` is the already-filtered accessible set (the route computes it via
    `accounts.public`); an empty set short-circuits to `([], None)` with no query.
    Ordered `(date DESC, id DESC)` — a total order (`id` UUID breaks `date` ties),
    both fields carried by `domain.Transaction` (no ORM leak). `LIMIT limit + 1`
    detects whether a next page exists; the keyset filter `(date, id) < after`
    keeps pagination stable under concurrent inserts. Splits are loaded in ONE
    grouped query (no N+1) and grouped in memory.
    """
    if not account_ids:
        return [], None
    stmt = select(TxModel).where(TxModel.account_id.in_(account_ids))
    if date_from is not None:
        stmt = stmt.where(TxModel.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(TxModel.date <= date_to)
    if state is not None:
        stmt = stmt.where(TxModel.state == state.value)
    if after is not None:
        stmt = stmt.where(tuple_(TxModel.date, TxModel.id) < after)
    stmt = stmt.order_by(TxModel.date.desc(), TxModel.id.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    page = rows[:limit]
    # The cursor is the LAST row of THIS page (not `rows[limit]`, the first row of
    # the next page): the keyset filter `(date, id) < after` is strict, so anchoring
    # on the first next-page row would skip it. `len(rows) > limit` ⇒ a next page exists.
    next_cursor = (page[-1].date, page[-1].id) if len(rows) > limit else None

    # Load every page split in ONE query, then group in memory (no N+1).
    page_ids = [tx.id for tx in page]
    splits_by_tx: dict[UUID, list[SplitModel]] = {}
    if page_ids:
        split_rows = (
            (
                await session.execute(
                    select(SplitModel)
                    .where(SplitModel.transaction_id.in_(page_ids))
                    .order_by(SplitModel.transaction_id, SplitModel.id)
                )
            )
            .scalars()
            .all()
        )
        for split in split_rows:
            splits_by_tx.setdefault(split.transaction_id, []).append(split)

    # `.get(tx.id, [])`: a listed `draft` may have zero split → no KeyError (→ 500).
    items = [_to_domain(tx, splits_by_tx.get(tx.id, [])) for tx in page]
    return items, next_cursor
