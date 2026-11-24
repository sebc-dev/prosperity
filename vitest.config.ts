import { defineConfig } from 'vitest/config';
import layout from './quality/layout.json' with { type: 'json' };
import thresholds from './quality/thresholds.json' with { type: 'json' };

// Périmètre de couverture choisi par `GATE_COVERAGE_SCOPE` :
// - `all` (défaut) : tout `src/**/*.ts`, aucun dossier retiré (plancher global) ;
// - `pure` : les seuls globs de `layout.pure` (posé par le check `unit`).
// Toute autre valeur est une erreur de configuration (échec fermé).
const scope = process.env['GATE_COVERAGE_SCOPE'] ?? 'all';
if (scope !== 'all' && scope !== 'pure') {
  throw new Error(`GATE_COVERAGE_SCOPE inconnu « ${scope} » (attendu : all | pure)`);
}

const toSourceGlob = (glob: string): string => glob.replace(/\*\*$/, '**/*.ts');

const include = scope === 'pure' ? layout.pure.map(toSourceGlob) : ['src/**/*.ts'];

// Mêmes seuils dans les deux périmètres : valeurs de `quality/thresholds.json`, jamais recopiées.
const pureThresholds = Object.fromEntries(
  layout.pure.map((glob) => [glob, thresholds.coverage.pure]),
);

export default defineConfig({
  test: {
    passWithNoTests: false,
    allowOnly: false,
    setupFiles: ['test/setup/fast-check.ts'],
    sequence: { shuffle: { files: true, tests: true } },
    projects: [
      {
        extends: true,
        test: { name: 'unit', include: ['src/**/*.test.ts', 'quality/**/*.test.ts'] },
      },
      // Le runner Vitest de Stryker joue tous les projets de la config : `stryker.config.mjs`
      // pose GATE_INTEGRATION=off pour que chaque mutant ne démarre pas PostgreSQL.
      ...(process.env['GATE_INTEGRATION'] === 'off'
        ? []
        : [
            {
              extends: true,
              test: {
                name: 'integration',
                include: ['test/**/*.int.test.ts'],
                globalSetup: ['test/global-setup.ts'],
                testTimeout: 120_000,
                hookTimeout: 120_000,
              },
            },
          ]),
    ],
    coverage: {
      provider: 'v8',
      include,
      exclude: ['src/**/*.test.ts'],
      reportsDirectory: scope === 'pure' ? 'reports/coverage' : 'reports/coverage-all',
      reporter: ['text', 'json-summary', 'json'],
      thresholds: { ...pureThresholds, ...thresholds.coverage.global },
    },
  },
});
