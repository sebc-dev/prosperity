# E01 — Backend bootstrap + quality gates

> **Durée estimée** : 5-8 jours
> **Statut** : not started
> **Dépend de** : —
> **Bloque** : tous les epics suivants
> **ADRs activés à la fin de cet epic** : 0005 (matérialisé par les 5 contrats import-linter)

---

## Objectif

Établir le filet de sécurité (tests + import-linter + lint + CI) **AVANT** toute logique métier, conformément au principe "les tests sont le filet face à Claude Code" ([Stratégie de tests §2.2](../Strat%C3%A9gie%20de%20tests.md)).

À la fin de cet epic, on dispose d'un squelette de projet vide mais avec :

- pytest + pytest-asyncio + Hypothesis + testcontainers + factory-boy + coverage opérationnels
- import-linter avec les **5 contrats ADR 0005** actifs (sur un graphe encore vide, mais prêts à enforcer dès que du code arrive)
- pre-commit hooks (`ruff` + `mypy`/`pyright`)
- Alembic initialisé avec une migration `0001_baseline_empty.py`
- CI GitHub Actions (`push.yml` < 5 min + `nightly.yml` 30-45 min) opérationnels et verts
- FastAPI minimal avec `/healthz` qui répond

---

## Stories

### S01.1 — Scaffolding projet et structure modulaire

**Objectif** : structure de répertoires conforme à l'architecture, `pyproject.toml` avec `uv`, FastAPI app minimaliste qui démarre.

**Livrable observable** : `uv run uvicorn backend.main:app` démarre, `GET /healthz` retourne `{"status": "ok"}`.

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.1.1** | Init repo backend : `pyproject.toml` (uv, Python 3.13), `.python-version`, `.gitignore` Python, `backend/__init__.py`. Aucune dep encore, juste la structure | ~50 |
| **P01.1.2** | Scaffold des 12 modules vides : `backend/modules/{auth,accounts,transactions,budget,banking,reconciliation,forecasting,debts,savings,notifications,sync,mcp}/` chacun avec `__init__.py` et `public.py` vide (juste un docstring). Plus `backend/shared/__init__.py` | ~60 |
| **P01.1.3** | Add FastAPI minimal : dep `fastapi`, dep `uvicorn[standard]`, `backend/main.py` avec `app = FastAPI()` + `GET /healthz`. Tests : `tests/integration/test_healthz.py` | ~80 |

---

### S01.2 — Framework de tests

**Objectif** : pytest + Hypothesis + testcontainers + factory-boy + coverage configurés via smoke tests minimaux. Cf. [Stratégie de tests §11](../Strat%C3%A9gie%20de%20tests.md#11-outils--tableau-récapitulatif).

**Livrable observable** : `uv run pytest` passe, `uv run pytest --cov` produit un rapport.

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.2.1** | Add `pytest` + `pytest-asyncio` deps + `tests/conftest.py` minimal (event_loop scope session) + `tests/unit/test_smoke.py` (trivial assert) | ~60 |
| **P01.2.2** | Add `hypothesis` dep + `tests/strategies.py` vide (juste un docstring) + `tests/unit/test_property_smoke.py` avec une property triviale (`assert sorted(sorted(xs)) == sorted(xs)`) | ~50 |
| **P01.2.3** | Add `testcontainers[postgres]` dep + fixture async `db_session` dans `conftest.py` (engine async SQLAlchemy 2 + rollback per-test) + `tests/integration/test_db_smoke.py` qui crée+rollback une row dans une table de test | ~150 |
| **P01.2.4** | Add `factory-boy` dep + `tests/factories/__init__.py` + `tests/factories/sqlalchemy.py` + `tests/factories/domain.py` (juste les imports squelettes). Pas de factory réelle encore (pas de modèle) | ~40 |
| **P01.2.5** | Add `coverage.py` + `pytest-cov` deps + config `[tool.coverage]` dans `pyproject.toml` + `pytest --cov` smoke run dans la CI (cible 0% pour l'instant, on ajustera) | ~50 |

---

### S01.3 — Lint, type check, pre-commit

**Objectif** : `ruff` + `mypy` (ou `pyright`, à trancher en P01.3.1) + `pre-commit` framework, hooks fonctionnels sur commit.

**Livrable observable** : `pre-commit run --all-files` passe sur le projet vide.

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.3.1** | Décision `mypy` vs `pyright` (P01.3.1 = ADR 0015 éventuel si non-trivial, sinon juste un commentaire dans `pyproject.toml`). Reco : `pyright` (plus rapide, meilleur sur Pydantic v2). Ajouter la dep choisie + config `pyproject.toml` strict mode | ~60 |
| **P01.3.2** | Add `ruff` dep + config `[tool.ruff]` dans `pyproject.toml` (line length 100, target 3.13, rules essentielles E/F/I/UP/B/PL) + un fichier corrigé pour vérifier que ça marche | ~50 |
| **P01.3.3** | Add `pre-commit` framework + `.pre-commit-config.yaml` avec hooks `ruff` (lint+format), `pyright` (en check mode), pytest sur fichiers modifiés. Doc README sur l'install (`uv run pre-commit install`) | ~70 |

---

### S01.4 — import-linter (5 contrats ADR 0005)

**Objectif** : les 5 contrats `import-linter` matérialisés dans `.importlinter` actifs sur le graphe vide. Cf. [Stratégie de tests §4.3](../Strat%C3%A9gie%20de%20tests.md#43-tests-darchitecture-import-linter).

**Livrable observable** : `uv run lint-imports` passe, retourne "0 broken contracts".

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.4.1** | Add `import-linter` dep + `.importlinter` à la racine avec le contrat 1 (`layers` directional graph 7 niveaux). Smoke run passe trivialement (modules vides). | ~90 |
| **P01.4.2** | Ajouter contrat 2 (`forbidden` internals cross-module : pas d'import de `*.service`, `*.models`, `*.domain`, `*.repository`, `*.transports`, `*.handlers` depuis un autre module) | ~30 |
| **P01.4.3** | Ajouter contrats 3 (`shared` isolé), 4 (banking provider isolated to `banking.service.polling`), 5 (mcp consumer-only). Smoke run final passe trivialement, mais les 5 sont en place | ~80 |

---

### S01.5 — Alembic initialisé

**Objectif** : Alembic configuré async SQLAlchemy 2, migration baseline vide créée, runnable.

**Livrable observable** : `uv run alembic upgrade head` passe sur DB vide, `alembic_version` est créée.

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.5.1** | `alembic init` + adapter `env.py` pour SQLAlchemy 2 async + chargement DSN depuis pydantic-settings (`backend/config.py` ajouté ici) + DSN par défaut pour DB locale testcontainers | ~150 |
| **P01.5.2** | Première migration `0001_baseline_empty.py` (juste pour valider qu'Alembic tourne). Test pytest niveau 1 schema check : applique upgrade head sur DB vide, snapshot SQL = vide. Cf. [Stratégie de tests §4.6](../Strat%C3%A9gie%20de%20tests.md#46-tests-de-migrations-alembic) | ~80 |

---

### S01.6 — CI GitHub Actions

**Objectif** : workflows `push.yml` (< 5 min) et `nightly.yml` (30-45 min) opérationnels, alignés sur [Stratégie de tests §9](../Strat%C3%A9gie%20de%20tests.md#9-pipelinecicd).

**Livrable observable** : un push sur `fresh-start` déclenche le workflow `push.yml`, tous les jobs sont verts.

| Phase | Description | Diff estimé |
|---|---|---|
| **P01.6.1** | `.github/workflows/push.yml` avec jobs parallèles : `backend-lint` (ruff + pyright + import-linter), `backend-unit` (pytest unit/), `backend-integration` (pytest integration/ + testcontainers Postgres service), `backend-sync` (placeholder vide pour l'instant), `backend-migrations` (alembic upgrade head + schema check). Tous verts sur le squelette | ~180 |
| **P01.6.2** | `.github/workflows/nightly.yml` schedule cron daily + jobs : property tests `max_examples=500`, audit deps `pip-audit`, coverage publication. Placeholder pour Playwright et Enable Banking niveau C (à activer en V1). Vert sur le squelette | ~120 |
| **P01.6.3** | README projet à la racine : commandes `make dev`, `make test`, `make lint`, `make migrate` (ou alias uv équivalents). Justifie les choix de stack à 1 niveau renvoyant vers les ADRs | ~80 |

---

## Récapitulatif

| ID | Type | Diff estimé | Cumul |
|---|---|---|---|
| S01.1 (3 phases) | Scaffold | 190 | 190 |
| S01.2 (5 phases) | Tests | 350 | 540 |
| S01.3 (3 phases) | Lint/Type | 180 | 720 |
| S01.4 (3 phases) | import-linter | 200 | 920 |
| S01.5 (2 phases) | Alembic | 230 | 1150 |
| S01.6 (3 phases) | CI | 380 | 1530 |
| **Total** | **6 stories / 19 phases** | **~1530 lignes** | |

**Densité** : ~80 lignes par phase en moyenne, bien sous la limite 400. Chaque phase est isolément reviewable en 15-30 min.

---

## Critères d'acceptation de l'epic

- [ ] `uv run pytest` passe sur le squelette
- [ ] `uv run pytest --cov` produit un rapport
- [ ] `uv run lint-imports` retourne "0 broken contracts" avec les 5 contrats actifs
- [ ] `uv run pre-commit run --all-files` passe
- [ ] `uv run alembic upgrade head` passe sur DB vide
- [ ] `uv run uvicorn backend.main:app` démarre, `GET /healthz` répond `{"status": "ok"}`
- [ ] Workflow `push.yml` GitHub Actions vert sur la branche
- [ ] Workflow `nightly.yml` vert au moins une fois

---

## Notes pour l'implémenteur

- **Ne pas créer de modèle métier** dans cet epic, même tentant. Le squelette doit rester vide pour valider que la machinerie tourne sans contenu.
- **Les 5 contrats import-linter sont actifs dès J1** : c'est ce qui empêchera Claude Code de produire des imports croisés non conformes lors des epics suivants. Cf. principe directeur de la stratégie de test.
- **Décision `mypy` vs `pyright`** (P01.3.1) : si tu hésites, prends `pyright`. Plus rapide, meilleur support Pydantic v2, et la plupart des erreurs `pyright` non-strict sont les mêmes que `mypy` strict, sans la lourdeur de config.
- **Choix testcontainers Postgres image** : pin sur `postgres:17-alpine` pour cohérence avec la prod (cf. stack §1 architecture).
- **Pré-installer `aiosqlite`** si tu veux pouvoir runner les tests sans Docker (pour des tests vraiment unitaires de l'engine SQLA async sans la couche Postgres). Optionnel.
