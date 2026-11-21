import { readFile, rm } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from './check-kit.ts';
import type { CheckMeta } from './check-kit.ts';
import type { CheckContext, CheckResult, Issue } from './gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from './tools.ts';
import type { ToolResult } from './tools.ts';

const SEED_LINE = /Running tests with seed "(\d+)"/;
const THRESHOLD_LINE =
  /ERROR: Coverage for (\w+) \(([\d.]+|Unknown)%\) does not meet (.+?) threshold \(([\d.]+)%\)/g;
const BRACKET_ID = /^\[([^\]]+)\]/;
const RUN_TIMEOUT_MS = 600_000;

/** Un check Vitest : ce qui change d'un check à l'autre (projets, périmètre, règles). */
export interface VitestRun {
  meta: CheckMeta;
  /** Rapport JSON de Vitest, relatif à la racine du dépôt. */
  reportPath: string;
  /** Arguments qui suivent `vitest run`. */
  args: readonly string[];
  /** Variables posées dans l'environnement du processus fils, jamais héritées de la gate. */
  env: Record<string, string>;
  /** Le run démarre PostgreSQL dans Docker : sans Docker, échec fermé `docker-unavailable`. */
  needsDocker: boolean;
  /** Règle de toute issue de test en échec ; par défaut l'identifiant entre crochets du titre. */
  failedTestRule?: string;
  /** Issues supplémentaires, calculées après un run dont le rapport est lisible. */
  extraIssues?: (root: string, reportText: string) => Promise<Issue[]>;
}

interface ReportOptions {
  root: string;
  failedTestRule: string | undefined;
}

/** Règle imposée si elle existe, sinon identifiant entre crochets en tête de titre, sinon nom. */
function testRule(options: ReportOptions, title: string, fullName: string): string {
  return options.failedTestRule ?? BRACKET_ID.exec(title)?.[1] ?? fullName;
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

function failedTestIssues(options: ReportOptions, file: string, assertions: unknown[]): Issue[] {
  const issues: Issue[] = [];
  for (const entry of assertions) {
    if (!isRecord(entry) || entry['status'] !== 'failed') {
      continue;
    }
    const title = typeof entry['title'] === 'string' ? entry['title'] : '';
    const fullName = typeof entry['fullName'] === 'string' ? entry['fullName'] : title;
    const detail = failureText(entry);
    issues.push({
      rule: testRule(options, title, fullName),
      message: options.failedTestRule === undefined ? detail : `${title} : ${detail}`,
      file,
    });
  }
  return issues;
}

/** Fichier de test en échec sans test détaillé (import cassé, erreur de collecte). */
function suiteIssue(file: string, entry: Record<string, unknown>): Issue {
  const message = typeof entry['message'] === 'string' ? entry['message'] : '';
  return { rule: 'test-file-failed', message: message.split('\n')[0] ?? '', file };
}

function fileIssues(options: ReportOptions, entry: Record<string, unknown>): Issue[] {
  const file = typeof entry['name'] === 'string' ? relative(options.root, entry['name']) : '';
  const assertions: unknown = entry['assertionResults'];
  const detailed = Array.isArray(assertions) ? failedTestIssues(options, file, assertions) : [];
  if (detailed.length > 0 || entry['status'] !== 'failed') {
    return detailed;
  }
  return [suiteIssue(file, entry)];
}

/** Fichiers de résultat du rapport JSON de Vitest (format Jest), `undefined` si illisible. */
export function reportFiles(text: string): Record<string, unknown>[] | undefined {
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
  return entries.filter(isRecord);
}

/** Un échec de test = une issue ; `undefined` si le rapport est illisible. */
function parseReport(options: ReportOptions, text: string): Issue[] | undefined {
  return reportFiles(text)?.flatMap((entry) => fileIssues(options, entry));
}

/** Une issue `coverage-threshold` par ligne de seuil non tenu. */
function thresholdIssues(output: string): Issue[] {
  return [...output.matchAll(THRESHOLD_LINE)].map((match) => ({
    rule: 'coverage-threshold',
    message: `${match[1] ?? ''} ${match[2] ?? ''} % sous le seuil ${match[3] ?? ''} (${match[4] ?? ''} %)`,
  }));
}

async function readReport(root: string, reportPath: string): Promise<string> {
  try {
    return await readFile(join(root, reportPath), 'utf8');
  } catch {
    return '';
  }
}

/** Docker répond-il ? Un démon injoignable ou une commande absente = non (jamais `skipped`). */
async function dockerReady(ctx: CheckContext): Promise<boolean> {
  const info = await runTool({
    command: 'docker',
    args: ['info', '--format', '{{.ServerVersion}}'],
    cwd: ctx.root,
    env: ctx.env,
    timeoutMs: 30_000,
  });
  return info.code === 0;
}

const DOCKER_ISSUE: Issue = {
  rule: 'docker-unavailable',
  message: 'Docker ne répond pas (`docker info`) : les tests d’intégration exigent PostgreSQL réel',
};

function toolFailure(
  run: VitestRun,
  found: string,
  vitest: ToolResult,
  start: number,
): CheckResult {
  const detail = vitest.stderr || vitest.stdout;
  return failedResult(run.meta, found, toolErrorIssue('vitest', vitest.code, detail), start);
}

/** Lance `vitest run` avec les paramètres du check et en tire un verdict. */
export async function runVitestCheck(ctx: CheckContext, run: VitestRun): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'vitest');
  if (!version.ok) {
    return failedResult(
      run.meta,
      version.found,
      versionMismatchIssue('vitest', version.found, version.expected),
      start,
    );
  }
  if (run.needsDocker && !(await dockerReady(ctx))) {
    return failedResult(run.meta, version.found, DOCKER_ISSUE, start);
  }
  // Un rapport antérieur ne peut jamais être relu comme celui de ce run.
  await rm(join(ctx.root, run.reportPath), { force: true });
  const vitest = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'vitest'),
    args: [
      'run',
      ...run.args,
      '--reporter=default',
      '--reporter=json',
      `--outputFile.json=${run.reportPath}`,
    ],
    cwd: ctx.root,
    env: { ...ctx.env, ...run.env, NO_COLOR: '1', FORCE_COLOR: '0' },
    timeoutMs: RUN_TIMEOUT_MS,
  });
  const output = `${vitest.stdout}\n${vitest.stderr}`;
  const reportText = await readReport(ctx.root, run.reportPath);
  const testIssues = parseReport(
    { root: ctx.root, failedTestRule: run.failedTestRule },
    reportText,
  );
  if (testIssues === undefined) {
    return toolFailure(run, version.found, vitest, start);
  }
  const extra = (await run.extraIssues?.(ctx.root, reportText)) ?? [];
  const issues = [...testIssues, ...thresholdIssues(output), ...extra];
  // Code non nul sans issue lisible : on ne conclut jamais « passé ».
  if (vitest.code !== 0 && issues.length === 0) {
    return toolFailure(run, version.found, vitest, start);
  }
  const seed = SEED_LINE.exec(output)?.[1];
  return buildResult(
    run.meta,
    {
      status: issues.length > 0 ? 'failed' : 'passed',
      version: version.found,
      issues,
      ...(seed === undefined ? {} : { note: `seed ${seed} (rejouable : --sequence.seed=${seed})` }),
    },
    start,
  );
}
