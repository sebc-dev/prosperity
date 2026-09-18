# 07 — `deptry` : les dépendances Python déclarées et importées coïncident

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `pyproject.toml`, `uv.lock`, `tests/unit/test_deptry_gate.py`

## Ce que ça livre

Depuis la racine, `uv run deptry .` échoue si une dépendance déclarée dans `pyproject.toml` n'est
importée nulle part (`DEP002`), si un import ne correspond à aucune dépendance déclarée (`DEP001`), ou
si un import repose sur une dépendance transitive non déclarée (`DEP003`) — et sort en succès sur la
base. `deptry` entre dans le groupe `dev` (version figée par `uv.lock`), avec une section
`[tool.deptry]` : `known_first_party = ["backend"]`, `exclude` `.venv`, `client`, `htmlcov` (et les
caches), `pep621_dev_dependency_groups = ["dev"]`.

**Calibrage motivé, pas silence.** Les extras et paquets importés sous un autre nom ou indirectement —
`pwdlib[argon2]`, `pyjwt[crypto]`, `uvicorn[standard]`, `psycopg2-binary`, `email-validator`,
`python-multipart`… — passent par `per_rule_ignores` (ou `package_module_name_map`) **avec un
commentaire qui dit pourquoi** ; jamais une extinction globale d'une règle `DEP*`. Ce que la mesure
révèle de réel (un paquet vraiment inutile, un import vraiment non déclaré) se corrige dans
`pyproject.toml` si c'est une ligne, se consigne dans la PR sinon. Aucun code de `backend/` ne change.

**Comment prouver** : un test pytest par critère, `SC-07x` dans le nom, `subprocess.run` (précédent :
`tests/unit/test_transactions_models.py`). Pour `DEP001/002/003`, un **projet temporaire** sous
`tmp_path` — un `pyproject.toml` minimal qui déclare un paquet jamais importé, un module qui importe
un paquet non déclaré — et `uv run deptry <tmp_path>` ; asserter le code de sortie et les codes/noms
dans la sortie (`--json-output`). Pour la base propre, `uv run deptry .` sur le dépôt → code 0.
Cas limite : un extra importé sous un autre nom de module (`pyjwt[crypto]` → `jwt`) reste silencieux
grâce à l'ignore motivé.

## Critères
- [ ] Quand `pyproject.toml` déclare un paquet qu'aucun module de `backend/`, `alembic/` ou `tests/` n'importe, `uv run deptry .` sort en échec en nommant le paquet (`DEP002`)   (SC-07a)
- [ ] Quand un module de `backend/` importe un paquet absent de `pyproject.toml` (transitif ou non), `uv run deptry .` sort en échec en nommant le module et l'import (`DEP001` ou `DEP003`)   (SC-07b)
- [ ] Quand chaque dépendance déclarée est importée et chaque import est déclaré, `uv run deptry .` sort en succès — c'est l'état de la base   (SC-07c)
