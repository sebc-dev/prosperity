# 04 — Le check `frontend-analyse` entre dans la gate, avec la sévérité que la mesure autorise

**Bloqué par :** 01, 02
**Vérif :** observé
**Fichiers :** `.claude/quality.json`, `docs/ci.md`

## Ce que ça livre

La gate du cycle `run` (`.claude/quality.json`) joue la passe d'analyse frontend sur chaque ticket :
une entrée `frontend-analyse` — `cmd: "npm --prefix client run analyse"`, `autofix: null` (les fixes
`stylistic` sont sûrs mais toucheraient des tests ; on n'active pas l'autofix dans ce change), pas de
champ `agent` (le diagnostiqueur `quality-frontend-analyse` est posé ensuite par la commande
`/scd-spec-dev:quality-agents` ; en attendant, un échec est routé vers le conseiller générique).

**La sévérité est fixée par la mesure, pas par principe.** Jouer `npm --prefix client run analyse` sur
`main` au moment de l'ajout et capturer la sortie (nombre de remontées, code de sortie, durée) :
- code 0 → `"severity": "blocking"` ;
- sinon → `"severity": "advisory"`, et `docs/ci.md` consigne pour ce check le **nombre de remontées**
  mesuré, la **date**, et la **condition de promotion** (« promouvoir `blocking` à 0 remontée »).
`quality.json` n'a pas de champ libre : l'arriéré vit dans `docs/ci.md`, jamais dans le JSON. Les
règles `boundaries/*` en `warn` ne comptent pas dans le code de sortie.

`docs/ci.md` (le cap que `ticket-briefer` lit) gagne, dans le tableau Frontend, la commande
`npm run analyse` avec son intention, son périmètre (`.ts`/`.tsx` de `src/`, hors artefacts générés)
et son **coût mesuré en secondes** (à froid et avec `--cache`), ainsi que `npm run check:agent` (si le
ticket 03 est mergé ; sinon la ligne est ajoutée par 10). Le paragraphe « quality gate du plugin » y
nomme le check neuf et sa sévérité.

**Preuve** (pas de test rejouable : la sévérité est une décision datée) : la sortie capturée de la
commande sur `main`, le `diff` de `quality.json`, et `grep` des lignes attendues dans `docs/ci.md`.
Hors périmètre : résorber l'arriéré, la CI GitHub, le diagnostiqueur.

## Critères
- [ ] Si `npm --prefix client run analyse` sort en succès sur `main` au moment de l'ajout, l'entrée `frontend-analyse` de `.claude/quality.json` porte `"severity": "blocking"`   (SC-04a)
- [ ] Si elle sort en échec sur `main`, l'entrée porte `"severity": "advisory"` et `docs/ci.md` donne, pour `frontend-analyse`, le nombre de remontées mesuré, la date et la condition de promotion   (SC-04b)
- [ ] Un check `blocking` a une base à zéro : sur une branche qui ne touche aucun fichier cité par une remontée, `frontend-analyse` sort en succès   (SC-04c)
- [ ] `docs/ci.md` donne à `ticket-briefer` la commande `npm run analyse`, son périmètre (`.ts`/`.tsx` de `src/`) et son coût mesuré en secondes   (SC-04d)
