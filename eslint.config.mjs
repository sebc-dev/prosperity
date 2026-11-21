import comments from '@eslint-community/eslint-plugin-eslint-comments/configs';
import vitest from '@vitest/eslint-plugin';
import { defineConfig } from 'eslint/config';
import sonarjs from 'eslint-plugin-sonarjs';
import { matchesGlob } from 'node:path/posix';
import tseslint from 'typescript-eslint';
import layout from './quality/layout.json' with { type: 'json' };
import thresholds from './quality/thresholds.json' with { type: 'json' };

const { lint } = thresholds;

// --- Règles du domaine (CLAUDE.md §10.2) -----------------------------------
// Dans une config plate, un bloc postérieur REMPLACE la liste `no-restricted-syntax`
// d'un bloc antérieur : chaque bloc ci-dessous porte donc sa liste complète.
const SELECTORS = {
  parseFloat: {
    selector: "CallExpression[callee.name='parseFloat']",
    message: 'parseFloat interdit : parser les montants en chaîne vers bigint',
  },
  numberParseFloat: {
    selector: "CallExpression[callee.property.name='parseFloat']",
    message: 'Number.parseFloat interdit : parser les montants en chaîne vers bigint',
  },
  sqlRaw: {
    selector: "MemberExpression[object.name='sql'][property.name='raw']",
    message: 'sql.raw interdit : requêtes paramétrées uniquement',
  },
  numberCall: {
    selector: "CallExpression[callee.name='Number']",
    message: 'Number( interdit hors des DTO (layout.dto) : bigint pour les montants',
  },
  newDate: {
    selector: "NewExpression[callee.name='Date']",
    message: 'new Date interdit hors Clock (layout.clock) : utiliser Temporal et le Clock injecté',
  },
  dateNow: {
    selector: "MemberExpression[object.name='Date'][property.name='now']",
    message: 'Date.now interdit hors Clock (layout.clock) : utiliser le Clock injecté',
  },
  processEnv: {
    selector: "MemberExpression[object.name='process'][property.name='env']",
    message: 'process.env interdit hors config (layout.config) : lire la configuration validée',
  },
  mathRound: {
    selector: "MemberExpression[object.name='Math'][property.name='round']",
    message: 'Math.round interdit dans le domaine pur : répartition au plus grand reste',
  },
};

// Chaque exception de fichier lève un sélecteur précis (globs lus dans layout.json).
const EXCEPTIONS = [
  { globs: layout.dto, lifts: ['numberCall'] },
  { globs: layout.clock, lifts: ['newDate', 'dateNow'] },
  { globs: layout.config, lifts: ['processEnv'] },
];

const SRC_NAMES = Object.keys(SELECTORS).filter((name) => name !== 'mathRound');

function restricted(names) {
  return ['error', ...names.map((name) => SELECTORS[name])];
}

// Un fichier d'exception qui vit dans le périmètre pur (ex. src/shared/clock.ts) garde Math.round interdit.
function overlapsPure(globs) {
  return globs.some((glob) => layout.pure.some((pure) => matchesGlob(glob, pure)));
}

const domainBlocks = [
  {
    files: ['src/**/*.ts'],
    rules: { 'no-restricted-syntax': restricted(SRC_NAMES), 'no-console': 'error' },
  },
  {
    files: layout.pure,
    rules: { 'no-restricted-syntax': restricted([...SRC_NAMES, 'mathRound']) },
  },
  ...EXCEPTIONS.map(({ globs, lifts }) => ({
    files: globs,
    rules: {
      'no-restricted-syntax': restricted([
        ...SRC_NAMES.filter((name) => !lifts.includes(name)),
        ...(overlapsPure(globs) ? ['mathRound'] : []),
      ]),
    },
  })),
];

// --- Règles de tests --------------------------------------------------------
const WEAK_MATCHERS = {
  toBeTruthy: 'Assertion creuse : vérifier la valeur exacte',
  toBeDefined: 'Assertion creuse : vérifier la valeur exacte',
  toBeFalsy: 'Assertion creuse : vérifier la valeur exacte',
};
const PURE_TEST_GLOBS = layout.pure.map((glob) => glob.replace(/\*\*$/, '**/*.test.ts'));

const testRules = {
  'vitest/expect-expect': 'error',
  'vitest/no-disabled-tests': 'error',
  'vitest/no-focused-tests': 'error',
  'vitest/no-conditional-expect': 'error',
  'vitest/no-conditional-tests': 'error',
  'vitest/valid-expect': 'error',
  'vitest/no-identical-title': 'error',
  'vitest/no-commented-out-tests': 'error',
  'vitest/require-to-throw-message': 'error',
  'vitest/no-restricted-matchers': ['error', WEAK_MATCHERS],
};

export default defineConfig(
  {
    ignores: ['reports/**', 'coverage/**', '.stryker-tmp/**', 'node_modules/**', 'semgrep/**'],
  },
  { linterOptions: { reportUnusedDisableDirectives: 'error' } },
  {
    files: ['**/*.ts'],
    extends: [
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      sonarjs.configs.recommended,
      comments.recommended,
    ],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      '@typescript-eslint/consistent-type-assertions': ['error', { assertionStyle: 'never' }],
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/strict-boolean-expressions': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      '@typescript-eslint/no-unnecessary-condition': 'error',
      'sonarjs/cognitive-complexity': ['error', lint.cognitiveComplexity],
      'max-lines-per-function': [
        'error',
        { max: lint.maxLinesPerFunction, skipBlankLines: true, skipComments: true },
      ],
      'max-depth': ['error', lint.maxDepth],
      'max-params': ['error', lint.maxParams],
      'max-lines': ['error', { max: lint.maxLines, skipBlankLines: true, skipComments: true }],
      '@eslint-community/eslint-comments/require-description': 'error',
      '@eslint-community/eslint-comments/no-unlimited-disable': 'error',
      '@eslint-community/eslint-comments/no-unused-disable': 'error',
      '@eslint-community/eslint-comments/disable-enable-pair': 'error',
    },
  },
  ...domainBlocks,
  {
    files: ['**/*.test.ts'],
    extends: [vitest.configs.recommended],
    rules: testRules,
  },
  {
    files: PURE_TEST_GLOBS,
    rules: {
      'vitest/no-restricted-matchers': [
        'error',
        {
          ...WEAK_MATCHERS,
          toMatchSnapshot: 'Snapshot interdit sur le domaine pur : asserter les valeurs',
        },
      ],
    },
  },
  {
    files: ['**/*.mjs', '**/*.cjs'],
    extends: [tseslint.configs.disableTypeChecked],
  },
);
