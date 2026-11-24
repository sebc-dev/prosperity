import { join, relative } from 'node:path';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { readJsonRecord, runTool } from '../tools.ts';
import { reportFiles, runVitestCheck } from '../vitest-kit.ts';

const META: CheckMeta = { id: 'coverage', tool: 'vitest', severity: 'blocking' };
const SUMMARY_PATH = join('reports', 'coverage-all', 'coverage-summary.json');
const SOURCE_DIR = 'src/db';
const TEST_SUFFIX = '.test.ts';

function scopeIssue(message: string, file?: string): Issue {
  return { rule: 'coverage-scope-incomplete', message, ...(file === undefined ? {} : { file }) };
}

/** Fichiers suivis de `src/db/` (hors tests) ; `undefined` si git ne répond pas. */
async function trackedDbFiles(root: string): Promise<string[] | undefined> {
  const listing = await runTool({
    command: 'git',
    args: ['ls-files', '--', SOURCE_DIR],
    cwd: root,
    timeoutMs: 15_000,
  });
  if (listing.code !== 0) {
    return undefined;
  }
  return listing.stdout
    .split('\n')
    .filter((file) => file.endsWith('.ts') && !file.endsWith(TEST_SUFFIX));
}

/**
 * Échec fermé : le plancher global porte sur tout `src/**`, infrastructure base de données
 * comprise. Un fichier suivi de `src/db/` absent du rapport, ou une intégration qui n'a pas été
 * fusionnée au run, rendraient le plancher trompeur.
 */
async function scopeIssues(root: string, reportText: string): Promise<Issue[]> {
  const issues: Issue[] = [];
  const tracked = await trackedDbFiles(root);
  if (tracked === undefined) {
    issues.push(scopeIssue(`impossible de lister les fichiers suivis de ${SOURCE_DIR} (git)`));
  } else {
    const summary = await readJsonRecord(join(root, SUMMARY_PATH));
    const covered = new Set(Object.keys(summary).map((path) => relative(root, path)));
    for (const file of tracked.filter((candidate) => !covered.has(candidate))) {
      issues.push(scopeIssue('fichier absent du rapport de couverture fusionné', file));
    }
  }
  const ranIntegration = (reportFiles(reportText) ?? []).some(
    (entry) => typeof entry['name'] === 'string' && entry['name'].endsWith('.int.test.ts'),
  );
  if (!ranIntegration) {
    issues.push(scopeIssue('aucun test d’intégration dans le run : couverture non fusionnée'));
  }
  return issues;
}

/**
 * Plancher global de couverture (85 % lignes, 80 % branches) sur tout `src/**`, `src/db/**`
 * compris (décision humaine). Un seul processus Vitest sélectionne les projets `unit` et
 * `integration` : la couverture est collectée pour tout le processus, donc fusionnée.
 * `--exclude 'quality/**'` retire seulement les tests de la gate (ils ne couvrent aucun fichier
 * de `src/` et le check `unit` les joue déjà). Sans Docker : `failed` avec `docker-unavailable`,
 * jamais `skipped` en profil full.
 */
function run(ctx: CheckContext): Promise<CheckResult> {
  return runVitestCheck(ctx, {
    meta: META,
    reportPath: join('reports', 'vitest-coverage.json'),
    args: [
      '--project',
      'unit',
      '--project',
      'integration',
      '--exclude',
      'quality/**',
      '--coverage',
    ],
    env: { GATE_COVERAGE_SCOPE: 'all' },
    needsDocker: true,
    // Une couverture mesurée sur un run rouge ne fait pas foi.
    failedTestRule: 'coverage-run-test-failed',
    extraIssues: scopeIssues,
  });
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  // D-12 : il embarque l'intégration PostgreSQL complète, il est joué en CI seulement.
  push: 'skip-ci-only',
  run,
};
