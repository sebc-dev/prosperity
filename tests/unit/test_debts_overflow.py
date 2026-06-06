"""Unit tests for `DebtCalculator.compute_for_overflow` (S11.2, P11.2.1 + P11.2.2).

Pure unit tier — no DB, no SQLAlchemy, no `Transaction`/`Budget`. Pins the F10
overflow projection : `compute_for_overflow` is the ONLY testable guardian of the
calculation (the `OverflowMember` value object is PERMISSIF — D4), so every guard
(`NonPositiveExpense`, `RatioOutOfBounds`) is exercised here.

Example tests (P11.2.1) cover the full F10 table (`force_no_debt` / `default` no
overflow / `default` overflow / `force_full_debt` / unbudgeted `default`), the
multi-member rounding omission, the orientation/self-debt invariants and the
guards with DETERMINISTIC inputs (robust under `ci=50`). Properties (P11.2.2)
live below in `TestComputeForOverflowProperties` (conservation, no-overflow→[],
`force_full_debt` equivalence, purity, ratio rejection).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import get_args
from uuid import UUID, uuid4

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from backend.modules.debts.domain import (
    Debt,
    DebtCalculationError,
    DebtCalculator,
    DebtGenerationOverride,
    NonPositiveExpenseError,
    OverflowMember,
    RatioOutOfBoundsError,
)
from backend.modules.transactions.domain import (
    DebtGenerationOverride as TxDebtGenerationOverride,
)
from backend.shared.money import Money
from tests.strategies import out_of_bounds_ratio, overflow_member_strategy, positive_money_eur

# Membres canoniques d'un compte commun (ids fixes : @example dans les properties
# les référencent à la décoration, et les tests example restent déterministes).
ALICE = uuid4()  # payeur/créancier par défaut
BOB = uuid4()
CAROL = uuid4()

# Singletons de défaut (Money est frozen) : évitent un appel en arg default (B008).
_DEFAULT_EXPENSE = Money(10000, "EUR")
_DEFAULT_REMAINING = Money(5000, "EUR")


def _member(user_id: UUID, ratio: str) -> OverflowMember:
    """Fabrique un `OverflowMember` (`share_ratio` en `Decimal`, jamais `float`)."""
    return OverflowMember(user_id=user_id, share_ratio=Decimal(ratio))


def _overflow(  # noqa: PLR0913 — façade keyword-only de la signature scalaire du calculator
    *,
    expense_total: Money = _DEFAULT_EXPENSE,
    budget_remaining_before: Money | None = _DEFAULT_REMAINING,
    members: Sequence[OverflowMember] | None = None,
    payer_user_id: UUID = ALICE,
    override: DebtGenerationOverride = "default",
    source_transaction_id: UUID | None = None,
    source_account_id: UUID | None = None,
) -> list[Debt]:
    """Appelle `compute_for_overflow` avec des défauts (payeur Alice, Alice/Bob 50-50)."""
    return DebtCalculator.compute_for_overflow(
        expense_total=expense_total,
        budget_remaining_before=budget_remaining_before,
        account_members=(
            members
            if members is not None
            else (_member(ALICE, "0.5"), _member(BOB, "0.5"))
        ),
        payer_user_id=payer_user_id,
        override=override,
        source_transaction_id=source_transaction_id or uuid4(),
        source_account_id=source_account_id or uuid4(),
    )


# ---------------------------------------------------------------------------
# P11.2.1 — `compute_for_overflow` (example, tableau F10)
# ---------------------------------------------------------------------------


class TestComputeForOverflow:
    """F10 : une dette par membre AUTRE que le payeur, sur la base à répartir,
    orientée membre→payeur, origine `shared_account_overflow`."""

    def test_default_no_overflow_returns_empty(self) -> None:
        # M=100€ ≤ R=150€ ⇒ E = max(0, M − R) = 0 ⇒ aucune dette.
        debts = _overflow(
            expense_total=Money(10000, "EUR"), budget_remaining_before=Money(15000, "EUR")
        )
        assert debts == []

    def test_default_overflow_splits_excess(self) -> None:
        # M=100€, R=50€ ⇒ E=50€ ; Bob (0.5) → 25€ vers Alice (payeur).
        debts = _overflow(
            expense_total=Money(10000, "EUR"), budget_remaining_before=Money(5000, "EUR")
        )
        assert len(debts) == 1
        debt = debts[0]
        assert debt.from_user_id == BOB  # débiteur
        assert debt.to_user_id == ALICE  # créancier/payeur
        assert debt.amount == Money(2500, "EUR")
        assert debt.origin == "shared_account_overflow"
        assert debt.share_ratio == Decimal("0.5")

    def test_force_full_debt_splits_total(self) -> None:
        # `force_full_debt` ⇒ base = montant total (100€), hors budget ; Bob → 50€.
        debts = _overflow(
            expense_total=Money(10000, "EUR"),
            budget_remaining_before=Money(5000, "EUR"),
            override="force_full_debt",
        )
        assert len(debts) == 1
        assert debts[0].amount == Money(5000, "EUR")
        assert debts[0].from_user_id == BOB

    def test_force_no_debt_returns_empty_even_in_overflow(self) -> None:
        # Dépassement franc (R=0) mais `force_no_debt` ⇒ le compte commun absorbe tout.
        debts = _overflow(
            expense_total=Money(10000, "EUR"),
            budget_remaining_before=Money(0, "EUR"),
            override="force_no_debt",
        )
        assert debts == []

    def test_default_unbudgeted_uses_full_total(self) -> None:
        # `budget_remaining_before is None` (dépense NON budgétisée) + `default` ⇒
        # base = montant total (décision S11.2). M=80€, Bob (0.5) → 40€.
        debts = _overflow(
            expense_total=Money(8000, "EUR"), budget_remaining_before=None, override="default"
        )
        assert len(debts) == 1
        assert debts[0].amount == Money(4000, "EUR")
        assert debts[0].from_user_id == BOB

    def test_three_unequal_members(self) -> None:
        # `default`-overflow E=90€ (M=140€, R=50€) ; payeur 0.5, B 0.3, C 0.2.
        members = (_member(ALICE, "0.5"), _member(BOB, "0.3"), _member(CAROL, "0.2"))
        debts = _overflow(
            expense_total=Money(14000, "EUR"),
            budget_remaining_before=Money(5000, "EUR"),
            members=members,
        )
        by_debtor = {d.from_user_id: d.amount for d in debts}
        assert by_debtor == {BOB: Money(2700, "EUR"), CAROL: Money(1800, "EUR")}
        assert ALICE not in by_debtor  # payeur exclu

    def test_degenerate_rounding_member_omitted(self) -> None:
        # base=1¢ (`force_full_debt`, M=1¢). Payeur 0.34, B 0.60 (→1¢), C 0.06 (→0¢).
        members = (_member(ALICE, "0.34"), _member(BOB, "0.60"), _member(CAROL, "0.06"))
        debts = _overflow(
            expense_total=Money(1, "EUR"),
            budget_remaining_before=None,
            members=members,
            override="force_full_debt",
        )
        # C dégénère à 0¢ ⇒ ligne OMISE (pas d'exception) ; B (1¢) présent.
        assert len(debts) == 1
        assert debts[0].from_user_id == BOB
        assert debts[0].amount == Money(1, "EUR")

    def test_default_overflow_base_equals_remaining_is_empty(self) -> None:
        # Frontière base == 0 exactement (M=R=100€), distincte de M < R.
        debts = _overflow(
            expense_total=Money(10000, "EUR"), budget_remaining_before=Money(10000, "EUR")
        )
        assert debts == []

    def test_single_debtor_full_ratio(self) -> None:
        # Mono-débiteur, ratio à la borne haute 1.0 ; overflow E=50€ ⇒ 50€.
        members = (_member(ALICE, "0.0001"), _member(BOB, "1"))
        debts = _overflow(
            expense_total=Money(10000, "EUR"),
            budget_remaining_before=Money(5000, "EUR"),
            members=members,
        )
        assert len(debts) == 1
        assert debts[0].from_user_id == BOB
        assert debts[0].amount == Money(5000, "EUR")

    def test_payer_absent_from_members_all_owe(self) -> None:
        # Payeur ∉ membres : le filtre `≠ payer` ne retire personne ⇒ tous doivent.
        # E=60€ (M=110€, R=50€), A 0.5 / B 0.5 ⇒ A→payeur 30€, B→payeur 30€.
        members = (_member(ALICE, "0.5"), _member(BOB, "0.5"))
        debts = _overflow(
            expense_total=Money(11000, "EUR"),
            budget_remaining_before=Money(5000, "EUR"),
            members=members,
            payer_user_id=CAROL,  # absent des membres
        )
        by_debtor = {d.from_user_id: d.amount for d in debts}
        assert by_debtor == {ALICE: Money(3000, "EUR"), BOB: Money(3000, "EUR")}
        assert all(d.to_user_id == CAROL for d in debts)

    def test_payer_never_self_debt(self) -> None:
        # Payeur parmi les membres : aucune dette `from == payer`, toutes → payeur.
        members = (_member(ALICE, "0.5"), _member(BOB, "0.3"), _member(CAROL, "0.2"))
        debts = _overflow(
            expense_total=Money(10000, "EUR"),
            budget_remaining_before=Money(2000, "EUR"),
            members=members,
        )
        assert all(d.from_user_id != ALICE for d in debts)
        assert all(d.from_user_id != d.to_user_id for d in debts)
        assert all(d.to_user_id == ALICE for d in debts)

    @pytest.mark.parametrize("amount_cents", [0, -500])
    def test_rejects_non_positive_expense(self, amount_cents: int) -> None:
        # `expense_total ≤ 0` validé EN PREMIER : erreur même sous `force_no_debt`.
        with pytest.raises(NonPositiveExpenseError) as exc:
            _overflow(expense_total=Money(amount_cents, "EUR"), override="force_no_debt")
        assert exc.value.code == "non_positive_expense"

    @pytest.mark.parametrize("ratio", ["1.5", "2.0", "0", "-0.5"])
    def test_rejects_ratio_out_of_bounds(self, ratio: str) -> None:
        # ⚠️ VERROU FINANCIER : `apply_ratio` n'a AUCUNE borne (money.py) ⇒ ce garde
        # est l'unique défense contre une dette `amount > base`. Ne jamais l'affaiblir.
        members = (_member(ALICE, "0.5"), _member(BOB, ratio))
        with pytest.raises(RatioOutOfBoundsError) as exc:
            _overflow(
                expense_total=Money(10000, "EUR"),
                budget_remaining_before=Money(5000, "EUR"),
                members=members,
            )
        assert exc.value.code == "ratio_out_of_bounds"

    def test_force_no_debt_skips_ratio_validation(self) -> None:
        # `force_no_debt` court-circuite AVANT la boucle ⇒ ratio aberrant non gardé.
        members = (_member(ALICE, "0.5"), _member(BOB, "9"))
        assert _overflow(members=members, override="force_no_debt") == []

    def test_origin_is_shared_account_overflow(self) -> None:
        members = (_member(ALICE, "0.5"), _member(BOB, "0.3"), _member(CAROL, "0.2"))
        debts = _overflow(
            expense_total=Money(10000, "EUR"),
            budget_remaining_before=Money(2000, "EUR"),
            members=members,
        )
        assert debts  # garde-fou : le cas produit bien des dettes
        assert all(d.origin == "shared_account_overflow" for d in debts)

    @pytest.mark.parametrize("trigger", ["non_positive_expense", "ratio_out_of_bounds"])
    def test_error_messages_carry_no_pii(self, trigger: str) -> None:
        # Messages STATIQUES : ni UUID (payeur/membre) ni montant interpolé. Couvre
        # les DEUX exceptions ; `RatioOutOfBoundsError` (UUID membres + base en scope)
        # est le chemin le plus à risque d'une future interpolation PII. Les montants
        # sont CHOISIS pour être réellement EN SCOPE au point de levée ⇒ les asserts
        # montant sont discriminants (non vacues) : `-5000` (expense) sur la garde
        # expense, `10000`/`5000` (total / remaining lus dans `base = total − remaining`)
        # sur le chemin générateur `default` qui atteint la garde ratio.
        exc_type: type[DebtCalculationError]
        if trigger == "non_positive_expense":
            members = (_member(ALICE, "0.5"), _member(BOB, "0.5"))
            kwargs = {
                "expense_total": Money(-5000, "EUR"),  # montant en scope au raise
                "budget_remaining_before": None,
                "override": "force_no_debt",
            }
            exc_type = NonPositiveExpenseError
        else:
            members = (_member(ALICE, "0.5"), _member(BOB, "5"))
            kwargs = {
                "expense_total": Money(10000, "EUR"),
                "budget_remaining_before": Money(5000, "EUR"),  # lu dans base = total − remaining
                "override": "default",  # base = 5000 > 0 ⇒ boucle ⇒ garde ratio atteinte
            }
            exc_type = RatioOutOfBoundsError
        with pytest.raises(exc_type) as exc:
            _overflow(members=members, **kwargs)  # type: ignore[arg-type]
        msg = str(exc.value)
        assert str(ALICE) not in msg
        assert str(BOB) not in msg
        assert "10000" not in msg and "5000" not in msg

    def test_guards_share_debt_calculation_base(self) -> None:
        # S11.3 mappe la famille via un seul `except DebtCalculationError`.
        for err in (NonPositiveExpenseError, RatioOutOfBoundsError):
            assert issubclass(err, DebtCalculationError)

    def test_override_set_parity(self) -> None:
        # Verrou anti-dérive du miroir local vs `transactions.domain` (hors
        # import-linter : le test importe les deux, pas le domaine pur).
        assert set(get_args(DebtGenerationOverride)) == set(get_args(TxDebtGenerationOverride))

    def test_overflow_member_is_permissive(self) -> None:
        # Aucun validator métier : un ratio aberrant construit SANS erreur (la garde
        # vit dans le calculator, unique gardien testable).
        member = OverflowMember(user_id=uuid4(), share_ratio=Decimal("5"))
        assert member.share_ratio == Decimal("5")


# ---------------------------------------------------------------------------
# P11.2.2 — properties (domaine pur, sans DB)
# ---------------------------------------------------------------------------


def _round_half_up(value: Decimal) -> int:
    """Arrondi commercial aux cents — MÊME politique que `Money.apply_ratio`."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TestComputeForOverflowProperties:
    """Properties Hypothesis sur la projection F10 PURE (aucune DB). Voir les
    réserves documentées par property : la conservation tolère un écart d'arrondi
    BORNÉ (pas de redistribution du reliquat en MVP, D-arrondi) ; idempotence est
    un oracle faible (garde anti-régression sur fonction pure)."""

    @given(data=overflow_member_strategy(), expense=positive_money_eur())
    @example(  # base minimale : zone d'arrondi (chaque membre près de 0)
        data=((_member(ALICE, "0.5"), _member(BOB, "0.5")), ALICE),
        expense=Money(1, "EUR"),
    )
    @example(  # mono-débiteur, ratio borne haute 1.0 (payeur exclu, ratio 0)
        data=((_member(ALICE, "0"), _member(BOB, "1")), ALICE),
        expense=Money(10000, "EUR"),
    )
    def test_property_conservation(
        self, data: tuple[tuple[OverflowMember, ...], UUID], expense: Money
    ) -> None:
        # `force_full_debt` ⇒ base = expense. `Σ debt.amount ≈ base × Σ_{m≠payer} r`
        # à `⌊(D+1)/2⌋` cents près (D = débiteurs AVANT omission ; l'arrondi par
        # membre ne se redistribue pas — décision MVP).
        members, payer = data
        debts = _overflow(
            expense_total=expense,
            budget_remaining_before=None,
            members=members,
            payer_user_id=payer,
            override="force_full_debt",
        )
        others = [m for m in members if m.user_id != payer]
        sum_others_ratio = sum((m.share_ratio for m in others), Decimal(0))
        expected = _round_half_up(Decimal(expense.amount_cents) * sum_others_ratio)
        actual = sum(d.amount.amount_cents for d in debts)
        assert abs(actual - expected) <= (len(others) + 1) // 2

    @given(
        data=overflow_member_strategy(),
        expense=positive_money_eur(),
        slack=st.integers(min_value=0, max_value=10**9),
    )
    def test_property_no_overflow_default_empty(
        self, data: tuple[tuple[OverflowMember, ...], UUID], expense: Money, slack: int
    ) -> None:
        # `default` + `budget_remaining_before ≥ expense_total` ⇒ base ≤ 0 ⇒ [].
        members, payer = data
        remaining = Money(expense.amount_cents + slack, "EUR")
        debts = _overflow(
            expense_total=expense,
            budget_remaining_before=remaining,
            members=members,
            payer_user_id=payer,
            override="default",
        )
        assert debts == []

    @given(
        data=overflow_member_strategy(),
        expense=positive_money_eur(),
        remaining=st.none() | positive_money_eur(),
    )
    def test_property_force_full_equals_unbudgeted_default(
        self,
        data: tuple[tuple[OverflowMember, ...], UUID],
        expense: Money,
        remaining: Money | None,
    ) -> None:
        # base = total des deux côtés ⇒ MÊME set. Tirage PARTAGÉ (mêmes ids source)
        # pour que seuls `override`/`remaining` diffèrent. `remaining` est tiré dans
        # `none() | positive_money_eur()` UNIQUEMENT pour prouver que `force_full_debt`
        # y est INSENSIBLE (il ignore `remaining`, y compris `None`).
        members, payer = data
        tx_id, acc_id = uuid4(), uuid4()
        full = _overflow(
            expense_total=expense,
            budget_remaining_before=remaining,
            members=members,
            payer_user_id=payer,
            override="force_full_debt",
            source_transaction_id=tx_id,
            source_account_id=acc_id,
        )
        unbudgeted = _overflow(
            expense_total=expense,
            budget_remaining_before=None,
            members=members,
            payer_user_id=payer,
            override="default",
            source_transaction_id=tx_id,
            source_account_id=acc_id,
        )
        assert set(full) == set(unbudgeted)

    @given(bad_ratio=out_of_bounds_ratio(), expense=positive_money_eur())
    def test_property_rejects_ratio_out_of_bounds(
        self, bad_ratio: Decimal, expense: Money
    ) -> None:
        # Parité gabarit S09.2 : un débiteur ratio ∉ (0,1] sur un chemin générateur
        # (base = expense > 0) ⇒ `RatioOutOfBoundsError`, tout le spectre hors borne.
        payer, debtor = ALICE, BOB
        members = (_member(payer, "0.5"), OverflowMember(user_id=debtor, share_ratio=bad_ratio))
        with pytest.raises(RatioOutOfBoundsError):
            _overflow(
                expense_total=expense,
                budget_remaining_before=None,
                members=members,
                payer_user_id=payer,
                override="force_full_debt",
            )

    @given(
        data=overflow_member_strategy(),
        expense=positive_money_eur(),
        override=st.sampled_from(["default", "force_full_debt", "force_no_debt"]),
    )
    def test_property_pure_idempotent(
        self,
        data: tuple[tuple[OverflowMember, ...], UUID],
        expense: Money,
        override: DebtGenerationOverride,
    ) -> None:
        # Deux appels identiques → résultat identique (projection pure ADR 0002).
        members, payer = data
        tx_id, acc_id = uuid4(), uuid4()
        kwargs = {
            "expense_total": expense,
            "budget_remaining_before": None,
            "members": members,
            "payer_user_id": payer,
            "override": override,
            "source_transaction_id": tx_id,
            "source_account_id": acc_id,
        }
        assert _overflow(**kwargs) == _overflow(**kwargs)  # type: ignore[arg-type]

    @given(data=overflow_member_strategy(), expense=positive_money_eur())
    def test_property_never_self_debt(
        self, data: tuple[tuple[OverflowMember, ...], UUID], expense: Money
    ) -> None:
        members, payer = data
        debts = _overflow(
            expense_total=expense,
            budget_remaining_before=None,
            members=members,
            payer_user_id=payer,
            override="force_full_debt",
        )
        assert all(d.from_user_id != d.to_user_id for d in debts)
        assert all(d.to_user_id == payer for d in debts)

    @given(data=overflow_member_strategy())
    def test_property_overflow_member_strategy_coherent(
        self, data: tuple[tuple[OverflowMember, ...], UUID]
    ) -> None:
        # Cohérence de la strategy : Σ ratio == 1 exact, tous > 0, payeur ∈ membres.
        members, payer = data
        assert sum((m.share_ratio for m in members), Decimal(0)) == Decimal("1.0000")
        assert all(m.share_ratio > 0 for m in members)
        assert payer in {m.user_id for m in members}
