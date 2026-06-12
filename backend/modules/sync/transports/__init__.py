"""HTTP transport layer for the sync module — internal to `sync`.

Cross-module callers must go through `backend.modules.sync.public`;
the import-linter contract `2-sync` forbids reaching into this subpackage.
"""
