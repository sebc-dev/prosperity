import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'deadcode', tool: 'knip', severity: 'blocking' };
const NORMAL_CODES = new Set([0, 1]);

function itemIssue(type: string, file: string, item: unknown): Issue {
  const record = isRecord(item) ? item : {};
  const name = typeof record['name'] === 'string' ? record['name'] : file;
  const issue: Issue = { rule: type, message: `${type} : ${name}`, file };
  if (typeof record['line'] === 'number') {
    issue.line = record['line'];
  }
  return issue;
}

/** Une entrée de `issues[]` porte un tableau par type de problème (`files`, `exports`, `unlisted`…). */
function entryIssues(entry: unknown): Issue[] | undefined {
  if (!isRecord(entry) || typeof entry['file'] !== 'string') {
    return undefined;
  }
  const file = entry['file'];
  return Object.entries(entry).flatMap(([type, items]) => {
    if (type === 'file' || !Array.isArray(items)) {
      return [];
    }
    const list: unknown[] = items;
    return list.map((item) => itemIssue(type, file, item));
  });
}

/** Sortie `--reporter json` : `{ issues: [{ file, files: [], exports: [{ name, line }], … }] }`. */
function parseKnipOutput(stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || !Array.isArray(parsed['issues'])) {
    return undefined;
  }
  const entries: unknown[] = parsed['issues'];
  const all: Issue[] = [];
  for (const entry of entries) {
    const issues = entryIssues(entry);
    if (issues === undefined) {
      return undefined;
    }
    all.push(...issues);
  }
  return all;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'knip');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('knip', version.found, version.expected),
      start,
    );
  }
  const knip = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'knip'),
    args: ['--reporter', 'json'],
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const issues = NORMAL_CODES.has(knip.code) ? parseKnipOutput(knip.stdout) : undefined;
  // Code 1 sans issue lisible : on ne conclut jamais « passé ».
  if (issues === undefined || (knip.code === 1 && issues.length === 0)) {
    return failedResult(META, version.found, toolErrorIssue('knip', knip.code, knip.stderr), start);
  }
  return buildResult(
    META,
    { status: issues.length > 0 ? 'failed' : 'passed', version: version.found, issues },
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
