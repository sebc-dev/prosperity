import { mkdtemp, rm } from 'node:fs/promises';
import { availableParallelism, tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { writeJsonAtomic } from '../gate-report.ts';
import { runCase, runControls, toResult } from './case-runner.ts';
import { loadCases, matchesExpected, SelectionError, selectCases } from './cases.ts';
import type { CaseResult, SelftestCase } from './cases.ts';
import { git, localEnv, pnpmInstall, tail } from './context.ts';
import type { Installer, RunContext, Verdict } from './context.ts';
import {
  addWorktree,
  cleanupStaleWorktrees,
  RUN_DIR_PREFIX,
  removeAllWorktreesSync,
  removeWorktree,
  trackRunDir,
  untrackRunDir,
  worktreeName,
} from './worktrees.ts';

export { matchesExpected, selectCases };

const EXIT_PASS = 0;
const EXIT_RED = 1;
const EXIT_USAGE = 2;
const DEFAULT_REPORT = join('reports', 'selftest.json');

export interface RunSelftestOptions {
  root: string;
  spec?: string | undefined;
  jobs: number;
  env: NodeJS.ProcessEnv;
  install: Installer;
}

export interface SelftestReport {
  generated_at: string;
  commit: string;
  cases: CaseResult[];
}

async function pool<T, R>(
  items: readonly T[],
  jobs: number,
  work: (item: T) => Promise<R>,
): Promise<R[]> {
  const results: R[] = [];
  let next = 0;
  const workers = Array.from({ length: Math.min(jobs, items.length) }, async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      const item = items[index];
      if (item !== undefined) {
        results[index] = await work(item);
      }
    }
  });
  await Promise.all(workers);
  return results;
}

async function headOf(root: string): Promise<string> {
  const outcome = await git(root, ['rev-parse', 'HEAD'], process.env);
  if (outcome.code !== 0) {
    throw new Error(`git rev-parse HEAD a échoué : ${tail(outcome.stderr)}`);
  }
  return outcome.stdout.trim();
}

async function selectedCases(root: string, spec: string | undefined): Promise<SelftestCase[]> {
  const all = await loadCases(root);
  const ids = new Set(
    selectCases(
      all.map((item) => item.id),
      spec,
    ),
  );
  if (ids.size === 0) {
    throw new SelectionError("aucun cas d'auto-test dans quality/selftest/cases");
  }
  return all.filter((item) => ids.has(item.id));
}

async function playCases(
  ctx: RunContext,
  cases: readonly SelftestCase[],
  jobs: number,
): Promise<CaseResult[]> {
  const base = await ctx.install(ctx.baseDir, ctx.env);
  if (!base.ok) {
    const failure: Verdict = { status: 'failed', reason: 'install-failed', detail: base.message };
    return cases.map((item) => toResult(item, Date.now(), failure));
  }
  const controls = await runControls(ctx, [...new Set(cases.map((item) => item.check))]);
  return pool(cases, jobs, (item) => runCase(ctx, item, controls.get(item.check)));
}

/**
 * Joue les cas retenus (D-07a). La sélection et la lecture des cas précèdent toute création de
 * worktree ; tout ce qui est créé est retiré en `finally`.
 */
export async function runSelftest(options: RunSelftestOptions): Promise<SelftestReport> {
  const root = resolve(options.root);
  const cases = await selectedCases(root, options.spec);
  await cleanupStaleWorktrees(root);
  const headSha = await headOf(root);
  const runDir = await mkdtemp(join(tmpdir(), RUN_DIR_PREFIX));
  trackRunDir(runDir);
  const baseDir = join(runDir, worktreeName('base'));
  const env = localEnv(options.env, runDir);
  try {
    await addWorktree(root, baseDir, headSha);
    const ctx: RunContext = { root, runDir, baseDir, headSha, env, install: options.install };
    const results = await playCases(ctx, cases, options.jobs);
    return { generated_at: new Date().toISOString(), commit: headSha, cases: results };
  } finally {
    await removeWorktree(root, baseDir);
    await rm(runDir, { recursive: true, force: true });
    untrackRunDir(runDir);
  }
}

// --- CLI ---------------------------------------------------------------------------------------

class UsageError extends Error {}

interface CliOptions {
  spec: string | undefined;
  jobs: number;
  report: string;
  root: string;
}

function parseJobs(raw: string | undefined): number {
  if (raw === undefined) {
    return Math.min(4, availableParallelism());
  }
  if (!/^[1-9]\d*$/.test(raw)) {
    throw new UsageError(`--jobs attend un entier strictement positif (reçu « ${raw} »)`);
  }
  return Number.parseInt(raw, 10);
}

function parseCli(argv: readonly string[], env: NodeJS.ProcessEnv): CliOptions {
  let values;
  try {
    ({ values } = parseArgs({
      args: [...argv],
      options: {
        case: { type: 'string' },
        jobs: { type: 'string' },
        report: { type: 'string' },
        root: { type: 'string' },
      },
      strict: true,
      allowPositionals: false,
    }));
  } catch (error) {
    throw new UsageError(error instanceof Error ? error.message : 'arguments illisibles');
  }
  const root = resolve(values.root ?? join(import.meta.dirname, '..', '..'));
  const fromEnv = env['GATE_SELFTEST_CASES'];
  return {
    spec: values.case ?? (fromEnv === undefined || fromEnv === '' ? undefined : fromEnv),
    jobs: parseJobs(values.jobs),
    report: resolve(root, values.report ?? DEFAULT_REPORT),
    root,
  };
}

function printTable(cases: readonly CaseResult[]): void {
  const width = Math.max(4, ...cases.map((item) => item.id.length));
  process.stdout.write(`${'cas'.padEnd(width)}  statut  raison\n`);
  for (const item of cases) {
    const detail = item.detail === undefined ? '' : ` (${item.detail})`;
    const line = `${item.id.padEnd(width)}  ${item.status.padEnd(6)}  ${item.reason}${detail}`;
    process.stdout.write(`${line}\n`);
  }
}

/** Un signal d'arrêt retire les dossiers de ce processus ; `git worktree prune` finit au démarrage suivant. */
function cleanOnSignals(): void {
  const codes: Record<string, number> = { SIGINT: 130, SIGTERM: 143 };
  for (const [signal, code] of Object.entries(codes)) {
    process.once(signal, () => {
      removeAllWorktreesSync();
      process.exit(code);
    });
  }
}

async function main(): Promise<number> {
  const options = parseCli(process.argv.slice(2), process.env);
  cleanOnSignals();
  const report = await runSelftest({
    root: options.root,
    spec: options.spec,
    jobs: options.jobs,
    env: process.env,
    install: pnpmInstall,
  });
  await writeJsonAtomic(options.report, report);
  printTable(report.cases);
  return report.cases.every((item) => item.status === 'passed') ? EXIT_PASS : EXIT_RED;
}

if (import.meta.main) {
  try {
    process.exitCode = await main();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    const usage = error instanceof UsageError || error instanceof SelectionError;
    process.exitCode = usage ? EXIT_USAGE : EXIT_RED;
  }
}
