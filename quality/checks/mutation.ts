import { access, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { matchesGlob } from 'node:path/posix';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import layout from '../layout.json' with { type: 'json' };
import thresholds from '../thresholds.json' with { type: 'json' };
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';
import type { ToolResult } from '../tools.ts';

const META: CheckMeta = { id: 'mutation', tool: 'stryker', severity: 'blocking' };
const STRYKER_PACKAGE = '@stryker-mutator/core';
const REPORT_PATH = join('reports', 'mutation', 'mutation.json');
const TEST_SUFFIX = '.test.ts';
const DETECTED = new Set(['Killed', 'Timeout']);
const UNDETECTED = new Set(['Survived', 'NoCoverage']);

/** `dir/x.test.ts` et `dir/x.<suffixe>.test.ts` testent le source colocalisé `dir/x.ts`. */
function sourceOfTest(file: string): string {
  const slash = file.lastIndexOf('/');
  const name = file.slice(slash + 1).slice(0, -TEST_SUFFIX.length);
  return `${file.slice(0, slash + 1)}${name.split('.')[0] ?? name}.ts`;
}

function isMutable(file: string): boolean {
  return !file.endsWith(TEST_SUFFIX) && layout.mutate.some((glob) => matchesGlob(file, glob));
}

async function exists(root: string, file: string): Promise<boolean> {
  try {
    await access(join(root, file));
    return true;
  } catch {
    return false;
  }
}

/** Fichiers mutables du diff, plus le source colocalisé de chaque test modifié. */
async function mutableFiles(root: string, changed: readonly string[]): Promise<string[]> {
  const candidates = new Set(
    changed.map((file) => (file.endsWith(TEST_SUFFIX) ? sourceOfTest(file) : file)),
  );
  const mutable = [...candidates].filter(isMutable);
  const present = await Promise.all(mutable.map((file) => exists(root, file)));
  return mutable.filter((_, index) => present[index] === true).sort((a, b) => a.localeCompare(b));
}

type Scope = { files: string[] | undefined } | { issue: Issue };

/** `GATE_MUTATION_SCOPE=all` (nightly) : tout `mutate` ; sinon le diff depuis la base. */
async function resolveScope(ctx: CheckContext): Promise<Scope> {
  if (ctx.env['GATE_MUTATION_SCOPE'] === 'all') {
    return { files: undefined };
  }
  const diff = await runTool({
    command: 'git',
    args: ['diff', '--name-only', '--diff-filter=ACMR', `${ctx.base}...HEAD`],
    cwd: ctx.root,
    timeoutMs: 30_000,
  });
  if (diff.code !== 0) {
    return { issue: toolErrorIssue('git diff', diff.code, diff.stderr) };
  }
  const changed = diff.stdout.split('\n').filter((line) => line.trim() !== '');
  return { files: await mutableFiles(ctx.root, changed) };
}

interface Outcome {
  detected: number;
  undetected: number;
  survivors: Issue[];
}

function mutantIssue(file: string, mutant: Record<string, unknown>): Issue {
  const mutator = typeof mutant['mutatorName'] === 'string' ? mutant['mutatorName'] : 'unknown';
  const location = isRecord(mutant['location']) ? mutant['location'] : {};
  const start = isRecord(location['start']) ? location['start'] : {};
  const issue: Issue = {
    rule: `survived:${mutator}`,
    message: `mutant ${mutator} non détecté par les tests`,
    file,
  };
  if (typeof start['line'] === 'number') {
    issue.line = start['line'];
  }
  return issue;
}

function tally(outcome: Outcome, file: string, mutants: unknown[]): void {
  for (const mutant of mutants) {
    const status = isRecord(mutant) ? mutant['status'] : undefined;
    if (!isRecord(mutant) || typeof status !== 'string') {
      continue;
    }
    if (DETECTED.has(status)) {
      outcome.detected += 1;
    } else if (UNDETECTED.has(status)) {
      outcome.undetected += 1;
      outcome.survivors.push(mutantIssue(file, mutant));
    }
  }
}

/** Les mutants `CompileError` et `RuntimeError` ne comptent ni comme tués ni comme survivants. */
function parseMutationReport(text: string): Outcome | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  const files = isRecord(parsed) ? parsed['files'] : undefined;
  if (!isRecord(files)) {
    return undefined;
  }
  const outcome: Outcome = { detected: 0, undetected: 0, survivors: [] };
  for (const [file, entry] of Object.entries(files)) {
    const mutants = isRecord(entry) ? entry['mutants'] : undefined;
    if (Array.isArray(mutants)) {
      tally(outcome, file, mutants);
    }
  }
  return outcome;
}

function scoreOf(outcome: Outcome): number {
  const total = outcome.detected + outcome.undetected;
  return total === 0 ? 100 : (outcome.detected / total) * 100;
}

async function runStryker(ctx: CheckContext, files: string[] | undefined): Promise<ToolResult> {
  await rm(join(ctx.root, REPORT_PATH), { force: true });
  return runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'stryker'),
    args: ['run', ...(files === undefined ? [] : ['--mutate', files.join(',')])],
    cwd: ctx.root,
    timeoutMs: 1_800_000,
  });
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
  const version = await verifyNpmToolVersion(ctx.root, STRYKER_PACKAGE);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('stryker', version.found, version.expected),
      start,
    );
  }
  const scope = await resolveScope(ctx);
  if ('issue' in scope) {
    return failedResult(META, version.found, scope.issue, start);
  }
  if (scope.files?.length === 0) {
    return buildResult(
      META,
      {
        status: 'passed',
        version: version.found,
        issues: [],
        note: 'aucun fichier mutable modifié',
      },
      start,
    );
  }
  const stryker = await runStryker(ctx, scope.files);
  const outcome = parseMutationReport(await readReport(ctx.root));
  if (outcome === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('stryker', stryker.code, stryker.stderr || stryker.stdout),
      start,
    );
  }
  return judge(version.found, outcome, stryker, start);
}

function judge(version: string, outcome: Outcome, stryker: ToolResult, start: number): CheckResult {
  const score = scoreOf(outcome);
  const note = `score ${score.toFixed(2)} % (${String(outcome.detected)} tués, ${String(outcome.undetected)} survivants)`;
  if (score < thresholds.mutation.break) {
    const below: Issue = {
      rule: 'mutation-score-below-break',
      message: `score ${score.toFixed(2)} % sous le seuil ${String(thresholds.mutation.break)} %`,
    };
    return buildResult(
      META,
      { status: 'failed', version, issues: [below, ...outcome.survivors], note },
      start,
    );
  }
  // Seuil tenu selon la gate mais Stryker a échoué : on ne conclut jamais « passé ».
  if (stryker.code !== 0) {
    return failedResult(
      META,
      version,
      toolErrorIssue('stryker', stryker.code, stryker.stderr),
      start,
    );
  }
  return buildResult(META, { status: 'passed', version, issues: [], note }, start);
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
