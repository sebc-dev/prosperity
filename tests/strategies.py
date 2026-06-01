"""Stratégies Hypothesis partagées pour les tests property-based (S05.5).

`account_with_members_strategy` génère des comptes **valides** (S05.2) selon
deux axes ORTHOGONAUX :

  - la **forme** (`shape`) : ``"personal"`` (owner, 0 membre) | ``"shared"``
    (owner=None, ≥ 2 membres, quote-parts ``Decimal`` Σ=1 exact) — c'est elle
    que `AccountValidator` lit (via ``owner_id`` / ``members``) ;
  - la **catégorie** (`account_type` ∈ `AccountType`) : courant / livret / … —
    DÉCORATIVE, jamais lue par le validator.

Devise EUR (ADR 0008). La strategy est pensée pour être réutilisée par les
épics aval (E08 budgets adossés aux comptes, E09 dettes via quote-parts) —
d'où sa signature paramétrable plutôt qu'un cas figé.

`share_ratios(n, total)` — le générateur de partition en « points de base »
entiers, exact à l'échelle 4 (jamais de ``float``) — est ré-exporté pour les
consommateurs qui veulent juste des quote-parts, et pour le test de rejet
Σ≠1 (`total != 10000`).

Pur et sans effet de bord : importable depuis n'importe quel test.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import hypothesis.strategies as st

from backend.modules.accounts.domain import AccountType, MemberShare

# Numeric(5, 4) → échelle 4 ⇒ 10000 « points de base » pour 1.0000 exact.
_BASIS_POINTS: int = 10_000
_MIN_MEMBERS: int = 2

Shape = Literal["personal", "shared"]


@dataclass(frozen=True, slots=True)
class GeneratedAccount:
    """Un compte valide généré par `account_with_members_strategy`.

    `type` (catégorie financière) est DÉCORATIF : `AccountValidator` ne le lit
    jamais. La forme perso/commun se lit sur ``owner_id`` / ``members`` :
    ``owner_id`` set ⇔ personnel (``members == []``) ; ``owner_id is None`` ⇔
    commun (``len(members) >= 2``).
    """

    type: AccountType
    currency: str  # toujours "EUR" en V1 (ADR 0008)
    owner_id: UUID | None  # set ⇔ personnel ; None ⇔ commun
    members: list[MemberShare]  # [] ⇔ personnel ; ≥ 2 ⇔ commun


@st.composite
def share_ratios(draw: st.DrawFn, *, n: int, total: int = _BASIS_POINTS) -> list[Decimal]:
    """N ratios `Decimal` strictement positifs, Σ == ``Decimal(total) / 10000``.

    Partitionne ``total`` en N parts entières ≥ 1 (cut-points distincts, requiert
    ``total >= n``), puis mappe chaque part ``p`` → ``Decimal(p) / Decimal(10000)``.
    Exact à l'échelle 4, jamais de ``float`` ; chaque part ≥ 1 ⇒ ratio > 0.

    ``total == 10000`` (défaut) ⇒ Σ == ``Decimal("1.0000")`` ; ``total != 10000``
    ⇒ Σ != 1 (alimente le test de rejet Σ≠1, S05.5 D3). Généralise le composite
    inline `_members_summing_to` de `test_accounts_validator.py`.
    """
    cuts = sorted(
        draw(
            st.lists(
                st.integers(min_value=1, max_value=total - 1),
                min_size=n - 1,
                max_size=n - 1,
                unique=True,
            )
        )
    )
    bounds = [0, *cuts, total]
    return [Decimal(bounds[i + 1] - bounds[i]) / Decimal(_BASIS_POINTS) for i in range(n)]


@st.composite
def account_with_members_strategy(  # noqa: PLR0913  # paramétrable par conception (réutilisé E08/E09)
    draw: st.DrawFn,
    *,
    shape: Shape | None = None,
    account_type: AccountType | None = None,
    n_members: int | None = None,
    user_ids: list[UUID] | None = None,
    max_members: int = 6,
) -> GeneratedAccount:
    """Génère un compte **valide**. Forme et catégorie sont deux axes séparés.

    - `shape` impose la forme ; ``None`` ⇒ ``"shared"`` si ``n_members`` /
      ``user_ids`` sont fournis, sinon tirée dans ``{"personal", "shared"}``.
    - `account_type` impose la catégorie (décorative, jamais lue par le
      validator) ; ``None`` ⇒ tirée librement dans `AccountType`.
    - `n_members` / `max_members` bornent la cardinalité d'un commun lorsque
      ``user_ids`` n'est pas fourni.
    - `user_ids` (optionnel) ancre les membres sur un pool d'`User` réels
      (FK ``RESTRICT``) — utilisé par la propriété DB de re-balance (P05.5.2).
    """
    acc_type = (
        account_type if account_type is not None else draw(st.sampled_from(list(AccountType)))
    )
    if shape is None:
        shape = (
            "shared"
            if (n_members is not None or user_ids is not None)
            else draw(st.sampled_from(["personal", "shared"]))
        )

    if shape == "personal":
        owner = user_ids[0] if user_ids else draw(st.uuids())
        return GeneratedAccount(type=acc_type, currency="EUR", owner_id=owner, members=[])

    # shape == "shared"
    if user_ids is not None:
        ids, n = user_ids, len(user_ids)
    else:
        n = n_members if n_members is not None else draw(st.integers(_MIN_MEMBERS, max_members))
        ids = [uuid4() for _ in range(n)]
    ratios = draw(share_ratios(n=n))  # total=10000 ⇒ Σ=1 exact
    members = [MemberShare(user_id=ids[i], ratio=ratios[i]) for i in range(n)]
    return GeneratedAccount(type=acc_type, currency="EUR", owner_id=None, members=members)
