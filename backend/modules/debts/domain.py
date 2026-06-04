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
