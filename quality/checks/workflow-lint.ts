import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { runMiseTool, verifyMiseToolVersion } from '../tools.ts';

const ID = 'workflow-lint';
const TOOL = 'actionlint';
const WORKFLOWS_DIR = '.github/workflows';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

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

function result(
  partial: Pick<CheckResult, 'status' | 'issues' | 'version'> & { note?: string },
  start: number,
): CheckResult {
  return {
    check: ID,
    tool: TOOL,
    severity: 'blocking',
    passed: partial.status === 'passed',
    duration_ms: Date.now() - start,
    ...partial,
  };
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyMiseToolVersion(ctx.root, TOOL, ['-version']);
  if (!version.ok) {
    return result(
      {
        status: 'failed',
        version: version.found,
        issues: [
          {
            rule: 'tool-version-mismatch',
            message: `actionlint ${version.found || 'introuvable'} trouvé, ${version.expected} attendu (mise.toml)`,
          },
        ],
      },
      start,
    );
  }

  const files = await listWorkflows(ctx.root);
  if (files.length === 0) {
    return result(
      { status: 'passed', version: version.found, issues: [], note: 'aucun workflow à vérifier' },
      start,
    );
  }

  const lint = await runMiseTool(TOOL, ['-format', '{{json .}}', ...files], {
    cwd: ctx.root,
    timeoutMs: 60_000,
  });
  // Le verdict vient de la sortie structurée ; le code 0/1 ne départage pas (Pitfall 3).
  const issues = lint.code === 0 || lint.code === 1 ? parseActionlintOutput(lint.stdout) : undefined;
  if (issues === undefined) {
    return result(
      {
        status: 'failed',
        version: version.found,
        issues: [
          {
            rule: 'tool-error',
            message: `actionlint a échoué (code ${String(lint.code)}) : ${lint.stderr.trim().slice(0, 300)}`,
          },
        ],
      },
      start,
    );
  }
  return result(
    { status: issues.length === 0 ? 'passed' : 'failed', version: version.found, issues },
    start,
  );
}

export const check: CheckDefinition = {
  id: ID,
  tool: TOOL,
  severity: 'blocking',
  push: 'run',
  run,
};
