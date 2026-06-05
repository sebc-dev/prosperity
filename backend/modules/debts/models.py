"""ORM models for the debts module (E09 socle persisté).

Premiers modèles du module (qui n'avait que `__init__.py` + `public.py`).
Archétype structurel des modules à `domain.py` : `models.py` est du SQLA
**pur**, sans logique métier — le calcul de dette (S09.2 `DebtCalculator`),
la matérialisation (S09.3) et la lecture dashboard (S09.4) vivent ailleurs.

Deux tables :

- `debts` — la **projection serveur** (ADR 0002), matérialisée par le
  serveur, lecture seule côté client. Pas de route `POST /debts` /
  `PATCH /debts/amount` : une dette est *dérivée*, jamais saisie. Seul
  `share_ratio` deviendra mutable (E10/E11). En E09, aucune mutation.
- `share_requests` — l'**acte explicite** par lequel le propriétaire d'un
  compte personnel matérialise une dette (« partage cette dépense avec X »).

Layering (ADR 0005, contrat 1) : `debts` est au-dessus de `transactions`
(arc directionnel légitime `debts → transactions.public`, ajouté en S09.3).
Les FK vers `users`/`accounts`/`transactions` sont déclarées **par chaîne**
(`ForeignKey("transactions.id")`), résolues au runtime par SQLAlchemy SANS
import Python des classes ORM — aucune relationship cross-module, donc le
graphe import-linter n'est pas inversé (cf. note S07.4 sur la FK dormante).

Surface publique : ce module n'est importable que depuis `debts` (contrat
`2-debts` ; `debts.models` listé en `forbidden_modules` des pairs).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    UUID,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base


class Debt(Base):
    """Une dette dérivée entre deux users du foyer (CONTEXT.md §Debt, ADR 0002).

    **Projection serveur** : matérialisée par le serveur à partir d'une
    transaction source (dépense sur compte commun « overflow », ou
    `ShareRequest` sur compte personnel). Lecture seule côté client — aucune
    route de mutation directe en E09 (le calcul pur vit en S09.2, la
    matérialisation one-shot synchrone en S09.3).

    `from_user_id` (débiteur) / `to_user_id` (créancier) → `users.id`
    `ON DELETE RESTRICT` (F02 — un user est désactivé, jamais hard-deleted).
    Le CHECK `ck_debts_no_self_debt` (`from_user_id <> to_user_id`) transforme
    l'invariant « pas d'auto-dette » (property S09.5) en garantie DB.

    `amount_cents` (`BigInteger`, gabarit `splits.amount_cents`, centimes,
    cohérence `shared/money.py`) + `currency` (`String(3)`) : colonnes brutes
    mappées vers/depuis `Money` par le service. CHECK `ck_debts_amount_positive`
    (`amount_cents > 0`) : garde-fou contre un montant nul/négatif (ex. tx de
    remboursement mal projetée) — une dette matérialisée porte toujours un
    montant strictement positif.

    `account_id` → `accounts.id` `ON DELETE RESTRICT` : le **compte source**
    de la dette (compte commun en overflow, ou compte personnel de l'émetteur
    d'une `ShareRequest`). Dénormalisé ici = clé du bucket `user_debt_{user_id}`
    (ADR 0003). RESTRICT : un compte référencé par une projection vivante ne
    peut pas être hard-deleted. ⚠️ **Masqué au débiteur** à la lecture (S09.4,
    review #22 B1) au même titre que `source_transaction_id` : le compte
    personnel source ne doit pas fuiter.

    `source_transaction_id` → `transactions.id` `ON DELETE CASCADE` :
    supprimer/void la tx source nettoie sa projection. FK par chaîne
    (`debts → transactions` est un arc directionnel légitime du contrat 1,
    mais déclaré sans import de classe pour ne pas inverser le graphe).

    `origin` (`shared_account_overflow` | `personal_share_request`) :
    `String` **SANS CHECK** — le set fermé est verrouillé au boundary Pydantic
    (gabarit `period_kind`/`scope` de S08.1), gardé évolutif (l'overflow F10
    élargit le set en E11) sans migration.

    `share_ratio` (`Numeric(5, 4)`, default `1.0`) : quote-part de la dette.
    `Decimal` (jamais float). Default Python (pas `server_default`) pour la
    parité create_all/Alembic du snapshot.

    `materialization_trace` (`String`, NULL) : marqueur forensique
    **server-only** — horodatage / debug « pourquoi cette dette existe ».
    **JAMAIS exposé via API** (exclu de tout DTO, S09.4 allowlist). En MVP il
    n'y a pas de calc run (insert one-shot synchrone) ; le champ *préfigure*
    l'id de calc run du mécanisme de matérialisation batch E11 (renommé depuis
    `materialized_by_calc_run`, review #22).
    """

    __tablename__ = "debts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_debts_from_user_id_users",
        ),
        nullable=False,
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_debts_to_user_id_users",
        ),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
            name="fk_debts_account_id_accounts",
        ),
        nullable=False,
    )
    source_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            ondelete="CASCADE",
            name="fk_debts_source_transaction_id_transactions",
        ),
        nullable=False,
    )
    # Set fermé (`shared_account_overflow`/`personal_share_request`) verrouillé
    # au boundary Pydantic, PAS en SQL (gabarit `period_kind`/`scope`) : le set
    # s'élargit (overflow F10, E11) sans migration.
    origin: Mapped[str] = mapped_column(String, nullable=False)
    share_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("1.0"),
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Server-only forensic marker — JAMAIS exposé via API (S09.4 allowlist).
    # Préfigure l'id de calc run de la matérialisation batch E11.
    materialization_trace: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        # Chaque FK vers `users` indexée (gabarit `ix_*`) : sans index, un DELETE
        # RESTRICT d'un user seq-scan `debts`. Les deux côtés de la dette + la tx
        # source sont les chemins de lecture du dashboard (S09.4) et du nettoyage
        # CASCADE. `account_id` n'a PAS d'index standalone à ce stade : aucune
        # requête ne le filtre (clé de bucket dérivée au service, pas en SQL).
        Index("ix_debts_from_user_id", "from_user_id"),
        Index("ix_debts_to_user_id", "to_user_id"),
        Index("ix_debts_source_transaction_id", "source_transaction_id"),
        # CHECK défensifs : transforment des invariants testés (S09.5) en
        # garanties DB. `name="..."` (pas le `ck_debts_...` complet) → la
        # NAMING_CONVENTION `ck_%(table_name)s_%(constraint_name)s` préfixe à
        # `ck_debts_no_self_debt` / `ck_debts_amount_positive`, à matcher
        # byte-for-byte dans 0014 via `op.f(...)` (gabarit
        # `ck_transactions_debt_generation_override`).
        CheckConstraint("from_user_id <> to_user_id", name="no_self_debt"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
    )


class ShareRequest(Base):
    """Acte explicite de partage d'une dépense personnelle (CONTEXT.md
    §ShareRequest).

    Le propriétaire d'un **compte personnel** matérialise une dette en
    demandant à un autre user de prendre en charge une quote-part d'une de ses
    transactions. C'est la **direction canonique** du lien
    `ShareRequest.source_transaction_id → Transaction` ;
    `transactions.share_request_id` (posée nullable en S07.4 / 0010) en est le
    *handle d'édition*, activé en FK par cette story (0014, `SET NULL`).

    `source_transaction_id` → `transactions.id` `ON DELETE CASCADE` :
    supprimer/void la tx source nettoie ses `ShareRequest`. FK par chaîne
    (aucun import de classe — voir docstring module).

    `requested_by` (= owner du compte source) / `requested_from` (débiteur) →
    `users.id` `ON DELETE RESTRICT` (F02). CHECK `ck_share_requests_no_self`
    (`requested_by <> requested_from`) : on ne se partage pas une dépense à
    soi-même.

    `ratio` (`Numeric(5, 4)`) : quote-part demandée. `Decimal` (jamais float).

    `short_label` (`String(100)`) : libellé court de la demande. La
    **validation serveur** (trim + rejet des caractères de contrôle) vit au
    boundary Pydantic (S09.3) — la colonne ne porte qu'une borne de longueur.

    `created_at` server_default ; `revoked_at` (`DateTime`, NULL) : la
    révocation ne supprime PAS la SR (set `revoked_at`, S09.3) — la tx garde la
    trace du lien via `share_request_id` pointant une SR `revoked`, c'est voulu.

    **Unique partiel** `(source_transaction_id, requested_from) WHERE
    revoked_at IS NULL` : interdit deux `ShareRequest` *actives* sur la même
    paire (tx, débiteur). Une SR révoquée n'occupe plus le créneau → une
    nouvelle demande sur la même paire est possible (gabarit
    `uq_invitations_pending_email`).
    """

    __tablename__ = "share_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            ondelete="CASCADE",
            name="fk_share_requests_source_transaction_id_transactions",
        ),
        nullable=False,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_share_requests_requested_by_users",
        ),
        nullable=False,
    )
    requested_from: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_share_requests_requested_from_users",
        ),
        nullable=False,
    )
    ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    short_label: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Unique partiel : une seule SR ACTIVE par (tx source, débiteur). Une SR
        # révoquée (`revoked_at IS NOT NULL`) sort de l'index → libère le créneau
        # (gabarit `uq_invitations_pending_email`). `postgresql_where` doit
        # matcher la migration byte-for-byte (parité create_all/Alembic).
        Index(
            "uq_share_requests_active",
            "source_transaction_id",
            "requested_from",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # FK `users` indexées pour les DELETE RESTRICT (sans index, seq-scan).
        # Pas d'index standalone sur `source_transaction_id` : l'unique partiel
        # ci-dessus l'a en colonne de tête (couvre les lookups de SR *actives*) ;
        # le CASCADE d'une tx source peut retomber en seq-scan sur les lignes
        # révoquées, accepté (révocation rare, table petite — l'issue n'énumère
        # que les index `(requested_from)`/`(requested_by)`).
        Index("ix_share_requests_requested_from", "requested_from"),
        Index("ix_share_requests_requested_by", "requested_by"),
        # On ne se partage pas une dépense à soi-même (gabarit `ck_debts_no_self_debt`).
        CheckConstraint("requested_by <> requested_from", name="no_self"),
    )


class Settlement(Base):
    """Règlement d'une ou plusieurs `Debt` (CONTEXT.md §Settlement, ADR 0011).

    Matérialise l'apurement multi-debt. Trois `type` (set fermé verrouillé au
    boundary Pydantic S10.2/S10.4, PAS en SQL — gabarit `Debt.origin`) :
    `internal_transfer` / `external_transfer` (liés à une `Transaction` de
    virement **préalable** via `linked_transaction_id`) ; `virtual`
    (compensation comptable sans mouvement d'argent, `linked_transaction_id`
    NULL). Aucun état ajouté sur `Debt` (ADR 0002/0011) : le solde restant se
    calcule par différence (S10.3), `Debt` reste une projection read-only.

    `household_id` → `household.id` (singleton ADR 0010) : clé de scoping foyer
    (gabarit `accounts.household_id`, sans `ondelete` ni index — le foyer n'est
    jamais supprimé). Le bucket sync `user_debt_{user_id}` (E13) sera dérivé des
    `debt_id` référencés par les `SettlementLine`, pas de `household_id`
    (glossaire §SettlementLine).

    `created_by` → `users.id` `ON DELETE RESTRICT` (F02 — un user est désactivé,
    jamais hard-deleted), indexé comme toute FK RESTRICT vers `users`.

    `created_at` server_default (horodatage technique) ; `settled_at` (`Date`)
    NOT NULL : la **date métier** du règlement, distincte de `created_at`.

    `linked_transaction_id` → `transactions.id` `ON DELETE RESTRICT`,
    **nullable**, par chaîne (aucune `relationship` inverse sur `transactions`,
    graphe import-linter non inversé) : le virement existe comme `Transaction`
    préalable (ADR 0011), le `Settlement` y est lié ensuite ; `RESTRICT` pour
    qu'une suppression de tx n'efface pas silencieusement un règlement. Indexé
    (chemin du `RESTRICT`).

    `note` (`Text`, nullable) : commentaire libre — PII potentielle, à filtrer
    dans les DTO (S10.4).

    Le CHECK `ck_settlements_virtual_no_link` matérialise le **biconditionnel**
    « `linked_transaction_id IS NULL` ⟺ `type = 'virtual'` » : rejette à la fois
    un `virtual` lié à une tx et un non-virtuel sans lien. Le littéral `'virtual'`
    y apparaît comme contrainte **relationnelle** type↔lien (pas une énumération
    du set de `type`, qui reste hors SQL).
    """

    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("household.id", name="fk_settlements_household_id_household"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_settlements_created_by_users",
        ),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    settled_at: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # Set fermé (`internal_transfer`/`external_transfer`/`virtual`) verrouillé
    # au boundary Pydantic, PAS en SQL (gabarit `Debt.origin`). Le littéral
    # 'virtual' n'apparaît QUE dans le CHECK relationnel ci-dessous.
    type: Mapped[str] = mapped_column(String, nullable=False)
    linked_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            ondelete="RESTRICT",
            name="fk_settlements_linked_transaction_id_transactions",
        ),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # FK RESTRICT indexées (sans index, un DELETE seq-scan `settlements`) :
        # `linked_transaction_id` (chemin du RESTRICT tx) et `created_by`
        # (gabarit de toute FK RESTRICT→users du codebase). `household_id` n'a
        # PAS d'index (singleton jamais supprimé, gabarit `accounts.household_id`).
        Index("ix_settlements_linked_transaction_id", "linked_transaction_id"),
        Index("ix_settlements_created_by", "created_by"),
        # Biconditionnel : lien NULL ⟺ type == 'virtual' (les deux sens).
        CheckConstraint(
            "(type = 'virtual') = (linked_transaction_id IS NULL)",
            name="virtual_no_link",
        ),
    )


class SettlementLine(Base):
    """Ligne d'un `Settlement` apurant une portion d'une `Debt` (CONTEXT.md
    §SettlementLine).

    `amount_cents` (`BigInteger`) **strictement positif** (CHECK
    `ck_settlement_lines_amount_positive`, décision D-SIGN affinant l'ADR 0011) :
    apure une portion d'**une** `Debt` dans le sens propre de cette dette. Le
    nettage bidirectionnel est porté par l'**orientation intrinsèque de chaque
    `Debt`** (`from_user_id`/`to_user_id`), PAS par un signe sur la ligne — la
    formule du solde restant `remaining = debt.amount_cents − SUM(lines.amount_cents)`
    (S10.3) et l'AC « no over-settlement » exigent des lignes dans `[0, amount]`
    par dette. Le « montant net viré » se calcule au validateur pur (S10.2) par
    `Σ amount × signe_direction(debt)`.

    `settlement_id` → `settlements.id` `ON DELETE CASCADE` : supprimer un
    `Settlement` nettoie ses lignes (agrégat ligne-fille). Indexé.

    `debt_id` → `debts.id` `ON DELETE CASCADE` : si la `Debt` source disparaît
    (révocation de `share_request` S09.3, ou CASCADE depuis la tx d'origine),
    ses lignes d'apurement n'ont plus de sens — la projection est régénérable
    (cohérent avec la suppression dure des `Debt`). Indexé : clé du calcul
    `remaining` (S10.3) **et** du CASCADE. ⚠️ Un `Settlement` non-virtuel peut
    subsister sans lignes après ce CASCADE — le virement reste tracé par
    `linked_transaction_id` (`RESTRICT`) ; comportement assumé (encart ADR 0011).

    `currency` (`String(3)`) dupliquée depuis la `Debt` : garde-fou de cohérence
    **applicatif** (le validateur S10.2 exige une devise unique sur tout le
    règlement) et évite un join `debts` à l'agrégation du solde restant (S10.3).

    FK par chaîne, aucune `relationship` (CASCADE = garantie DB ; doctrine
    `models.py` SQLA pur). Le service S10.2 insère les lignes explicitement.
    """

    __tablename__ = "settlement_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    settlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "settlements.id",
            ondelete="CASCADE",
            name="fk_settlement_lines_settlement_id_settlements",
        ),
        nullable=False,
    )
    debt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "debts.id",
            ondelete="CASCADE",
            name="fk_settlement_lines_debt_id_debts",
        ),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    __table_args__ = (
        Index("ix_settlement_lines_debt_id", "debt_id"),
        Index("ix_settlement_lines_settlement_id", "settlement_id"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
    )
