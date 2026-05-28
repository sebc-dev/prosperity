"""Unit tests for `backend.shared.http.client_ip_for` (follow-up S03.3 #69).

`client_ip_for` is the seam every `client_ip` log line goes through.
The matrix below pins:

* `TRUSTED_PROXY_IPS` empty → XFF never consulted (anti-spoofing default).
* Peer outside trusted set → XFF ignored (defense-in-depth: an attacker
  who reaches the box directly cannot forge the log entry).
* Peer inside trusted set → rightmost-untrusted XFF entry wins (chained
  proxies are stripped; the actual originating client surfaces).
* Malformed XFF entries, IPv6 chains, cross-family CIDRs all behave
  without raising — a single garbage hop must not break a request.

A regression here is a silent forensic / rate-limit hole, so the tests
are paranoid by design.
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import Any

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from backend.config import Settings
from backend.shared.http import client_ip_for


def _make_request(
    *,
    client_host: str | None,
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a Starlette `Request` with a minimal ASGI scope.

    `Request` (the FastAPI re-export) is just `starlette.requests.Request`,
    so constructing it directly avoids spinning up a TestClient.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "client": (client_host, 0) if client_host is not None else None,
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
        ],
    }
    return Request(scope)


def _settings_with_trusted(*cidrs: str) -> Settings:
    return Settings(trusted_proxy_ips=cidrs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. No trusted proxies configured → XFF never consulted
# ---------------------------------------------------------------------------


def test_no_trusted_proxies_returns_raw_client_host() -> None:
    settings = _settings_with_trusted()
    request = _make_request(client_host="203.0.113.5")
    assert client_ip_for(request, settings) == "203.0.113.5"


def test_no_trusted_proxies_ignores_xff_even_if_present() -> None:
    """Anti-spoofing default: any direct client can set XFF.

    Without a trusted-proxy whitelist, honouring XFF would let any
    attacker pick the IP that lands in the log.
    """
    settings = _settings_with_trusted()
    request = _make_request(
        client_host="203.0.113.5",
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


def test_request_without_client_returns_none() -> None:
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(client_host=None)
    assert client_ip_for(request, settings) is None


# ---------------------------------------------------------------------------
# 2. Peer outside trusted set → XFF ignored
# ---------------------------------------------------------------------------


def test_untrusted_peer_with_xff_falls_back_to_raw() -> None:
    """A client connecting directly cannot dictate `client_ip`.

    The peer is on the public Internet (203.0.113.5) and not inside
    our trusted CIDR — XFF gets ignored even though it's set.
    """
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="203.0.113.5",
        headers={"X-Forwarded-For": "198.51.100.1"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


# ---------------------------------------------------------------------------
# 3. Trusted peer + XFF → return rightmost untrusted hop
# ---------------------------------------------------------------------------


def test_trusted_peer_single_xff_entry() -> None:
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="10.0.0.7",
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


def test_trusted_peer_chained_proxies_returns_rightmost_untrusted() -> None:
    """Two reverse-proxies in series → the IP just upstream of them wins.

    XFF is appended-to as the request travels: leftmost is the
    originating client (potentially spoofed), rightmost is the most
    recent hop. Walking right-to-left and skipping our own trusted
    chain gives the first untrusted entry — the actual client.
    """
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="10.0.0.7",
        headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.99"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


def test_trusted_peer_no_xff_returns_raw_peer() -> None:
    """The proxy didn't set XFF (misconfigured) → log the proxy itself."""
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(client_host="10.0.0.7")
    assert client_ip_for(request, settings) == "10.0.0.7"


def test_trusted_peer_empty_xff_returns_raw_peer() -> None:
    """Whitespace-only XFF is equivalent to missing — log the peer."""
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="10.0.0.7",
        headers={"X-Forwarded-For": "   ,  "},
    )
    assert client_ip_for(request, settings) == "10.0.0.7"


def test_trusted_peer_xff_all_trusted_falls_back_to_leftmost() -> None:
    """Pathological config: every hop is itself in `trusted_proxy_ips`.

    The leftmost entry is the best guess of the originating client.
    """
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="10.0.0.7",
        headers={"X-Forwarded-For": "10.1.1.1, 10.2.2.2, 10.3.3.3"},
    )
    assert client_ip_for(request, settings) == "10.1.1.1"


def test_trusted_peer_malformed_xff_entry_is_skipped() -> None:
    """A garbage hop must not crash the request — skip + keep walking."""
    settings = _settings_with_trusted("10.0.0.0/8")
    request = _make_request(
        client_host="10.0.0.7",
        headers={"X-Forwarded-For": "203.0.113.5, not-an-ip, 10.0.0.99"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


# ---------------------------------------------------------------------------
# 4. IPv6 paths
# ---------------------------------------------------------------------------


def test_trusted_ipv6_peer_with_ipv6_xff() -> None:
    settings = _settings_with_trusted("fd00::/8")
    request = _make_request(
        client_host="fd00::1",
        headers={"X-Forwarded-For": "2001:db8::5"},
    )
    assert client_ip_for(request, settings) == "2001:db8::5"


def test_cross_family_cidr_does_not_raise() -> None:
    """`IPv4Address in IPv6Network` raises TypeError — must be caught.

    Mixing families in `TRUSTED_PROXY_IPS` is valid config (multi-stack
    deployments). The helper treats cross-family as "not a match" and
    keeps going.
    """
    settings = _settings_with_trusted("fd00::/8")  # v6 net only
    request = _make_request(
        client_host="10.0.0.7",  # v4 peer
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    # Peer is not in any trusted v6 net → XFF ignored, return raw.
    assert client_ip_for(request, settings) == "10.0.0.7"


# ---------------------------------------------------------------------------
# 5. Multiple trusted CIDRs
# ---------------------------------------------------------------------------


def test_multiple_trusted_cidrs() -> None:
    settings = _settings_with_trusted("10.0.0.0/8", "192.168.0.0/16")
    request = _make_request(
        client_host="192.168.1.1",
        headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.99"},
    )
    assert client_ip_for(request, settings) == "203.0.113.5"


# ---------------------------------------------------------------------------
# 6. Settings parsing — CSV → tuple[IPNetwork, ...]
# ---------------------------------------------------------------------------


def test_trusted_proxy_csv_parses_into_networks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8,192.168.0.0/16, fd00::/8")
    settings = Settings()
    assert settings.trusted_proxy_ips == (
        IPv4Network("10.0.0.0/8"),
        IPv4Network("192.168.0.0/16"),
        IPv6Network("fd00::/8"),
    )


def test_trusted_proxy_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default is empty tuple — XFF ignored unless explicitly opted-in."""
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    settings = Settings()
    assert settings.trusted_proxy_ips == ()


def test_trusted_proxy_invalid_cidr_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mistyped CIDR fails startup — surfacing the typo loudly is the point."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8,not-a-network")
    with pytest.raises(ValidationError):
        Settings()


def test_trusted_proxy_empty_csv_yields_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TRUSTED_PROXY_IPS=` (or just whitespace) → still empty."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "  ,   ,")
    settings = Settings()
    assert settings.trusted_proxy_ips == ()
