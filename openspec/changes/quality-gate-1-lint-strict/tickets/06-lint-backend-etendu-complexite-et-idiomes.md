# 06 — Lint backend étendu : complexité, idiomes pytest et perf dans `ruff check`, base verte

**Bloqué par :** 05
**Vérif :** test
**Fichiers :** `pyproject.toml`, `tests/unit/test_ruff_gate.py`, `tests/**` (corrections ponctuelles révélées par la mesure)

## Ce que ça livre

`uv run ruff check .` — check `backend-lint`, **bloquant**, autofix `ruff check . --fix` — applique en
plus de `E F I UP B PL` (+ `PGH004 RUF100`) les familles **`C90`** (mccabe, `[tool.ruff.lint.mccabe]
max-complexity = 10`), **`SIM`**, **`RET`**, **`PERF`**, **`PT`** et **`W`**. `PLR` est déjà dans `PL`.
La commande **reste verte sur la base** (le ticket 05 a mis `backend/` à zéro ; ce ticket calibre
`tests/**`).

**Calibrage `tests/**` sur mesure.** Mesure du 2026-09-17 sur `tests/` : 84 remontées — `PT018` 53
(assertions composites), `PT019` 16 (fixture en paramètre sans valeur), `SIM300` 6 (yoda, fix sûr),
`PT012` 2, `SIM117` 2 (fix sûr), `C901` 1, `PERF403` 1, `PT011` 1, `PT017` 1, `SIM105` 1. Re-mesurer au
ticket (`uv run ruff check tests --extend-select C90,SIM,RET,PERF,PT,W --statistics`). Règle : une
famille volumineuse dont le bruit tient au contrat de la bibliothèque de test ou au patron
arrange/act/assert s'**éteint** dans `[tool.ruff.lint.per-file-ignores] "tests/**"`, **chaque ligne
avec son chiffre et sa raison** (comme `PLR2004` aujourd'hui) ; une remontée isolée se **corrige**
(les fixes sûrs par `--fix`). `PT011` en particulier : 1 occurrence → la corriger plutôt que l'éteindre
(le critère SC-06b attend qu'elle remonte). Aucune extinction ne s'applique à `backend/`.

**Autofix sûr conservé** : toutes les corrections que `--fix` applique sans `--unsafe-fixes` restent
sûres ; les familles ajoutées n'introduisent aucune correction non sûre appliquée (Ruff les marque
« hidden fixes », elles ne s'appliquent pas). L'autofix de la gate garde donc sa validité.

**Comment prouver** : un test pytest par critère, `SC-06x` dans le nom, dans
`tests/unit/test_ruff_gate.py` — `subprocess.run` (précédent : `tests/unit/test_transactions_models.py`)
de `uv run ruff check --output-format json` sur un **source passé par stdin avec
`--stdin-filename`** (chemin virtuel sous `backend/` ou `tests/` selon le cas : pas de fixture fautive
sur disque, elle entrerait dans le périmètre linté). Cas limites : mccabe **10 passe / 11 échoue** ;
le même code sous `tests/unit/x.py` et sous `backend/x.py` (partition production / test).

## Critères
- [ ] Une fonction de `backend/` de complexité cyclomatique supérieure à 10 fait échouer `uv run ruff check .` sur `C901`, en citant la fonction et sa valeur   (SC-06a)
- [ ] Un test de `tests/` qui utilise `pytest.raises` sans `match` ni type d'exception précis fait remonter `PT011`, sauf si le calibrage `tests/**` l'a explicitement éteint avec son motif   (SC-06b)
- [ ] `ruff check . --fix` n'applique que les corrections marquées sûres par Ruff ; aucune règle des familles ajoutées n'introduit de correction non sûre appliquée   (SC-06c)
- [ ] Toute règle désactivée pour les fichiers de test dans `pyproject.toml` porte, sur sa ligne, un commentaire avec le nombre de remontées éteintes et la raison   (SC-06d)
- [ ] La même règle, enfreinte dans `backend/`, est remontée (le calibrage ne touche jamais la production)   (SC-06e)
- [ ] `uv run ruff check .` sort en succès sur la base : le check bloquant `backend-lint` n'échoue sur aucun arriéré   (SC-06f)
