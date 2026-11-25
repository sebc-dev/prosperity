---
status: testing
phase: 01-socle-et-quality-gate
source: [01-VERIFICATION.md]
started: 2026-11-25T16:00:00Z
updated: 2026-11-25T16:00:00Z
---

## Current Test

number: 1
name: Refus de l'outil Write sur un chemin protégé
expected: |
  Dans une session agent neuve, l'outil Write (pas Edit) sur un chemin protégé (par exemple `quality/thresholds.json` ou `.github/workflows/quality.yml`) est refusé par les permissions (« denied by your permission settings »).
awaiting: user response

## Tests

### 1. Refus de l'outil Write sur un chemin protégé
expected: Dans une session agent neuve, demander l'outil Write (pas Edit) sur un chemin protégé, par exemple `quality/thresholds.json` ou `.github/workflows/quality.yml` : refus par les permissions (« denied by your permission settings »). Le dépôt n'a que 66 règles `Edit(...)` et aucune règle `Write(...)` ; la doctrine du plan veut qu'`Edit` couvre Write et NotebookEdit.
result: [pending]

### 2. Réglages GitHub du juge hors PR
expected: Dans GitHub (Settings), l'environnement `gate-verdict` est restreint à `main`, le secret `GATE_APP_PRIVATE_KEY` et la variable `GATE_APP_ID` existent au niveau de l'environnement seulement, l'auto-fusion est désactivée et les durcissements Actions (épinglage par SHA, approbation des contributeurs externes) sont actifs ; application `prosperity-gate` (ID 5887661, `statuses: write` seule).
result: [pending]

### 3. Timer SonarQube nightly sur kfzcore
expected: `systemctl --user list-timers prosperity-sonar.timer` montre le timer actif, et une analyse nightly a été traitée (`journalctl --user -u prosperity-sonar` se termine par « analyse traitée (SUCCESS) »). Advisory (D-16).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
