"""Pure domain for the debts module (no SQLAlchemy / session / FastAPI / Transaction).

Les `Debt`/`ShareRequestData` Pydantic ici sont DISTINCTS des modèles ORM de
S09.1 (archétype `domain.py`, gabarit `transactions.domain`). Le
`DebtCalculator` est une fonction de VALEURS (ADR 0002, note « Refined-by E09 ») :
il reçoit des SCALAIRES (`expense_total` dérivé par le service S09.3 = somme des
`classification` legs, ADR 0017) — JAMAIS le type `Transaction` (graphe ADR 0005,
contrat import-linter `2-debts`). Le mapper domain↔modèle vit côté service S09.3.

Interne à `modules.debts` : n'importe que `backend.shared.money` (+ stdlib +
Pydantic) ⇒ aucun arc cross-module. La taxonomie `DebtCalculationError` reste
stdlib-only afin que le service S09.3 mappe la famille avec un seul
`except DebtCalculationError` (→ 422). `code` (ClassVar) est le canal client
stable et SANS PII : le service NE DOIT JAMAIS recopier `str(exc)` (qui pourrait
contenir un UUID/montant) dans le message exposé.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from backend.shared.money import Money

# Set fermé des origines de dette (gabarit `DebtGenerationOverride`/`LegRole`).
# Le modèle ORM `origin` est `String` SANS CHECK SQL (S09.1) : ce `Literal` EST
# le verrou au boundary Pydantic. `shared_account_overflow` est listé mais NON
# produit en E09 (overflow F10 → E11) : verrou de set fermé volontaire.
DebtOrigin = Literal["shared_account_overflow", "personal_share_request"]


class DebtCalculationError(Exception):
    """Base de toute violation du calcul de dette (gabarit `TransactionError`).

    Base commune ⇒ le service S09.3 mappe TOUTE la famille avec un seul
    `except DebtCalculationError` (→ 422). `code` est stable et SANS PII (à
    recopier tel quel côté client ; jamais `str(exc)`).
    """

    code: ClassVar[str] = "debt_calculation_error"


class NonPositiveExpenseError(DebtCalculationError):
    """`expense_total ≤ 0` : on ne matérialise pas de dette sur une dépense nulle."""

    code: ClassVar[str] = "non_positive_expense"


class RatioOutOfBoundsError(DebtCalculationError):
    """`ratio ∉ (0, 1]` : garde FAIL-SAFE (S09.2 D5b).

    La DB n'a AUCUN CHECK sur `share_ratio` (`Numeric(5, 4)` accepte jusqu'à
    9.9999) ⇒ sans ce garde, un `ratio > 1` produirait silencieusement une dette
    aberrante (`amount > expense_total`). Le calculator est l'unique gardien
    testable (D4) ; la validation 422 UX reste au boundary S09.3.
    """

    code: ClassVar[str] = "ratio_out_of_bounds"


class SelfDebtError(DebtCalculationError):
    """`requested_from == requested_by` : on ne se doit rien à soi-même (miroir du
    CHECK `ck_debts_no_self_debt`)."""

    code: ClassVar[str] = "self_debt"


class NonPositiveDebtAmountError(DebtCalculationError):
    """Le partage ARRONDI dégénère à ≤ 0 cent (S09.2 D5a).

    Avec des entrées valides (`expense_total > 0`, `0 < r ≤ 1`) l'arrondi peut
    tomber à 0 (`M=1¢, r=0.4 → 0`), ce que le CHECK `ck_debts_amount_positive`
    interdirait au service. Distinct de `RatioOutOfBoundsError` : ici le ratio
    est VALIDE, mais l'expense trop petite.
    """

    code: ClassVar[str] = "non_positive_debt_amount"


class ShareRequestData(BaseModel):
    """Miroir pur (PERMISSIF) de la `ShareRequest` consommée par S09.3.

    AUCUN validator métier (borne ratio, garde self, borne longueur
    `short_label`) : c'est volontaire (D4) pour que le `DebtCalculator` reste
    l'UNIQUE gardien testable — sinon les branches `SelfDebtError`/
    `RatioOutOfBoundsError` de `compute_*` deviendraient inatteignables (dead
    code + trou de coverage). La validation d'entrée 422 (`short_label` : trim +
    rejet caractères de contrôle + borne longueur ≤ 100 ; rejet `ratio`/self
    AVANT le domaine pour l'UX) vit au boundary S09.3.

    `short_label` est porté pour le mirror fidèle de la SR, bien qu'INUTILISÉ par
    le calcul — assumé.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    source_transaction_id: UUID
    requested_by: UUID  # créancier (= owner du compte source)
    requested_from: UUID  # débiteur
    ratio: Decimal
    short_label: str  # porté pour le mirror ; non lu par le calcul


class Debt(BaseModel):
    """Miroir pur du modèle SQLA `Debt` (ADR 0002), en `Money`.

    ⚠️ SÉCURITÉ — `source_transaction_id` et `account_id` sont MASQUÉS au
    débiteur (glossaire §Visibilité d'une dette `personal_share_request` ;
    review #22 B1 : le compte personnel source ne doit pas fuiter). NE JAMAIS
    sérialiser ce `Debt` du domaine DIRECTEMENT vers un client (`.model_dump()`
    naïf en log debug, message d'erreur, sérialisation hâtive S09.3) : le rendu
    client passe OBLIGATOIREMENT par l'allowlist DTO S09.4.

    `created_at` et `materialization_trace` sont ABSENTS : DB-générés /
    server-only, posés par le mapper S09.3 (hors domaine pur — symétrie, D3b).

    `share_ratio` ne reproduit PAS le `default=Decimal("1.0")` de la colonne ORM :
    un value object pur exige une quote-part explicite (pas de default silencieux),
    et le calculator la fournit toujours. Le default ORM reste la valeur de repli
    côté persistance (S09.3+), pas du miroir.

    Reproduit les 2 CHECK SQL (`ck_debts_amount_positive`, `ck_debts_no_self_debt`)
    comme `model_validator` : le domaine ne peut pas représenter une dette que la
    DB rejetterait (défense en profondeur). `strict=True` refuse les coercions
    implicites (gabarit `Money`/`Transaction`).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    from_user_id: UUID  # débiteur
    to_user_id: UUID  # créancier
    amount: Money
    account_id: UUID  # compte source — masqué au débiteur (S09.4)
    source_transaction_id: UUID  # masqué au débiteur (S09.4)
    origin: DebtOrigin
    share_ratio: Decimal

    @model_validator(mode="after")
    def _mirror_db_checks(self) -> Debt:
        # Reproduit ck_debts_amount_positive + ck_debts_no_self_debt (S09.1).
        if self.amount.amount_cents <= 0:
            raise ValueError("amount must be strictly positive")
        if self.from_user_id == self.to_user_id:
            raise ValueError("no self-debt")
        return self


class DebtCalculator:
    """Projection PURE des dettes (ADR 0002). MVP : `compute_for_share_request`.

    `compute_for_overflow` (sous-cas `shared_account_overflow`, argument
    `Budget`) est DÉFÉRÉ à E11. La classe (vs fonctions module-level) reflète le
    nom contractuel ADR 0002/glossaire et la cohésion des 2 futures méthodes.
    """

    @staticmethod
    def compute_for_share_request(
        *,
        share_request: ShareRequestData,
        expense_total: Money,
        source_account_id: UUID,
    ) -> list[Debt]:
        """`requested_from` doit `expense_total × ratio` à `requested_by`.

        Retourne EXACTEMENT une `Debt` orientée débiteur→créancier, d'origine
        `personal_share_request`. Idempotent par construction (projection pure).

        Gardes (toute la famille `DebtCalculationError`) : `NonPositiveExpense`
        (`expense_total ≤ 0`), `RatioOutOfBounds` (`ratio ∉ (0, 1]`, fail-safe
        D5b), `SelfDebt` (`requested_from == requested_by`), `NonPositiveDebtAmount`
        (montant arrondi ≤ 0, D5a). Le garde borne ratio est levé AVANT
        `apply_ratio` : le domaine ne présuppose pas un appelant S09.3 correct.
        """
        if expense_total.amount_cents <= 0:
            raise NonPositiveExpenseError("expense_total must be strictly positive")
        if not (0 < share_request.ratio <= 1):
            raise RatioOutOfBoundsError("ratio must be within (0, 1]")
        if share_request.requested_from == share_request.requested_by:
            raise SelfDebtError("requested_from must differ from requested_by")
        amount = expense_total.apply_ratio(share_request.ratio)
        if amount.amount_cents <= 0:
            raise NonPositiveDebtAmountError("share rounds to a non-positive amount")
        return [
            Debt(
                from_user_id=share_request.requested_from,
                to_user_id=share_request.requested_by,
                amount=amount,
                account_id=source_account_id,
                source_transaction_id=share_request.source_transaction_id,
                origin="personal_share_request",
                share_ratio=share_request.ratio,
            )
        ]


# ---------------------------------------------------------------------------
# S10.2 — Settlement : validateur PUR (multi-line, 3 types) — ADR 0011
# ---------------------------------------------------------------------------

# Set fermé des types de règlement — verrou au boundary Pydantic (le modèle ORM
# `Settlement.type` est `String` SANS CHECK d'énumération, S10.1 ; gabarit
# `DebtOrigin`). Le littéral `virtual` est le seul discriminant lien↔type
# (miroir du CHECK `ck_settlements_virtual_no_link`, ADR 0011 §2).
SettlementType = Literal["internal_transfer", "external_transfer", "virtual"]


class DebtContext(BaseModel):
    """Vue scalaire d'une `Debt` ciblée — dérivée par le service S10.4.

    Le `SettlementValidator` est PUR (ADR 0002 affiné E09) : comme
    `DebtCalculator` reçoit `expense_total: Money` (jamais un `Transaction`), il
    reçoit des `DebtContext` scalaires — JAMAIS une `Debt` ORM ni une `Session`.
    Le service S10.4 dérive ces scalaires (charge la dette, son `remaining` via
    S10.3, ses contreparties).

    Ne porte PAS `household_id` : l'isolation foyer (`debt → account → household`)
    est intrinsèquement effectful ⇒ gardée par le **service S10.4**, hors du
    validateur pur (ADR 0011 §4, encart Refined-by E10 — précision de couche ;
    AC opposable `cross_household_leak` sur #155). Ne porte pas non plus
    `account_id`/`source_transaction_id` : aucune fuite du compte source (S09.4).

    `remaining_cents` = solde restant COURANT (S10.3), AVANT ce règlement ;
    `> 0` attendu, vérifié par la règle (6) du validateur.

    PERMISSIF (gabarit `ShareRequestData`, S09.2 D4) : aucun `model_validator`
    métier (pas de garde `from != to`) ⇒ `SettlementValidator` reste l'UNIQUE
    gardien testable, sinon des branches d'erreur deviendraient inatteignables.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    debt_id: UUID
    from_user_id: UUID  # débiteur
    to_user_id: UUID  # créancier
    currency: str
    remaining_cents: int  # solde restant courant (S10.3) ; > 0 vérifié règle (6)


class SettlementLineInput(BaseModel):
    """Une ligne d'apurement — montant POSITIF (D-SIGN, ADR 0011 §1).

    Le signe du nettage est porté par l'ORIENTATION de la `Debt` (calculé par le
    validateur, règle (8)) — JAMAIS stocké signé sur la ligne (miroir du CHECK
    `ck_settlement_lines_amount_positive`, S10.1). PERMISSIF comme `DebtContext` :
    la garde `amount_cents > 0` vit dans le validateur (règle (7)), unique
    gardien testable — sinon la branche `OverSettlementError` serait inatteignable.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    debt_id: UUID
    amount_cents: int  # > 0 ; sens porté par l'orientation de la Debt (règle 8)


class ValidatedSettlement(BaseModel):
    """Sortie normalisée d'un règlement validé — scalaires pour S10.4 / traçabilité.

    `net_transfer_cents` = `abs(net)` orienté (non-virtuel, == montant tx liée) /
    `0` (virtuel) — D5. Exposé pour traçabilité/tests ; le service le compare déjà
    (comparaison faite ici). Le sens RÉEL débiteur→créancier du virement (aligné
    sur payeur→bénéficiaire de la tx) reste effectful ⇒ S10.4 : le domaine pur
    garde la MAGNITUDE, pas l'orientation réelle.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    type: SettlementType
    counterparties: frozenset[UUID]  # exactement {A, B}
    net_transfer_cents: int  # abs(net) (non-virtuel) / 0 (virtuel) — D5
    currency: str
    lines: tuple[SettlementLineInput, ...]


class SettlementValidationError(Exception):
    """Base de toute violation de validation d'un règlement (gabarit
    `DebtCalculationError`).

    Famille DISTINCTE de `DebtCalculationError` : deux actes métier distincts
    (matérialisation d'une dette vs règlement) ⇒ le service S10.4 mappe TOUTE la
    famille via un seul `except SettlementValidationError` (→ 422), séparé du 422
    share-request de S09.3. `code` (ClassVar) est le canal client stable et SANS
    PII : recopier `code`, JAMAIS `str(exc)` (peut contenir UUID/montant).
    """

    code: ClassVar[str] = "settlement_validation_error"


class EmptySettlementError(SettlementValidationError):
    """Règle (1) : un règlement sans aucune ligne n'apure rien."""

    code: ClassVar[str] = "empty_settlement"


class UnknownDebtLineError(SettlementValidationError):
    """Règle (2) : une ligne cible un `debt_id` absent des `debt_contexts`."""

    code: ClassVar[str] = "unknown_debt_line"


class MixedCurrencyError(SettlementValidationError):
    """Règle (3) : les dettes ciblées s'étalent sur plusieurs devises (CONTEXT.md
    §SettlementLine : la devise est dupliquée depuis la `Debt`, garde-fou)."""

    code: ClassVar[str] = "mixed_currency"


class MultipleCounterpartiesError(SettlementValidationError):
    """Règle (4) : les dettes ciblées n'impliquent pas EXACTEMENT deux
    contreparties `{A, B}` (3+ tiers, ou self-debt dégénérée `< 2`)."""

    code: ClassVar[str] = "multiple_counterparties"


class LinkedTransactionMismatchError(SettlementValidationError):
    """Règle (5) : incohérence `linked_transaction` ⟺ `type` (miroir du CHECK
    `ck_settlements_virtual_no_link`, ADR 0011 §2 ; défense en profondeur — le
    domaine pur ne dépend pas de la DB pour être complet/testable Hypothesis)."""

    code: ClassVar[str] = "linked_transaction_mismatch"


class ClosedDebtError(SettlementValidationError):
    """Règle (6) : une dette ciblée est déjà soldée (`remaining_cents <= 0`)."""

    code: ClassVar[str] = "closed_debt"


class OverSettlementError(SettlementValidationError):
    """Règle (7) : une ligne (ou la somme des lignes d'une même dette) dépasse le
    `remaining_cents` de la dette, ou un montant non strictement positif."""

    code: ClassVar[str] = "over_settlement"


class NetTransferMismatchError(SettlementValidationError):
    """Règle (8) : le net orienté ne correspond pas au montant de la tx liée
    (non-virtuel), ou n'est pas nul (virtuel — ADR 0011 §2)."""

    code: ClassVar[str] = "net_transfer_mismatch"


class SettlementValidator:
    """Validation PURE d'un règlement avant insert (S10.4).

    Aucune session, aucun `Transaction` : entrées/sorties scalaires (ADR 0002
    affiné E09, ADR 0011). Testable Hypothesis sans DB (S10.5, `Stratégie` §4.2 ;
    `DebtContext`/`ValidatedSettlement` sont les types que la
    `settlement_scenario_strategy` peuplera).

    `internal_transfer` et `external_transfer` sont traités à L'IDENTIQUE ici
    (tous deux : `linked` NOT NULL, net == montant tx) : distinguer la FORME du
    virement (intra-foyer vs sortant tiers) est effectful (charge les comptes) ⇒
    S10.4. L'isolation foyer (ADR 0011 §4) est elle aussi effectful ⇒ S10.4.
    """

    @staticmethod
    def validate(  # noqa: PLR0912 — 8 invariants séquentiels, ordre déterministe documenté
        *,
        settlement_type: SettlementType,
        lines: Sequence[SettlementLineInput],
        debt_contexts: Mapping[UUID, DebtContext],
        linked_transaction_amount_cents: int | None,  # abs(montant) ; None ssi virtual
    ) -> ValidatedSettlement:
        """Valide les 8 invariants scalaires d'un règlement, dans un ORDRE
        déterministe : (1) non vide → (2) ligne orpheline → (3) devise unique →
        (4) exactement 2 contreparties → (5) lien ⟺ virtual → (6) dette close →
        (7) over-settlement → (8) net orienté == virement.

        Retourne `ValidatedSettlement` (lignes normalisées + net tracé) si valide ;
        lève une sous-classe de `SettlementValidationError` au premier invariant
        violé. Accepte : `internal_transfer`/`external_transfer` dont
        `Σ ligne × signe_direction == linked (> 0)` ; `virtual` (`linked = NULL`)
        dont le net orienté `== 0` (nettage croisé symétrique).
        """
        # (1) non vide → sinon `EmptySettlementError`.
        if not lines:
            raise EmptySettlementError("settlement must have at least one line")

        # (2) chaque ligne référence un `DebtContext` connu → sinon orpheline.
        for line in lines:
            if line.debt_id not in debt_contexts:
                raise UnknownDebtLineError("line targets an unknown debt")

        # Contextes effectivement ciblés (déterministe : ordre des lignes).
        targeted = [debt_contexts[line.debt_id] for line in lines]

        # (3) devise unique sur tous les contextes ciblés (CONTEXT.md §SettlementLine).
        currencies = {ctx.currency for ctx in targeted}
        if len(currencies) != 1:
            raise MixedCurrencyError("targeted debts span multiple currencies")
        (currency,) = currencies

        # (4) exactement deux contreparties : union des `{from, to}` de cardinalité 2.
        parties = {uid for ctx in targeted for uid in (ctx.from_user_id, ctx.to_user_id)}
        if len(parties) != 2:  # noqa: PLR2004 — exactement 2 contreparties {A, B}
            # Message couvrant les DEUX côtés : `> 2` (3+ tiers) et `< 2` (self-debt
            # dégénérée, possible car `DebtContext` est permissif). La règle raisonne
            # sur des `user_id` (orthogonale au foyer ; la garde foyer est en S10.4).
            raise MultipleCounterpartiesError("settlement must involve exactly two parties")

        # (5) biconditionnel lien ⟺ virtual (miroir `ck_settlements_virtual_no_link`).
        is_virtual = settlement_type == "virtual"
        if is_virtual != (linked_transaction_amount_cents is None):
            raise LinkedTransactionMismatchError("linked tx inconsistent with type")
        # Après le biconditionnel : non-virtuel ⇒ `linked is not None` (sinon levé
        # ci-dessus, branche morte non re-testée) ; seul le montant non-positif reste
        # à garder. `assert` pour narrower le type pour pyright.
        if not is_virtual:
            assert linked_transaction_amount_cents is not None  # garanti par (5)
            if linked_transaction_amount_cents <= 0:
                # Non-virtuel ⇒ montant lié strictement positif (D5, défense en profondeur).
                raise LinkedTransactionMismatchError(
                    "non-virtual requires a positive linked amount"
                )

        # (6) aucune dette ciblée déjà soldée (`remaining_cents <= 0`).
        for ctx in targeted:
            if ctx.remaining_cents <= 0:
                raise ClosedDebtError("targeted debt is already settled")

        # (7) no over-settlement (somme par dette ≤ remaining). `strict=True` ne
        #     garantit QUE le typage `int`, PAS la positivité (value object permissif)
        #     ⇒ la garde `> 0` est explicite ici : UNIQUE gardien testable du « > 0 »
        #     côté domaine (le CHECK SQL `ck_settlement_lines_amount_positive` est le
        #     miroir DB, S10.1).
        per_debt: dict[UUID, int] = {}
        for line in lines:
            if line.amount_cents <= 0:
                raise OverSettlementError("line amount must be strictly positive")
            per_debt[line.debt_id] = per_debt.get(line.debt_id, 0) + line.amount_cents
        for debt_id, total in per_debt.items():
            if total > debt_contexts[debt_id].remaining_cents:
                raise OverSettlementError("line(s) exceed the debt remaining")

        # (8) net orienté canonique (D4) puis comparaison au virement (D5). Ordre
        #     canonique déterministe par valeur d'UUID (indépendant de l'ordre
        #     d'arrivée des lignes) : requis pour les properties S10.5.
        lo, hi = sorted(parties, key=lambda u: u.int)
        net = 0
        for line in lines:
            ctx = debt_contexts[line.debt_id]
            sign = 1 if (ctx.from_user_id == lo and ctx.to_user_id == hi) else -1
            net += sign * line.amount_cents
        if is_virtual:
            if net != 0:
                raise NetTransferMismatchError("virtual settlement must net to zero")
            net_transfer_cents = 0
        else:
            assert linked_transaction_amount_cents is not None  # garanti par (5)
            if abs(net) != linked_transaction_amount_cents:
                raise NetTransferMismatchError("net does not match linked transaction")
            net_transfer_cents = abs(net)

        return ValidatedSettlement(
            type=settlement_type,
            counterparties=frozenset(parties),
            net_transfer_cents=net_transfer_cents,
            currency=currency,
            lines=tuple(lines),
        )
