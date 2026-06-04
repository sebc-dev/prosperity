"""Service layer for the debts module (S09.3+).

Cross-module orchestration of the share-request flow lives here: validating the
act, inserting the `ShareRequest`, and materialising the `Debt` via the pure
`DebtCalculator` (S09.2). Transaction-agnostic — the commit belongs to `get_db`
(ADR 0015). The pure projection lives in `debts.domain`; this layer is the only
one in `debts` that reaches into the lower `.public` surfaces of `transactions`,
`accounts`, and `auth` (contract `2-debts`).
"""
