"""HTTP transport layer for the accounts module — internal to `accounts`.

Cross-module callers must go through `backend.modules.accounts.public`;
the import-linter contract forbids reaching into this subpackage.
"""
