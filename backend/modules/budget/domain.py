"""Pure domain for the budget module (no SQLAlchemy / session / FastAPI).

`CycleDetector` decides whether re-parenting a category would close a cycle
in the unbounded tree (CONTEXT.md §Catégorie « Cycle prevention : validation
au service »). It is **pure**: the service injects `get_parent`, a callable
mapping a node to its parent — in production a closure over a parent chain
pre-loaded by one `WITH RECURSIVE` query; in tests a plain `dict.get`. The
domain never touches the DB (gabarit `accounts.domain.AccountValidator`,
which receives `household_base_currency` instead of importing the ORM).

Internal to `modules.budget`: cross-module callers reach domain values
through `backend.modules.budget.public` (empty in S06.2 — no consumer yet).
Import-linter contract `2-budget` forbids reaching into this module from
peer modules; it imports only the stdlib, so it creates no cross-module arc.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CategoryError(Exception):
    """Base of every pure category-rule violation (S06.2).

    Stays in `domain.py` (stdlib-only) so the service can map the whole
    family with one `except CategoryError` at the S06.3 boundary while
    `domain.py` imports nothing but the stdlib.
    """


class CategoryCycleError(CategoryError):
    """Re-parenting would close a cycle (direct self-ref or descendant loop)."""


class CategoryNotFoundError(CategoryError):
    """Target category does not exist (used by `move_category`, S06.2).

    Co-located with the family even though it reports a *DB-absence* state
    (not a pure rule violation) — acceptable for a single S06.3 route
    mapping; the class itself imports nothing, keeping `domain.py` stdlib-only.
    """


class CategoryInUseError(CategoryError):
    """Hard-delete refused: the category is still referenced (S06.3, D8).

    Raised by `delete_category` when the node has ≥ 1 non-archived
    sub-category, or when the self-FK `RESTRICT` trips on an archived child
    at flush (the DB-level twin is stricter than the service count, so the
    service catches the 23503 and re-raises it here for a uniform contract).
    In E07 the counter extends to `splits.category_id`.

    Co-located with the family — like `CategoryNotFoundError`, it reports a
    DB-state condition (not a pure rule violation), so the S06.3 boundary
    maps the whole family with one `except CategoryError` while `domain.py`
    stays stdlib-only.
    """


class CycleDetector:
    """Pure acyclicity guard for category re-parenting (CONTEXT.md §Catégorie).

    `detect_cycle` raises `CategoryCycleError` iff setting `node_id`'s parent
    to `new_parent_id` would create a cycle:
      - `new_parent_id is None` (root) → always OK;
      - `new_parent_id == node_id`   → direct self-reference → cycle;
      - walking ancestors of `new_parent_id` reaches `node_id` → `node_id` is
        an ancestor of the new parent, i.e. we'd hang the new parent's subtree
        (which contains `node_id`) under `node_id` → cycle.

    Termination is unconditional: the `visited` set bounds the walk to at
    most N distinct steps even on an already-corrupted tree (acceptance
    criterion #5). No integer bound constant — it would be a dead branch
    behind `visited` and sink branch coverage.
    """

    @staticmethod
    def detect_cycle(
        *,
        node_id: UUID,
        new_parent_id: UUID | None,
        get_parent: Callable[[UUID], UUID | None],
    ) -> None:
        if new_parent_id is None:
            return  # re-parent to root: never a cycle
        if new_parent_id == node_id:
            raise CategoryCycleError(f"category {node_id} cannot be its own parent")

        # Order matters: test `== node_id` *before* the visited-guard, so a
        # legitimate cycle whose node sits inside a corrupted loop is still
        # reported instead of silently broken out of.
        visited: set[UUID] = set()
        current: UUID | None = new_parent_id
        while current is not None:
            if current == node_id:
                raise CategoryCycleError(
                    f"category {node_id} is an ancestor of {new_parent_id}: "
                    "moving it under its own descendant would create a cycle"
                )
            if current in visited:
                break  # corrupted-tree guard: terminate, never loop
            visited.add(current)
            current = get_parent(current)


# --- Budget consumption (S08.2) --------------------------------------------
#
# The aggregation core of E08: how much of a budget has been spent over the
# period window containing `as_of`. `BudgetConsumption` and the period-window
# arithmetic are pure (no SQLAlchemy / session / clock); the SUM over the
# category subtree, the contributor filter and the `force_full_debt` exclusion
# live at the service (`budget.service.consumption`, CONTEXT.md §Budget « les
# budgets agrègent à la lecture, pas à l'écriture »).

PeriodKind = Literal["monthly", "quarterly", "yearly"]

# Number of calendar months spanned by one window of each kind. Used to step
# the window anchor forward/backward in `compute_period_window`.
_MONTHS_PER_PERIOD: Final[dict[str, int]] = {"monthly": 1, "quarterly": 3, "yearly": 12}


class BudgetConsumption(BaseModel):
    """Consommation d'un budget sur une fenêtre de période (CONTEXT.md §Budget).

    `consumed_cents` = SUM des legs « catégorie » (forme canonique E15) des
    splits comptés ; positif pour une dépense, réduit par un remboursement.
    `remaining_cents = amount_cents − consumed_cents` (négatif en dépassement).
    `percent` = ratio Decimal `consumed/amount` (`0.80` = 80 %), non arrondi —
    le formatage `×100`/`%` est une décision d'affichage (S08.4).
    `splits_count` = nombre de splits comptés (drill-down UI S08.4.3).

    Pas de champ `currency` : mono-devise V1 (ADR 0008) — `remaining` impose
    déjà l'unicité de devise. `frozen=True, strict=True` : valeur immuable, pas
    de coercition implicite (gabarit domaine pur).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    consumed_cents: int
    remaining_cents: int
    percent: Decimal
    splits_count: int


def consumption_from_totals(
    *, consumed_cents: int, amount_cents: int, splits_count: int
) -> BudgetConsumption:
    """Factory pure : dérive `remaining`/`percent` des totaux (testable sans DB).

    `percent = consumed/amount` (ratio Decimal non arrondi). `amount_cents <= 0`
    → `percent = Decimal("0")` (garde-fou anti `ZeroDivisionError` ; un budget
    bien formé a `amount > 0`, garanti au boundary S08.4). `remaining` peut être
    négatif (dépassement).
    """
    percent = Decimal(consumed_cents) / Decimal(amount_cents) if amount_cents > 0 else Decimal("0")
    return BudgetConsumption(
        consumed_cents=consumed_cents,
        remaining_cents=amount_cents - consumed_cents,
        percent=percent,
        splits_count=splits_count,
    )


def _add_months(anchor: date, months: int) -> date:
    """`anchor` décalé de `months`, jour **clampé** à la longueur du mois cible.

    Ancre le 31 → fév : 28/29 (clamp). `months` peut être négatif (recul). La
    séquence `k ↦ _add_months(anchor, k·step)` est monotone non décroissante en
    `k`, propriété sur laquelle s'appuie la recherche de fenêtre de
    `compute_period_window`.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last_day = monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def compute_period_window(
    period_kind: PeriodKind, period_start: date, as_of: date
) -> tuple[date, date]:
    """Fenêtre `[start, end)` du genre `period_kind` contenant `as_of`, ancrée
    sur `period_start`.

    Pure (aucune session/DB/horloge). `period_start` est l'**ancre** récurrente
    (S08.1) : un mensuel ancré le 15 ouvre `[15, 15 du mois suivant)`. On
    avance/recule par pas de `_MONTHS_PER_PERIOD[period_kind]` mois jusqu'à
    encadrer `as_of`.

    Invariants (property Hypothesis P08.2.1) : `start ≤ as_of < end` ; fenêtres
    adjacentes contiguës (`window(as_of).end == window(end).start`) et
    disjointes ; idempotence (tout `as_of'` dans `[start, end)` → même fenêtre).

    La recherche linéaire est bornée par l'écart `as_of − period_start` (quelques
    périodes pour des budgets posés à l'usage, V1) ; un calcul `O(1)` (division
    entière de l'écart en mois) la remplacerait si un `as_of` lointain devenait
    réel — YAGNI ici (note roadmap).
    """
    step = _MONTHS_PER_PERIOD[period_kind]
    k = 0
    if as_of >= period_start:
        # Avance tant que la borne haute de la fenêtre k reste ≤ as_of.
        while _add_months(period_start, (k + 1) * step) <= as_of:
            k += 1
    else:
        # Recule tant que la borne basse de la fenêtre k dépasse as_of.
        while _add_months(period_start, k * step) > as_of:
            k -= 1
    start = _add_months(period_start, k * step)
    end = _add_months(period_start, (k + 1) * step)
    return start, end
