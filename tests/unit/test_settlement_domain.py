"""Unit tests for `backend.modules.debts.domain.SettlementValidator` (S10.2).

Pure unit tier — no DB, no SQLAlchemy, no `Transaction`. Pins the pure settlement
validator : the scalar value objects (`DebtContext`, `SettlementLineInput`,
`ValidatedSettlement`) and `SettlementValidator.validate` (the only testable
guardian of the 8 invariants, ADR 0011).

Example tests cover one happy path per `type` (internal/external with
`net == linked`, virtual with `net == 0`) plus one negative per rule (1)…(8),
edge cases, and one Hypothesis property (D4 net invariant under line permutation).

⚠️ UUID littéraux FIXES et ORDONNÉS (`A < B < C` par `u.int`) — pas `uuid4()` :
le déterminisme du net (D4) dépend du tri `u.int`, donc les tests contrôlent
l'ordre `lo/hi` pour exercer LES DEUX branches de signe (`A→B` et `B→A`).
`distinct_uuid_pair` (S09.5) est réservé aux properties Hypothesis de S10.5.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.modules.debts.domain import (
    ClosedDebtError,
    DebtContext,
    EmptySettlementError,
    LinkedTransactionMismatchError,
    MixedCurrencyError,
    MultipleCounterpartiesError,
    NetTransferMismatchError,
    OverSettlementError,
    SettlementLineInput,
    SettlementValidationError,
    SettlementValidator,
    UnknownDebtLineError,
    ValidatedSettlement,
)
from backend.shared.currency import Currency

# UUID fixes et ordonnés : A < B < C par valeur entière (contrôle du tri D4).
A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)


def _ctx(
    *,
    debt_id: UUID,
    from_user_id: UUID = A,
    to_user_id: UUID = B,
    currency: Currency = "EUR",
    remaining_cents: int = 100,
) -> DebtContext:
    """Fabrique un `DebtContext` valide ; dette A→B EUR remaining 100 par défaut."""
    return DebtContext(
        debt_id=debt_id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        currency=currency,
        remaining_cents=remaining_cents,
    )


def _line(*, debt_id: UUID, amount_cents: int) -> SettlementLineInput:
    """Fabrique une `SettlementLineInput`."""
    return SettlementLineInput(debt_id=debt_id, amount_cents=amount_cents)


# ---------------------------------------------------------------------------
# Sentinelles PII : un `debt_id` (424242) et un montant (999999) distinctifs,
# injectés dans CHAQUE scénario d'erreur (cf. `test_error_messages_carry_no_pii`).
# Un thunk par sous-classe déclenche son erreur via `validate`, en respectant
# l'ordre des règles pour que l'erreur CIBLE soit la première levée.
# ---------------------------------------------------------------------------
_PII_DEBT = UUID(int=424242)
_PII_D2 = UUID(int=424243)
_PII_AMOUNT = 999999


def _raise_empty() -> None:  # (1)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[],
        debt_contexts={},
        linked_transaction_amount_cents=None,
    )


def _raise_unknown() -> None:  # (2)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[_line(debt_id=_PII_DEBT, amount_cents=_PII_AMOUNT)],
        debt_contexts={},
        linked_transaction_amount_cents=None,
    )


def _raise_mixed_currency() -> None:  # (3)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[
            _line(debt_id=_PII_DEBT, amount_cents=_PII_AMOUNT),
            _line(debt_id=_PII_D2, amount_cents=_PII_AMOUNT),
        ],
        debt_contexts={
            _PII_DEBT: _ctx(debt_id=_PII_DEBT, currency="EUR", remaining_cents=_PII_AMOUNT),
            _PII_D2: _ctx(debt_id=_PII_D2, currency="USD", remaining_cents=_PII_AMOUNT),
        },
        linked_transaction_amount_cents=None,
    )


def _raise_multiple_parties() -> None:  # (4)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[
            _line(debt_id=_PII_DEBT, amount_cents=_PII_AMOUNT),
            _line(debt_id=_PII_D2, amount_cents=_PII_AMOUNT),
        ],
        debt_contexts={
            _PII_DEBT: _ctx(
                debt_id=_PII_DEBT, from_user_id=A, to_user_id=B, remaining_cents=_PII_AMOUNT
            ),
            _PII_D2: _ctx(
                debt_id=_PII_D2, from_user_id=A, to_user_id=C, remaining_cents=_PII_AMOUNT
            ),
        },
        linked_transaction_amount_cents=None,
    )


def _raise_linked_mismatch() -> None:  # (5)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[_line(debt_id=_PII_DEBT, amount_cents=50)],
        debt_contexts={_PII_DEBT: _ctx(debt_id=_PII_DEBT)},
        linked_transaction_amount_cents=_PII_AMOUNT,
    )


def _raise_closed_debt() -> None:  # (6)
    SettlementValidator.validate(
        settlement_type="virtual",
        lines=[_line(debt_id=_PII_DEBT, amount_cents=_PII_AMOUNT)],
        debt_contexts={_PII_DEBT: _ctx(debt_id=_PII_DEBT, remaining_cents=0)},
        linked_transaction_amount_cents=None,
    )


def _raise_over_settlement() -> None:  # (7)
    SettlementValidator.validate(
        settlement_type="internal_transfer",
        lines=[_line(debt_id=_PII_DEBT, amount_cents=_PII_AMOUNT)],
        debt_contexts={_PII_DEBT: _ctx(debt_id=_PII_DEBT, remaining_cents=100)},
        linked_transaction_amount_cents=_PII_AMOUNT,
    )


def _raise_net_mismatch() -> None:  # (8)
    SettlementValidator.validate(
        settlement_type="internal_transfer",
        lines=[_line(debt_id=_PII_DEBT, amount_cents=100)],
        debt_contexts={_PII_DEBT: _ctx(debt_id=_PII_DEBT, remaining_cents=100)},
        linked_transaction_amount_cents=_PII_AMOUNT,
    )


# ---------------------------------------------------------------------------
# Happy path — un positif par `type` + nettage
# ---------------------------------------------------------------------------


class TestSettlementValidatorHappyPath:
    """`validate` accepte un règlement valide et retourne un `ValidatedSettlement`
    normalisé (lignes, net tracé, contreparties, devise)."""

    def test_internal_transfer_single_debt(self) -> None:
        d = UUID(int=10)
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[_line(debt_id=d, amount_cents=100)],
            debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
            linked_transaction_amount_cents=100,
        )
        assert result.net_transfer_cents == 100
        assert result.counterparties == frozenset({A, B})
        assert result.currency == "EUR"
        assert result.type == "internal_transfer"
        assert result.lines == (_line(debt_id=d, amount_cents=100),)

    def test_external_transfer_partial(self) -> None:
        # `internal`/`external` traités à l'identique côté domaine pur (D3/note issue).
        d = UUID(int=10)
        result = SettlementValidator.validate(
            settlement_type="external_transfer",
            lines=[_line(debt_id=d, amount_cents=60)],
            debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
            linked_transaction_amount_cents=60,
        )
        assert result.net_transfer_cents == 60
        assert result.type == "external_transfer"

    def test_virtual_symmetric_netting(self) -> None:
        # 2 dettes opposées A→B 50 et B→A 50 ⇒ net == 0 (nettage croisé symétrique).
        d1, d2 = UUID(int=10), UUID(int=11)
        result = SettlementValidator.validate(
            settlement_type="virtual",
            lines=[
                _line(debt_id=d1, amount_cents=50),
                _line(debt_id=d2, amount_cents=50),
            ],
            debt_contexts={
                d1: _ctx(debt_id=d1, from_user_id=A, to_user_id=B, remaining_cents=50),
                d2: _ctx(debt_id=d2, from_user_id=B, to_user_id=A, remaining_cents=50),
            },
            linked_transaction_amount_cents=None,
        )
        assert result.net_transfer_cents == 0
        assert result.type == "virtual"

    def test_net_is_direction_canonical(self) -> None:
        # Prouve que la branche `sign=+1` (dette A→B = lo→hi) ET `sign=-1`
        # (dette B→A = hi→lo) sont exercées et donnent le même `abs(net)`, et que
        # permuter l'ordre d'arrivée des lignes ne change pas le résultat (D4).
        d_fwd, d_bwd = UUID(int=10), UUID(int=11)
        contexts = {
            d_fwd: _ctx(debt_id=d_fwd, from_user_id=A, to_user_id=B, remaining_cents=70),
            d_bwd: _ctx(debt_id=d_bwd, from_user_id=B, to_user_id=A, remaining_cents=20),
        }
        # net = +70 (A→B) − 20 (B→A) = 50.
        forward_order = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[
                _line(debt_id=d_fwd, amount_cents=70),
                _line(debt_id=d_bwd, amount_cents=20),
            ],
            debt_contexts=contexts,
            linked_transaction_amount_cents=50,
        )
        reversed_order = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[
                _line(debt_id=d_bwd, amount_cents=20),
                _line(debt_id=d_fwd, amount_cents=70),
            ],
            debt_contexts=contexts,
            linked_transaction_amount_cents=50,
        )
        assert forward_order.net_transfer_cents == 50
        assert reversed_order.net_transfer_cents == 50

    def test_multiple_lines_same_debt_within_remaining(self) -> None:
        # 2 lignes 40 + 40 sur la MÊME dette remaining 100 ⇒ OK (chemin nominal de
        # la boucle d'agrégation `per_debt`, pendant positif du rejet sommé (7b)).
        d = UUID(int=10)
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[
                _line(debt_id=d, amount_cents=40),
                _line(debt_id=d, amount_cents=40),
            ],
            debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
            linked_transaction_amount_cents=80,
        )
        assert result.net_transfer_cents == 80
        # Les deux lignes sont préservées telles quelles dans la sortie normalisée.
        assert result.lines == (
            _line(debt_id=d, amount_cents=40),
            _line(debt_id=d, amount_cents=40),
        )

    def test_single_reverse_debt_non_virtual(self) -> None:
        # Dette UNIQUE `hi→lo` (B→A) : net global négatif (−60) ⇒ `abs(net) == 60`
        # accepté en non-virtuel (linked=60). Exerce `abs()` sur un net globalement
        # négatif (le seul signe en jeu est `-1`), pendant non-virtuel du nettage.
        d = UUID(int=10)
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[_line(debt_id=d, amount_cents=60)],
            debt_contexts={d: _ctx(debt_id=d, from_user_id=B, to_user_id=A, remaining_cents=60)},
            linked_transaction_amount_cents=60,
        )
        assert result.net_transfer_cents == 60


# ---------------------------------------------------------------------------
# Rejets — un négatif par règle (1)…(8)
# ---------------------------------------------------------------------------


class TestSettlementValidatorRejections:
    """Un négatif par règle : chaque invariant violé lève sa sous-classe typée."""

    def test_rejects_empty(self) -> None:  # (1)
        with pytest.raises(EmptySettlementError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[],
                debt_contexts={},
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "empty_settlement"

    def test_rejects_orphan_line(self) -> None:  # (2)
        d, orphan = UUID(int=10), UUID(int=99)
        with pytest.raises(UnknownDebtLineError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[_line(debt_id=orphan, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d)},
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "unknown_debt_line"

    def test_rejects_mixed_currency(self) -> None:  # (3)
        d1, d2 = UUID(int=10), UUID(int=11)
        with pytest.raises(MixedCurrencyError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=50),
                    _line(debt_id=d2, amount_cents=50),
                ],
                debt_contexts={
                    d1: _ctx(debt_id=d1, currency="EUR", remaining_cents=50),
                    d2: _ctx(debt_id=d2, currency="USD", remaining_cents=50),
                },
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "mixed_currency"

    def test_rejects_three_parties(self) -> None:  # (4a) branche `> 2`
        d1, d2 = UUID(int=10), UUID(int=11)
        with pytest.raises(MultipleCounterpartiesError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=50),
                    _line(debt_id=d2, amount_cents=50),
                ],
                debt_contexts={
                    d1: _ctx(debt_id=d1, from_user_id=A, to_user_id=B, remaining_cents=50),
                    d2: _ctx(debt_id=d2, from_user_id=A, to_user_id=C, remaining_cents=50),
                },
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "multiple_counterparties"

    def test_rejects_single_party(self) -> None:  # (4b) branche `< 2`
        # `DebtContext` permissif (pas de garde from != to) ⇒ self-debt dégénérée
        # ⇒ `len(parties) == 1` ⇒ couvre la branche `< 2` (sinon non exercée).
        d = UUID(int=10)
        with pytest.raises(MultipleCounterpartiesError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d, from_user_id=A, to_user_id=A)},
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "multiple_counterparties"

    def test_rejects_self_debt_mixed_with_real_debt(self) -> None:  # (4c) / (8) garde
        # Self-debt `A→A` COMBINÉE à une dette réelle `A→B` : l'union `{from, to}`
        # vaut `{A, B}` (cardinalité 2) et franchit donc la règle (4). La garde de
        # robustesse de la règle (8) rejette explicitement la ligne `A→A` (orientation
        # ni `lo→hi` ni `hi→lo`) plutôt que de lui affecter un signe par défaut
        # silencieux (qui ferait netter `A→A 50 + A→B 50` à 0, accepté à tort en
        # virtuel). Cas non-persistable en prod (CHECK `ck_debts_no_self_debt`).
        d_self, d_real = UUID(int=10), UUID(int=11)
        with pytest.raises(MultipleCounterpartiesError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d_self, amount_cents=50),
                    _line(debt_id=d_real, amount_cents=50),
                ],
                debt_contexts={
                    d_self: _ctx(debt_id=d_self, from_user_id=A, to_user_id=A, remaining_cents=50),
                    d_real: _ctx(debt_id=d_real, from_user_id=A, to_user_id=B, remaining_cents=50),
                },
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "multiple_counterparties"

    def test_rejects_virtual_with_link(self) -> None:  # (5a)
        d = UUID(int=10)
        with pytest.raises(LinkedTransactionMismatchError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d)},
                linked_transaction_amount_cents=100,
            )
        assert exc.value.code == "linked_transaction_mismatch"

    def test_rejects_non_virtual_without_link(self) -> None:  # (5b)
        d = UUID(int=10)
        with pytest.raises(LinkedTransactionMismatchError) as exc:
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d)},
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "linked_transaction_mismatch"

    @pytest.mark.parametrize("linked", [0, -5])
    def test_rejects_non_virtual_non_positive_link(self, linked: int) -> None:  # (5c)
        # Garde D5 : non-virtuel ⇒ montant lié strictement positif (frontière 0 +
        # strictement négatif).
        d = UUID(int=10)
        with pytest.raises(LinkedTransactionMismatchError) as exc:
            SettlementValidator.validate(
                settlement_type="external_transfer",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d)},
                linked_transaction_amount_cents=linked,
            )
        assert exc.value.code == "linked_transaction_mismatch"

    def test_rejects_closed_debt(self) -> None:  # (6)
        d = UUID(int=10)
        with pytest.raises(ClosedDebtError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=0)},
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "closed_debt"

    def test_rejects_over_settlement_single(self) -> None:  # (7a)
        d = UUID(int=10)
        with pytest.raises(OverSettlementError) as exc:
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=120)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
                linked_transaction_amount_cents=120,
            )
        assert exc.value.code == "over_settlement"

    def test_rejects_over_settlement_summed(self) -> None:  # (7b)
        # 2 lignes 60 + 60 sur la MÊME dette remaining 100 ⇒ somme par dette > remaining.
        d = UUID(int=10)
        with pytest.raises(OverSettlementError) as exc:
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[
                    _line(debt_id=d, amount_cents=60),
                    _line(debt_id=d, amount_cents=60),
                ],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
                linked_transaction_amount_cents=120,
            )
        assert exc.value.code == "over_settlement"

    def test_rejects_non_positive_line(self) -> None:  # (7c) gardien unique du `> 0`
        d = UUID(int=10)
        with pytest.raises(OverSettlementError) as exc:
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=0)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
                linked_transaction_amount_cents=100,
            )
        assert exc.value.code == "over_settlement"

    def test_rejects_net_mismatch_non_virtual(self) -> None:  # (8a)
        d = UUID(int=10)
        with pytest.raises(NetTransferMismatchError) as exc:
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=100)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
                linked_transaction_amount_cents=90,
            )
        assert exc.value.code == "net_transfer_mismatch"

    def test_rejects_virtual_unbalanced(self) -> None:  # (8b)
        # A→B 50 + B→A 20 ⇒ net = 30 ≠ 0 ⇒ virtuel déséquilibré.
        d1, d2 = UUID(int=10), UUID(int=11)
        with pytest.raises(NetTransferMismatchError) as exc:
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=50),
                    _line(debt_id=d2, amount_cents=20),
                ],
                debt_contexts={
                    d1: _ctx(debt_id=d1, from_user_id=A, to_user_id=B, remaining_cents=50),
                    d2: _ctx(debt_id=d2, from_user_id=B, to_user_id=A, remaining_cents=20),
                },
                linked_transaction_amount_cents=None,
            )
        assert exc.value.code == "net_transfer_mismatch"


# ---------------------------------------------------------------------------
# Cas limites + gardes de contrat
# ---------------------------------------------------------------------------


class TestSettlementValidatorEdgeCases:
    def test_partial_netting_as_internal_transfer(self) -> None:
        # Miroir exact de (8b) mais en non-virtuel : le MÊME nettage (net=30) est
        # valide selon le `type` (linked=30 == net).
        d1, d2 = UUID(int=10), UUID(int=11)
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[
                _line(debt_id=d1, amount_cents=50),
                _line(debt_id=d2, amount_cents=20),
            ],
            debt_contexts={
                d1: _ctx(debt_id=d1, from_user_id=A, to_user_id=B, remaining_cents=50),
                d2: _ctx(debt_id=d2, from_user_id=B, to_user_id=A, remaining_cents=20),
            },
            linked_transaction_amount_cents=30,
        )
        assert result.net_transfer_cents == 30

    def test_value_objects_are_frozen(self) -> None:
        d = UUID(int=10)
        validated = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[_line(debt_id=d, amount_cents=100)],
            debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
            linked_transaction_amount_cents=100,
        )
        with pytest.raises(ValidationError):
            validated.net_transfer_cents = 0  # type: ignore[misc]
        with pytest.raises(ValidationError):
            _ctx(debt_id=d).remaining_cents = 0  # type: ignore[misc]
        # `frozen` épinglé sur les 3 value objects (le 3e directement, pas seulement
        # via le `model_config` partagé) : mutation post-construction refusée.
        with pytest.raises(ValidationError):
            _line(debt_id=d, amount_cents=100).amount_cents = 0  # type: ignore[misc]
        # strict=True : une coercion str → int est refusée.
        with pytest.raises(ValidationError):
            SettlementLineInput(debt_id=d, amount_cents="100")  # type: ignore[arg-type]

    def test_error_family_shares_base(self) -> None:
        # S10.4 mappe toute la famille via un seul `except SettlementValidationError`.
        for err in (
            EmptySettlementError,
            UnknownDebtLineError,
            MixedCurrencyError,
            MultipleCounterpartiesError,
            LinkedTransactionMismatchError,
            ClosedDebtError,
            OverSettlementError,
            NetTransferMismatchError,
        ):
            assert issubclass(err, SettlementValidationError)

    def test_base_error_code_is_stable(self) -> None:
        # La base n'est jamais levée par le validateur (il lève toujours une
        # sous-classe), donc son `code` par défaut — canal client stable — n'est
        # exercé par aucun chemin : on l'épingle explicitement contre une régression.
        assert SettlementValidationError.code == "settlement_validation_error"

    @pytest.mark.parametrize(
        ("error_cls", "trigger"),
        [
            (EmptySettlementError, _raise_empty),
            (UnknownDebtLineError, _raise_unknown),
            (MixedCurrencyError, _raise_mixed_currency),
            (MultipleCounterpartiesError, _raise_multiple_parties),
            (LinkedTransactionMismatchError, _raise_linked_mismatch),
            (ClosedDebtError, _raise_closed_debt),
            (OverSettlementError, _raise_over_settlement),
            (NetTransferMismatchError, _raise_net_mismatch),
        ],
    )
    def test_error_messages_carry_no_pii(
        self,
        error_cls: type[SettlementValidationError],
        trigger: Callable[[], None],
    ) -> None:
        # Canal client = `code` seul ; ni le `debt_id` (424242) ni le montant-sentinelle
        # (999999) injectés ne doivent apparaître dans `str(exc)`. Couvre LES 8
        # sous-classes (garde anti-régression si un futur dev enrichit un message en
        # f"debt {debt_id} exceeds {remaining}").
        with pytest.raises(error_cls) as exc:
            trigger()
        assert str(_PII_DEBT) not in str(exc.value)
        assert str(_PII_AMOUNT) not in str(exc.value)


# ---------------------------------------------------------------------------
# Property-based — divergence vs S09.2 (déterminisme/idempotence livrés dès la
# story domaine) : UNE property non-tautologique exprimant D4 (déterminisme du
# net sous permutation des lignes). Les invariants quantifiables (zero-sum,
# no over-settlement) restent S10.5 (exigent `settlement_scenario_strategy`).
# ---------------------------------------------------------------------------


class TestSettlementValidatorProperties:
    @given(perm=st.permutations([0, 1, 2]))
    def test_net_invariant_under_line_permutation(self, perm: list[int]) -> None:
        # 3 dettes entre A et B en directions MIXTES (A→B 70, B→A 30, A→B 40) ⇒
        # net orienté = +70 − 30 + 40 = 80 quel que soit l'ordre d'arrivée. En
        # mêlant les deux signes (+1 `lo→hi`, −1 `hi→lo`), la property discrimine
        # vraiment D4 (déterminisme du sens canonique sous permutation) — au-delà
        # de la simple commutativité de l'addition à signe uniforme.
        d = [UUID(int=10), UUID(int=11), UUID(int=12)]
        directions = [(A, B), (B, A), (A, B)]
        amounts = [70, 30, 40]
        contexts = {
            d[i]: _ctx(
                debt_id=d[i],
                from_user_id=directions[i][0],
                to_user_id=directions[i][1],
                remaining_cents=amounts[i],
            )
            for i in range(3)
        }
        lines = [_line(debt_id=d[i], amount_cents=amounts[i]) for i in perm]
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=lines,
            debt_contexts=contexts,
            linked_transaction_amount_cents=80,
        )
        assert result.net_transfer_cents == 80


# ---------------------------------------------------------------------------
# SC-05b — Ticket 05 (préfactoring C901) : `validate` a été décomposé en 8
# fonctions privées `_validate_*`/`_compute_net_transfer_cents`, une par
# invariant, appelées EN SÉQUENCE dans `validate`. La classe `Rejections`
# ci-dessus prouve déjà que chaque invariant ISOLÉ lève sa sous-classe. Ce que
# ces cas isolés NE prouvent PAS — et que l'extraction en fonctions distinctes
# aurait pu discrètement inverser si l'ORDRE des appels dans `validate` avait
# changé — c'est la PRIORITÉ entre invariants : quand une entrée viole DEUX
# invariants à la fois, seul le PREMIER (ordre canonique (1)…(8)) doit être
# rapporté. Chaque test ci-dessous construit délibérément une double violation
# adjacente et épingle laquelle des deux gagne, plus un cas valide de bout en
# bout après refactor.
# ---------------------------------------------------------------------------


class TestSC05bValidateOrderPreservedAfterExtraction:
    """Un test par frontière d'ordre (i, i+1) + un cas valide (SC-05b)."""

    def test_SC_05b_rule1_empty_wins_over_any_later_rule(self) -> None:
        # Arrange : aucune ligne, mais un `debt_contexts` qui referme une dette
        # déjà soldée (violerait la règle (6) si elle était atteinte).
        closed = UUID(int=100_001)
        # Act / Assert : (1) est vérifiée avant même de regarder `debt_contexts`.
        with pytest.raises(EmptySettlementError):
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[],
                debt_contexts={closed: _ctx(debt_id=closed, remaining_cents=0)},
                linked_transaction_amount_cents=None,
            )

    def test_SC_05b_rule2_unknown_line_wins_over_rule3_mixed_currency(self) -> None:
        # Arrange : deux dettes connues en devises DIFFÉRENTES (violerait (3))
        # PLUS une ligne ciblant une dette absente de `debt_contexts` (viole (2)).
        d1, d2, orphan = UUID(int=200_001), UUID(int=200_002), UUID(int=200_099)
        with pytest.raises(UnknownDebtLineError):
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=10),
                    _line(debt_id=d2, amount_cents=10),
                    _line(debt_id=orphan, amount_cents=10),
                ],
                debt_contexts={
                    d1: _ctx(debt_id=d1, currency="EUR", remaining_cents=50),
                    d2: _ctx(debt_id=d2, currency="USD", remaining_cents=50),
                },
                linked_transaction_amount_cents=None,
            )

    def test_SC_05b_rule3_mixed_currency_wins_over_rule4_multiple_parties(self) -> None:
        # Arrange : `A→B` EUR et `A→C` USD ⇒ à la fois devises mêlées (3) ET 3
        # contreparties `{A, B, C}` (4).
        d1, d2 = UUID(int=300_001), UUID(int=300_002)
        with pytest.raises(MixedCurrencyError):
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=10),
                    _line(debt_id=d2, amount_cents=10),
                ],
                debt_contexts={
                    d1: _ctx(
                        debt_id=d1, from_user_id=A, to_user_id=B, currency="EUR", remaining_cents=50
                    ),
                    d2: _ctx(
                        debt_id=d2, from_user_id=A, to_user_id=C, currency="USD", remaining_cents=50
                    ),
                },
                linked_transaction_amount_cents=None,
            )

    def test_SC_05b_rule4_multiple_parties_wins_over_rule5_linked_mismatch(self) -> None:
        # Arrange : 3 contreparties `{A, B, C}` (4) ET `virtual` avec un montant
        # lié non-nul (violerait (5) si atteinte).
        d1, d2 = UUID(int=400_001), UUID(int=400_002)
        with pytest.raises(MultipleCounterpartiesError):
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[
                    _line(debt_id=d1, amount_cents=10),
                    _line(debt_id=d2, amount_cents=10),
                ],
                debt_contexts={
                    d1: _ctx(debt_id=d1, from_user_id=A, to_user_id=B, remaining_cents=50),
                    d2: _ctx(debt_id=d2, from_user_id=A, to_user_id=C, remaining_cents=50),
                },
                linked_transaction_amount_cents=999,
            )

    def test_SC_05b_rule5_linked_mismatch_wins_over_rule6_closed_debt(self) -> None:
        # Arrange : dette déjà soldée (`remaining_cents=0`, violerait (6)) ET
        # `virtual` avec un montant lié non-nul (viole (5)).
        d = UUID(int=500_001)
        with pytest.raises(LinkedTransactionMismatchError):
            SettlementValidator.validate(
                settlement_type="virtual",
                lines=[_line(debt_id=d, amount_cents=10)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=0)},
                linked_transaction_amount_cents=999,
            )

    def test_SC_05b_rule6_closed_debt_wins_over_rule7_over_settlement(self) -> None:
        # Arrange : dette soldée (`remaining_cents=0`, viole (6)) ciblée par une
        # ligne strictement positive qui la dépasserait forcément aussi (7).
        d = UUID(int=600_001)
        with pytest.raises(ClosedDebtError):
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=50)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=0)},
                linked_transaction_amount_cents=50,
            )

    def test_SC_05b_rule7_over_settlement_wins_over_rule8_net_mismatch(self) -> None:
        # Arrange : ligne (150) > remaining (100) ⇒ over-settlement (7) ; le
        # `linked_transaction_amount_cents=100` fourni ne matche PAS non plus le
        # net (150), ce qui violerait aussi (8) si (7) ne l'avait pas court-circuité.
        d = UUID(int=700_001)
        with pytest.raises(OverSettlementError):
            SettlementValidator.validate(
                settlement_type="internal_transfer",
                lines=[_line(debt_id=d, amount_cents=150)],
                debt_contexts={d: _ctx(debt_id=d, remaining_cents=100)},
                linked_transaction_amount_cents=100,
            )

    def test_SC_05b_valid_entry_returns_expected_validated_settlement(self) -> None:
        # Arrange : règlement `internal_transfer` valide, une seule ligne, sans
        # violer aucun des 8 invariants.
        d = UUID(int=800_001)
        # Act : passe par les 8 fonctions privées déléguées, dans l'ordre.
        result = SettlementValidator.validate(
            settlement_type="internal_transfer",
            lines=[_line(debt_id=d, amount_cents=42)],
            debt_contexts={d: _ctx(debt_id=d, remaining_cents=42)},
            linked_transaction_amount_cents=42,
        )
        # Assert : le même `ValidatedSettlement` qu'avant l'extraction.
        assert isinstance(result, ValidatedSettlement)
        assert result == ValidatedSettlement(
            type="internal_transfer",
            lines=(_line(debt_id=d, amount_cents=42),),
            currency="EUR",
            counterparties=frozenset({A, B}),
            net_transfer_cents=42,
        )
