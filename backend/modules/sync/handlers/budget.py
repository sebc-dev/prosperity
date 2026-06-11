"""Sous-handlers `categories` + `budgets` du write upload handler (S13.4 / P13.4.3).

Delta D5 : `Category` ET `Budget` vivent dans le module `budget` — un seul fichier
de handler couvre les deux tables (pas de module `categories`). Mappe `(op, payload)`
vers `budget.public` (ADR 0014). Flush-only (D-I).

Les éditions partielles passent par des allowlists FERMÉES (verrouillées par les
schémas Pydantic, `payloads.py`) : aucun champ hors `{name,color,icon}` (catégories)
/ `{amount_cents,carry_over_remainder}` (budgets) ne peut atteindre le `setattr`
aveugle des services `update_category`/`update_budget`.
"""

from __future__ import annotations

from typing import assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.budget.public import (
    archive_budget,
    archive_category,
    create_budget,
    create_category,
    move_category,
    update_budget,
    update_category,
)
from backend.modules.sync.handlers.payloads import (
    BudgetDeletePayload,
    BudgetInsertPayload,
    BudgetUpdatePayload,
    CategoryDeletePayload,
    CategoryInsertPayload,
    CategoryUpdatePayload,
)
from backend.modules.sync.schemas import Mutation, WriteResult


def _ack(mutation: Mutation) -> WriteResult:
    return WriteResult(client_request_id=mutation.client_request_id, success=True)


async def handle_category(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`categories/{insert,update,delete}` → `budget.public`. `update` route vers
    `move_category` si `parent_id` fourni (cycle rejeté par le service), sinon vers
    `update_category(fields allowlistés)`."""
    if mutation.op == "insert":
        ins = CategoryInsertPayload.model_validate(mutation.payload)
        await create_category(
            session, name=ins.name, color=ins.color, icon=ins.icon, parent_id=ins.parent_id
        )
    elif mutation.op == "update":
        upd = CategoryUpdatePayload.model_validate(mutation.payload)
        if upd.has_parent_change():  # re-parentage (cycle → CategoryCycleError, propage)
            await move_category(session, category_id=upd.id, new_parent_id=upd.parent_id)
        else:
            await update_category(session, category_id=upd.id, fields=upd.editable_fields())
    elif mutation.op == "delete":
        dele = CategoryDeletePayload.model_validate(mutation.payload)
        await archive_category(session, category_id=dele.id)
    else:  # pragma: no cover — op ∉ enum impossible (Pydantic `MutationOp`, D-O)
        assert_never(mutation.op)
    return _ack(mutation)


async def handle_budget(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`budgets/{insert,update,delete}` → `budget.public`. `created_by`/`user_id`
    forcés `user.id` (jamais lus du payload)."""
    if mutation.op == "insert":
        ins = BudgetInsertPayload.model_validate(mutation.payload)
        await create_budget(
            session,
            category_id=ins.category_id,
            period_kind=ins.period_kind,
            period_start=ins.period_start,
            amount_cents=ins.amount_cents,
            scope=ins.scope,
            carry_over_remainder=ins.carry_over_remainder,
            contributor_ids=ins.contributor_ids,
            created_by=user.id,
        )
    elif mutation.op == "update":
        upd = BudgetUpdatePayload.model_validate(mutation.payload)
        await update_budget(
            session,
            budget_id=upd.id,
            user_id=user.id,
            fields=upd.editable_fields(),
            contributor_ids=upd.contributor_ids,
        )
    elif mutation.op == "delete":
        dele = BudgetDeletePayload.model_validate(mutation.payload)
        await archive_budget(session, budget_id=dele.id, user_id=user.id)
    else:  # pragma: no cover — op ∉ enum impossible (Pydantic `MutationOp`, D-O)
        assert_never(mutation.op)
    return _ack(mutation)
