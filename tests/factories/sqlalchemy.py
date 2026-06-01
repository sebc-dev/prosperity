"""SQLAlchemy-backed factories for integration tests.

Populate this module as modules expose ORM models. The pattern (per
Stratégie de tests §10) is:

    class TransactionFactory(SQLAlchemyModelFactory):
        class Meta:
            model = Transaction
            sqlalchemy_session_persistence = "flush"

The async session wiring (factory.create called inside a sync wrapper
fed by `db_session`) is documented in Stratégie de tests §10.4.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from factory.alchemy import SQLAlchemyModelFactory
from factory.declarations import LazyFunction
from factory.faker import Faker
from factory.helpers import lazy_attribute, post_generation
from pwdlib import PasswordHash

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, AccountMember
from backend.modules.auth.models import User
from backend.modules.budget.models import Category
from backend.modules.transactions.models import Split, Transaction

__all__ = [
    "AccountFactory",
    "AccountMemberFactory",
    "CategoryFactory",
    "SplitFactory",
    "TransactionFactory",
    "UserFactory",
]


_password_hasher = PasswordHash.recommended()

# Default magnitude of a `SplitFactory` leg, shared by the factory field and
# `TransactionFactory`'s zero-sum pair so the two never drift apart.
_DEFAULT_SPLIT_AMOUNT_CENTS = 1000


class UserFactory(SQLAlchemyModelFactory):
    """Persist a `User` with an Argon2id hash derived from a plaintext.

    Callers pass `password="<plaintext>"` to control the secret; otherwise
    a random Faker password is used. The plaintext lives on `Params` so
    factory-boy doesn't forward it to the SQLA model constructor — only
    its derived `password_hash` (an Argon2id digest) is persisted.

    Bind a session at use-site:

        UserFactory._meta.sqlalchemy_session = db_session
        user = UserFactory(password="hunter2")

    NOTE: this assignment mutates a class-level attribute shared across
    every test that loads the module — not thread-safe. Fine while
    pytest runs serially (session-scoped loop, `asyncio_mode=auto`), but
    do not enable `pytest-xdist` (or any intra-worker parallelism) until
    callers migrate to `factory.Factory.build()` plus an explicit session
    pass-through.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        sqlalchemy_session_persistence = "flush"

    email = Faker("email")
    display_name = Faker("name")
    role = "member"

    class Params:
        # Transient: read by `password_hash` below, not forwarded to User.
        password = Faker("password", length=16)

    @lazy_attribute
    def password_hash(self) -> str:
        plaintext: str = self.password  # type: ignore[attr-defined]
        return _password_hasher.hash(plaintext)


class AccountFactory(SQLAlchemyModelFactory):
    """Persist an `Account`.

    Caller sets `owner_id` for a personal account, or leaves it `None` and
    attaches `AccountMemberFactory` rows for a shared one. `household_id`
    defaults to the singleton via the model's column default, so a bare
    `AccountFactory()` needs no household wiring.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Account
        sqlalchemy_session_persistence = "flush"

    name = Faker("company")
    type = AccountType.COURANT
    currency = "EUR"
    owner_id = None


class AccountMemberFactory(SQLAlchemyModelFactory):
    """Persist an `AccountMember`. Caller passes `account_id` + `user_id`.

    WARNING: `default_share_ratio` defaults to `0.5000` — valid ONLY for a
    2-member account (Σ = 1.0000). For ≥3 members the caller MUST pass
    explicit ratios summing to 1.0000; the default would otherwise yield
    Σ ≠ 1 and silently violate the invariant the S05.2 service validates.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = AccountMember
        sqlalchemy_session_persistence = "flush"

    default_share_ratio = Decimal("0.5000")  # 50/50 — 2 members only (see docstring)


class CategoryFactory(SQLAlchemyModelFactory):
    """Persist a `Category`. Caller passes `parent_id=<id>` for a child;
    omit it for a root. `color`/`icon` left NULL by default (UI-assigned).
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Category
        sqlalchemy_session_persistence = "flush"

    name = Faker("word")
    parent_id = None


class SplitFactory(SQLAlchemyModelFactory):
    """Persist a `Split`. Caller passes `transaction_id` + `account_id`.

    `amount_cents`/`currency` default to a single positive EUR leg; pair two
    explicit instances (`-N`/`+N`) for a balanced transaction, or use
    `TransactionFactory` which builds the balanced pair automatically.
    `category_id`/`savings_goal_id` left NULL by default.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Split
        sqlalchemy_session_persistence = "flush"

    amount_cents = _DEFAULT_SPLIT_AMOUNT_CENTS
    currency = "EUR"
    category_id = None
    savings_goal_id = None


class TransactionFactory(SQLAlchemyModelFactory):
    """Persist a `Transaction`; by default attach a **zero-sum** pair of
    splits (one debit `-N`, one credit `+N`, same currency, same account).

    Caller passes the required FKs `account_id` + `created_by`.

    - `TransactionFactory()` -> balanced (`sum(splits.amount_cents) == 0`).
    - `TransactionFactory(splits__amount_cents=5000)` -> balanced at ±5000.
    - `TransactionFactory(splits=False)` -> NO auto-splits (the test adds its
      own, e.g. an unbalanced pair for a negative test).

    `SplitFactory` shares this factory's session (bound together by
    `bound_transaction_factories`), so the post-generation splits flush in the
    same session as their transaction — `obj.id` is available post-flush.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Transaction
        sqlalchemy_session_persistence = "flush"

    date = Faker("date_object")
    state = "draft"
    payee = Faker("company")
    description = None
    category_id = None
    tags = LazyFunction(list)
    debt_generation_override = "default"

    # `obj` (the built `Transaction`) is left unannotated: factory-boy passes
    # the instance as the first positional arg, but pyright models the hook as
    # a method and would reject any non-`self` type there. The remaining params
    # and the return are typed, so no blanket `# type: ignore` is needed.
    @post_generation
    def splits(obj, create: bool, extracted: object, **kwargs: object) -> None:  # noqa: N805
        # `extracted is False` -> caller opts out of the auto balanced pair.
        if not create or extracted is False:
            return
        amount = cast(int, kwargs.get("amount_cents", _DEFAULT_SPLIT_AMOUNT_CENTS))
        currency = cast(str, kwargs.get("currency", "EUR"))
        transaction = cast(Transaction, obj)
        # The debit/credit reference the transaction's own account by default;
        # equal magnitudes with opposite signs keep the pair zero-sum.
        SplitFactory(
            transaction_id=transaction.id,
            account_id=transaction.account_id,
            amount_cents=-amount,
            currency=currency,
        )
        SplitFactory(
            transaction_id=transaction.id,
            account_id=transaction.account_id,
            amount_cents=amount,
            currency=currency,
        )
