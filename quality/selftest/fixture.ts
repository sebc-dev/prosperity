import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach } from 'vitest';
import { isRecord, runTool } from '../tools.ts';
import type { CaseResult } from './cases.ts';
import type { InstallOutcome } from './context.ts';

// Outillage des tests de l'auto-test : un mini-dépôt git dont `quality/run.ts` est un faux gate.

/** Faux `quality/run.ts` : trace ses arguments et son environnement, lit un marqueur dans `src/`. */
const STUB_RUN = `
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
const { values } = parseArgs({
  options: { only: { type: 'string' }, profile: { type: 'string' }, base: { type: 'string' }, report: { type: 'string' } },
  strict: true,
});
const root = resolve(import.meta.dirname, '..');
const env = process.env;
if (env.FIXTURE_LOG) {
  appendFileSync(env.FIXTURE_LOG, JSON.stringify({
    only: values.only, profile: values.profile, base: values.base, root,
    github: env.GITHUB_ACTIONS ?? null, ci: env.CI ?? null, event: env.GITHUB_EVENT_NAME ?? null,
    baseRef: env.GITHUB_BASE_REF ?? null, baseDir: env.GATE_BASE_DIR ?? null, kinds: env.GATE_APPROVED_KINDS ?? null,
  }) + '\\n');
}
await new Promise((done) => setTimeout(done, 150));
const read = (name) => {
  const path = resolve(root, 'src', name);
  return existsSync(path) ? readFileSync(path, 'utf8').trim() : undefined;
};
const rule = read('violation.txt');
const broken = read('broken-tool.txt');
const issues = rule !== undefined ? [{ rule, message: 'violation' }]
  : broken !== undefined ? [{ rule: 'tool-error', message: 'outil absent' }] : [];
const status = issues.length === 0 ? 'passed' : 'failed';
mkdirSync(dirname(values.report), { recursive: true });
writeFileSync(values.report, JSON.stringify({
  profile: values.profile, commit: 'x', base: values.base, generated_at: 'x',
  verdict: status === 'passed' ? 'pass' : 'fail',
  checks: [{ check: values.only, tool: 't', version: '1', severity: 'blocking', passed: status === 'passed', status, issues, duration_ms: 0 }],
}));
process.exitCode = status === 'passed' ? 0 : 1;
`;

export const APPLY_STALE = `
export default async function apply() {
  throw new Error('case-stale');
}
`;

export const INAPPLICABLE_PATCH =
  'diff --git a/src/missing.txt b/src/missing.txt\n--- a/src/missing.txt\n+++ b/src/missing.txt\n@@ -1 +1 @@\n-old\n+new\n';

export function applyViolation(rule: string): string {
  return `
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
export default async function apply(root) {
  await mkdir(join(root, 'src'), { recursive: true });
  await writeFile(join(root, 'src', 'violation.txt'), '${rule}\\n');
}
`;
}

export function newFilePatch(path: string, content: string): string {
  return `diff --git a/${path} b/${path}\nnew file mode 100644\n--- /dev/null\n+++ b/${path}\n@@ -0,0 +1 @@\n+${content}\n`;
}

export interface FixtureCase {
  id: string;
  check: string;
  rule: string;
  install?: 'frozen' | 'link';
  patch?: string;
  apply?: string;
}

/** Dossier de travail jetable d'un fichier de tests ; les worktrees `selftest-*` y sont créés par les tests. */
export function useScratch(): () => string {
  let scratch = '';
  beforeEach(async () => {
    scratch = await mkdtemp(join(tmpdir(), 'gate-fixture-'));
  });
  afterEach(async () => {
    await rm(scratch, { recursive: true, force: true });
  });
  return () => scratch;
}

export async function git(cwd: string, ...args: string[]): Promise<string> {
  const identity = ['-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid'];
  const outcome = await runTool({
    command: 'git',
    args: [...identity, '-c', 'commit.gpgsign=false', ...args],
    cwd,
    timeoutMs: 60_000,
  });
  if (outcome.code !== 0) {
    throw new Error(`git ${args.join(' ')} : ${outcome.stderr}`);
  }
  return outcome.stdout.trim();
}

export async function put(root: string, rel: string, text: string): Promise<void> {
  const path = join(root, rel);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text, 'utf8');
}

async function putCase(root: string, item: FixtureCase): Promise<void> {
  const dir = `quality/selftest/cases/${item.id}`;
  const expected = { check: item.check, rule: item.rule, install: item.install ?? 'frozen' };
  await put(root, `${dir}/expected.json`, `${JSON.stringify(expected)}\n`);
  if (item.patch !== undefined) {
    await put(root, `${dir}/patch`, item.patch);
  }
  if (item.apply !== undefined) {
    await put(root, `${dir}/apply.ts`, item.apply);
  }
}

/** Mini-dépôt git committé : faux gate, cas d'auto-test et fichiers supplémentaires. */
export async function buildFixture(
  scratch: string,
  name: string,
  cases: readonly FixtureCase[],
  extra: Record<string, string> = {},
): Promise<string> {
  const root = join(scratch, name);
  await mkdir(root, { recursive: true });
  await git(root, 'init', '-q', '-b', 'main');
  await put(root, 'package.json', '{"name":"fixture","private":true}\n');
  await put(root, 'quality/run.ts', STUB_RUN);
  await put(root, 'src/keep.txt', 'keep\n');
  for (const item of cases) {
    await putCase(root, item);
  }
  for (const [rel, text] of Object.entries(extra)) {
    await put(root, rel, text);
  }
  await git(root, 'add', '-A');
  await git(root, 'commit', '-q', '-m', 'fixture');
  return root;
}

/** Lignes `worktree …` de `git worktree list` qui désignent un worktree `selftest-*`. */
export async function selftestWorktrees(root: string): Promise<string[]> {
  const listing = await git(root, 'worktree', 'list', '--porcelain');
  return listing.split('\n').filter((line) => line.includes('selftest-'));
}

export type LogEntry = Record<string, unknown>;

export async function readLog(path: string): Promise<LogEntry[]> {
  const text = await readFile(path, 'utf8');
  return text
    .split('\n')
    .filter((line) => line !== '')
    .flatMap((line) => {
      const parsed: unknown = JSON.parse(line);
      return isRecord(parsed) ? [parsed] : [];
    });
}

export function field(entry: LogEntry, key: string): string {
  const value = entry[key];
  return typeof value === 'string' ? value : '';
}

export function isBaseRun(entry: LogEntry): boolean {
  return field(entry, 'root').includes('selftest-base-');
}

export function noInstall(): Promise<InstallOutcome> {
  return Promise.resolve({ ok: true, message: '' });
}

export function byId(results: readonly CaseResult[], id: string): CaseResult | undefined {
  return results.find((entry) => entry.id === id);
}
