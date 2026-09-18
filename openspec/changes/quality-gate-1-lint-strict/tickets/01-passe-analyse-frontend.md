# 01 — Passe `analyse` frontend : lint type-aware strict, sonarjs et jsx-a11y

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `client/package.json`, `client/package-lock.json`, `client/eslint.config.analyse.js`, `client/tests/lint/analyse.test.ts`

## Ce que ça livre

Depuis `client/`, `npm run analyse` joue une configuration ESLint **séparée** de celle du style
(`eslint.config.js`, intouchée ici) sur tous les `.ts`/`.tsx` de `src/` hors artefacts générés
(`src/routeTree.gen.ts`, `src/lib/api/schema.d.ts`, `dist`, `coverage`, `drizzle`, `android`). Elle
porte, une intention par bloc : typescript-eslint `recommendedTypeChecked` **+ `stylisticTypeChecked`**
(`projectService`, comme le fichier de style — pas `strictTypeChecked`, promotion ultérieure) ; le
**sous-ensemble nommé** d'`eslint-plugin-sonarjs` — `cognitive-complexity` (seuil 15),
`no-identical-functions`, `no-duplicate-string` (seuil 5), `no-duplicated-branches`, `no-collapsible-if`,
`no-redundant-boolean`, `no-inverted-boolean-check`, `prefer-immediate-return`, `no-useless-catch`,
`max-switch-cases` — jamais `configs.recommended` entier ; et `eslint-plugin-jsx-a11y` (recommended).
Le script `analyse` passe `--cache`. Versions figées au ticket avec `npm view`, pas recopiées d'un
rapport ; `package-lock.json` à jour.

**Calibrage `tests/**` sur mesure, jamais sur principe** : avant toute extinction, mesurer
(`npx eslint --config eslint.config.analyse.js src/ --format json`) ; chaque règle éteinte ou
assouplie sur `src/**/*.test.{ts,tsx}` et `tests/**` porte un commentaire avec le **nombre de
remontées** qu'elle éteint et la **raison** (contrat de la bibliothèque de test, patron
arrange/act/assert). Une extinction ne s'applique jamais au code de production.

**Ce que ce ticket ne fait pas** : les frontières de zones (`eslint-plugin-boundaries`) → ticket 02 ;
le rapport JSON/digest `check:agent` → 03 ; l'entrée dans `.claude/quality.json` et la sévérité → 04
(la passe **peut** être rouge sur `src/` à la fin de ce ticket : l'arriéré révélé se consigne dans la
PR, il ne se résorbe pas ici et ne se fait pas taire par un `eslint-disable`). `eslint.config.js`
n'est pas touché (react-hooks ≥ 6 → ticket 09).

**Comment prouver** : un test vitest par critère, `SC-01x` dans le nom, dans `client/tests/lint/`
(inclus par `vitest.config` via `tests/**/*.test.ts`). Patron : `new ESLint({ cwd: <client/>,
overrideConfigFile: 'eslint.config.analyse.js' })` puis `lintText(source, { filePath })` — le
`filePath` est celui d'un **fichier réel** de `src/` (`projectService` exige un fichier connu du
`tsconfig` ; ESLint linte le texte fourni, pas le disque) ; assertions sur `ruleId`, `severity`,
`line` et le message. Pas de fixture sur disque (elle entrerait dans le périmètre linté). Cas limites
attendus : complexité cognitive **15 passe / 16 échoue** ; même code fautif sous un `filePath` de test
→ silence si la règle est éteinte, sous un `filePath` de `src/` → remontée.

## Critères
- [ ] Une fonction de `src/` (hors tests) dont la complexité cognitive dépasse 15 fait échouer `npm run analyse`, et la remontée cite le fichier, la ligne, la règle `sonarjs/cognitive-complexity` et la valeur mesurée   (SC-01a)
- [ ] Un appel de fonction rendant une `Promise` sans `await`, `void`, `.then`/`.catch` dans `src/` (hors tests) fait échouer `npm run analyse` sur `@typescript-eslint/no-floating-promises`   (SC-01b)
- [ ] Deux fonctions d'un même fichier de `src/` (hors tests) au corps identique font échouer `npm run analyse` sur `sonarjs/no-identical-functions`   (SC-01c)
- [ ] Une infraction dans `src/routeTree.gen.ts` ou `src/lib/api/schema.d.ts` n'est pas remontée par `npm run analyse` (fichiers hors périmètre)   (SC-01d)
- [ ] Quand aucun fichier de `src/` n'enfreint une règle de la passe, `npm run analyse` sort en succès (code 0) sans remontée   (SC-01e)
- [ ] Toute règle désactivée ou assouplie pour les fichiers de test dans `eslint.config.analyse.js` porte, sur sa ligne, un commentaire avec le nombre de remontées éteintes et la raison   (SC-01f)
- [ ] La même règle, enfreinte dans `src/` hors tests, est remontée (le calibrage ne touche jamais la production)   (SC-01g)
