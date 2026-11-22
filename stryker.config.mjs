import layout from './quality/layout.json' with { type: 'json' };
import thresholds from './quality/thresholds.json' with { type: 'json' };

// Mutation : seuils et globs viennent de quality/*.json, jamais recopiés ici.
// Appel diff-scopé : `stryker run --mutate a.ts,b.ts` (la ligne de commande remplace `mutate`).
// Le runner Vitest n'a pas d'option de projet : il joue tous ceux de `vitest.config.ts`.
// Le projet `integration` (Docker, PostgreSQL) reste hors des runs de mutation ; les workers
// forkés héritent de cette variable.
process.env['GATE_INTEGRATION'] = 'off';

// Pas d'annotation de type importée d'`@stryker-mutator/api` : paquet transitif, non listé (knip).
export default {
  // Sous pnpm, les plugins ne se découvrent pas seuls (`Cannot find Checker plugin "typescript"`).
  plugins: ['@stryker-mutator/vitest-runner', '@stryker-mutator/typescript-checker'],
  testRunner: 'vitest',
  checkers: ['typescript'],
  tsconfigFile: 'tsconfig.json',
  mutate: [...layout.mutate, '!**/*.test.ts'],
  coverageAnalysis: 'perTest',
  reporters: ['json', 'clear-text'],
  jsonReporter: { fileName: 'reports/mutation/mutation.json' },
  // Bug #6004 : jamais de fichier incrémental committé ni d'option incrémentale en CI.
  incremental: false,
  // Mitigation du bug #6335 (faux survivants) : voir la mesure de stabilité du SUMMARY 01-03.
  disableBail: true,
  thresholds: thresholds.mutation,
  tempDirName: '.stryker-tmp',
  // Jamais `--logLevel debug` avec ce runner (issue #6272).
  vitest: { configFile: 'vitest.config.ts' },
};
