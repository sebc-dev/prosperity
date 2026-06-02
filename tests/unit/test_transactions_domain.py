"""Unit tests for `transactions.domain` (S07.3) — pure aggregate, no DB.

The `Transaction`/`Split` of `domain.py` are DISTINCT from the S07.2 ORM models
(archetype: pure domain ≠ ORM). Everything here runs without testcontainers:
the four invariants — zero-sum at `confirmed`, the state machine, partial
immutability after `confirmed`, and expense categorisation — are pure Pydantic
+ stdlib, so they are pinned with example tests and Hypothesis properties
(Stratégie §4.1/§4.2), grouped in `Test<Concept>` classes (D13).

Properties verify the invariants with oracles INDEPENDENT of the
implementation (e.g. mutating exactly one frozen field and asserting the
checker rejects it), never by re-running the production helper against itself
(anti-pattern Stratégie §12).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.modules.transactions.domain import (
    EDITABLE_AFTER_CONFIRMED,
    STATE_TRANSITIONS,
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    Split,
    Transaction,
    TransactionState,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
    assert_expenses_categorized,
    assert_transition,
    assert_zero_sum,
    check_mutation_allowed,
    is_transfer,
)
from backend.shared.money import IncompatibleCurrencyError, Money
from tests.strategies import (
    balanced_splits_strategy,
    confirmed_transaction_strategy,
)

_DATE = dt.date(2026, 1, 15)


def _split(
    amount: Money, *, account_id: UUID | None = None, category_id: UUID | None = None
) -> Split:
    """A `Split` with sensible defaults; only the axis under test is varied."""
    return Split(
        account_id=account_id if account_id is not None else uuid4(),
        category_id=category_id,
        amount=amount,
    )


def _tx(
    *,
    state: TransactionState,
    splits: tuple[Split, ...],
    **overrides: object,
) -> Transaction:
    """Build a `Transaction` with required identity fields filled in."""
    base: dict[str, object] = {
        "id": uuid4(),
        "account_id": uuid4(),
        "date": _DATE,
        "state": state,
        "created_by": uuid4(),
        "splits": splits,
    }
    base.update(overrides)
    return Transaction(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# P07.3.1 — zero-sum invariant + Split/Transaction shape
# ---------------------------------------------------------------------------


class TestZeroSum:
    """`sum(splits) == Money(0, ccy)` enforced ONLY at `confirmed` (D4)."""

    def test_draft_unbalanced_is_allowed(self) -> None:
        # Déséquilibre toléré en édition (draft).
        _tx(state=TransactionState.DRAFT, splits=(_split(Money(1000, "EUR")),))

    def test_planned_unbalanced_is_allowed(self) -> None:
        # Zero-sum revérifié au service à transition_to_planned (S07.4), pas ici.
        _tx(state=TransactionState.PLANNED, splits=(_split(Money(1000, "EUR")),))

    def test_confirmed_balanced_ok(self) -> None:
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(_split(Money(-1000, "EUR")), _split(Money(1000, "EUR"))),
        )
        assert tx.state is TransactionState.CONFIRMED

    def test_confirmed_unbalanced_raises(self) -> None:
        with pytest.raises(UnbalancedTransactionError):
            _tx(
                state=TransactionState.CONFIRMED,
                splits=(_split(Money(-1000, "EUR")), _split(Money(500, "EUR"))),
            )

    def test_confirmed_empty_splits_raises(self) -> None:
        with pytest.raises(UnbalancedTransactionError):
            _tx(state=TransactionState.CONFIRMED, splits=())

    def test_confirmed_mixed_currency_raises(self) -> None:
        # La devise mixte propage IncompatibleCurrencyError (du `+` de Money),
        # HORS taxonomie TransactionError (D5/D9 ; bordé côté S07.4).
        with pytest.raises(IncompatibleCurrencyError):
            _tx(
                state=TransactionState.CONFIRMED,
                splits=(_split(Money(-1000, "EUR")), _split(Money(1000, "USD"))),
            )

    def test_confirmed_multi_split_balanced_ok(self) -> None:
        _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR")),
                _split(Money(600, "EUR")),
                _split(Money(400, "EUR")),
            ),
        )

    def test_draft_mixed_currency_allowed(self) -> None:
        # Validator inactif hors confirmed → mélange de devises toléré en draft
        # (documente l'intention : l'équilibre/devise unique ne sont gelés qu'à
        # confirmed).
        _tx(
            state=TransactionState.DRAFT,
            splits=(_split(Money(-1000, "EUR")), _split(Money(1000, "USD"))),
        )

    def test_transaction_is_frozen(self) -> None:
        tx = _tx(state=TransactionState.DRAFT, splits=(_split(Money(1000, "EUR")),))
        with pytest.raises(ValidationError):  # frozen=True → réassignation interdite
            tx.state = TransactionState.PLANNED  # type: ignore[misc]

    def test_splits_collection_is_immutable(self) -> None:
        # `splits` est un tuple (D12) : pas de mutation en place qui
        # contournerait le validator zero-sum (atteinte à la double-entrée).
        tx = _tx(state=TransactionState.DRAFT, splits=(_split(Money(1000, "EUR")),))
        assert isinstance(tx.splits, tuple)
        with pytest.raises(AttributeError):
            tx.splits.append(_split(Money(1, "EUR")))  # type: ignore[attr-defined]

    def test_split_amount_is_money(self) -> None:
        # strict=True refuse un int brut là où un Money est attendu.
        with pytest.raises(ValidationError):
            Split(account_id=uuid4(), amount=100)  # type: ignore[arg-type]

    @given(splits=balanced_splits_strategy())
    def test_property_balanced_splits_construct_confirmed(self, splits: tuple[Split, ...]) -> None:
        # ∀ ensemble de splits équilibré (même devise) → construction `confirmed`
        # SANS erreur (invariant central ADR 0001, §4.1 « pour toute combinaison »).
        tx = _tx(state=TransactionState.CONFIRMED, splits=splits)
        assert tx.state is TransactionState.CONFIRMED

    @given(splits=balanced_splits_strategy(), delta=st.integers(min_value=1, max_value=10**6))
    def test_property_unbalanced_splits_raise_confirmed(
        self, splits: tuple[Split, ...], delta: int
    ) -> None:
        # Déséquilibre une jambe d'un montant non nul (même devise) → la somme
        # devient ≠ 0 → UnbalancedTransactionError.
        first = splits[0]
        bumped = first.model_copy(
            update={"amount": Money(first.amount.amount_cents + delta, first.amount.currency)}
        )
        unbalanced = (bumped, *splits[1:])
        with pytest.raises(UnbalancedTransactionError):
            _tx(state=TransactionState.CONFIRMED, splits=unbalanced)


class TestAssertZeroSum:
    """`assert_zero_sum` standalone (D3) — vérifie le solde à `planned` ET `confirmed`.

    Le `model_validator` n'enforce le zero-sum qu'à `confirmed` ; le helper extrait
    est appelé par le service aux deux transitions. Indépendant de l'état (il prend
    une `Transaction` quelconque), donc testé sur un `draft` jetable.
    """

    def test_balanced_ok(self) -> None:
        tx = _tx(
            state=TransactionState.DRAFT,
            splits=(_split(Money(-1000, "EUR")), _split(Money(1000, "EUR"))),
        )
        assert_zero_sum(tx)  # no raise

    def test_unbalanced_raises(self) -> None:
        tx = _tx(
            state=TransactionState.DRAFT,
            splits=(_split(Money(-1000, "EUR")), _split(Money(500, "EUR"))),
        )
        with pytest.raises(UnbalancedTransactionError):
            assert_zero_sum(tx)

    def test_empty_splits_raises(self) -> None:
        tx = _tx(state=TransactionState.DRAFT, splits=())
        with pytest.raises(UnbalancedTransactionError):
            assert_zero_sum(tx)

    def test_mixed_currency_propagates_incompatible(self) -> None:
        # Devise mixte → IncompatibleCurrencyError (HORS taxonomie, bordé S07.4).
        tx = _tx(
            state=TransactionState.DRAFT,
            splits=(_split(Money(-1000, "EUR")), _split(Money(1000, "USD"))),
        )
        with pytest.raises(IncompatibleCurrencyError):
            assert_zero_sum(tx)

    @given(data=st.data(), splits=balanced_splits_strategy())
    def test_property_balanced_permuted_never_raises(
        self, data: st.DataObject, splits: tuple[Split, ...]
    ) -> None:
        # ∀ tirage équilibré (même devise) ET toute permutation de l'ordre des
        # splits → `assert_zero_sum` ne lève JAMAIS (la somme est invariante par
        # permutation). Cible le helper standalone que D3 extrait.
        permuted = tuple(data.draw(st.permutations(splits)))
        assert_zero_sum(_tx(state=TransactionState.DRAFT, splits=permuted))

    @given(splits=balanced_splits_strategy(), delta=st.integers(min_value=1, max_value=10**6))
    def test_property_unbalanced_always_raises(self, splits: tuple[Split, ...], delta: int) -> None:
        # ∀ déséquilibre injecté (delta non nul, devise unique) → lève TOUJOURS
        # UnbalancedTransactionError.
        first = splits[0]
        bumped = first.model_copy(
            update={"amount": Money(first.amount.amount_cents + delta, first.amount.currency)}
        )
        with pytest.raises(UnbalancedTransactionError):
            assert_zero_sum(_tx(state=TransactionState.DRAFT, splits=(bumped, *splits[1:])))


class TestStateTransitionsConst:
    """Shape of `STATE_TRANSITIONS` + verrou D14 sur les clés."""

    def test_state_transitions_const_shape(self) -> None:
        assert TransactionState.PLANNED not in STATE_TRANSITIONS[TransactionState.CONFIRMED]
        assert STATE_TRANSITIONS[TransactionState.VOID] == frozenset()
        # Verrou D14 : toutes les clés couvrent l'enum (aucun état orphelin →
        # `assert_transition` ne tombe jamais sur le défaut `.get`).
        assert set(STATE_TRANSITIONS) == set(TransactionState)


# ---------------------------------------------------------------------------
# P07.3.2 — immutability checker
# ---------------------------------------------------------------------------


class TestImmutability:
    """`check_mutation_allowed` gèle tout champ ∉ EDITABLE_AFTER_CONFIRMED (D10)."""

    @staticmethod
    def _confirmed_pair() -> Transaction:
        return _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), category_id=uuid4()),
                _split(Money(1000, "EUR"), category_id=uuid4()),
            ),
            payee="ACME",
            category_id=uuid4(),
            description="orig",
        )

    def test_noop_when_old_not_confirmed(self) -> None:
        # Pas de gel en draft : une divergence sur un champ financier passe.
        old = _tx(state=TransactionState.DRAFT, splits=(_split(Money(1000, "EUR")),))
        new = old.model_copy(update={"account_id": uuid4()})
        check_mutation_allowed(old, new)  # no raise

    def test_edit_category_id_ok(self) -> None:
        old = self._confirmed_pair()
        check_mutation_allowed(old, old.model_copy(update={"category_id": uuid4()}))

    def test_edit_tags_description_override_share_request_ok(self) -> None:
        old = self._confirmed_pair()
        for field, value in (
            ("tags", ("a", "b")),
            ("description", "edited"),
            ("debt_generation_override", "force_full_debt"),
            ("share_request_id", uuid4()),
        ):
            check_mutation_allowed(old, old.model_copy(update={field: value}))

    def test_edit_split_amount_raises(self) -> None:
        # Mutation ÉQUILIBRÉE des splits (permutation des account_id préserve la
        # somme) pour ne pas déclencher le validator zero-sum à la construction
        # de `new` (piège « double exception »). Ici on change un account_id de
        # split → divergence sur `splits` → ImmutableFieldViolation.
        old = self._confirmed_pair()
        mutated_splits = (
            old.splits[0].model_copy(update={"account_id": uuid4()}),
            *old.splits[1:],
        )
        new = old.model_copy(update={"splits": mutated_splits})
        with pytest.raises(ImmutableFieldViolation) as exc:
            check_mutation_allowed(old, new)
        assert exc.value.field == "splits"

    def test_edit_account_id_raises(self) -> None:
        old = self._confirmed_pair()
        with pytest.raises(ImmutableFieldViolation) as exc:
            check_mutation_allowed(old, old.model_copy(update={"account_id": uuid4()}))
        assert exc.value.field == "account_id"

    def test_edit_date_payee_created_by_id_raises(self) -> None:
        old = self._confirmed_pair()
        for field, value in (
            ("date", dt.date(2030, 12, 31)),
            ("payee", "OTHER"),
            ("created_by", uuid4()),
            ("id", uuid4()),  # pivot d'identité de l'aggregate
        ):
            with pytest.raises(ImmutableFieldViolation) as exc:
                check_mutation_allowed(old, old.model_copy(update={field: value}))
            assert exc.value.field == field

    def test_state_change_not_flagged_by_checker(self) -> None:
        # confirmed→void diffère sur `state` mais le checker l'ignore : la
        # garantie anti-confirmed→planned repose sur assert_transition appelé
        # AVANT le checker côté service (D10).
        old = self._confirmed_pair()
        check_mutation_allowed(old, old.model_copy(update={"state": TransactionState.VOID}))

    def test_rebuilt_identical_splits_not_flagged(self) -> None:
        # Filet load-bearing : le checker compare `splits` PAR VALEUR (et non par
        # identité). Le mapper S07.4 reconstruira des `Split` distincts depuis la
        # DB → s'ils sont structurellement égaux, aucune ImmutableFieldViolation
        # ne doit être levée. Une régression de `Split.__eq__`/`__hash__` (passage
        # à une comparaison d'identité) ferait échouer CHAQUE édition d'une
        # transaction confirmée — ce test la rattrape.
        old = self._confirmed_pair()
        rebuilt = tuple(
            Split(
                account_id=s.account_id,
                category_id=s.category_id,
                amount=Money(s.amount.amount_cents, s.amount.currency),
            )
            for s in old.splits
        )
        # Instances réellement distinctes (sinon le test ne prouverait rien).
        assert rebuilt is not old.splits
        assert all(new_s is not old_s for new_s, old_s in zip(rebuilt, old.splits, strict=True))
        assert rebuilt == old.splits  # … mais égaux par valeur.
        check_mutation_allowed(old, old.model_copy(update={"splits": rebuilt}))  # no raise

    def test_editable_set_matches_model_fields(self) -> None:
        # Verrou D14 : partition gelé/éditable figée. Tout renommage/ajout de
        # champ casse ce test plutôt que de faire fuiter un champ financier.
        assert EDITABLE_AFTER_CONFIRMED == {
            "category_id",
            "tags",
            "description",
            "debt_generation_override",
            "share_request_id",
        }
        assert EDITABLE_AFTER_CONFIRMED <= set(Transaction.model_fields)

    @given(data=st.data(), old=confirmed_transaction_strategy())
    def test_property_only_editable_fields_accepted(
        self, data: st.DataObject, old: Transaction
    ) -> None:
        # ∀ confirmed `old` + mutation portant UNIQUEMENT sur un sous-ensemble
        # de EDITABLE_AFTER_CONFIRMED → jamais d'ImmutableFieldViolation.
        # min_size=1 : on veut au moins une mutation réelle (la liste vide
        # donnerait un no-raise trivial qui dilue le signal de la property).
        fields = data.draw(
            st.lists(st.sampled_from(sorted(EDITABLE_AFTER_CONFIRMED)), min_size=1, unique=True)
        )
        updates: dict[str, object] = {}
        for field in fields:
            if field == "category_id":
                updates[field] = uuid4()
            elif field == "tags":
                updates[field] = data.draw(st.lists(st.text(max_size=8), max_size=3))
                updates[field] = tuple(updates[field])  # type: ignore[arg-type]
            elif field == "description":
                updates[field] = data.draw(st.none() | st.text(max_size=12))
            elif field == "debt_generation_override":
                updates[field] = data.draw(
                    st.sampled_from(["default", "force_full_debt", "force_no_debt"])
                )
            else:  # share_request_id
                updates[field] = data.draw(st.none() | st.uuids())
        new = old.model_copy(update=updates)
        check_mutation_allowed(old, new)  # no raise

    @given(old=confirmed_transaction_strategy())
    def test_property_any_frozen_divergence_raises(self, old: Transaction) -> None:
        # ∀ divergence sur un champ gelé NON FINANCIER (évite le piège « double
        # exception » : muter un montant déséquilibrerait `new` → le validator
        # zero-sum lèverait avant le checker). On mute chaque champ gelé sûr.
        frozen_mutations: dict[str, object] = {
            "id": uuid4(),
            "account_id": uuid4(),
            "date": old.date + dt.timedelta(days=1),
            "created_by": uuid4(),
            "payee": (old.payee or "") + "x",
        }
        for field, value in frozen_mutations.items():
            with pytest.raises(ImmutableFieldViolation) as exc:
                check_mutation_allowed(old, old.model_copy(update={field: value}))
            assert exc.value.field == field


# ---------------------------------------------------------------------------
# P07.3.3 — state machine
# ---------------------------------------------------------------------------

_ALLOWED_PAIRS = [
    (TransactionState.DRAFT, TransactionState.PLANNED),
    (TransactionState.DRAFT, TransactionState.VOID),
    (TransactionState.PLANNED, TransactionState.CONFIRMED),
    (TransactionState.PLANNED, TransactionState.VOID),
    (TransactionState.CONFIRMED, TransactionState.VOID),
]
_ALL_PAIRS = [(f, t) for f in TransactionState for t in TransactionState]


class TestStateMachine:
    """`assert_transition` valide via STATE_TRANSITIONS, jamais silencieux (D8)."""

    @pytest.mark.parametrize(("from_state", "to_state"), _ALLOWED_PAIRS)
    def test_allowed_transitions(
        self, from_state: TransactionState, to_state: TransactionState
    ) -> None:
        assert_transition(from_state, to_state)  # no raise

    def test_forbidden_confirmed_to_planned(self) -> None:
        # Cas emblématique ADR 0001 : revenir en planned rouvrirait les montants.
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(TransactionState.CONFIRMED, TransactionState.PLANNED)

    @pytest.mark.parametrize("to_state", list(TransactionState))
    def test_void_is_terminal(self, to_state: TransactionState) -> None:
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(TransactionState.VOID, to_state)

    @pytest.mark.parametrize("state", list(TransactionState))
    def test_no_self_transition(self, state: TransactionState) -> None:
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(state, state)

    def test_draft_to_confirmed_forbidden(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(TransactionState.DRAFT, TransactionState.CONFIRMED)

    @pytest.mark.parametrize(("from_state", "to_state"), _ALL_PAIRS)
    def test_full_matrix_parametrized(
        self, from_state: TransactionState, to_state: TransactionState
    ) -> None:
        # assert OK ⟺ la paire est dans STATE_TRANSITIONS.
        allowed = (from_state, to_state) in _ALLOWED_PAIRS
        if allowed:
            assert_transition(from_state, to_state)
        else:
            with pytest.raises(InvalidStateTransitionError):
                assert_transition(from_state, to_state)

    def test_error_carries_states(self) -> None:
        with pytest.raises(InvalidStateTransitionError) as exc:
            assert_transition(TransactionState.CONFIRMED, TransactionState.PLANNED)
        assert exc.value.from_state is TransactionState.CONFIRMED
        assert exc.value.to_state is TransactionState.PLANNED


# ---------------------------------------------------------------------------
# P07.3.4 — transfer predicate + categorisation guard
# ---------------------------------------------------------------------------


class TestTransferGuard:
    """`is_transfer` (structurel) + `assert_expenses_categorized` (D6/D11)."""

    def test_expense_uncategorized_raises(self) -> None:
        acc = uuid4()
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), account_id=acc, category_id=uuid4()),
                _split(Money(1000, "EUR"), account_id=acc, category_id=None),
            ),
        )
        with pytest.raises(UncategorizedExpenseError) as exc:
            assert_expenses_categorized(tx)
        # L'UUID est porté par un attribut typé (canal sûr), pas seulement le message.
        assert exc.value.transaction_id == tx.id
        assert exc.value.code == "uncategorized_expense"

    def test_expense_fully_categorized_ok(self) -> None:
        acc = uuid4()
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), account_id=acc, category_id=uuid4()),
                _split(Money(1000, "EUR"), account_id=acc, category_id=uuid4()),
            ),
        )
        assert_expenses_categorized(tx)  # no raise

    def test_transfer_without_category_ok(self) -> None:
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), account_id=uuid4(), category_id=None),
                _split(Money(1000, "EUR"), account_id=uuid4(), category_id=None),
            ),
        )
        assert is_transfer(tx)
        assert_expenses_categorized(tx)  # no raise

    def test_transfer_with_partial_category_ok(self) -> None:
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), account_id=uuid4(), category_id=uuid4()),
                _split(Money(1000, "EUR"), account_id=uuid4(), category_id=None),
            ),
        )
        assert_expenses_categorized(tx)  # transfert prime, pas d'exigence

    def test_is_transfer_true_distinct_accounts(self) -> None:
        two = _tx(
            state=TransactionState.DRAFT,
            splits=(
                _split(Money(-1000, "EUR"), account_id=uuid4()),
                _split(Money(1000, "EUR"), account_id=uuid4()),
            ),
        )
        assert is_transfer(two)
        a, b, c = uuid4(), uuid4(), uuid4()
        three = _tx(
            state=TransactionState.DRAFT,
            splits=(
                _split(Money(-1000, "EUR"), account_id=a),
                _split(Money(600, "EUR"), account_id=b),
                _split(Money(400, "EUR"), account_id=c),
            ),
        )
        assert is_transfer(three)

    def test_is_transfer_false_same_account(self) -> None:
        acc = uuid4()
        tx = _tx(
            state=TransactionState.DRAFT,
            splits=(
                _split(Money(-1000, "EUR"), account_id=acc),
                _split(Money(1000, "EUR"), account_id=acc),
            ),
        )
        assert not is_transfer(tx)

    def test_is_transfer_single_split(self) -> None:
        tx = _tx(state=TransactionState.DRAFT, splits=(_split(Money(1000, "EUR")),))
        assert not is_transfer(tx)

    def test_assert_expenses_categorized_single_categorized_split(self) -> None:
        # 1 split (non-transfert) catégorisé → OK (couvre la branche any()=False).
        tx = _tx(
            state=TransactionState.DRAFT,
            splits=(_split(Money(1000, "EUR"), category_id=uuid4()),),
        )
        assert_expenses_categorized(tx)

    def test_split_expense_two_accounts_classified_as_transfer(self) -> None:
        # LIMITE V1 CONNUE (D6) : une dépense non catégorisée éclatée sur 2
        # comptes est classée transfert → assert_expenses_categorized no-op.
        # L'enforcement réel (transfert vs dépense-éclatée) appartient à S07.4
        # qui a le contexte comptes du foyer (accounts.public).
        tx = _tx(
            state=TransactionState.CONFIRMED,
            splits=(
                _split(Money(-1000, "EUR"), account_id=uuid4(), category_id=None),
                _split(Money(1000, "EUR"), account_id=uuid4(), category_id=None),
            ),
        )
        assert is_transfer(tx)
        assert_expenses_categorized(tx)  # no raise — comportement documenté

    @given(splits=balanced_splits_strategy(distinct_accounts=False))
    def test_property_uncategorized_expense_raises(self, splits: tuple[Split, ...]) -> None:
        # ∀ dépense confirmée (même compte → non-transfert) dont AU MOINS un split
        # perd sa catégorie → UncategorizedExpenseError. `distinct_accounts=False`
        # exerce la forme dépense canonique (is_transfer False) en property-based,
        # absente des autres properties (toutes en distinct_accounts=True).
        uncategorized = (splits[0].model_copy(update={"category_id": None}), *splits[1:])
        tx = _tx(state=TransactionState.CONFIRMED, splits=uncategorized)
        assert not is_transfer(tx)
        with pytest.raises(UncategorizedExpenseError):
            assert_expenses_categorized(tx)
