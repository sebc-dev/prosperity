"""Pure domain for the transactions module (no SQLAlchemy / session / FastAPI).

Aggregate root immutable à `confirmed` (ADR 0001) : le `Transaction` Pydantic
ici est DISTINCT du modèle ORM de S07.2 (archétype `domain.py`). Le service
(S07.4) mappe `model ↔ domain` et `(amount_cents, currency) ↔ Money`.

Cette story matérialise quatre invariants métier, tous testables sans DB :

  - **zero-sum** (`sum(splits) == Money(0, ccy)`) — enforced au `model_validator`
    UNIQUEMENT à l'état `confirmed` ; toléré en `draft`/`planned` (édition en
    cours) ;
  - **state machine** (`STATE_TRANSITIONS` + `assert_transition`) :
    `draft → planned → confirmed`, `* → void`, `void` terminal, et surtout
    `confirmed → planned` INTERDIT (ADR 0001 / Q8 reconciliation) ;
  - **immutabilité partielle** après `confirmed` (`check_mutation_allowed`) :
    seuls les champs de `EDITABLE_AFTER_CONFIRMED` peuvent diverger ;
  - **catégorisation** des dépenses (`assert_expenses_categorized`) : une
    dépense (non-transfert) confirmée doit avoir une catégorie sur chaque split.

**Contrat d'immutabilité.** Les invariants (zero-sum, gel) ne tiennent QUE pour
les instances construites via le constructeur validant. `model_construct(...)`
et `model_copy(update=...)` CONTOURNENT le `model_validator` zero-sum ; leur
usage est réservé au mapper S07.4 (qui garantit lui-même la cohérence
DB → domaine). Toute édition côté domaine passe par le constructeur (rouge si
un invariant est cassé).

Interne à `modules.transactions` (import-linter contrat `2-transactions`) ;
n'importe que `backend.shared` + stdlib → aucun arc cross-module. La taxonomie
`TransactionError` reste stdlib-only afin que le service S07.4 mappe la famille
avec un seul `except TransactionError`. ⚠️ `IncompatibleCurrencyError` (levée
par `Money.__add__` sur devise mixte) n'hérite PAS de `TransactionError` : le
boundary S07.4 doit l'attraper séparément (`except (TransactionError,
IncompatibleCurrencyError)`).
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any, ClassVar, Final, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from backend.shared.money import Money

# `default` au create ; `force_full_debt`/`force_no_debt` forcent la génération
# de dette (ADR 0011 / Q2). Source unique de vérité du futur CHECK SQL différé
# en S07.4 (le `String` ORM de S07.2 n'a volontairement pas de contrainte).
DebtGenerationOverride = Literal["default", "force_full_debt", "force_no_debt"]

# Marqueur STRUCTUREL du rôle d'une jambe (ADR 0017, option 1). Set fermé à 2
# valeurs, source unique de vérité : le CHECK SQL `ck_splits_leg_role`
# (migration 0013), le default ORM context-sensitive (`models._default_leg_role`)
# et le validator `before` ci-dessous miroitent EXACTEMENT ces deux valeurs.
# `funding` = mouvement de compte (peut rester non catégorisé) ; `classification`
# = jambe de dépense. En S08.5.1 aucune règle ne le lit encore
# (`assert_expenses_categorized` inchangé) ; sa lecture arrive en S08.5.2.
LegRole = Literal["funding", "classification"]


class TransactionState(enum.StrEnum):
    """États du cycle de vie d'une transaction (ADR 0001).

    Valeurs = exactement les `String` stockés par l'ORM (S07.2) → mapping
    trivial au service, et source unique pour les schemas API S07.5. Gabarit
    `accounts.domain.AccountType`.
    """

    DRAFT = "draft"
    PLANNED = "planned"
    CONFIRMED = "confirmed"
    VOID = "void"


# Transitions autorisées (D8). `confirmed → planned` ABSENT (ADR 0001 :
# revenir en `planned` rouvrirait l'édition des montants gelés). `void`
# terminal (frozenset vide). `draft → confirmed` direct absent (doit passer
# par `planned`). Toute clé de l'enum est présente (verrou D14) → `.get` ne
# tombe jamais sur le défaut en pratique, mais `assert_transition` reste
# fail-closed si un futur état était oublié.
STATE_TRANSITIONS: Final[dict[TransactionState, frozenset[TransactionState]]] = {
    TransactionState.DRAFT: frozenset({TransactionState.PLANNED, TransactionState.VOID}),
    TransactionState.PLANNED: frozenset({TransactionState.CONFIRMED, TransactionState.VOID}),
    TransactionState.CONFIRMED: frozenset({TransactionState.VOID}),
    TransactionState.VOID: frozenset(),
}

# Champs éditables après `confirmed` (D7 ; issue #114 fait autorité sur le
# fichier roadmap qui listait `share_request_added/removed`). Tout le reste
# (splits, `account_id`, `date`, `payee`, `created_by`, `id`) est gelé. `state`
# n'est PAS ici : il évolue via la state machine, pas via le checker
# d'immutabilité (cf. `check_mutation_allowed`). La partition est verrouillée
# par un test déterministe (D14) pour qu'un futur ajout de champ ne fasse pas
# fuiter silencieusement un champ financier dans l'éditable.
EDITABLE_AFTER_CONFIRMED: Final[frozenset[str]] = frozenset(
    {"category_id", "tags", "description", "debt_generation_override", "share_request_id"}
)


class TransactionError(Exception):
    """Base de toute violation de règle métier du domaine transactions (S07.3).

    Une base commune laisse le service S07.4 mapper toute la famille avec un
    `except TransactionError` unique, tout en gardant `domain.py` stdlib-only
    (gabarit `budget.domain.CategoryError` / `accounts.domain.AccountValidationError`).

    `code` (ClassVar) : identifiant stable et SANS PII, à recopier tel quel dans
    le `WriteResult.error.code` exposé client. Le service NE DOIT JAMAIS recopier
    `str(exc)` (qui peut contenir un UUID/un montant) dans `error.message` : il
    utilise `exc.code` + les attributs typés (`field`, `transaction_id`, …) comme
    canal sûr, jamais le message libre.
    """

    code: ClassVar[str] = "transaction_error"


class UnbalancedTransactionError(TransactionError):
    """`sum(splits) != Money(0, ccy)` sur une transaction `confirmed` (ADR 0001)."""

    code: ClassVar[str] = "unbalanced_transaction"


class InvalidStateTransitionError(TransactionError):
    """Transition non listée dans `STATE_TRANSITIONS` (jamais silencieuse)."""

    code: ClassVar[str] = "invalid_state_transition"

    def __init__(self, from_state: TransactionState, to_state: TransactionState) -> None:
        super().__init__(f"transition interdite : {from_state} → {to_state}")
        self.from_state = from_state
        self.to_state = to_state


class ImmutableFieldViolation(TransactionError):
    """Édition d'un champ gelé d'une transaction `confirmed` (ADR 0001).

    Correspond au code `WriteResult` `immutable_field_violation` (glossaire,
    anticipe E13). Le service NE DOIT JAMAIS copier `str(exc)` dans le
    `error.message` exposé client : utiliser `code` + l'attribut typé `field`.
    """

    code: ClassVar[str] = "immutable_field_violation"

    def __init__(self, field: str) -> None:
        super().__init__(f"champ gelé modifié sur une transaction confirmée : {field}")
        self.field = field


class UncategorizedExpenseError(TransactionError):
    """Confirmation refusée : un split dépense (non-transfert) n'a pas de catégorie.

    Glossaire §`splits.category_id NULL` : pas de catégorie « Sans catégorie »
    magique — l'utilisateur choisit explicitement. L'UUID de la transaction est
    porté par l'attribut typé `transaction_id` (canal de debug structuré), PAS
    seulement dans le message : le service utilise `code`/`transaction_id` et NE
    DOIT JAMAIS recopier `str(exc)` dans le `error.message` exposé client.
    """

    code: ClassVar[str] = "uncategorized_expense"

    def __init__(self, transaction_id: UUID) -> None:
        super().__init__(
            f"dépense non catégorisée sur une transaction confirmée : {transaction_id}"
        )
        self.transaction_id = transaction_id


class Split(BaseModel):
    """Une ligne signée d'une transaction (CONTEXT.md §Split).

    `amount` est typé `Money` (et non `amount_cents` + `currency` séparés comme
    l'ORM) : le domaine raisonne en `Money` (zero-sum = `sum(splits) == 0`). Le
    découplage colonnes ↔ `Money` est la responsabilité du mapper S07.4.
    `category_id` NULL = transfert ou split en cours d'édition.

    `leg_role` (ADR 0017, option 1) : marqueur STRUCTUREL du rôle de la jambe.
    `funding` = mouvement de compte (peut être non catégorisé) ; `classification`
    = jambe de dépense (catégorie attendue une fois la règle réécrite, S08.5.2).
    En S08.5.1 le champ est exposé mais AUCUNE règle ne le lit
    (`assert_expenses_categorized` inchangé) : il dérive de `category_id` quand le
    constructeur ne le reçoit pas (même règle que le back-fill `0013` et le
    default ORM `_default_leg_role`), et les mappers S07.4 passent la valeur
    autoritative du SGBD.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    account_id: UUID
    category_id: UUID | None = None
    amount: Money
    # Default présent UNIQUEMENT pour le type-checker (les sites de construction
    # n'ont pas à passer `leg_role`) ; le validator `before` ci-dessous impose la
    # valeur réelle, donc ce littéral n'est jamais utilisé à l'exécution.
    leg_role: LegRole = "classification"

    @model_validator(mode="before")
    @classmethod
    def _derive_leg_role(cls, data: Any) -> Any:
        """Dérive `leg_role` de `category_id` quand l'appelant l'omet.

        Règle identique au back-fill `0013` et au default ORM : pas de
        `category_id` ⇒ `funding`, sinon `classification`. Si l'appelant fournit
        `leg_role` (cas des mappers : valeur autoritative du SGBD), on le
        respecte. N'agit que sur un input `dict` (construction par kwargs) —
        `model_construct`/`model_copy` (réservés au mapper, D11) ne passent pas
        par ce validator, et c'est voulu.
        """
        if not isinstance(data, dict):
            return data
        values = cast(dict[str, Any], data)
        if "leg_role" not in values:
            derived = "funding" if values.get("category_id") is None else "classification"
            values = {**values, "leg_role": derived}
        return values


class Transaction(BaseModel):
    """Aggregate root immutable à `confirmed` (ADR 0001).

    `splits: tuple[Split, ...]` (PAS `list`) et `tags: tuple[str, ...]` :
    `frozen=True` empêche la réassignation d'attribut (`tx.splits = [...]`) mais
    PAS la mutation en place d'une `list` (`tx.splits.append(...)` /
    `tx.splits[0] = ...`) — qui contournerait le `model_validator` zero-sum
    (atteinte directe à la double-entrée). Le `tuple` ferme ce trou (immutable,
    hashable, comparable par valeur — requis par le checker d'immutabilité). Le
    mapper S07.4 convertit depuis les `list`/ARRAY de l'ORM. `strict=True`
    refuse les coercions implicites (gabarit `Money`).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    id: UUID
    account_id: UUID
    date: dt.date
    state: TransactionState
    payee: str | None = None
    created_by: UUID
    splits: tuple[Split, ...]
    # Champs éditables après `confirmed` (D7, `EDITABLE_AFTER_CONFIRMED`).
    category_id: UUID | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    debt_generation_override: DebtGenerationOverride = "default"
    # DELTA-1 : pas de colonne ORM `share_request_id` encore (la relation
    # `ShareRequest` vit dans `debts`/E09). Le domaine porte l'UUID nullable
    # SANS importer `debts` ; la migration de la colonne est un follow-up S07.4.
    share_request_id: UUID | None = None

    @model_validator(mode="after")
    def _enforce_zero_sum_when_confirmed(self) -> Transaction:
        """Impose `sum(splits) == Money(0, ccy)` SI `state is CONFIRMED` (D4).

        Toléré en `draft`/`planned` (édition en cours ; le service revérifie le
        zero-sum à `transition_to_planned`, S07.4). Délègue à `assert_zero_sum`
        (helper standalone S07.4) : comportement préservé (ne s'exécute qu'à
        `CONFIRMED`). La somme via `Money.__add__` propage
        `IncompatibleCurrencyError` sur devise mixte (devise unique imposée
        « gratuitement » par le type) — exception HORS taxonomie
        `TransactionError`, à border côté S07.4.
        """
        if self.state is not TransactionState.CONFIRMED:
            return self
        assert_zero_sum(self)
        return self


def assert_zero_sum(tx: Transaction) -> None:
    """Lève `UnbalancedTransactionError` si `sum(splits) != Money(0, ccy)`.

    Standalone (gabarit `assert_transition`/`assert_expenses_categorized`) pour
    que le service vérifie le solde à `planned` ET `confirmed` sans construire un
    `confirmed` jetable (le `model_validator` n'enforce le zero-sum qu'à
    `confirmed`). La somme via `Money.__add__` propage `IncompatibleCurrencyError`
    sur devise mixte (HORS taxonomie `TransactionError`, à border côté service).
    Le message « sans split » diffère du validator (« confirmée sans split ») —
    sans impact : le canal client est `code`, jamais `str(exc)`.
    """
    if not tx.splits:
        raise UnbalancedTransactionError("transaction sans split")
    total = tx.splits[0].amount
    for split in tx.splits[1:]:
        total = total + split.amount  # lève IncompatibleCurrencyError si mélange
    if total != Money(0, total.currency):
        raise UnbalancedTransactionError(f"somme des splits = {total}, attendu 0")


def assert_transition(from_state: TransactionState, to_state: TransactionState) -> None:
    """Lève `InvalidStateTransitionError` si `to_state ∉ STATE_TRANSITIONS[from_state]`.

    Jamais de passage silencieux (critère d'acceptation). `void` terminal :
    toute sortie de `void` lève. `confirmed → planned` lève (ADR 0001).

    `.get(from_state, frozenset())` (et non `[from_state]`) : un `from_state`
    sans entrée (futur état enum oublié) lève l'exception TYPÉE (rattrapée par
    `except TransactionError` au service S07.4), pas un `KeyError` brut hors
    taxonomie (qui remonterait en 500 non mappé). Le verrou D14
    (`set(STATE_TRANSITIONS) == set(TransactionState)`) garantit par ailleurs
    qu'aucune clé ne manque.
    """
    if to_state not in STATE_TRANSITIONS.get(from_state, frozenset()):
        raise InvalidStateTransitionError(from_state, to_state)


def check_mutation_allowed(old: Transaction, new: Transaction) -> None:
    """Lève `ImmutableFieldViolation` à la 1re divergence interdite (D10).

    No-op si `old.state is not CONFIRMED` (édition libre en `draft`/`planned`).
    `state` est exclu de la comparaison : son évolution passe par la state
    machine (`assert_transition`), pas par le checker. L'invariant de sûreté
    `confirmed → planned` interdit repose donc sur l'ordre d'appel côté
    service (`assert_transition` AVANT `check_mutation_allowed`).

    Comparaison structurelle sur les `model_fields` : tout champ ∉
    `EDITABLE_AFTER_CONFIRMED` (et hors `state`) doit être égal entre `old` et
    `new` — `splits` compris (comparés par valeur, `Money`/`Split` ont un
    `__eq__` structurel). Lever sur la PREMIÈRE divergence donne un message
    ciblé.
    """
    if old.state is not TransactionState.CONFIRMED:
        return
    for field in type(old).model_fields:
        if field in EDITABLE_AFTER_CONFIRMED or field == "state":
            continue
        if getattr(old, field) != getattr(new, field):
            raise ImmutableFieldViolation(field)


def is_transfer(tx: Transaction) -> bool:
    """`True` ssi les splits couvrent ≥ 2 comptes distincts (D6, DELTA-2).

    Prédicat STRUCTUREL pur : aucune connaissance des comptes du foyer n'est
    importée (le service garantit en amont, via `accounts.public`, que tout
    `account_id` est un compte du foyer — le domaine n'a pas à le revérifier et
    reste pur). Forme canonique S07.2 : dépense/revenu = 2 jambes MÊME compte ;
    transfert = jambes sur comptes DISTINCTS.

    ⚠️ Limite V1 assumée (tracée vers S07.4) : une dépense « éclatée » sur 2
    comptes (achat réglé moitié carte A / moitié carte B) est classée transfert
    → échappe à `assert_expenses_categorized`. L'enforcement réel (distinguer
    transfert vs dépense-éclatée via le contexte comptes) appartient au service
    S07.4 ; un `transfer_kind` explicite serait réintroduit si le cas devient
    supporté (V2).
    """
    return len({split.account_id for split in tx.splits}) >= 2  # noqa: PLR2004 — ≥ 2 comptes = transfert


def assert_expenses_categorized(tx: Transaction) -> None:
    """Lève `UncategorizedExpenseError` si une dépense (non-transfert) n'a pas
    de catégorie. No-op pour un transfert (D11).

    Appelé par le service à `transition_to_confirmed` (S07.4) — il vit dans le
    domaine (pur), pas dans le service. Glossaire §`splits.category_id NULL` :
    transfert et `draft` tolérés ; pour `confirmed`, tout split dépense doit
    avoir une catégorie.
    """
    if is_transfer(tx):
        return
    if any(split.category_id is None for split in tx.splits):
        raise UncategorizedExpenseError(tx.id)
