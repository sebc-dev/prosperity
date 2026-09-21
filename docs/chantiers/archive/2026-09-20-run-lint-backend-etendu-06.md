# Run bloqué — lint backend étendu (ticket 06)

Portée : quality-gate-1-lint-strict · ticket 06
Ouvert le 2026-09-20 · Fermé le 2026-09-21 · branche `impl/lint-backend-etendu-complexite-et-idiomes-06` · HEAD `3aaceaf`

## Objectif
Faire aboutir le run du ticket 06 (Ruff `C90 SIM RET PERF PT W`, mccabe 10, calibrage `tests/**`,
tests `SC-06a..f`) jusqu'à sa PR — statut `blocked-quality` : la gate a échoué sur `backend-typecheck`.

## Contexte à charger
à lire      `openspec/changes/quality-gate-1-lint-strict/tickets/06-lint-backend-etendu-complexite-et-idiomes.md` — le ticket (55 l.)
à situer    worktree `.git/scd-worktrees/lint-backend-etendu-complexite-et-idiomes-06` — le SEUL exemplaire
            du travail, rien n'est commité : `pyproject.toml`, 7 tests existants corrigés
            (`tests/integration/*` ×5, `tests/unit/test_budget_cycle_detector.py`,
            `tests/unit/test_sync_error_mapping.py`), `tests/unit/test_ruff_gate.py` (neuf, non suivi)

## Acquis
- La gate était verte sur 4 checks sur 5 dans le worktree : `ruff check .` (familles ajoutées
  incluses), `ruff format --check`, `lint-imports`, `pytest tests/unit/` (1050 passed).
- Le seul échec : `pyright` sur le test neuf du ticket, `tests/unit/test_ruff_gate.py:213` —
  `re.search(...).group()` appelé sans garde de `None` (`reportOptionalMemberAccess`), dans le test
  `SC-06d` qui compte et vérifie le motif des extinctions calibrées. Une ligne ; l'applier de projet
  avait renforcé 3 assertions (audit `test-edit-validator` : ok) mais pas résorbé celle-ci.
- Le run s'est arrêté à la gate : la review 8 dimensions n'a pas été jouée.

## Issue
Fermé : run relancé en séquentiel après le hotfix #285 (`[tool.deptry] exclude` sans `.git` faisait
rougir `backend-deps` depuis un worktree du cycle) — PR #286 ouverte, review 8 dimensions jouée.
Piège rencontré à la relance : `oldBase = impl/…-05` (dépendance mergée) fait rejouer au rebaser les
commits de `main` entre 05 et la fourche → conflit ; l'`oldBase` juste est le point de fourche.

## Prochaine étape (au moment du blocage)
Corriger la garde (`match = re.search(...); assert match is not None; … match.group()`), rejouer
`uv run pyright && uv run ruff check . && uv run pytest tests/unit/ -n auto` depuis le worktree, puis
décider : finir à la main (commit, push, PR — sans review 8 dimensions) ou sauver le diff en patch,
retirer branche + worktree et relancer `/scd-spec-dev:run quality-gate-1-lint-strict 06` pour la
review complète.

## Écarté
- Un `# type: ignore` ou un `# pyright: ignore` sur la ligne — escape-hatch dans un test, refusé par
  la review d'intégrité.
- Passer `tests/` en `reportOptionalMemberAccess = "none"` dans `pyproject.toml` — affaiblirait le
  typecheck de tous les tests pour une ligne.
