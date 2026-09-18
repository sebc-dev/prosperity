# 09 — Les règles du React Compiler entrent dans le lint bloquant (`react-hooks` ≥ 6)

**Bloqué par :** —
**Vérif :** test
**Fichiers :** `client/package.json`, `client/package-lock.json`, `client/eslint.config.js`, `client/tests/lint/react-hooks.test.ts`

## Ce que ça livre

`npm run lint` (le style, **bloquant** : check `frontend-lint`, joué aussi par la CI `frontend-lint`)
applique `eslint-plugin-react-hooks` en version **6 ou ultérieure** via `configs.flat.recommended`
(npm publie 7.1.1 au 2026-09-17 ; figer avec `npm view`, jamais recopier un numéro), qui ajoute aux
`rules-of-hooks` / `exhaustive-deps` les règles du **React Compiler** (`react-hooks/immutability`,
`react-hooks/purity`, `react-hooks/refs`, `react-hooks/set-state-in-effect`…). Le bloc « Règles React »
d'`eslint.config.js` remplace le spread `reactHooks.configs.recommended.rules` (API v5) par la config
plate v6+ ; le reste du fichier ne change pas (ignores, `recommendedTypeChecked`, relâchement
`src/components/ui/**`, bloc `*.js`).

**Base verte, mesurée d'abord.** Avant de monter la version, jouer `npm run lint` avec la nouvelle
config sur `src/` et capturer l'arriéré. Décision prise à la décomposition : l'arriéré **mécanique** se
corrige dans le ticket (une dépendance manquante, une valeur muée pendant le rendu que le compilateur
refuse) ; un défaut React Compiler **non trivial** (une refonte de composant) arrête le ticket et se
remonte — dérogation déclarée ou ticket dédié — plutôt qu'un `eslint-disable` ou un passage en
`warn`, qui contredirait les critères (« `npm run lint` sort en échec »).

**Coexistence** : le change `arch-guards` ajoute deux blocs `no-restricted-imports` au même
`eslint.config.js` ; blocs distincts, à merger l'un après l'autre (pas de dépendance, un rebase).

**Comment prouver** : un test vitest par critère, `SC-09x` dans le nom, dans `client/tests/lint/` —
`new ESLint({ cwd: <client/> })` (charge `eslint.config.js`) puis `lintText(source, { filePath })`
avec un `filePath` réel de `src/` ; assertions sur `ruleId` et `severity === 2`.

## Critères
- [ ] Un composant de `src/` qui appelle un hook à l'intérieur d'une condition fait échouer `npm run lint` sur `react-hooks/rules-of-hooks`   (SC-09a)
- [ ] Un composant de `src/` qui mute une prop ou une valeur issue d'un hook pendant le rendu fait échouer `npm run lint` sur une règle `react-hooks/*` du React Compiler (ex. `react-hooks/immutability`)   (SC-09b)
- [ ] `npm run lint` sort en succès sur la base : le check bloquant `frontend-lint` n'échoue sur aucun arriéré   (SC-09c)
