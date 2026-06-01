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

from factory.alchemy import SQLAlchemyModelFactory
from factory.faker import Faker
from factory.helpers import lazy_attribute
from pwdlib import PasswordHash

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, AccountMember
from backend.modules.auth.models import User
from backend.modules.budget.models import Category

__all__ = ["AccountFactory", "AccountMemberFactory", "CategoryFactory", "UserFactory"]


_password_hasher = PasswordHash.recommended()


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
