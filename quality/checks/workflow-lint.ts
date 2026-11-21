import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runMiseTool, verifyMiseToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'workflow-lint', tool: 'actionlint', severity: 'blocking' };
const TOOL = META.tool;
const WORKFLOWS_DIR = '.github/workflows';

function toIssue(entry: unknown): Issue {
  if (!isRecord(entry)) {
    return { rule: 'tool-error', message: 'entrée actionlint illisible' };
  }
  const issue: Issue = {
    rule: typeof entry['kind'] === 'string' ? entry['kind'] : 'actionlint',
    message: typeof entry['message'] === 'string' ? entry['message'] : '',
  };
  if (typeof entry['filepath'] === 'string') {
    issue.file = entry['filepath'];
  }
  if (typeof entry['line'] === 'number') {
    issue.line = entry['line'];
  }
  return issue;
}

/** Sortie `-format '{{json .}}'` : un tableau d'erreurs, ou `null` sans erreur. */
function parseActionlintOutput(stdout: string): Issue[] | undefined {
  const text = stdout.trim();
  if (text === '') {
    return [];
  }
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

async function listWorkflows(root: string): Promise<string[]> {
  try {
    const names = await readdir(join(root, WORKFLOWS_DIR));
    return names
      .filter((name) => name.endsWith('.yml') || name.endsWith('.yaml'))
      .sort()
      .map((name) => `${WORKFLOWS_DIR}/${name}`);
  } catch {
    return [];
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyMiseToolVersion(ctx.root, TOOL, ['-version']);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue(TOOL, version.found, version.expected),
      start,
    );
  }

  const files = await listWorkflows(ctx.root);
  if (files.length === 0) {
    return buildResult(
      META,
      { status: 'passed', version: version.found, issues: [], note: 'aucun workflow à vérifier' },
      start,
    );
  }

  const lint = await runMiseTool(TOOL, ['-format', '{{json .}}', ...files], {
    cwd: ctx.root,
    timeoutMs: 60_000,
  });
  // Le verdict vient de la sortie structurée ; le code 0/1 ne départage pas (Pitfall 3).
  const issues =
    lint.code === 0 || lint.code === 1 ? parseActionlintOutput(lint.stdout) : undefined;
  if (issues === undefined) {
    return failedResult(META, version.found, toolErrorIssue(TOOL, lint.code, lint.stderr), start);
  }
  return buildResult(
    META,
    { status: issues.length === 0 ? 'passed' : 'failed', version: version.found, issues },
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
