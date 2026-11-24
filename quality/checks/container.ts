import { basename } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runMiseTool, runTool, verifyMiseToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'container', tool: 'hadolint', severity: 'blocking' };
const TOOL = META.tool;
const NOT_APPLICABLE = 'non applicable : aucun Containerfile suivi';
const CONTAINER_NAME = /^(?:Containerfile|Dockerfile)$|\.(?:Containerfile|Dockerfile)$/;

/** Fichiers suivis par git : `Containerfile`, `Dockerfile` et `*.Containerfile`. */
async function listContainerfiles(root: string): Promise<string[] | undefined> {
  const listing = await runTool({
    command: 'git',
    args: ['ls-files', '-z'],
    cwd: root,
    timeoutMs: 15_000,
  });
  if (listing.code !== 0) {
    return undefined;
  }
  return listing.stdout
    .split('\0')
    .filter((path) => path !== '' && CONTAINER_NAME.test(basename(path)))
    .sort((a, b) => a.localeCompare(b));
}

function toIssue(entry: unknown): Issue {
  if (!isRecord(entry)) {
    return { rule: 'tool-error', message: 'entrée hadolint illisible' };
  }
  const issue: Issue = {
    rule: typeof entry['code'] === 'string' ? entry['code'] : 'hadolint',
    message: typeof entry['message'] === 'string' ? entry['message'] : '',
  };
  if (typeof entry['file'] === 'string') {
    issue.file = entry['file'];
  }
  if (typeof entry['line'] === 'number') {
    issue.line = entry['line'];
  }
  return issue;
}

/** Sortie `--format json` : un tableau de constats (vide sans constat). */
function parseHadolintOutput(stdout: string): Issue[] | undefined {
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
  return Array.isArray(parsed) ? parsed.map(toIssue) : undefined;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyMiseToolVersion(ctx.root, TOOL, ['--version']);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue(TOOL, version.found, version.expected),
      start,
    );
  }
  const files = await listContainerfiles(ctx.root);
  if (files === undefined) {
    return failedResult(
      META,
      version.found,
      { rule: 'tool-error', message: 'git ls-files a échoué' },
      start,
    );
  }
  // Q9 : jamais `skipped` — un dépôt sans Containerfile est conforme, et le dit.
  if (files.length === 0) {
    return buildResult(
      META,
      { status: 'passed', version: version.found, issues: [], note: NOT_APPLICABLE },
      start,
    );
  }
  const lint = await runMiseTool(TOOL, ['--format', 'json', ...files], {
    cwd: ctx.root,
    timeoutMs: 60_000,
  });
  // Le verdict vient de la sortie structurée ; le code 0/1 ne départage pas.
  const issues = lint.code === 0 || lint.code === 1 ? parseHadolintOutput(lint.stdout) : undefined;
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
  push: 'skip-ci-only',
  run,
};
