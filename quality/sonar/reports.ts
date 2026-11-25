import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { runTool } from '../tools.ts';
import { childEnv, relativizeEslintReport, relativizeLcov } from './sonar-kit.ts';
import type { Coverage, Failure } from './sonar-kit.ts';

// Rapports que Sonar importe (D-16) : ESLint en JSON (configuration bloquante, puis configuration de
// sécurité) et couverture LCOV. Tous écrits sous `reports/sonar/` (ignoré par git). Les processus de
// lint et de tests ne reçoivent jamais le jeton ni l'adresse du serveur (`childEnv`).

const LINT_TIMEOUT_MS = 300_000;
const TEST_TIMEOUT_MS = 1_800_000;
const REPORT_DIR = 'reports/sonar';
const LCOV = `${REPORT_DIR}/coverage/lcov.info`;

async function eslintReport(
  root: string,
  name: string,
  extra: readonly string[],
): Promise<Failure | undefined> {
  const run = await runTool({
    command: join(root, 'node_modules', '.bin', 'eslint'),
    args: [...extra, '.', '--format', 'json', '--output-file', `${REPORT_DIR}/${name}.json`],
    cwd: root,
    env: childEnv(process.env),
    timeoutMs: LINT_TIMEOUT_MS,
  });
  // 0 : aucune erreur ; 1 : des erreurs de lint (le rapport est écrit) ; au-delà : ESLint a échoué.
  return run.code <= 1
    ? undefined
    : { error: `ESLint (${name}) a échoué : code ${String(run.code)}` };
}

async function coverageReport(root: string, coverage: Coverage): Promise<Failure | undefined> {
  const projects = coverage === 'full' ? ['unit', 'integration'] : ['unit'];
  const run = await runTool({
    command: join(root, 'node_modules', '.bin', 'vitest'),
    args: [
      'run',
      ...projects.flatMap((name) => ['--project', name]),
      '--coverage.enabled',
      '--coverage.reporter=lcovonly',
      // Sans cette option, Vitest n'écrit aucun rapport quand un test échoue : l'analyse advisory
      // perdait alors tout le LCOV.
      '--coverage.reportOnFailure',
      `--coverage.reportsDirectory=${REPORT_DIR}/coverage`,
    ],
    cwd: root,
    env: { ...childEnv(process.env), GATE_COVERAGE_SCOPE: 'all' },
    timeoutMs: TEST_TIMEOUT_MS,
  });
  // Code 1 : tests ou seuils de couverture en échec ; le LCOV est écrit quand même (analyse advisory).
  if (run.code > 1) {
    return { error: `Vitest a échoué : code ${String(run.code)}` };
  }
  if (run.code === 1) {
    process.stderr.write(
      'avertissement : Vitest a rendu 1 (tests ou seuils) ; analyse poursuivie (advisory)\n',
    );
  }
  return undefined;
}

/** ESLint ne connaît que les chemins absolus ; le scanner voit la racine du dépôt sous `/usr/src`. */
async function relativizeReports(root: string): Promise<void> {
  const lcov = join(root, LCOV);
  await writeFile(lcov, relativizeLcov(await readFile(lcov, 'utf8'), root), 'utf8');
  for (const name of ['eslint', 'eslint-security']) {
    const path = join(root, REPORT_DIR, `${name}.json`);
    const parsed: unknown = JSON.parse(await readFile(path, 'utf8'));
    await writeFile(path, JSON.stringify(relativizeEslintReport(parsed, root)), 'utf8');
  }
}

/** Recrée `reports/sonar/` et y produit les trois rapports ; aucune analyse n'est envoyée sans LCOV. */
export async function produceReports(
  root: string,
  coverage: Coverage,
): Promise<Failure | undefined> {
  await rm(join(root, REPORT_DIR), { recursive: true, force: true });
  await mkdir(join(root, REPORT_DIR), { recursive: true });
  const failure =
    (await eslintReport(root, 'eslint', [])) ??
    (await eslintReport(root, 'eslint-security', ['--config', 'eslint.security.config.mjs'])) ??
    (await coverageReport(root, coverage));
  if (failure !== undefined) {
    return failure;
  }
  try {
    await relativizeReports(root);
  } catch {
    return {
      error: `rapport manquant ou illisible (${LCOV} ou ESLint JSON) : aucune analyse envoyée`,
    };
  }
  return undefined;
}
