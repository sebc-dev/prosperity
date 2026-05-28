"""Trusted-proxy aware client-IP extraction.

`client_ip_for(request, settings)` returns the best-guess originating
client IP, honouring `X-Forwarded-For` only when the immediate transport
peer is in `settings.trusted_proxy_ips`. Otherwise XFF is ignored — any
direct client can set the header to anything they like.

Use this everywhere a log line records `"client_ip": …`. Reading
`request.client.host` directly behind a reverse proxy logs the proxy
IP for every request — useless for forensic, and structurally defeats
any future IP-based rate limit that would key on it.
"""

from __future__ import annotations

from ipaddress import AddressValueError, IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ipaddress import IPv4Network, IPv6Network

    from fastapi import Request

    from backend.config import Settings


def _parse_ip(raw: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(raw)
    except (ValueError, AddressValueError):
        return None


def _in_trusted_networks(
    addr: IPv4Address | IPv6Address,
    networks: tuple[IPv4Network | IPv6Network, ...],
) -> bool:
    for net in networks:
        # `IPv4Address in IPv6Network` (and vice versa) raises TypeError
        # — treat cross-family as "not a match" rather than crashing.
        try:
            if addr in net:
                return True
        except TypeError:
            continue
    return False


def client_ip_for(  # noqa: PLR0911 — each return is a documented branch of the trusted-proxy decision tree; collapsing would obscure the anti-spoofing rationale.
    request: Request, settings: Settings
) -> str | None:
    """Best-guess originating client IP, with trusted-proxy XFF handling.

    Returns `None` if `request.client` is `None` (ASGI scope without a
    peer — e.g. a TestClient call that didn't set one). Otherwise:

    - No `TRUSTED_PROXY_IPS` configured → return the transport peer IP
      as-is. `X-Forwarded-For` is never consulted; trusting it without
      a proxy configured would let any client forge the audit trail.
    - Transport peer is in `trusted_proxy_ips` → walk the XFF chain
      right-to-left, return the first IP not in `trusted_proxy_ips`.
      That is the real client just upstream of our trusted-proxy
      chain. If every entry is itself trusted, fall back to the
      leftmost (best guess of the originating client).
    - Transport peer is NOT in `trusted_proxy_ips` → return the
      transport peer IP. XFF is ignored — same anti-spoofing rationale
      as the no-config case.
    """
    if request.client is None:
        return None
    raw_ip = request.client.host

    networks = settings.trusted_proxy_ips
    if not networks:
        return raw_ip

    peer = _parse_ip(raw_ip)
    if peer is None or not _in_trusted_networks(peer, networks):
        return raw_ip

    xff = request.headers.get("X-Forwarded-For")
    if not xff:
        return raw_ip

    entries = [part.strip() for part in xff.split(",") if part.strip()]
    if not entries:
        return raw_ip

    for entry in reversed(entries):
        ip = _parse_ip(entry)
        if ip is None:
            # Malformed hop — skip silently rather than crashing the
            # log line. A proxy injecting garbage into XFF should not
            # break the request.
            continue
        if not _in_trusted_networks(ip, networks):
            return entry

    # Entire chain is itself in the trusted set (or unparseable). The
    # leftmost entry is the best-effort originating client.
    return entries[0]
