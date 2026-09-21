# 08 — Le check `backend-deps` entre dans la gate, avec la sévérité que la mesure autorise

**Bloqué par :** 07
**Vérif :** observé
**Fichiers :** `.claude/quality.json`, `docs/ci.md`

## Ce que ça livre

La gate du cycle `run` (`.claude/quality.json`) joue `deptry` sur chaque ticket backend : une entrée
`backend-deps` — `cmd: "uv run deptry ."`, `autofix: null`, pas de champ `agent` (le diagnostiqueur
`quality-backend-deps` est posé ensuite par `/scd-spec-dev:quality-agents` ; en attendant, un échec
est routé vers le conseiller générique).

**La sévérité est fixée par la mesure.** Jouer `uv run deptry .` sur `main` au moment de l'ajout et
capturer la sortie (remontées, code de sortie, durée) : code 0 → `"severity": "blocking"` ; sinon
`"severity": "advisory"` et `docs/ci.md` consigne le nombre de remontées, la date et la condition de
promotion (« promouvoir `blocking` à 0 remontée »). `quality.json` n'a pas de champ libre.

`docs/ci.md` gagne, dans le tableau Backend, la ligne `uv run deptry .` avec son intention
(dépendances manquantes / inutilisées / transitives) et son coût mesuré en secondes ; le paragraphe
« quality gate du plugin » nomme le check neuf et sa sévérité.

**Preuve** (pas de test rejouable : la sévérité est une décision datée) : sortie capturée de la
commande sur `main`, `diff` de `quality.json`, `grep` de `docs/ci.md`. Hors périmètre : la CI GitHub,
le diagnostiqueur, toute modification de `pyproject.toml`.

## Critères
- [x] Si `uv run deptry .` sort en succès sur `main` au moment de l'ajout, l'entrée `backend-deps` de `.claude/quality.json` porte `"severity": "blocking"`   (SC-08a)
- [x] Si elle sort en échec sur `main`, l'entrée porte `"severity": "advisory"` et `docs/ci.md` donne, pour `backend-deps`, le nombre de remontées mesuré, la date et la condition de promotion   (SC-08b)
- [x] Un check `blocking` a une base à zéro : sur une branche qui ne touche aucun fichier cité par une remontée, `backend-deps` sort en succès   (SC-08c)
- [x] `docs/ci.md` liste `uv run deptry .` avec son intention et son coût mesuré en secondes   (SC-08d)
