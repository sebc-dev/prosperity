import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isProtected, loadProtectedPaths } from '../protected-paths.ts';
import { parseSelftestReport } from '../selftest/cases.ts';
import type { CaseResult } from '../selftest/cases.ts';
import { isRecord, runTool } from '../tools.ts';

const META: CheckMeta = { id: 'selftest', tool: 'selftest', severity: 'blocking' };
const VERSION = '1';
const NOT_TRIGGERED = 'non déclenché : aucun chemin protégé modifié (D-08)';
const SELFTEST_TIMEOUT_MS = 1_800_000;

async function git(ctx: CheckContext, args: readonly string[]): Promise<string | undefined> {
  const outcome = await runTool({ command: 'git', args, cwd: ctx.root, timeoutMs: 60_000 });
  return outcome.code === 0 ? outcome.stdout : undefined;
}

/** Fichiers du diff `base...HEAD` ; `undefined` quand git ne peut pas le calculer. */
async function changedFiles(ctx: CheckContext): Promise<string[] | undefined> {
  if (ctx.base.startsWith('-')) {
    return undefined;
  }
  // --no-renames : un fichier sorti d'un chemin protégé par renommage reste visible sous son ancien
  // chemin.
  const out = await git(ctx, ['diff', '--name-only', '--no-renames', `${ctx.base}...HEAD`]);
  return out?.split('\n').filter((line) => line !== '');
}

/** Globs protégés de la base : un fichier absent ou illisible ne protège rien de plus. */
async function baseGlobs(ctx: CheckContext): Promise<string[]> {
  const out = await git(ctx, ['show', `${ctx.base}:quality/protected-paths.json`]);
  try {
    const parsed: unknown = JSON.parse(out ?? '');
    const paths = isRecord(parsed) ? parsed['paths'] : undefined;
    const list: unknown[] = Array.isArray(paths) ? paths : [];
    return list.filter((glob) => typeof glob === 'string');
  } catch {
    return [];
  }
}

/**
 * D-08 : l'auto-test se joue sur demande (`--only`), de force (`GATE_FORCE_SELFTEST=1`, le
 * nightly), ou en CI quand le diff touche un chemin protégé (union des listes de la base et de la
 * tête). Un diff qu'on ne sait pas calculer déclenche : jamais de « vert par saut ».
 */
export async function isSelftestTriggered(ctx: CheckContext): Promise<boolean> {
  if (ctx.selected || ctx.env['GATE_FORCE_SELFTEST'] === '1') {
    return true;
  }
  if (!ctx.inCi) {
    return false;
  }
  const changed = await changedFiles(ctx);
  if (changed === undefined) {
    return true;
  }
  const globs = [...(await loadProtectedPaths(ctx.root)).paths, ...(await baseGlobs(ctx))];
  return changed.some((file) => isProtected(file, globs));
}

/** Une issue `case-not-detected:<id>` par cas rouge. */
export function casesToIssues(cases: readonly CaseResult[]): Issue[] {
  return cases
    .filter((item) => item.status === 'failed')
    .map((item) => {
      const detail = item.detail === undefined ? '' : ` (${item.detail})`;
      return {
        rule: `case-not-detected:${item.id}`,
        message: `${item.check} / ${item.rule} : ${item.reason}${detail}`,
      };
    });
}

async function playSelftest(ctx: CheckContext, start: number): Promise<CheckResult> {
  const scratch = await mkdtemp(join(tmpdir(), 'gate-selftest-report-'));
  try {
    const report = join(scratch, 'selftest.json');
    const spec = ctx.env['GATE_SELFTEST_CASES'];
    const run = await runTool({
      command: process.execPath,
      args: [
        join(ctx.root, 'quality', 'selftest', 'run.ts'),
        ...(spec === undefined || spec === '' ? [] : ['--case', spec]),
        '--report',
        report,
      ],
      cwd: ctx.root,
      env: ctx.env,
      timeoutMs: SELFTEST_TIMEOUT_MS,
    });
    const text = await readFile(report, 'utf8').catch(() => '');
    const cases = run.code <= 1 ? parseSelftestReport(text) : undefined;
    if (cases === undefined || cases.length === 0) {
      return failedResult(META, VERSION, toolErrorIssue('selftest', run.code, run.stderr), start);
    }
    const issues = casesToIssues(cases);
    return buildResult(
      META,
      {
        status: issues.length === 0 ? 'passed' : 'failed',
        version: VERSION,
        issues,
        note: `${String(cases.length)} cas joués`,
      },
      start,
    );
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  if (!(await isSelftestTriggered(ctx))) {
    return buildResult(
      META,
      { status: 'passed', version: VERSION, issues: [], note: NOT_TRIGGERED },
      start,
    );
  }
  return playSelftest(ctx, start);
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
