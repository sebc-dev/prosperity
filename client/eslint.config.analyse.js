import globals from 'globals'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import sonarjs from 'eslint-plugin-sonarjs'
import tseslint from 'typescript-eslint'

// Passe `analyse` (EPIC-18 / STORY-S18.2, ticket 01) : configuration ESLint SÉPARÉE de
// `eslint.config.js` (style, bloquant, intouché ici). Une intention par bloc — jouée par
// `npm run analyse`, jamais par `npm run lint`.

export default tseslint.config(
  // Code généré / artefacts : jamais analysés (miroir D11 de eslint.config.js). `dist`,
  // `coverage`, `drizzle`, `android` sont hors périmètre par nature ; `routeTree.gen.ts` et
  // `schema.d.ts` sont sous `src/` mais générés — une infraction dedans n'est pas remontée.
  {
    ignores: [
      'dist',
      'coverage',
      'src/routeTree.gen.ts',
      'src/lib/api/schema.d.ts',
      'drizzle',
      'android',
    ],
  },

  // Socle type-aware strict : `recommendedTypeChecked` + `stylisticTypeChecked`
  // (`projectService`, même montage que `eslint.config.js` — pas `strictTypeChecked`,
  // promotion ultérieure après mesure, cf. design.md § Decisions). Porte notamment
  // `@typescript-eslint/no-floating-promises` (SC-01b) déjà inclus par `recommendedTypeChecked`.
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },

  // Sous-ensemble nommé d'eslint-plugin-sonarjs (jamais `configs.recommended` entier, cf.
  // design.md § Decisions) : les règles à valeur ajoutée au-delà de typescript-eslint. Scopé à
  // `src/` (application) et `tests/**` (harnais partagé) — pas les fichiers de config racine
  // (`vite.config.ts`, `drizzle.config.ts`…) qui ne sont pas la cible de cette passe.
  {
    files: ['src/**/*.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
    plugins: { sonarjs },
    rules: {
      'sonarjs/cognitive-complexity': ['error', 15],
      'sonarjs/no-identical-functions': 'error',
      'sonarjs/no-duplicate-string': ['error', { threshold: 5 }],
      'sonarjs/no-duplicated-branches': 'error',
      'sonarjs/no-collapsible-if': 'error',
      'sonarjs/no-redundant-boolean': 'error',
      'sonarjs/no-inverted-boolean-check': 'error',
      'sonarjs/prefer-immediate-return': 'error',
      'sonarjs/no-useless-catch': 'error',
      'sonarjs/max-switch-cases': 'error',
    },
  },

  // eslint-plugin-jsx-a11y (recommended), même périmètre que le bloc sonarjs ci-dessus.
  {
    ...jsxA11y.flatConfigs.recommended,
    files: ['src/**/*.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
  },

  // Calibrage mesuré sur les fichiers de test (`src/**/*.test.{ts,tsx}` co-localisés et
  // `tests/**`, harnais partagé) — jamais sur le code de production (SC-01g). Mesure de
  // référence sur la base au ticket 01 (`npx eslint --config eslint.config.analyse.js src tests
  // --format json`) : 23 remontées au total, dont 21 dans des fichiers de test. Seules les deux
  // règles ci-dessous ont une justification structurelle de test et sont éteintes ; les 3
  // remontées restantes en fichiers de test (`array-type` ×1 sur
  // `src/lib/drizzle/schema.test.ts`, `consistent-type-definitions` ×1 sur
  // `tests/mocks/powersync.ts`, `cognitive-complexity` ×1 sur `tests/lint/analyse.test.ts` — hors
  // périmètre de ce calibrage) et les 2 en `src/` hors tests (`no-empty-function` sur
  // `src/lib/powersync/adopt.ts`, `cognitive-complexity` sur `src/lib/sse/client.ts`) restent un
  // arriéré réel, consigné dans la PR, jamais éteint sur principe.
  {
    files: ['src/**/*.test.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
    rules: {
      // 14 remontées éteintes (mesure ci-dessus) — les doublures de test implémentent des
      // méthodes de contrat sans corps (`IntersectionObserver.observe/unobserve/disconnect`
      // dans tests/setup.ts, callbacks no-op passés à un composant rendu) : le corps vide est
      // le stub légitime du patron arrange/act/assert, pas un oubli.
      '@typescript-eslint/no-empty-function': 'off',
      // 4 remontées éteintes (mesure ci-dessus) — les littéraux répétés (états, identifiants de
      // compte/transaction) sont des données de fixture arrange/act/assert délibérément répétées
      // d'un cas à l'autre, pas de la duplication applicative à factoriser.
      'sonarjs/no-duplicate-string': 'off',
    },
  },

  // Fichiers de config JS (eslint.config.js, eslint.config.analyse.js) : hors type-check,
  // comme `eslint.config.js`.
  {
    files: ['**/*.js'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
