"""Garde STATIQUE anti-fuite du token dans les logs (S17.1, P17.1.5, F4).

Le token SSE transite en query param (loggable). Au-delà de la redaction proxy
(runbook), on verrouille côté application que `modules/sse` ne référence **jamais**
`request.url` brut — un grep statique du source (plus robuste qu'un `caplog`
runtime, qui ne couvre que les chemins exercés)."""

from __future__ import annotations

import pathlib


def test_sse_module_never_references_raw_request_url() -> None:
    sse_dir = pathlib.Path(__file__).resolve().parents[2] / "backend" / "modules" / "sse"
    offenders = [
        f.relative_to(sse_dir.parents[3])
        for f in sse_dir.rglob("*.py")
        if "request.url" in f.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"modules/sse référence request.url (risque de fuite du token) : {offenders}"
    )
