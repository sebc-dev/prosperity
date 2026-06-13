"""HTTP transport layer for the sse module — internal to `sse`.

Cross-module callers must go through `backend.modules.sse.public` (which exposes
nothing — `sse` is consumer-only); the import-linter contract `2-sse` forbids
reaching into this subpackage.
"""
