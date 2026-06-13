import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Code généré / artefacts : jamais lintés (D11).
  { ignores: ['dist', 'coverage', 'src/routeTree.gen.ts'] },

  // Base JS + TypeScript type-checked (D5).
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
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

  // Règles React (hooks + Fast Refresh) sur le code source.
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },

  // Primitives shadcn/ui (vendored, D9) : code copié dans le repo mais maintenu
  // upstream. Il exporte légitimement des `cva` variants à côté du composant
  // (`buttonVariants`) → on relâche `react-refresh/only-export-components` sur ce
  // seul périmètre, sans affaiblir les règles du reste du projet.
  {
    files: ['src/components/ui/**'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },

  // Fichiers de config JS (eslint.config.js) : hors type-check.
  {
    files: ['**/*.js'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
