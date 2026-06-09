"""Composition-root transports — HTTP surfaces that sit ABOVE every module.

`backend.transports` is deliberately **outside** `backend.modules`: it composes
several modules' public surfaces into one user-facing flow that no single module
may own. The OFX import (`imports_http`) is the canonical case — `commit` reads
`banking.public` (parse/analyze/log) AND writes `transactions.public` (create the
draft), but `banking ⊥ transactions` are peer modules (contract 1) forbidden from
importing each other. Only the composition root, like `main.py`, may import all
`*.public` surfaces freely.

Import-linter contract #6 keeps this directional: `backend.modules.*` and
`backend.shared` are forbidden from importing `backend.transports` (consumer-only,
mirror of contract #5 for `mcp`). The composition root consumes; it is never
consumed.
"""
