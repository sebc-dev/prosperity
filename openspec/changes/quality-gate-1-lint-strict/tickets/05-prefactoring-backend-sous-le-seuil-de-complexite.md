# 05 — Préfactoring : les fonctions de `backend/` passent sous le seuil de complexité 10

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `backend/modules/debts/domain.py`, `backend/modules/debts/service/settlement.py`, `backend/modules/auth/service/jwt.py`, `backend/modules/budget/service/consumption.py`, `backend/modules/sse/service/broadcaster.py`, `tests/unit/test_settlement_domain.py`, `tests/unit/test_auth_sse_jwt.py`

## Ce que ça livre

*Make the change easy, then make the easy change.* Le ticket 06 ajoute à `uv run ruff check .` —
check **bloquant** de la gate — les familles `C90` (mccabe, seuil 10), `SIM`, `RET`, `PERF`, `PT`, `W`.
Mesure du 2026-09-17 sur `backend/` + `alembic/` avec ces familles : **5 remontées**, toutes en code de
production — `C901` sur `backend/modules/debts/domain.py::SettlementValidator.validate` (**21** > 10),
`backend/modules/debts/service/settlement.py::create_settlement` (12) et
`backend/modules/auth/service/jwt.py::verify_sse_token` (11) ; `PERF401` dans
`budget/service/consumption.py:375` ; `SIM105` dans `sse/service/broadcaster.py:109`. Un check
bloquant n'échoue jamais sur l'arriéré : la base doit être à zéro **avant** que la règle entre.
Décision prise à la décomposition : **corriger le code**, pas déroger.

Ce ticket ramène les trois fonctions à une complexité cyclomatique ≤ 10 **sans changer leur
comportement** — mêmes erreurs levées, dans le même ordre, mêmes valeurs rendues — et corrige les
deux remontées mineures. Pour `validate` : les 8 invariants séquentiels (ordre déterministe documenté
dans la docstring) deviennent des fonctions privées appelées dans le même ordre ; la dérogation
`# noqa: PLR0912` qu'elle porte devient morte après extraction (`RUF100` la refuserait) → la retirer.
Rien d'autre ne change : ni signature publique, ni exceptions, ni messages.

**Mode `test`, stratégie characterization** : le filet existant est riche (`test_settlement_domain.py`,
`test_settlement_invariants.py` + Hypothesis, `test_auth_sse_jwt.py`, `test_settlement_conservation.py`,
e2e `test_debt_settlement_lifecycle.py`) et doit rester vert tel quel. Les tests neufs, nommés
`SC-05x`, capturent le comportement des fonctions refactorées là où le filet est par cas
(chaque invariant de `validate` → son erreur, un cas valide → le `ValidatedSettlement` attendu). Ils
ne remplacent aucun test existant.

**Comment prouver la complexité** : `uv run ruff check backend alembic --select C901 --config
"lint.mccabe.max-complexity=10"` sort en succès (la config `pyproject.toml` elle-même est le ticket
06). Hors périmètre : `tests/**` (calibré en 06), toute règle nouvelle dans `pyproject.toml`, tout
autre refactor.

## Critères
- [x] `uv run ruff check backend alembic --select C901,PERF401,SIM105` avec `max-complexity = 10` sort en succès : `validate`, `create_settlement` et `verify_sse_token` sont ≤ 10, `PERF401` et `SIM105` sont corrigés   (SC-05a)
- [x] `SettlementValidator.validate` conserve son comportement : pour chacun de ses 8 invariants, la même exception (`SettlementValidationError` spécialisée) est levée dans le même ordre, et une entrée valide rend le même `ValidatedSettlement`   (SC-05b)
- [x] `create_settlement` et `verify_sse_token` conservent leur comportement : leurs cas d'erreur et leurs sorties nominales sont inchangés, et les suites `tests/unit/`, `tests/integration/` (debts, auth) et `tests/e2e/test_debt_settlement_lifecycle.py` passent sans modification   (SC-05c)
