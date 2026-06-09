"""Unit tests for the upload size cap `_enforce_size_cap` (S12.4 D13).

The cap rejects oversized OR unbounded uploads with 413 BEFORE the body is read
(anti-DoS, mirror of the parser's `MAX_OFX_BYTES`). The "Content-Length absent →
reject" path is the load-bearing one — httpx always sets the header, so the
route-level integration tests can't exercise it; here we drive the guard directly
with forged request scopes.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from backend.transports import imports_http
from backend.transports.imports_http import MAX_REQUEST_BYTES, _enforce_size_cap


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "headers": headers})


def test_size_cap_allows_within_limit() -> None:
    _enforce_size_cap(_request([(b"content-length", b"1024")]))  # no raise


def test_size_cap_allows_exactly_at_limit() -> None:
    _enforce_size_cap(_request([(b"content-length", str(MAX_REQUEST_BYTES).encode())]))


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param([], id="absent"),
        pytest.param([(b"content-length", b"")], id="empty"),
        pytest.param([(b"content-length", b"not-a-number")], id="non_digit"),
        pytest.param([(b"content-length", str(MAX_REQUEST_BYTES + 1).encode())], id="over_cap"),
    ],
)
def test_size_cap_rejects(headers: list[tuple[bytes, bytes]]) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _enforce_size_cap(_request(headers))
    assert exc_info.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert exc_info.value.detail == imports_http._PAYLOAD_TOO_LARGE
