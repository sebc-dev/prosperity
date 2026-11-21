import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool } from '../tools.ts';

const META: CheckMeta = { id: 'integrity', tool: 'integrity', severity: 'blocking' };
const VERSION = '1';
const TRUSTED_REPORT = join('reports', 'integrity.json');

function missingReport(message: string, start: number): CheckResult {
  return failedResult(META, VERSION, { rule: 'missing-trusted-report', message }, start);
}

function toIssue(value: unknown): Issue[] {
  if (
    !isRecord(value) ||
    typeof value['rule'] !== 'string' ||
    typeof value['message'] !== 'string'
  ) {
    return [];
  }
  const file = value['file'];
  return [
    {
      rule: value['rule'],
      message: value['message'],
      ...(typeof file === 'string' ? { file } : {}),
    },
  ];
}

/** Résultat d'intégrité sérialisé par `quality/integrity.ts` ; `undefined` s'il est illisible. */
function parseResult(text: string, start: number): CheckResult | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || parsed['check'] !== 'integrity' || !Array.isArray(parsed['issues'])) {
    return undefined;
  }
  const status = parsed['status'];
  if (status !== 'passed' && status !== 'failed') {
    return undefined;
  }
  const issues: unknown[] = parsed['issues'];
  const note = parsed['note'];
  return buildResult(
    META,
    {
      status,
      version: VERSION,
      issues: issues.flatMap(toIssue),
      ...(typeof note === 'string' ? { note } : {}),
    },
    start,
  );
}

/** En CI sur `pull_request` : le rapport de l'étape de confiance, échec fermé s'il manque. */
async function fromTrustedReport(ctx: CheckContext, start: number): Promise<CheckResult> {
  let text: string;
  try {
    text = await readFile(join(ctx.root, TRUSTED_REPORT), 'utf8');
  } catch {
    return missingReport(
      `${TRUSTED_REPORT} absent : l'étape de confiance ne l'a pas produit`,
      start,
    );
  }
  return parseResult(text, start) ?? missingReport(`${TRUSTED_REPORT} illisible`, start);
}

/** Auto-test local : `GATE_BASE_DIR` désigne la copie de base, la tête est le dépôt courant. */
async function runAgainstBase(
  ctx: CheckContext,
  baseDir: string,
  start: number,
): Promise<CheckResult> {
  const scratch = await mkdtemp(join(tmpdir(), 'gate-integrity-'));
  try {
    const out = join(scratch, 'integrity.json');
    const kinds = ctx.env['GATE_APPROVED_KINDS'] ?? '';
    const run = await runTool({
      command: process.execPath,
      args: [
        join(ctx.root, 'quality', 'integrity.ts'),
        '--base-dir',
        baseDir,
        '--head-dir',
        ctx.root,
        '--out',
        out,
        ...(kinds === '' ? [] : ['--approved', kinds]),
      ],
      cwd: ctx.root,
      timeoutMs: 120_000,
    });
    const text = await readFile(out, 'utf8').catch(() => '');
    const result = run.code <= 1 ? parseResult(text, start) : undefined;
    return (
      result ??
      failedResult(META, VERSION, toolErrorIssue('integrity', run.code, run.stderr), start)
    );
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }
}

function skipped(): CheckResult {
  return {
    check: META.id,
    tool: META.tool,
    version: VERSION,
    severity: META.severity,
    passed: false,
    status: 'skipped',
    skipped_reason: 'ci-only',
    issues: [],
    duration_ms: 0,
  };
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const baseDir = ctx.env['GATE_BASE_DIR'] ?? '';
  if (baseDir !== '') {
    return runAgainstBase(ctx, baseDir, start);
  }
  if (!ctx.inCi) {
    return skipped();
  }
  if (ctx.env['GITHUB_EVENT_NAME'] === 'pull_request') {
    return fromTrustedReport(ctx, start);
  }
  return buildResult(
    META,
    {
      status: 'passed',
      version: VERSION,
      issues: [],
      note: 'hors pull_request : aucune base à comparer',
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
