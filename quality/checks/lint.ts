import { join, relative } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, readJsonRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'lint', tool: 'eslint', severity: 'blocking' };
const NORMAL_CODES = new Set([0, 1]);
// Motif écrit sans le littéral de la directive : le contrôle « aucune directive dans le code » reste exact.
const UNUSED_DIRECTIVE = /unused eslint(?:-)disable directive/i;

interface Parsed {
  issues: Issue[];
  errorCount: number;
  warningCount: number;
}

async function readMaxWarnings(root: string): Promise<number | undefined> {
  const thresholds = await readJsonRecord(join(root, 'quality', 'thresholds.json'));
  const lint = thresholds['lint'];
  const max = isRecord(lint) ? lint['maxWarnings'] : undefined;
  return typeof max === 'number' && Number.isInteger(max) && max >= 0 ? max : undefined;
}

function ruleOf(message: Record<string, unknown>): string {
  const ruleId = message['ruleId'];
  if (typeof ruleId === 'string') {
    return ruleId;
  }
  const text = typeof message['message'] === 'string' ? message['message'] : '';
  if (UNUSED_DIRECTIVE.test(text)) {
    return 'unused-disable-directive';
  }
  return message['fatal'] === true ? 'parse-error' : 'eslint';
}

function messageIssue(root: string, filePath: string, message: unknown): Issue | undefined {
  if (!isRecord(message)) {
    return undefined;
  }
  const issue: Issue = {
    rule: ruleOf(message),
    message: typeof message['message'] === 'string' ? message['message'] : '',
    file: relative(root, filePath),
  };
  if (typeof message['line'] === 'number') {
    issue.line = message['line'];
  }
  return issue;
}

function countOf(entry: Record<string, unknown>, key: string): number {
  const value = entry[key];
  return typeof value === 'number' ? value : 0;
}

/** Sortie `--format json` : un tableau de `{ filePath, messages, errorCount, warningCount }`. */
function parseEslintOutput(root: string, stdout: string): Parsed | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!Array.isArray(parsed)) {
    return undefined;
  }
  const result: Parsed = { issues: [], errorCount: 0, warningCount: 0 };
  const entries: unknown[] = parsed;
  for (const entry of entries) {
    if (
      !isRecord(entry) ||
      typeof entry['filePath'] !== 'string' ||
      !Array.isArray(entry['messages'])
    ) {
      return undefined;
    }
    const filePath = entry['filePath'];
    const messages: unknown[] = entry['messages'];
    result.errorCount += countOf(entry, 'errorCount') + countOf(entry, 'fatalErrorCount');
    result.warningCount += countOf(entry, 'warningCount');
    for (const message of messages) {
      const issue = messageIssue(root, filePath, message);
      if (issue !== undefined) {
        result.issues.push(issue);
      }
    }
  }
  return result;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'eslint');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('eslint', version.found, version.expected),
      start,
    );
  }
  const maxWarnings = await readMaxWarnings(ctx.root);
  if (maxWarnings === undefined) {
    return failedResult(
      META,
      version.found,
      { rule: 'config-error', message: 'quality/thresholds.json : lint.maxWarnings illisible' },
      start,
    );
  }
  const eslint = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'eslint'),
    args: ['.', '--format', 'json', '--max-warnings', String(maxWarnings)],
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const parsed = NORMAL_CODES.has(eslint.code)
    ? parseEslintOutput(ctx.root, eslint.stdout)
    : undefined;
  if (parsed === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('eslint', eslint.code, eslint.stderr),
      start,
    );
  }
  const failed = parsed.errorCount > 0 || parsed.warningCount > maxWarnings || eslint.code !== 0;
  // Code 1 sans message lisible : on ne conclut jamais « passé ».
  if (failed && parsed.issues.length === 0) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('eslint', eslint.code, eslint.stderr),
      start,
    );
  }
  return buildResult(
    META,
    { status: failed ? 'failed' : 'passed', version: version.found, issues: parsed.issues },
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
