"""Unit tests for `backend.modules.debts.domain` (S09.2, P09.2.1 + P09.2.2).

Pure unit tier — no DB, no SQLAlchemy, no `Transaction`. Pins the pure debts
domain : the `Debt`/`ShareRequestData` value objects (mirror of the SQLA models
of S09.1, but in `Money` — D3/D4) and `DebtCalculator.compute_for_share_request`
(the only testable guardian of the calculation, D4/D5).

Example tests (P09.2.1) cover the happy path (ratio 1.0 / 0.5 / non-trivial
rounding) and the four guards (`NonPositiveExpense`, `RatioOutOfBounds`,
`SelfDebt`, `NonPositiveDebtAmount`) with DETERMINISTIC inputs (robust under
`ci=50`). Properties (P09.2.2) live below in `TestDebtCalculatorProperties`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.modules.debts.domain import (
    Debt,
    DebtCalculationError,
    DebtCalculator,
    NonPositiveDebtAmountError,
    NonPositiveExpenseError,
    RatioOutOfBoundsError,
    SelfDebtError,
    ShareRequestData,
)
from backend.shared.money import Money
from tests.strategies import out_of_bounds_ratio, personal_share_ratio, positive_money_eur


def _share_request(
    *,
    requested_by: UUID | None = None,
    requested_from: UUID | None = None,
    ratio: Decimal = Decimal("1.0"),
    source_transaction_id: UUID | None = None,
    short_label: str = "Courses",
) -> ShareRequestData:
    """Fabrique une `ShareRequestData` valide ; ids distincts par défaut."""
    return ShareRequestData(
        source_transaction_id=source_transaction_id or uuid4(),
        requested_by=requested_by or uuid4(),
        requested_from=requested_from or uuid4(),
        ratio=ratio,
        short_label=short_label,
    )


# ---------------------------------------------------------------------------
# P09.2.1 — `DebtCalculator.compute_for_share_request` (example)
# ---------------------------------------------------------------------------


class TestComputeForShareRequest:
    """Le calculator : `requested_from` doit `expense_total × ratio` à
    `requested_by`, orientation débiteur→créancier, origine fixée."""

    def test_ratio_one_full_amount(self) -> None:
        creditor, debtor, tx_id, account_id = uuid4(), uuid4(), uuid4(), uuid4()
        sr = _share_request(
            requested_by=creditor,
            requested_from=debtor,
            ratio=Decimal("1.0"),
            source_transaction_id=tx_id,
        )

        debts = DebtCalculator.compute_for_share_request(
            share_request=sr,
            expense_total=Money(1000, "EUR"),
            source_account_id=account_id,
        )

        assert len(debts) == 1
        debt = debts[0]
        assert debt.from_user_id == debtor  # débiteur
        assert debt.to_user_id == creditor  # créancier
        assert debt.amount == Money(1000, "EUR")
        assert debt.origin == "personal_share_request"
        assert debt.share_ratio == Decimal("1.0")
        assert debt.account_id == account_id
        assert debt.source_transaction_id == tx_id

    def test_ratio_half(self) -> None:
        debts = DebtCalculator.compute_for_share_request(
            share_request=_share_request(ratio=Decimal("0.5")),
            expense_total=Money(1000, "EUR"),
            source_account_id=uuid4(),
        )
        assert debts[0].amount == Money(500, "EUR")

    def test_non_trivial_rounding(self) -> None:
        # 333 × 0.5 = 166,5 → 167 (ROUND_HALF_UP via `Money.apply_ratio`).
        debts = DebtCalculator.compute_for_share_request(
            share_request=_share_request(ratio=Decimal("0.5")),
            expense_total=Money(333, "EUR"),
            source_account_id=uuid4(),
        )
        assert debts[0].amount == Money(167, "EUR")

    def test_returns_single_debt(self) -> None:
        debts = DebtCalculator.compute_for_share_request(
            share_request=_share_request(ratio=Decimal("0.5")),
            expense_total=Money(1000, "EUR"),
            source_account_id=uuid4(),
        )
        assert len(debts) == 1

    @pytest.mark.parametrize("amount_cents", [0, -500])
    def test_rejects_non_positive_expense(self, amount_cents: int) -> None:
        with pytest.raises(NonPositiveExpenseError) as exc:
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=Decimal("0.5")),
                expense_total=Money(amount_cents, "EUR"),
                source_account_id=uuid4(),
            )
        assert exc.value.code == "non_positive_expense"

    @pytest.mark.parametrize("ratio", ["1.5", "2.0", "0", "-0.5"])
    def test_rejects_ratio_out_of_bounds(self, ratio: str) -> None:
        # Garde fail-safe `0 < r ≤ 1` (D5b) : la DB n'a AUCUN CHECK sur
        # `share_ratio` ⇒ un ratio > 1 produirait une dette aberrante.
        with pytest.raises(RatioOutOfBoundsError) as exc:
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=Decimal(ratio)),
                expense_total=Money(1000, "EUR"),
                source_account_id=uuid4(),
            )
        assert exc.value.code == "ratio_out_of_bounds"

    def test_rejects_self_debt(self) -> None:
        same = uuid4()
        with pytest.raises(SelfDebtError) as exc:
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(
                    requested_by=same, requested_from=same, ratio=Decimal("0.5")
                ),
                expense_total=Money(1000, "EUR"),
                source_account_id=uuid4(),
            )
        assert exc.value.code == "self_debt"

    def test_rejects_share_rounding_to_zero(self) -> None:
        # Ratio VALIDE (0,4 ∈ (0, 1]) mais expense trop petite : 1¢ × 0.4 = 0,4 → 0.
        # Distinct du garde borne ratio (D5a vs D5b).
        with pytest.raises(NonPositiveDebtAmountError) as exc:
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=Decimal("0.4")),
                expense_total=Money(1, "EUR"),
                source_account_id=uuid4(),
            )
        assert exc.value.code == "non_positive_debt_amount"

    def test_guards_share_a_common_base(self) -> None:
        # S09.3 mappe toute la famille via un seul `except DebtCalculationError`.
        for err in (
            NonPositiveExpenseError,
            RatioOutOfBoundsError,
            SelfDebtError,
            NonPositiveDebtAmountError,
        ):
            assert issubclass(err, DebtCalculationError)

    def test_error_messages_carry_no_pii(self) -> None:
        # Messages sans UUID/montant/libellé (canal client = `code`, jamais str(exc)).
        debtor_id = uuid4()
        with pytest.raises(NonPositiveExpenseError) as exc:
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(requested_from=debtor_id, ratio=Decimal("0.5")),
                expense_total=Money(0, "EUR"),
                source_account_id=uuid4(),
            )
        assert str(debtor_id) not in str(exc.value)


# ---------------------------------------------------------------------------
# P09.2.1 — `Debt` value object mirrors the SQLA CHECKs (example)
# ---------------------------------------------------------------------------


def _valid_debt_kwargs() -> dict[str, object]:
    return {
        "from_user_id": uuid4(),
        "to_user_id": uuid4(),
        "amount": Money(1000, "EUR"),
        "account_id": uuid4(),
        "source_transaction_id": uuid4(),
        "origin": "personal_share_request",
        "share_ratio": Decimal("1.0"),
    }


class TestDebtMirror:
    """`Debt` reproduit les 2 CHECK SQL (`amount > 0`, `from != to`) + le set
    fermé `origin` au boundary Pydantic (D3/D7)."""

    def test_valid_debt_constructs(self) -> None:
        assert Debt(**_valid_debt_kwargs()).amount == Money(1000, "EUR")  # type: ignore[arg-type]

    def test_zero_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Debt(**{**_valid_debt_kwargs(), "amount": Money(0, "EUR")})  # type: ignore[arg-type]

    def test_negative_amount_rejected(self) -> None:
        # Le CHECK SQL est `> 0` : le miroir refuse le négatif AUTANT que le zéro
        # (seul moyen d'exercer l'intention, `compute_*` ne produit pas de négatif).
        with pytest.raises(ValidationError):
            Debt(**{**_valid_debt_kwargs(), "amount": Money(-5, "EUR")})  # type: ignore[arg-type]

    def test_self_debt_rejected(self) -> None:
        same = uuid4()
        with pytest.raises(ValidationError):
            Debt(**{**_valid_debt_kwargs(), "from_user_id": same, "to_user_id": same})  # type: ignore[arg-type]

    def test_unknown_origin_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Debt(**{**_valid_debt_kwargs(), "origin": "bogus"})  # type: ignore[arg-type]

    def test_strict_rejects_coercion(self) -> None:
        # strict=True : un `share_ratio` str au lieu de `Decimal` est refusé
        # (pas de coercition implicite, gabarit `Money`/`Transaction`).
        with pytest.raises(ValidationError):
            Debt(**{**_valid_debt_kwargs(), "share_ratio": "1.0"})  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        debt = Debt(**_valid_debt_kwargs())  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            debt.amount = Money(1, "EUR")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# P09.2.2 — properties (domaine pur, sans DB)
# ---------------------------------------------------------------------------


def _oriented(debt: Debt, *, positive_when_from: UUID) -> int:
    """Montant ORIENTÉ relatif à une paire fixe : `+cents` si le débiteur est
    `positive_when_from`, `−cents` sinon. Outil de la property d'antisymétrie."""
    sign = 1 if debt.from_user_id == positive_when_from else -1
    return sign * debt.amount.amount_cents


class TestDebtCalculatorProperties:
    """Properties Hypothesis sur le domaine PUR (aucune DB). Voir les réserves
    documentées par property : déterminisme/idempotence sont des gardes
    anti-régression (oracle faible sur fonction pure) ; l'antisymétrie est un
    PROXY MVP de `debt(A→B) == −debt(B→A)` (l'invariant matriciel zero-sum
    complet est déféré à S09.5)."""

    @given(ratio=personal_share_ratio(), expense=positive_money_eur())
    def test_property_deterministic(self, ratio: Decimal, expense: Money) -> None:
        # ⚠️ Oracle FAIBLE par construction (fonction pure, aucune source de
        # non-déterminisme). Valeur réelle = garde anti-régression si `compute`
        # se complexifie en E11 (overflow → tri/dédup à ordre instable).
        sr = _share_request(ratio=ratio)
        account_id = uuid4()
        try:
            a = DebtCalculator.compute_for_share_request(
                share_request=sr, expense_total=expense, source_account_id=account_id
            )
        except NonPositiveDebtAmountError:
            return  # zone d'arrondi→0 (cf. test_property_rounding_to_zero_raises)
        b = DebtCalculator.compute_for_share_request(
            share_request=sr, expense_total=expense, source_account_id=account_id
        )
        assert a == b

    @given(ratio=personal_share_ratio(), expense=positive_money_eur())
    def test_property_idempotent_set(self, ratio: Decimal, expense: Money) -> None:
        # ⚠️ Même réserve : ce n'est PAS la ré-application sur le résultat ; la
        # vraie idempotence ADR 0002/§83 (re-projeter en DB → même set) est en
        # S09.3/S09.5. Garde anti-régression.
        sr = _share_request(ratio=ratio)
        account_id = uuid4()
        try:
            first = DebtCalculator.compute_for_share_request(
                share_request=sr, expense_total=expense, source_account_id=account_id
            )
        except NonPositiveDebtAmountError:
            return  # zone d'arrondi→0
        second = DebtCalculator.compute_for_share_request(
            share_request=sr, expense_total=expense, source_account_id=account_id
        )
        assert set(first) == set(second)

    @given(ratio=personal_share_ratio(), amount_cents=st.integers(min_value=100, max_value=10**9))
    @example(ratio=Decimal("0.0001"), amount_cents=10_000)  # ratio →0⁺
    @example(ratio=Decimal("1.0000"), amount_cents=10_000)  # ratio =1 (borne haute)
    def test_property_antisymmetry(self, ratio: Decimal, amount_cents: int) -> None:
        # ⚠️ PROXY MVP de `debt(A→B) == −debt(B→A)` (§82) : ratio identique des
        # deux côtés ⇒ prouve surtout l'indépendance du montant vis-à-vis de la
        # direction (1 dette). L'invariant matriciel zero-sum complet est en S09.5.
        a, b = uuid4(), uuid4()
        tx_id, account_id = uuid4(), uuid4()
        expense = Money(amount_cents, "EUR")
        try:
            forward = DebtCalculator.compute_for_share_request(
                share_request=_share_request(
                    requested_from=a, requested_by=b, ratio=ratio, source_transaction_id=tx_id
                ),
                expense_total=expense,
                source_account_id=account_id,
            )
        except NonPositiveDebtAmountError:
            return  # zone d'arrondi→0 : symétrique des deux côtés, pas un trou
        backward = DebtCalculator.compute_for_share_request(
            share_request=_share_request(
                requested_from=b, requested_by=a, ratio=ratio, source_transaction_id=tx_id
            ),
            expense_total=expense,
            source_account_id=account_id,
        )
        assert _oriented(forward[0], positive_when_from=a) == -_oriented(
            backward[0], positive_when_from=a
        )

    @given(ratio=personal_share_ratio(), amount_cents=st.integers(min_value=100, max_value=10**9))
    @example(ratio=Decimal("1.0000"), amount_cents=10_000)  # borne haute : amount == expense
    def test_property_amount_bounds(self, ratio: Decimal, amount_cents: int) -> None:
        # Pour `0 < r ≤ 1` et un expense assez grand pour que l'arrondi reste > 0
        # (`amount_cents ≥ 100`, `ratio ≥ 0.0001` ⇒ ≥ 0.01¢… on borne le bas via
        # le garde du calculator, ci-dessous) : `0 < amount ≤ expense_total`.
        expense = Money(amount_cents, "EUR")
        try:
            debts = DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=ratio),
                expense_total=expense,
                source_account_id=uuid4(),
            )
        except NonPositiveDebtAmountError:
            # Zone d'arrondi→0 : couverte par `test_property_rounding_to_zero_raises`,
            # pas un trou ici.
            return
        amount = debts[0].amount
        assert amount.amount_cents > 0
        assert amount <= expense

    @given(ratio=personal_share_ratio(), expense=positive_money_eur())
    def test_property_never_self_debt(self, ratio: Decimal, expense: Money) -> None:
        sr = _share_request(ratio=ratio)
        try:
            debts = DebtCalculator.compute_for_share_request(
                share_request=sr, expense_total=expense, source_account_id=uuid4()
            )
        except NonPositiveDebtAmountError:
            return
        assert debts[0].from_user_id != debts[0].to_user_id

    @given(ratio=st.sampled_from([Decimal("0.0001"), Decimal("0.2"), Decimal("0.4")]))
    def test_property_rounding_to_zero_raises(self, ratio: Decimal) -> None:
        # `expense_total = 1¢`, ratio ≤ 0.4 (valide) ⇒ arrondi → 0 ⇒ garde D5a.
        with pytest.raises(NonPositiveDebtAmountError):
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=ratio),
                expense_total=Money(1, "EUR"),
                source_account_id=uuid4(),
            )

    @given(ratio=out_of_bounds_ratio(), expense=positive_money_eur())
    def test_property_rejects_ratio_out_of_bounds(self, ratio: Decimal, expense: Money) -> None:
        # Fail-safe sur TOUTE la borne (≤ 0 ou > 1), pas seulement sous ratio valide.
        with pytest.raises(RatioOutOfBoundsError):
            DebtCalculator.compute_for_share_request(
                share_request=_share_request(ratio=ratio),
                expense_total=expense,
                source_account_id=uuid4(),
            )
