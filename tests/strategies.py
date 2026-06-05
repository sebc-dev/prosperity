"""Stratégies Hypothesis partagées pour les tests property-based (S05.5, S06.4, S07.1, S07.3).

`money_strategy` (S07.1) génère un `Money` valide (devise tirée dans `CURRENCIES`,
montant entier borné) ; `distinct_currency_pair` fournit deux devises garanties
distinctes pour les properties cross-devise. Premier consommateur de `Money` en
property-based ; calque `account_with_members_strategy`.

`balanced_splits_strategy` / `transaction_confirmed_strategy` /
`transaction_draft_strategy` (S07.3, complétées S07.6) génèrent respectivement un
tuple de `Split` zero-sum (même devise), une `Transaction` `confirmed` valide
(zero-sum garanti par construction) et une `Transaction` `draft` (splits libres
par défaut, « confirmable » sur demande) — réutilisent `money_strategy` (devise
unique). `balanced_splits_strategy` accepte `n_splits` pour fixer la cardinalité.
Pensées pour réuse E07/E08/E09/E10 (l'aggregate immutable est le socle des
budgets, dettes et règlements adossés aux transactions).


`category_tree_strategy` (S06.4) génère un arbre/forêt de catégories
**acyclique par construction** (chaque nœud pointe vers un parent déjà émis ou
``None``), paramétrable (nb de nœuds / profondeur / arité) pour réuse E07
(transactions catégorisées) et E08 (budgets agrégeant la hiérarchie). Comme
`account_with_members_strategy`, elle n'importe **aucun** module
`backend.modules.budget` : ses valeurs sont pures (`UUID` + parent-map), donc
le `CycleDetector` n'est lu que par les *tests*, jamais par la strategy.

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
from decimal import ROUND_CEILING, Decimal
from typing import Final, Literal
from uuid import UUID, uuid4

import hypothesis.strategies as st

from backend.modules.accounts.domain import AccountType, MemberShare
from backend.modules.debts.domain import (
    Debt,
    DebtCalculator,
    DebtContext,
    SettlementLineInput,
    SettlementType,
    ShareRequestData,
)
from backend.modules.transactions.domain import Split, Transaction, TransactionState
from backend.shared.currency import CURRENCIES, Currency
from backend.shared.money import Money

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

    `ValueError` si ``total < n`` : N parts entières ≥ 1 imposent ``total >= n``
    (sinon partition impossible). Garde explicite car le helper est public et
    réutilisable hors de ses appelants S05.5.
    """
    if total < n:
        raise ValueError(f"share_ratios requiert total >= n, reçu total={total}, n={n}")
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


@dataclass(frozen=True, slots=True)
class GeneratedCategoryTree:
    """Arbre/forêt de catégories ACYCLIQUE par construction (S06.4).

    `nodes` est en ordre TOPOLOGIQUE : le parent de tout nœud (s'il existe)
    apparaît STRICTEMENT avant lui ⇒ INSERT direct sous la self-FK
    `categories.parent_id` (property c, S06.4), et acyclicité prouvable par le
    seul ordre (parent index < child index). Gabarit `GeneratedAccount`.
    """

    nodes: tuple[tuple[UUID, UUID | None], ...]

    @property
    def ids(self) -> list[UUID]:
        """Les ids des nœuds, en ordre topologique (parents avant enfants)."""
        return [nid for nid, _ in self.nodes]

    @property
    def parent_of(self) -> dict[UUID, UUID | None]:
        """`{node: parent}` — INJECTABLE TEL QUEL comme `get_parent` (via `.get`).

        Contrat verrouillé par les properties (a)/(b) de S06.4 : tant qu'il
        renvoie ce dict, `CycleDetector.detect_cycle(get_parent=tree.parent_of.get)`
        et l'oracle `_is_acyclic(mutated)` restent valides (jamais vacants).
        """
        return {nid: pid for nid, pid in self.nodes}

    def descendants(self, root: UUID) -> set[UUID]:
        """Tous les nœuds dont la chaîne d'ancêtres passe par `root` (root exclu).

        IMPLÉMENTATION UNIQUE du calcul de descendants (S06.4) : les properties
        (b) et (c) l'appellent. Purement structurel (remontée des `parent_of`),
        INDÉPENDANT du service `archive_category` — sert d'oracle de non-cascade
        en (c) et de sélecteur de candidats de move en (b). La garde `seen`
        borne la remontée même sur une map corrompue (jamais utilisée ici, mais
        rend le helper sûr pour les consommateurs aval E07/E08).
        """
        parent = self.parent_of
        out: set[UUID] = set()
        for nid in parent:
            current, seen = parent.get(nid), {nid}
            while current is not None and current not in seen:
                if current == root:
                    out.add(nid)
                    break
                seen.add(current)
                current = parent.get(current)
        return out


@st.composite
def category_tree_strategy(
    draw: st.DrawFn,
    *,
    min_nodes: int = 1,
    max_nodes: int = 12,
    max_depth: int | None = None,
    max_arity: int | None = None,
) -> GeneratedCategoryTree:
    """Arbre N-aire valide, ACYCLIQUE PAR CONSTRUCTION (gabarit `account_with_members_strategy`).

    Émet `n` nœuds dans l'ordre ; le nœud 0 est une racine ; chaque nœud i>0
    tire son parent dans `{None} ∪ {nœuds déjà émis éligibles}` — éligible ⇔
    profondeur < `max_depth` ET nb d'enfants < `max_arity`. Aucun éligible ⇒
    racine (`None`). Ne pointer que vers un nœud déjà émis rend tout cycle
    impossible. Peut générer une **forêt** (plusieurs racines).

    `max_depth` compte les **NIVEAUX, PAS les arêtes** (off-by-one volontaire) :

      - racine seule = `depth 0` ;
      - `max_depth=1` ⇒ UNIQUEMENT des racines (`depth[parent]+1 < 1` toujours faux) ;
      - `max_depth=2` ⇒ racines + 1 niveau d'enfants (`depth ∈ {0, 1}`) ;
      - profondeur maximale atteignable = `max_depth - 1`.

    `max_arity` borne le nb d'enfants DIRECTS par nœud ; `max_arity=0` ⇒ aucun
    nœud ne peut être parent ⇒ forêt de singletons (cas plat extrême).
    ``None`` (défaut) sur l'un ou l'autre ⇒ borne illimitée.

    Paramétrable (taille / profondeur / arité) pour réuse E07 / E08.
    """
    n = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    ids = [uuid4() for _ in range(n)]
    parent: dict[UUID, UUID | None] = {}
    depth: dict[UUID, int] = {}
    children: dict[UUID, int] = {}
    for i, node in enumerate(ids):
        if i == 0:
            chosen: UUID | None = None
        else:
            eligible = [
                ids[j]
                for j in range(i)
                if (max_depth is None or depth[ids[j]] + 1 < max_depth)
                and (max_arity is None or children.get(ids[j], 0) < max_arity)
            ]
            chosen = draw(st.sampled_from([None, *eligible]))
        parent[node] = chosen
        depth[node] = 0 if chosen is None else depth[chosen] + 1
        if chosen is not None:
            children[chosen] = children.get(chosen, 0) + 1
    return GeneratedCategoryTree(nodes=tuple((nid, parent[nid]) for nid in ids))


_MONEY_BOUND: Final[int] = 10**9  # ±10 M€ en centimes : large mais évite l'overflow visuel
_CURRENCY_CHOICES: Final = sorted(CURRENCIES)  # dérivé du Literal `Currency` (source unique)


@st.composite
def money_strategy(draw: st.DrawFn, *, currency: Currency | None = None) -> Money:
    """Génère un `Money` valide (S07.1, premier consommateur property-based).

    `currency=None` => devise tirée dans les codes connus (`CURRENCIES`, donc
    suit automatiquement une extension V2 — pas de liste en dur). Montant entier
    borné par `±_MONEY_BOUND` : large, mais évite des sorties illisibles sans
    masquer de cas limite (l'arithmétique entière de Python n'overflow pas).
    """
    cur = currency if currency is not None else draw(st.sampled_from(_CURRENCY_CHOICES))
    amount = draw(st.integers(min_value=-_MONEY_BOUND, max_value=_MONEY_BOUND))
    return Money(amount, cur)  # type: ignore[arg-type]  # cur ∈ Currency par construction


@st.composite
def distinct_currency_pair(draw: st.DrawFn) -> tuple[Currency, Currency]:
    """Deux devises GARANTIES distinctes (évite le rejet `assume`, zéro exemple gaspillé)."""
    a = draw(st.sampled_from(_CURRENCY_CHOICES))
    b = draw(st.sampled_from([c for c in _CURRENCY_CHOICES if c != a]))
    return a, b  # type: ignore[return-value]  # a != b ∈ Currency par construction


# ---------------------------------------------------------------------------
# S09.2 — stratégies du `DebtCalculator` (domaine pur ; ratios `Decimal`, jamais
# de `float` — ADR 0008). `_BASIS_POINTS` (échelle 4) déjà défini en tête.
# ---------------------------------------------------------------------------


@st.composite
def personal_share_ratio(draw: st.DrawFn) -> Decimal:
    """Ratio `Decimal` à l'échelle 4 dans `(0, 1]` (jamais `float`).

    Réutilise l'approche « points de base » de `share_ratios` : bp ∈ [1, 10000]
    ⇒ `Decimal(bp) / 10000` ∈ [0.0001, 1.0000], strictement positif et ≤ 1
    (miroir de la colonne `share_ratio Numeric(5, 4)` sous la borne métier).
    """
    bp = draw(st.integers(min_value=1, max_value=_BASIS_POINTS))
    return Decimal(bp) / Decimal(_BASIS_POINTS)


@st.composite
def positive_money_eur(draw: st.DrawFn) -> Money:
    """`Money` EUR à montant strictement positif, SANS `assume` (zéro exemple gaspillé).

    `money_strategy` tire dans [−10⁹, +10⁹] ; filtrer par `assume(amount > 0)`
    rejetterait ~50 % des exemples (risque `filter_too_much` en `ci=50`).
    Convention repo (`distinct_currency_pair`) = générateur sans rejet.
    """
    return Money(draw(st.integers(min_value=1, max_value=_MONEY_BOUND)), "EUR")


@st.composite
def out_of_bounds_ratio(draw: st.DrawFn) -> Decimal:
    """Ratio `Decimal` HORS `(0, 1]` : soit ≤ 0, soit > 1 (property de rejet S09.2)."""
    return draw(
        st.one_of(
            st.integers(min_value=-_BASIS_POINTS, max_value=0).map(
                lambda bp: Decimal(bp) / Decimal(_BASIS_POINTS)
            ),
            st.integers(min_value=_BASIS_POINTS + 1, max_value=10 * _BASIS_POINTS).map(
                lambda bp: Decimal(bp) / Decimal(_BASIS_POINTS)
            ),
        )
    )


# ---------------------------------------------------------------------------
# S09.5 — infrastructure Hypothesis du module `debts` (domaine pur).
# NE teste PAS d'invariant neuf du calculator (clos par S09.2) : fournit les
# générateurs réutilisables que E10 (properties zero-sum du Settlement, où
# l'ensemble des dettes d'une tx cesse d'être un singleton) consommera.
# Générateurs SANS rejet (convention repo) : aucune zone d'arrondi→0, aucun
# self-debt, aucun `.filter`.
# ---------------------------------------------------------------------------


_UUID_SPACE: Final[int] = 2**128


@st.composite
def distinct_uuid_pair(draw: st.DrawFn) -> tuple[UUID, UUID]:
    """Deux `UUID` GARANTIS distincts, SANS rejet.

    Le second est dérivé du premier par un offset NON NUL modulo 2¹²⁸ ⇒
    distinction PAR CONSTRUCTION (jamais `a == b` car 1 ≤ offset ≤ 2¹²⁸−1).
    Préféré à `st.tuples(...).filter(a != b)` : aucun `.filter`, aucun
    `filter_too_much` (esprit de `distinct_currency_pair`).
    """
    a = draw(st.uuids())
    offset = draw(st.integers(min_value=1, max_value=_UUID_SPACE - 1))
    return a, UUID(int=(a.int + offset) % _UUID_SPACE)


@st.composite
def share_request_strategy(draw: st.DrawFn) -> ShareRequestData:
    """`ShareRequestData` VALIDE : paire d'users distincts, ratio ∈ (0,1].

    `short_label` = `st.text(max_size=100)` : miroir du domaine PERMISSIF
    (`ShareRequestData` n'a aucun validator métier — D4 de S09.2 ; le champ
    n'est PAS lu par le calcul). Ce n'est PAS un miroir de la colonne validée
    S09.3 (trim + rejet caractères de contrôle) — inutile ici, le calculator
    ignore `short_label`.
    """
    requested_by, requested_from = draw(distinct_uuid_pair())
    return ShareRequestData(
        source_transaction_id=draw(st.uuids()),
        requested_by=requested_by,
        requested_from=requested_from,
        ratio=draw(personal_share_ratio()),
        short_label=draw(st.text(max_size=100)),
    )


@st.composite
def debt_strategy(draw: st.DrawFn) -> Debt:
    """Une `Debt` VALIDE telle que produite par le calculator, SANS rejet.

    Tire `ratio` PUIS `expense_cents ≥ ⌈1/ratio⌉` ⇒ produit exact ≥ 1 ⇒
    `amount ≥ 1` après `ROUND_HALF_UP` (l'arrondi ne descend pas sous 1 quand
    le produit exact est ≥ 1) ⇒ `NonPositiveDebtAmountError` JAMAIS levé. Donc
    aucun `try/except`/`assume`. Réutilisable E10 (population de `Debt` valides
    pour les properties zero-sum du Settlement).
    """
    sr = draw(share_request_strategy())
    min_cents = int((Decimal(1) / sr.ratio).to_integral_value(rounding=ROUND_CEILING))
    expense = Money(draw(st.integers(min_value=min_cents, max_value=_MONEY_BOUND)), "EUR")
    return DebtCalculator.compute_for_share_request(
        share_request=sr, expense_total=expense, source_account_id=draw(st.uuids())
    )[0]


# Borne réduite pour les splits (vs `_MONEY_BOUND` à ±10 M€) : la somme de
# `_MAX_SPLITS - 1` montants ne doit pas produire un dernier split aberrant,
# et des montants plus petits gardent les exemples lisibles sans masquer de cas
# limite (zero-sum testé sur tout le spectre des signes).
_SPLIT_AMOUNT_BOUND: Final[int] = 10**7
_MIN_SPLITS: Final[int] = 2
_MAX_SPLITS: Final[int] = 5


@st.composite
def balanced_splits_strategy(  # noqa: PLR0913 — paramétrable par conception (réutilisé E09/E10)
    draw: st.DrawFn,
    *,
    currency: Currency | None = None,
    n_splits: int | None = None,
    min_splits: int = _MIN_SPLITS,
    max_splits: int = _MAX_SPLITS,
    distinct_accounts: bool = True,
) -> tuple[Split, ...]:
    """Tuple de `Split` zero-sum (MÊME devise), prêt pour une `Transaction` `confirmed`.

    Tire `n ∈ [min_splits, max_splits]` montants entiers ; les `n-1` premiers
    sont libres, le dernier ferme la somme à 0 (`-Σ` des précédents) ⇒ zero-sum
    EXACT par construction, jamais de rejet `assume`. Devise unique (réutilise
    le code des montants de `money_strategy`) ⇒ pas d'`IncompatibleCurrencyError`.

    `n_splits` (optionnel) FIXE la cardinalité exacte (`min == max == n_splits`),
    convenance pour les consommateurs qui veulent un nombre de jambes déterminé
    (signature de l'AC #117) ; `min_splits`/`max_splits` (plus expressifs) sont
    ignorés quand `n_splits` est fourni.

    `distinct_accounts=True` (défaut) ⇒ un `account_id` par split (forme
    transfert structurelle, `is_transfer` vrai) ; `False` ⇒ tous les splits sur
    le même compte (forme dépense/revenu canonique S07.2). `category_id` est
    posé sur chaque jambe (transaction « catégorisée ») — neutre pour le
    zero-sum, utile aux consommateurs aval.
    """
    cur = currency if currency is not None else draw(st.sampled_from(_CURRENCY_CHOICES))
    lo, hi = (n_splits, n_splits) if n_splits is not None else (min_splits, max_splits)
    n = draw(st.integers(min_value=lo, max_value=hi))
    head = draw(
        st.lists(
            st.integers(min_value=-_SPLIT_AMOUNT_BOUND, max_value=_SPLIT_AMOUNT_BOUND),
            min_size=n - 1,
            max_size=n - 1,
        )
    )
    amounts = [*head, -sum(head)]
    shared_account = uuid4()
    return tuple(
        Split(
            account_id=uuid4() if distinct_accounts else shared_account,
            category_id=uuid4(),
            amount=Money(a, cur),  # type: ignore[arg-type]  # cur ∈ Currency par construction
        )
        for a in amounts
    )


@st.composite
def canonical_expense_splits_strategy(
    draw: st.DrawFn,
    *,
    currency: Currency | None = None,
) -> tuple[Split, ...]:
    """Forme canonique B (ADR 0017) : 1 jambe `funding` (cat NULL, `-Σ`) + N jambes
    `classification` catégorisées (`+a_i`), MÊME compte, zero-sum.

    `is_transfer` False (compte unique), confirmable (toute jambe `classification`
    a une catégorie, ≤ 1 jambe `funding`) et consommatrice (la somme des jambes
    `classification`). `leg_role` est posé EXPLICITEMENT (valeur autoritative,
    comme un mapper) plutôt que dérivé. Pensée pour réuse aval (properties de
    transition S08.5.2 et seeds budget S08.5.3)."""
    cur = currency if currency is not None else draw(st.sampled_from(_CURRENCY_CHOICES))
    acc = uuid4()
    positives = draw(
        st.lists(
            st.integers(min_value=1, max_value=_SPLIT_AMOUNT_BOUND),
            min_size=1,
            max_size=3,
        )
    )
    classification = tuple(
        Split(
            account_id=acc,
            category_id=uuid4(),
            amount=Money(a, cur),  # type: ignore[arg-type]  # cur ∈ Currency par construction
            leg_role="classification",
        )
        for a in positives
    )
    funding = Split(
        account_id=acc,
        category_id=None,
        amount=Money(-sum(positives), cur),  # type: ignore[arg-type]
        leg_role="funding",
    )
    return (funding, *classification)


@st.composite
def transaction_confirmed_strategy(
    draw: st.DrawFn,
    *,
    currency: Currency | None = None,
    distinct_accounts: bool = True,
) -> Transaction:
    """`Transaction` à l'état `confirmed`, zero-sum GARANTI (bâtie sur `balanced_splits_strategy`).

    La construction réussit toujours (le `model_validator` zero-sum est
    satisfait par les splits équilibrés) — c'est le point fixe sur lequel
    s'appuient les properties d'immutabilité (S07.3, P07.3.2) et les invariants
    service (S07.6). Nomenclature parallèle à `transaction_draft_strategy`.
    """
    splits = draw(balanced_splits_strategy(currency=currency, distinct_accounts=distinct_accounts))
    return Transaction(
        id=uuid4(),
        account_id=uuid4(),
        date=draw(st.dates()),
        state=TransactionState.CONFIRMED,
        payee=draw(st.none() | st.text(max_size=20)),
        created_by=uuid4(),
        splits=splits,
        category_id=draw(st.none() | st.uuids()),
        description=draw(st.none() | st.text(max_size=20)),
        tags=tuple(draw(st.lists(st.text(max_size=10), max_size=3))),
        debt_generation_override="default",
        share_request_id=draw(st.none() | st.uuids()),
    )


@st.composite
def transaction_draft_strategy(
    draw: st.DrawFn,
    *,
    currency: Currency | None = None,
    balanced: bool = False,
) -> Transaction:
    """`Transaction` à l'état `draft`, devise unique (gabarit `transaction_confirmed_strategy`).

    `balanced=False` (défaut) ⇒ splits LIBRES (le `draft` tolère `sum != 0`,
    S07.3 `domain.py`) : le `model_validator` zero-sum n'est pas actif hors
    `confirmed`, donc la construction réussit même déséquilibrée. `balanced=True`
    ⇒ réutilise `balanced_splits_strategy` (un `draft` « confirmable », somme
    nulle par construction). Réutilisable E09/E10 (signature paramétrable).
    """
    # cur ∈ Currency par construction (`_CURRENCY_CHOICES` dérive du Literal).
    cur: Currency = (
        currency if currency is not None else draw(st.sampled_from(_CURRENCY_CHOICES))  # type: ignore[assignment]
    )
    if balanced:
        splits = draw(balanced_splits_strategy(currency=cur))
    else:
        n = draw(st.integers(min_value=_MIN_SPLITS, max_value=_MAX_SPLITS))
        splits = tuple(
            Split(
                account_id=uuid4(),
                category_id=draw(st.none() | st.uuids()),
                amount=draw(money_strategy(currency=cur)),
            )
            for _ in range(n)
        )
    return Transaction(
        id=uuid4(),
        account_id=uuid4(),
        date=draw(st.dates()),
        state=TransactionState.DRAFT,
        payee=draw(st.none() | st.text(max_size=20)),
        created_by=uuid4(),
        splits=splits,
        category_id=draw(st.none() | st.uuids()),
        description=draw(st.none() | st.text(max_size=20)),
        tags=tuple(draw(st.lists(st.text(max_size=10), max_size=3))),
        debt_generation_override="default",
        share_request_id=draw(st.none() | st.uuids()),
    )


# ---------------------------------------------------------------------------
# S10.5 — `settlement_scenario_strategy` : population de règlements PURS apurant
# EXACTEMENT un ensemble de dettes entre {A, B}, SANS rejet. C'est l'aboutissement
# de la property zero-sum non-dégénérée explicitement DIFFÉRÉE par S09.5 (#146) :
# l'ensemble des dettes ciblées cesse d'être un singleton (≠ projection
# `personal_share_request` de S09.2). Génère l'INPUT RÉEL du `SettlementValidator`
# (scalaire, S10.2) : des `DebtContext` (clé `debt_id`) + des `SettlementLineInput`,
# JAMAIS un `Debt` domaine — qui n'a pas d'`id` alors que le validateur clé par
# `debt_id`. Réutilisable E11 (overflow F10).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SettlementScenario:
    """Dettes entre {A, B} + lignes qui les apurent EXACTEMENT (full apurement).

    `virtual` ⇒ totaux par direction égaux ⇒ net 0 (équilibré) ; non-virtuel ⇒
    sens unique lo→hi ⇒ net == Σ > 0 et `linked == net`. Toutes les dettes sont
    fraîches (`remaining_cents == montant plein`) et chaque ligne apure sa dette
    intégralement (`amount == remaining`). L'union `{from, to}` vaut toujours
    `{lo, hi}` (cardinalité 2) et la devise est unique (`EUR`) PAR CONSTRUCTION.
    """

    settlement_type: SettlementType
    debt_contexts: tuple[DebtContext, ...]
    lines: tuple[SettlementLineInput, ...]
    linked_transaction_amount_cents: int | None  # None ssi virtual ; sinon abs(net)
    expected_net_transfer_cents: int  # 0 (virtual) / abs(net) (non-virtuel)

    @property
    def contexts_by_id(self) -> dict[UUID, DebtContext]:
        return {c.debt_id: c for c in self.debt_contexts}

    @property
    def counterparties(self) -> frozenset[UUID]:
        return frozenset(u for c in self.debt_contexts for u in (c.from_user_id, c.to_user_id))


def _partition(draw: st.DrawFn, *, total: int, n: int) -> list[int]:
    """N entiers ≥ 1, Σ == ``total`` (cut-points distincts, requiert ``total >= n``).

    Cœur entier de `share_ratios` (cut-points), sans la division /10000 : chaque
    part ≥ 1 ⇒ ``remaining > 0`` PAR CONSTRUCTION (jamais d'`assume`).

    Court-circuite ``n == 1`` : sinon `st.integers(1, total - 1)` est construit
    avec ``total == 1`` ⇒ `st.integers(1, 0)`, que Hypothesis REJETTE à la
    construction (`max_value < min_value`) AVANT de regarder ``min_size=0`` ⇒
    `InvalidArgument` même si aucun cut-point n'est requis. Une seule part = total.
    """
    if n == 1:
        return [total]
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
    return [bounds[i + 1] - bounds[i] for i in range(n)]


@st.composite
def settlement_scenario_strategy(
    draw: st.DrawFn, *, balanced: bool | None = None
) -> SettlementScenario:
    """Scénario de règlement apurant EXACTEMENT un ensemble de dettes entre {A, B}.

    `balanced=True` (ou tiré) ⇒ `virtual` à net 0 : deux directions, totaux par
    direction ÉGAUX (= S), apurés intégralement ⇒ net orienté nul. `balanced=False`
    ⇒ non-virtuel sens unique lo→hi ⇒ net == Σ > 0, `linked == net`.

    SANS rejet (convention repo, S09.5) : réutilise `distinct_uuid_pair` (paire
    {A, B} garantie distincte) et `_partition` (parts ≥ 1 par construction). Tire
    les montants dans `(0, _MONEY_BOUND]` via la partition — aucun `.filter`,
    aucun `assume`. Réutilisable E11 (le validateur est identique).
    """
    a, b = draw(distinct_uuid_pair())  # paire {A, B} garantie distincte (S09.5)
    lo, hi = sorted((a, b), key=lambda u: u.int)  # ordre canonique = celui du validateur
    if balanced is None:
        balanced = draw(st.booleans())

    def _debt(from_u: UUID, to_u: UUID, amount: int) -> tuple[DebtContext, SettlementLineInput]:
        did = draw(st.uuids())  # debt_id frais (uniques : st.uuids ~ collision nulle)
        ctx = DebtContext(
            debt_id=did,
            from_user_id=from_u,
            to_user_id=to_u,
            currency="EUR",
            remaining_cents=amount,
        )
        return ctx, SettlementLineInput(debt_id=did, amount_cents=amount)  # apurement complet

    if balanced:
        # virtual, net 0 : DEUX directions, totaux égaux = S (apurement complet ⇒ net 0).
        n_fwd = draw(st.integers(min_value=1, max_value=3))
        n_bwd = draw(st.integers(min_value=1, max_value=3))
        # S ≥ n par direction ⇒ `_partition` toujours satisfiable.
        s = draw(st.integers(min_value=max(n_fwd, n_bwd), max_value=_MONEY_BOUND))
        fwd = _partition(draw, total=s, n=n_fwd)  # lo→hi
        bwd = _partition(draw, total=s, n=n_bwd)  # hi→lo
        pairs = [_debt(lo, hi, m) for m in fwd] + [_debt(hi, lo, m) for m in bwd]
        ctxs, lines = zip(*pairs, strict=True)
        return SettlementScenario("virtual", tuple(ctxs), tuple(lines), None, 0)

    # non-virtuel : sens unique lo→hi ⇒ net = Σ > 0 ⇒ linked == net (≠ 0, passe la règle 5).
    n = draw(st.integers(min_value=1, max_value=4))
    total = draw(st.integers(min_value=n, max_value=_MONEY_BOUND))
    parts = _partition(draw, total=total, n=n)
    pairs = [_debt(lo, hi, m) for m in parts]
    ctxs, lines = zip(*pairs, strict=True)
    stype: SettlementType = draw(st.sampled_from(["internal_transfer", "external_transfer"]))
    return SettlementScenario(stype, tuple(ctxs), tuple(lines), total, total)
