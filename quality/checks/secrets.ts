import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runMiseTool, runTool, verifyMiseToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'secrets', tool: 'gitleaks', severity: 'blocking' };
const TOOL = META.tool;

/**
 * Pointe de l'ancien `main` (décision `merge-ours` du plan 01-01) : l'historique hérité est déjà
 * public, son scan ne peut rien corriger. Il est exclu du scan quand il est ancêtre de HEAD.
 */
export const LEGACY_MAIN_SHA = '3c1c95519e5b21bb8575e45ac12859110249004c';

async function legacyIsAncestor(root: string): Promise<boolean> {
  const result = await runTool({
    command: 'git',
    args: ['merge-base', '--is-ancestor', LEGACY_MAIN_SHA, 'HEAD'],
    cwd: root,
    timeoutMs: 15_000,
  });
  return result.code === 0;
}

/** Seuls `RuleID`, `File`, `StartLine` et `Description` sont repris : jamais `Match` ni `Secret`. */
function toIssue(entry: unknown): Issue {
  if (!isRecord(entry)) {
    return { rule: 'tool-error', message: 'entrée gitleaks illisible' };
  }
  const issue: Issue = {
    rule: typeof entry['RuleID'] === 'string' ? entry['RuleID'] : 'gitleaks',
    message: typeof entry['Description'] === 'string' ? entry['Description'] : 'secret détecté',
  };
  if (typeof entry['File'] === 'string') {
    issue.file = entry['File'];
  }
  if (typeof entry['StartLine'] === 'number') {
    issue.line = entry['StartLine'];
  }
  return issue;
}

/** Rapport gitleaks : un tableau JSON (vide sans résultat). */
function parseReport(text: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (parsed === null) {
    return [];
  }
  return Array.isArray(parsed) ? parsed.map(toIssue) : undefined;
}

type ScanOutcome = { issues: Issue[] } | { error: Issue };

async function scan(root: string, extra: readonly string[]): Promise<ScanOutcome> {
  const dir = await mkdtemp(join(tmpdir(), 'gate-gitleaks-'));
  try {
    const reportPath = join(dir, 'report.json');
    const result = await runMiseTool(
      TOOL,
      [
        'git',
        '--report-format',
        'json',
        '--report-path',
        reportPath,
        '--redact',
        '--no-banner',
        '--exit-code',
        '0',
        ...extra,
      ],
      { cwd: root, timeoutMs: 120_000 },
    );
    const issues = result.code === 0 ? parseReport(await readFile(reportPath, 'utf8')) : undefined;
    return issues === undefined
      ? { error: toolErrorIssue(TOOL, result.code, result.stderr) }
      : { issues };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyMiseToolVersion(ctx.root, TOOL, ['version']);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue(TOOL, version.found, version.expected),
      start,
    );
  }
  const excludeLegacy = await legacyIsAncestor(ctx.root);
  const extra = excludeLegacy ? [`--log-opts=HEAD --not ${LEGACY_MAIN_SHA}`] : [];
  const outcome = await scan(ctx.root, extra);
  if ('error' in outcome) {
    return failedResult(META, version.found, outcome.error, start);
  }
  return buildResult(
    META,
    {
      status: outcome.issues.length === 0 ? 'passed' : 'failed',
      version: version.found,
      issues: outcome.issues,
      ...(excludeLegacy ? { note: 'historique hérité exclu (LEGACY_MAIN_SHA)' } : {}),
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'run',
  run,
};
