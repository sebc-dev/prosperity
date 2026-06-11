"""Sous-handlers du write upload handler, un par table cliente-sync.

Vide en S13.2 ; peuplé en S13.4 (`transactions.py`, `accounts.py`, …). Chaque
sous-handler valide le `Mutation.payload` contre le schema de SA table puis
appelle le `service.py` du module métier via son `public.py` (ADR 0014 — jamais
d'écriture DB directe depuis `sync`).
"""
