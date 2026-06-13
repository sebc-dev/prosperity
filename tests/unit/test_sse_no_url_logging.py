"""Garde STATIQUE anti-fuite du token dans les logs (S17.1, P17.1.5, F4).

Le token SSE transite en query param (loggable). Au-delà de la redaction proxy
(runbook), on verrouille côté application que `modules/sse` ne référence **jamais**
`request.url` brut — un grep statique du source (plus robuste qu'un `caplog`
runtime, qui ne couvre que les chemins exercés)."""

from __future__ import annotations

import pathlib
import re

_SSE_DIR = pathlib.Path(__file__).resolve().parents[2] / "backend" / "modules" / "sse"

# Un appel de log/print (`logger.info(...)`, `logging.warning(...)`, `print(...)`).
_LOG_CALL = re.compile(r"\b(?:logger|logging|log|print)\b")
# Ce qui ne doit JAMAIS apparaître dans un tel appel : l'URL brute ou le token.
_SENSITIVE = re.compile(r"request\.url|token")


def test_sse_module_never_references_raw_request_url() -> None:
    offenders = [
        f.relative_to(_SSE_DIR.parents[3])
        for f in _SSE_DIR.rglob("*.py")
        if "request.url" in f.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"modules/sse référence request.url (risque de fuite du token) : {offenders}"
    )


def test_sse_module_never_logs_token_or_url() -> None:
    # Élargit le verrou : aucune ligne du module ne doit combiner un appel de log/print
    # avec le token ou l'URL (la promesse du runbook : « ni request.url ni le token »).
    offenders: list[str] = []
    for f in _SSE_DIR.rglob("*.py"):
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _LOG_CALL.search(line) and _SENSITIVE.search(line):
                offenders.append(f"{f.name}:{lineno}")
    assert not offenders, f"modules/sse logge le token/l'URL (risque de fuite) : {offenders}"
