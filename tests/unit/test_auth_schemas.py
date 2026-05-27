"""Unit tests for `backend.modules.auth.schemas` (follow-up #55)."""

from __future__ import annotations

import dns.resolver
import email_validator
import pytest
from pydantic import SecretStr, ValidationError

from backend.modules.auth.schemas import LoginRequest


def test_login_request_normalizes_email_domain_to_lowercase() -> None:
    req = LoginRequest(email="User@Example.COM", password=SecretStr("x"))
    assert req.email == "User@example.com"


def test_login_request_malformed_email_raises_validation_error() -> None:
    # Pins the 422-on-malformed vs 401-on-unknown channel: kept as-is
    # (Option A). The rate-limit landing in S02.5 caps exploitation.
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password=SecretStr("x"))


def test_login_request_validation_does_not_trigger_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EmailStr validation MUST NOT hit DNS — anti-timing-oracle pin (#55).

    Pydantic v2 calls `email_validator.validate_email(..., check_deliverability=False)`
    (see `pydantic/networks.py`), which short-circuits the lazy `dns.resolver`
    import inside `email_validator`. If a future change (Pydantic flips the
    default, swap `EmailStr` for `NameEmail`, custom validator with
    `check_deliverability=True`) reintroduces DNS, the latency would depend
    on whether the domain exists and leak email validity independently of
    the constant-time password check at `/auth/login`.
    """
    calls: list[dict[str, object]] = []
    original_validate = email_validator.validate_email

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return original_validate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(email_validator, "validate_email", spy)

    def fail_on_resolve(
        self: dns.resolver.Resolver,
        qname: object,
        rdtype: object = "A",
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            f"DNS resolution attempted for {qname!r}/{rdtype!r} during EmailStr validation"
        )

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", fail_on_resolve)

    LoginRequest(email="user@example.com", password=SecretStr("x"))

    assert calls, "Pydantic did not invoke email_validator.validate_email"
    for kwargs in calls:
        assert kwargs.get("check_deliverability") is False, (
            f"deliverability check not disabled: kwargs={kwargs!r}"
        )
