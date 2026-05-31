"""Domain events published by the accounts module (S05.4).

Concrete event types live **here**, not in `backend.shared.events`: import-linter
contract #3 forbids `shared` from knowing `modules.*`, so `shared` only owns the
`DomainEvent` base. `accounts` sits above `shared` in the layer graph and may
subclass it. The types are re-exported via `accounts.public` as a surface
discipline (ADR 0005) for the first real subscriber — `notifications` (the
canonical mini-bus consumer) and/or `budget` (E08, which reacts to quote-parts).

These events are published **synchronously, inside the request transaction**
(see `service.members`): in V1 there is no subscriber, so `publish` is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from backend.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class AccountMemberAdded(DomainEvent):
    """A member was added to a shared account (its quote-part is `share_ratio`)."""

    account_id: UUID
    user_id: UUID
    share_ratio: Decimal


@dataclass(frozen=True, slots=True)
class AccountMemberRemoved(DomainEvent):
    """A member was removed from a shared account."""

    account_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class ShareRatioUpdated(DomainEvent):
    """The focal member's quote-part changed from `old_ratio` to `new_ratio`.

    ⚠️ On a re-balance the **co-members'** ratios change too but are **not**
    evented separately in V1 (D8). A subscriber (budget E08) must therefore not
    rely on this focal delta alone — it should **re-read the full roster** via
    `account_id` to recompute on up-to-date quote-parts.
    """

    account_id: UUID
    user_id: UUID
    old_ratio: Decimal
    new_ratio: Decimal
