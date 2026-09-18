# 10 — La frontière avec la CI et le budget de la gate sont écrits

**Bloqué par :** 04, 08
**Vérif :** observé
**Fichiers :** `runbooks/ci.md`, `docs/ci.md`

## Ce que ça livre

Un lecteur qui cherche dans `runbooks/ci.md` (qui fait autorité sur ce qui bloque une PR) si
`frontend-analyse` ou `backend-deps` bloque une PR lit **explicitement** que ces checks — comme
`npm run analyse`, `npm run check:agent`, `uv run deptry .` — ne sont joués **que par la quality gate
du cycle `run`**, jamais par `push.yml` : la CI GitHub reste le juge final et n'accueille aucun check
nouveau (promouvoir un garde en CI touche trois surfaces — c'est un change à part). Une section
courte, à côté de « Escape-hatches » ; pas de doublon de la matrice.

`docs/ci.md` consigne le **budget total de la gate** : la somme des coûts mesurés des checks
(`analyse` avec et sans `--cache`, `deptry`, les checks existants), la date, et le seuil de révision
(~3 min : au-delà, revoir la composition de la gate). Si le ticket 03 est mergé et que `check:agent`
manque encore au tableau Frontend, l'ajouter ici. Ce ticket ne change aucune commande, aucun check,
aucune sévérité.

**Preuve** : `grep` des lignes attendues dans les deux fichiers ; les durées viennent de sorties
capturées (`time`), pas d'estimations.

## Critères
- [ ] `runbooks/ci.md` dit explicitement que `frontend-analyse` et `backend-deps` ne sont joués que par la gate du cycle `run`, jamais par `push.yml`   (SC-10a)
- [ ] `docs/ci.md` consigne le budget total mesuré de la gate (somme des coûts par check, date, seuil de révision) et liste `analyse`, `check:agent` et `deptry` avec leur intention et leur coût   (SC-10b)
