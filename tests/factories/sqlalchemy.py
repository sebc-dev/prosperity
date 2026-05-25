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

from factory.alchemy import SQLAlchemyModelFactory
from factory.faker import Faker
from factory.helpers import lazy_attribute
from pwdlib import PasswordHash

from backend.modules.auth.models import User

__all__ = ["UserFactory"]


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
