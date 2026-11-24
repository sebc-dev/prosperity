import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import { parseCheckResult } from '../deps-guard.ts';
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';
import { runTool } from '../tools.ts';

const META: CheckMeta = { id: 'deps', tool: 'deps-guard', severity: 'blocking' };
const REPORT = 'reports/deps.json';

/** Le rapport est écrit par l'étape de confiance, depuis une copie de la base ; illisible = absent. */
async function readTrustedReport(root: string): Promise<CheckResult | undefined> {
  try {
    return parseCheckResult(JSON.parse(await readFile(join(root, REPORT), 'utf8')));
  } catch {
    return undefined;
  }
}

async function runLocal(ctx: CheckContext, baseDir: string, start: number): Promise<CheckResult> {
  const dir = await mkdtemp(join(tmpdir(), 'gate-deps-'));
  try {
    const out = join(dir, 'deps.json');
    const approved = ctx.env['GATE_APPROVED_KINDS'] ?? '';
    const run = await runTool({
      command: process.execPath,
      args: [
        join(ctx.root, 'quality', 'deps-guard.ts'),
        ...['--base-dir', baseDir, '--head-dir', ctx.root, '--out', out],
        ...(approved === '' ? [] : ['--approved', approved]),
      ],
      cwd: ctx.root,
      env: ctx.env,
      timeoutMs: 120_000,
    });
    const report = await readFile(out, 'utf8')
      .then((text): unknown => JSON.parse(text))
      .then(parseCheckResult)
      .catch(() => undefined);
    return run.code <= 1 && report !== undefined
      ? report
      : failedResult(META, process.version, toolErrorIssue(META.tool, run.code, run.stderr), start);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  if (ctx.inCi) {
    if (ctx.env['GITHUB_EVENT_NAME'] !== 'pull_request') {
      const note = 'hors pull_request : jugé par le verdict de confiance';
      return buildResult(META, { status: 'passed', version: '', issues: [], note }, start);
    }
    const report = await readTrustedReport(ctx.root);
    if (report === undefined) {
      const message = `${REPORT} absent ou illisible : l'étape de confiance ne l'a pas produit`;
      return failedResult(META, '', { rule: 'missing-trusted-report', message }, start);
    }
    // Le rapport vient d'un fichier : ni sa sévérité ni son identité ne sont reprises telles quelles.
    return { ...report, check: META.id, tool: META.tool, severity: META.severity };
  }
  const baseDir = ctx.env['GATE_BASE_DIR'];
  if (baseDir !== undefined && baseDir !== '') {
    return runLocal(ctx, baseDir, start);
  }
  return {
    check: META.id,
    tool: META.tool,
    version: '',
    severity: META.severity,
    passed: false,
    status: 'skipped',
    skipped_reason: 'ci-only',
    issues: [],
    duration_ms: Date.now() - start,
  };
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
