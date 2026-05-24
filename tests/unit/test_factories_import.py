"""factory-boy + factories package import smoke."""

import factory

from tests.factories import domain, sqlalchemy


def test_factory_boy_importable() -> None:
    assert hasattr(factory, "Factory")


def test_factories_packages_importable() -> None:
    assert hasattr(domain, "__all__")
    assert hasattr(sqlalchemy, "__all__")
