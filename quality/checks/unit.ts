import { readFile, rm } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'unit', tool: 'vitest', severity: 'blocking' };
const REPORT_PATH = join('reports', 'vitest-unit.json');
const SEED_LINE = /Running tests with seed "(\d+)"/;
const THRESHOLD_LINE =
  /ERROR: Coverage for (\w+) \(([\d.]+|Unknown)%\) does not meet (.+?) threshold \(([\d.]+)%\)/g;
const BRACKET_ID = /^\[([^\]]+)\]/;

/** Identifiant entre crochets en tête de titre s'il existe, sinon nom complet du test. */
function testRule(title: string, fullName: string): string {
  return BRACKET_ID.exec(title)?.[1] ?? fullName;
}

function failureText(entry: Record<string, unknown>): string {
  const messages: unknown = entry['failureMessages'];
  if (!Array.isArray(messages)) {
    return '';
  }
  const texts: unknown[] = messages;
  const first = texts.find((text): text is string => typeof text === 'string');
  return first?.split('\n')[0] ?? '';
}

function failedTestIssues(file: string, assertions: unknown[]): Issue[] {
  const issues: Issue[] = [];
  for (const entry of assertions) {
    if (!isRecord(entry) || entry['status'] !== 'failed') {
      continue;
    }
    const title = typeof entry['title'] === 'string' ? entry['title'] : '';
    const fullName = typeof entry['fullName'] === 'string' ? entry['fullName'] : title;
    issues.push({ rule: testRule(title, fullName), message: failureText(entry), file });
  }
  return issues;
}

/** Fichier de test en échec sans test détaillé (import cassé, erreur de collecte). */
function suiteIssue(file: string, entry: Record<string, unknown>): Issue {
  const message = typeof entry['message'] === 'string' ? entry['message'] : '';
  return { rule: 'test-file-failed', message: message.split('\n')[0] ?? '', file };
}

function fileIssues(root: string, entry: Record<string, unknown>): Issue[] {
  const file = typeof entry['name'] === 'string' ? relative(root, entry['name']) : '';
  const assertions: unknown = entry['assertionResults'];
  const detailed = Array.isArray(assertions) ? failedTestIssues(file, assertions) : [];
  if (detailed.length > 0 || entry['status'] !== 'failed') {
    return detailed;
  }
  return [suiteIssue(file, entry)];
}

/** Rapport JSON de Vitest (format Jest) : un échec de test = une issue. */
function parseReport(root: string, text: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  const results = isRecord(parsed) ? parsed['testResults'] : undefined;
  if (!Array.isArray(results)) {
    return undefined;
  }
  const entries: unknown[] = results;
  return entries.flatMap((entry) => (isRecord(entry) ? fileIssues(root, entry) : []));
}

/** Une issue `coverage-threshold` par ligne de seuil non tenu. */
function thresholdIssues(output: string): Issue[] {
  return [...output.matchAll(THRESHOLD_LINE)].map((match) => ({
    rule: 'coverage-threshold',
    message: `${match[1] ?? ''} ${match[2] ?? ''} % sous le seuil ${match[3] ?? ''} (${match[4] ?? ''} %)`,
  }));
}

async function readReport(root: string): Promise<string> {
  try {
    return await readFile(join(root, REPORT_PATH), 'utf8');
  } catch {
    return '';
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'vitest');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('vitest', version.found, version.expected),
      start,
    );
  }
  // Un rapport antérieur ne peut jamais être relu comme celui de ce run.
  await rm(join(ctx.root, REPORT_PATH), { force: true });
  const vitest = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'vitest'),
    args: [
      'run',
      '--project',
      'unit',
      '--coverage',
      '--reporter=default',
      '--reporter=json',
      `--outputFile.json=${REPORT_PATH}`,
    ],
    cwd: ctx.root,
    // Le périmètre est posé ici, jamais hérité de l'environnement de la gate.
    env: { ...ctx.env, GATE_COVERAGE_SCOPE: 'pure', NO_COLOR: '1', FORCE_COLOR: '0' },
    timeoutMs: 600_000,
  });
  const output = `${vitest.stdout}\n${vitest.stderr}`;
  const testIssues = parseReport(ctx.root, await readReport(ctx.root));
  if (testIssues === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('vitest', vitest.code, vitest.stderr || vitest.stdout),
      start,
    );
  }
  const issues = [...testIssues, ...thresholdIssues(output)];
  // Code non nul sans issue lisible : on ne conclut jamais « passé ».
  if (vitest.code !== 0 && issues.length === 0) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('vitest', vitest.code, vitest.stderr || vitest.stdout),
      start,
    );
  }
  const seed = SEED_LINE.exec(output)?.[1];
  return buildResult(
    META,
    {
      status: issues.length > 0 ? 'failed' : 'passed',
      version: version.found,
      issues,
      ...(seed === undefined ? {} : { note: `seed ${seed} (rejouable : --sequence.seed=${seed})` }),
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
