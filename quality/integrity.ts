import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import type { CheckResult, Issue } from './gate-report.ts';
import type { Sides } from './integrity-fs.ts';
import { byName, changeKind, digest, listFiles, readJson, readText, show } from './integrity-fs.ts';
import { policyWeakenings } from './pnpm-policy.ts';
import { isProtected, loadProtectedPaths } from './protected-paths.ts';
import { isRecord } from './tools.ts';

// Ce script tourne depuis une copie de la ref de base (Pattern 2) : il n'importe que
// `node:*` et des modules de `quality/` qui existent déjà dans la base.

export interface IntegrityInput {
  baseDir: string;
  headDir: string;
  approvedKinds: readonly string[];
  bootstrap: boolean;
}

type Direction = 'lower-is-stricter' | 'higher-is-stricter';

/** Sens « plus strict » de chaque section de `quality/thresholds.json` ; section inconnue = tout écart est une baisse. */
export const DIRECTIONS: Readonly<Record<string, Direction>> = {
  lint: 'lower-is-stricter',
  coverage: 'higher-is-stricter',
  mutation: 'higher-is-stricter',
  supplyChain: 'higher-is-stricter',
};

const GATE_APPROVAL = 'gate-change-approved';
const THRESHOLDS = 'quality/thresholds.json';
const BASELINE = 'quality/baseline.json';
const PROTECTED_LIST = 'quality/protected-paths.json';
const PNPM_POLICY = 'pnpm-workspace.yaml';
const MIGRATIONS = 'db/migrations/';
const TEST_SUFFIX = '.test.ts';
const EXPECT_CALL = /\bexpect(?:\.soft)?\(/g;
const VERSION = '1';

async function protectedPathIssues(s: Sides, globs: readonly string[]): Promise<Issue[]> {
  const issues: Issue[] = [];
  const all = [...new Set([...s.baseFiles, ...s.headFiles])].sort(byName);
  for (const file of all.filter((path) => isProtected(path, globs))) {
    const [before, after] = await Promise.all([digest(s.baseDir, file), digest(s.headDir, file)]);
    if (before !== after) {
      issues.push({
        rule: 'protected-path-changed',
        file,
        message: `chemin protégé ${changeKind(before, after)}`,
      });
    }
  }
  return issues;
}

function flatten(value: unknown, prefix: string, out: Map<string, unknown>): Map<string, unknown> {
  if (isRecord(value)) {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix === '' ? key : `${prefix}.${key}`, out);
    }
  } else {
    out.set(prefix, value);
  }
  return out;
}

function isLowered(key: string, before: unknown, after: unknown): boolean {
  if (after === undefined) {
    return true;
  }
  if (typeof before !== 'number' || typeof after !== 'number') {
    return before !== after;
  }
  const direction = DIRECTIONS[key.split('.')[0] ?? ''];
  if (direction === undefined) {
    return after !== before;
  }
  return direction === 'lower-is-stricter' ? after > before : after < before;
}

async function thresholdIssues(s: Sides): Promise<Issue[]> {
  const base = await readJson(s.baseDir, THRESHOLDS);
  if (base === undefined) {
    return [];
  }
  const head = await readJson(s.headDir, THRESHOLDS);
  if (head === undefined) {
    return [
      { rule: 'threshold-lowered', file: THRESHOLDS, message: 'seuils supprimés ou illisibles' },
    ];
  }
  const after = flatten(head, '', new Map());
  return [...flatten(base, '', new Map())]
    .filter(([key, before]) => isLowered(key, before, after.get(key)))
    .map(([key, before]) => ({
      rule: 'threshold-lowered',
      file: THRESHOLDS,
      message: `${key} : ${show(before)} remplacé par ${after.has(key) ? show(after.get(key)) : 'rien (clé supprimée)'}`,
    }));
}

function expectCount(text: string | undefined): number {
  return text === undefined ? 0 : [...text.matchAll(EXPECT_CALL)].length;
}

async function assertionIssues(s: Sides): Promise<Issue[]> {
  const issues: Issue[] = [];
  for (const file of [...s.baseFiles].filter((path) => path.endsWith(TEST_SUFFIX)).sort(byName)) {
    const before = expectCount(await readText(s.baseDir, file));
    const after = expectCount(await readText(s.headDir, file));
    if (after < before) {
      issues.push({
        rule: 'assertion-removed',
        file,
        message: `${String(before)} appels expect dans la base, ${String(after)} dans la tête`,
      });
    }
  }
  return issues;
}

async function supplyChainIssues(s: Sides): Promise<Issue[]> {
  const base = await readText(s.baseDir, PNPM_POLICY);
  if (base === undefined) {
    return [];
  }
  const head = await readText(s.headDir, PNPM_POLICY);
  const messages =
    head === undefined ? ['pnpm-workspace.yaml supprimé'] : policyWeakenings(base, head);
  return messages.map((message) => ({
    rule: 'supply-chain-policy-weakened',
    file: PNPM_POLICY,
    message,
  }));
}

function counters(file: Record<string, unknown> | undefined): Record<string, unknown> {
  const table = file?.['escapeHatches'];
  return isRecord(table) ? table : {};
}

async function baselineIssues(s: Sides): Promise<Issue[]> {
  const base = await readJson(s.baseDir, BASELINE);
  if (base === undefined) {
    return [];
  }
  const before = counters(base);
  const issues: Issue[] = [];
  for (const [pattern, value] of Object.entries(counters(await readJson(s.headDir, BASELINE)))) {
    const allowed = before[pattern];
    if (typeof value === 'number' && value > (typeof allowed === 'number' ? allowed : 0)) {
      issues.push({
        rule: 'escape-hatch-baseline-raised',
        file: BASELINE,
        message: `« ${pattern} » : ${show(allowed ?? 0)} relevé à ${String(value)}`,
      });
    }
  }
  return issues;
}

async function migrationIssues(s: Sides): Promise<Issue[]> {
  const issues: Issue[] = [];
  for (const file of [...s.baseFiles].filter((path) => path.startsWith(MIGRATIONS)).sort(byName)) {
    const [before, after] = await Promise.all([digest(s.baseDir, file), digest(s.headDir, file)]);
    if (before !== after) {
      issues.push({
        rule: 'migration-modified',
        file,
        message: `migration existante ${changeKind(before, after)} (forward-only : écrire une nouvelle migration)`,
      });
    }
  }
  return issues;
}

/**
 * Juge l'intégrité de la tête contre la base : chemins protégés, seuils, assertions,
 * politique pnpm, cliquet d'échappatoires, migrations. Toute issue exige l'approbation
 * `gate-change-approved` ; avec elle le check passe et les issues restent listées.
 */
export async function evaluateIntegrity(input: IntegrityInput): Promise<CheckResult> {
  const start = Date.now();
  const [baseFiles, headFiles] = await Promise.all([
    listFiles(input.baseDir),
    listFiles(input.headDir),
  ]);
  const s: Sides = { baseDir: input.baseDir, headDir: input.headDir, baseFiles, headFiles };
  const bootstrap = input.bootstrap || !baseFiles.has(THRESHOLDS);
  // La liste vient de la base ; de la tête seulement en amorçage (ou si la base n'en a pas).
  const listDir = bootstrap || !baseFiles.has(PROTECTED_LIST) ? input.headDir : input.baseDir;
  const { paths } = await loadProtectedPaths(listDir);
  const issues: Issue[] = [
    ...(bootstrap
      ? [{ rule: 'bootstrap', message: 'amorçage : aucune base à comparer, approbation requise' }]
      : []),
    ...(await protectedPathIssues(s, paths)),
    ...(await thresholdIssues(s)),
    ...(await assertionIssues(s)),
    ...(await supplyChainIssues(s)),
    ...(await baselineIssues(s)),
    ...(await migrationIssues(s)),
  ];
  const approved = input.approvedKinds.includes(GATE_APPROVAL);
  const passed = issues.length === 0 || approved;
  return {
    check: 'integrity',
    tool: 'integrity',
    version: VERSION,
    severity: 'blocking',
    passed,
    status: passed ? 'passed' : 'failed',
    ...(approved && issues.length > 0
      ? { note: `${GATE_APPROVAL} : ${String(issues.length)} écart(s) approuvé(s), listés` }
      : {}),
    issues,
    duration_ms: Date.now() - start,
  };
}

class UsageError extends Error {}

async function approvalsFrom(file: string | undefined): Promise<string[]> {
  if (file === undefined) {
    return [];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(file, 'utf8'));
  } catch {
    throw new UsageError(`--approvals-report illisible : ${file}`);
  }
  const approved = isRecord(parsed) ? parsed['approved'] : undefined;
  if (!Array.isArray(approved)) {
    throw new UsageError(`--approvals-report sans tableau « approved » : ${file}`);
  }
  const kinds: unknown[] = approved;
  return kinds.filter((kind): kind is string => typeof kind === 'string');
}

async function writeJsonAtomic(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const tmp = join(dirname(path), `.${basename(path)}.${String(process.pid)}.tmp`);
  await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await rename(tmp, path);
}

async function runCli(argv: readonly string[]): Promise<number> {
  const { values } = parseArgs({
    args: [...argv],
    options: {
      'base-dir': { type: 'string' },
      'head-dir': { type: 'string' },
      approved: { type: 'string' },
      'approvals-report': { type: 'string' },
      bootstrap: { type: 'boolean', default: false },
      out: { type: 'string' },
    },
    strict: true,
    allowPositionals: false,
  });
  const baseDir = values['base-dir'];
  const headDir = values['head-dir'];
  const out = values.out;
  if (baseDir === undefined || headDir === undefined || out === undefined) {
    throw new UsageError('--base-dir, --head-dir et --out sont obligatoires');
  }
  const listed = (values.approved ?? '')
    .split(',')
    .map((kind) => kind.trim())
    .filter((kind) => kind !== '');
  const approvedKinds = [...listed, ...(await approvalsFrom(values['approvals-report']))];
  const result = await evaluateIntegrity({
    baseDir: resolve(baseDir),
    headDir: resolve(headDir),
    approvedKinds,
    bootstrap: values.bootstrap,
  });
  await writeJsonAtomic(resolve(out), result);
  return result.status === 'passed' ? 0 : 1;
}

if (import.meta.main) {
  try {
    process.exitCode = await runCli(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    process.exitCode = 2;
  }
}
