import { readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'duplication', tool: 'jscpd', severity: 'blocking' };
const NORMAL_CODES = new Set([0, 1]);
const REPORT_PATH = ['reports', 'jscpd', 'jscpd-report.json'];
const SCAN_ROOT = 'src';
const TEST_SUFFIX = '.test.ts';

/** Les noms du rapport sont relatifs au dossier scanné (`src`). */
function sourceName(clone: Record<string, unknown>, key: 'firstFile' | 'secondFile'): string {
  const file = clone[key];
  const name = isRecord(file) ? file['name'] : undefined;
  return typeof name === 'string' ? `${SCAN_ROOT}/${name}` : '';
}

function lineOf(clone: Record<string, unknown>): number | undefined {
  const file = clone['firstFile'];
  const start = isRecord(file) ? file['start'] : undefined;
  return typeof start === 'number' ? start : undefined;
}

/**
 * Un clone nouveau entre fichiers hors tests bloque (`new-clone`) ; un clone nouveau qui
 * touche un fichier de test est listé sans bloquer (`clone-in-tests`, CLAUDE.md : advisory).
 */
function cloneIssue(entry: unknown): Issue | undefined {
  if (!isRecord(entry) || entry['isNew'] !== true) {
    return undefined;
  }
  const first = sourceName(entry, 'firstFile');
  const second = sourceName(entry, 'secondFile');
  const inTests = first.endsWith(TEST_SUFFIX) || second.endsWith(TEST_SUFFIX);
  const issue: Issue = {
    rule: inTests ? 'clone-in-tests' : 'new-clone',
    message: `${first} ≈ ${second}`,
    file: first,
  };
  const line = lineOf(entry);
  if (line !== undefined) {
    issue.line = line;
  }
  return issue;
}

/** Rapport JSON : `duplicates[]` (avec `isNew` sous `--baseline-from-ref`) et `statistics.total.newClones`. */
function parseReport(text: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || !Array.isArray(parsed['duplicates'])) {
    return undefined;
  }
  const clones: unknown[] = parsed['duplicates'];
  return clones.flatMap((entry) => cloneIssue(entry) ?? []);
}

async function readReport(root: string): Promise<string | undefined> {
  try {
    return await readFile(join(root, ...REPORT_PATH), 'utf8');
  } catch {
    return undefined;
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'jscpd');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('jscpd', version.found, version.expected),
      start,
    );
  }
  // Un rapport périmé ne doit jamais être lu à la place de celui de ce run.
  await rm(join(ctx.root, ...REPORT_PATH), { force: true });
  const jscpd = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'jscpd'),
    args: ['--config', '.jscpd.json', '--baseline-from-ref', ctx.base, '--fail-on-new-clones'],
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const text = NORMAL_CODES.has(jscpd.code) ? await readReport(ctx.root) : undefined;
  const issues = text === undefined ? undefined : parseReport(text);
  if (issues === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('jscpd', jscpd.code, jscpd.stderr),
      start,
    );
  }
  const blocked = issues.some((issue) => issue.rule === 'new-clone');
  return buildResult(
    META,
    { status: blocked ? 'failed' : 'passed', version: version.found, issues },
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
