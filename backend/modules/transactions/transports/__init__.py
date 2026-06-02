"""HTTP transport layer for the transactions module — internal to `transactions`.

Cross-module callers must go through `backend.modules.transactions.public`;
the import-linter contract `2-transactions` forbids reaching into this subpackage.
"""
