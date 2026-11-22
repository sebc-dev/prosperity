import { spawn } from 'node:child_process';
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { casesToIssues, check, isSelftestTriggered } from '../checks/selftest.ts';
import type { CheckContext, CheckResult } from '../gate-report.ts';
import { runTool } from '../tools.ts';
import type { CaseResult } from './cases.ts';
import { matchesExpected, runSelftest, selectCases } from './run.ts';
import { cleanupStaleWorktrees } from './worktrees.ts';

const ROOT = resolve(import.meta.dirname, '..', '..');
const SELFTEST_CLI = join(ROOT, 'quality', 'selftest', 'run.ts');
const LONG = 90_000;

// --- Fixture : un mini-dépôt git dont `quality/run.ts` est un faux gate -----------------------

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
    forced: env.GATE_FORCE_SELFTEST ?? null,
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

const APPLY_VIOLATION = (rule: string): string => `
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
export default async function apply(root) {
  await mkdir(join(root, 'src'), { recursive: true });
  await writeFile(join(root, 'src', 'violation.txt'), '${rule}\\n');
}
`;

const APPLY_STALE = `
export default async function apply() {
  throw new Error('case-stale');
}
`;

function newFilePatch(path: string, content: string): string {
  return `diff --git a/${path} b/${path}\nnew file mode 100644\n--- /dev/null\n+++ b/${path}\n@@ -0,0 +1 @@\n+${content}\n`;
}

const INAPPLICABLE_PATCH =
  'diff --git a/src/missing.txt b/src/missing.txt\n--- a/src/missing.txt\n+++ b/src/missing.txt\n@@ -1 +1 @@\n-old\n+new\n';

interface FixtureCase {
  id: string;
  check: string;
  rule: string;
  install?: 'frozen' | 'link';
  patch?: string;
  apply?: string;
}

let scratch = '';

async function git(cwd: string, ...args: string[]): Promise<string> {
  const outcome = await runTool({
    command: 'git',
    args: [
      '-c',
      'user.name=fixture',
      '-c',
      'user.email=fixture@example.invalid',
      '-c',
      'commit.gpgsign=false',
      ...args,
    ],
    cwd,
    timeoutMs: 60_000,
  });
  if (outcome.code !== 0) {
    throw new Error(`git ${args.join(' ')} : ${outcome.stderr}`);
  }
  return outcome.stdout.trim();
}

async function put(root: string, rel: string, text: string): Promise<void> {
  const path = join(root, rel);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text, 'utf8');
}

async function buildFixture(
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
  for (const [rel, text] of Object.entries(extra)) {
    await put(root, rel, text);
  }
  await git(root, 'add', '-A');
  await git(root, 'commit', '-q', '-m', 'fixture');
  return root;
}

async function selftestWorktrees(root: string): Promise<string[]> {
  const listing = await git(root, 'worktree', 'list', '--porcelain');
  return listing.split('\n').filter((line) => line.includes('selftest-'));
}

async function readLog(path: string): Promise<Record<string, string | null>[]> {
  const text = await readFile(path, 'utf8');
  const lines = text.split('\n').filter((line) => line !== '');
  return lines.map((line): Record<string, string | null> => JSON.parse(line));
}

function noInstall(): Promise<{ ok: boolean; message: string }> {
  return Promise.resolve({ ok: true, message: '' });
}

function byId(results: readonly CaseResult[], id: string): CaseResult | undefined {
  return results.find((entry) => entry.id === id);
}

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'selftest-unit-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

// --- Fonctions pures --------------------------------------------------------------------------

function failedWith(...rules: string[]): Pick<CheckResult, 'status' | 'issues'> {
  return { status: 'failed', issues: rules.map((rule) => ({ rule, message: 'm' })) };
}

describe('matchesExpected', () => {
  it.each([
    ['la règle exacte', failedWith('no-restricted-syntax'), 'no-restricted-syntax', true],
    ['la règle parmi d’autres', failedWith('a', 'exports'), 'exports', true],
    ['un suffixe séparé par un point', failedWith('rules.prosperity.no-sql'), 'prosperity.no-sql', true],
    ['une autre règle', failedWith('exports'), 'files', false],
    ['un suffixe sans frontière', failedWith('tool-error'), 'error', false],
    ['tool-error', failedWith('tool-error'), 'github-pat', false],
    ['tool-error même attendu', failedWith('tool-error'), 'tool-error', false],
    ['tool-version-mismatch', failedWith('tool-version-mismatch'), 'github-pat', false],
    ['check-crashed même attendu', failedWith('check-crashed'), 'check-crashed', false],
    ['aucune issue', failedWith(), 'exports', false],
    ['un check passé', { status: 'passed', issues: [] }, 'exports', false],
    ['un check sauté', { status: 'skipped', issues: [] }, 'exports', false],
  ] as const)('pour %s', (_label, result, rule, expected) => {
    expect(matchesExpected(result, { rule })).toBe(expected);
  });
});

describe('selectCases', () => {
  const ids = ['a-x', 'a-y', 'b-z', 'c-w'];

  it.each([
    ['a-*,b-z', ['a-x', 'a-y', 'b-z']],
    [' b-z , a-x ', ['a-x', 'b-z']],
    ['a-*,a-x', ['a-x', 'a-y']],
    ['*', ['a-x', 'a-y', 'b-z', 'c-w']],
    ['c-w', ['c-w']],
  ])('retient l’union triée pour « %s »', (spec, expected) => {
    expect(selectCases(ids, spec)).toEqual(expected);
  });

  it('retient tous les cas quand la liste est absente', () => {
    expect(selectCases(['b-z', 'a-x'], undefined)).toEqual(['a-x', 'b-z']);
  });

  it('refuse un élément vide en le nommant', () => {
    expect(() => selectCases(ids, 'a-*,')).toThrow(/vide.*2/);
    expect(() => selectCases(ids, '')).toThrow(/vide.*1/);
  });

  it('refuse un élément qui ne retient aucun cas en le nommant', () => {
    expect(() => selectCases(ids, 'a-*,zz-*')).toThrow(/zz-\*/);
  });
});

// --- Cycle complet sur un mini-dépôt ----------------------------------------------------------

describe('runSelftest', () => {
  it(
    'ne rend vert que le cas dont le check échoue pour la règle attendue',
    async () => {
      const root = await buildFixture('verdicts', [
        { id: 'ok-patch', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-a') },
        { id: 'ok-apply', check: 'lint', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') },
        { id: 'wrong-rule', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-b') },
        { id: 'tool-broken', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/broken-tool.txt', 'x') },
        { id: 'not-detected', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/harmless.txt', 'x') },
        { id: 'stale', check: 'lint', rule: 'rule-a', apply: APPLY_STALE },
        { id: 'bad-patch', check: 'lint', rule: 'rule-a', patch: INAPPLICABLE_PATCH },
      ]);

      const report = await runSelftest({ root, jobs: 2, env: process.env, install: noInstall });

      const summary = report.cases.map((entry) => [entry.id, entry.status, entry.reason]);
      expect(summary).toEqual([
        ['bad-patch', 'failed', 'case-not-applicable'],
        ['not-detected', 'failed', 'not-detected'],
        ['ok-apply', 'passed', 'detected'],
        ['ok-patch', 'passed', 'detected'],
        ['stale', 'failed', 'case-not-applicable'],
        ['tool-broken', 'failed', 'tool-failure'],
        ['wrong-rule', 'failed', 'wrong-rule'],
      ]);
      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );

  it(
    'joue le contrôle propre une fois par check avant les cas, avec l’environnement local',
    async () => {
      const root = await buildFixture('control', [
        { id: 'one', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-a') },
        { id: 'two', check: 'lint', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') },
        { id: 'three', check: 'secrets', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') },
      ]);
      const log = join(scratch, 'trace.jsonl');
      const head = await git(root, 'rev-parse', 'HEAD');

      const report = await runSelftest({
        root,
        jobs: 1,
        env: {
          ...process.env,
          FIXTURE_LOG: log,
          GITHUB_ACTIONS: 'true',
          CI: 'true',
          GITHUB_EVENT_NAME: 'pull_request',
          GITHUB_BASE_REF: 'main',
          GATE_APPROVED_KINDS: 'deps-approved',
        },
        install: noInstall,
      });

      expect(report.cases.map((entry) => entry.status)).toEqual(['passed', 'passed', 'passed']);
      const runs = await readLog(log);
      const controls = runs.filter((entry) => entry['root']?.includes('selftest-base-'));
      expect(controls.map((entry) => entry['only']).sort()).toEqual(['lint', 'secrets']);
      expect(runs.slice(0, 2).every((entry) => entry['root']?.includes('selftest-base-'))).toBe(true);
      const caseRuns = runs.filter((entry) => !entry['root']?.includes('selftest-base-'));
      expect(caseRuns).toHaveLength(3);
      for (const entry of caseRuns) {
        expect(entry['profile']).toBe('full');
        expect(entry['base']).toBe(head);
        expect(entry['github']).toBeNull();
        expect(entry['ci']).toBeNull();
        expect(entry['event']).toBeNull();
        expect(entry['baseRef']).toBeNull();
        expect(entry['kinds']).toBe('');
        expect(entry['baseDir']).toContain('selftest-base-');
      }
    },
    LONG,
  );

  it(
    'rend rouge, avec control-failed, tous les cas d’un check déjà rouge sur la copie propre',
    async () => {
      const root = await buildFixture(
        'control-failed',
        [{ id: 'victim', check: 'lint', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') }],
        { 'src/violation.txt': 'rule-a\n' },
      );

      const report = await runSelftest({ root, jobs: 1, env: process.env, install: noInstall });

      expect(report.cases.map((entry) => [entry.id, entry.status, entry.reason])).toEqual([
        ['victim', 'failed', 'control-failed'],
      ]);
      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );

  it(
    'rend rouge un cas dont l’installation échoue',
    async () => {
      const root = await buildFixture('install-failed', [
        { id: 'victim', check: 'lint', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') },
      ]);
      let calls = 0;
      const install = (): Promise<{ ok: boolean; message: string }> => {
        calls += 1;
        return Promise.resolve({ ok: calls === 1, message: 'store introuvable' });
      };

      const report = await runSelftest({ root, jobs: 1, env: process.env, install });

      expect(report.cases.map((entry) => [entry.id, entry.status, entry.reason])).toEqual([
        ['victim', 'failed', 'install-failed'],
      ]);
    },
    LONG,
  );

  it(
    'exécute des cas en parallèle sans interférence entre eux',
    async () => {
      const root = await buildFixture('parallel', [
        { id: 'p-good', check: 'lint', rule: 'rule-a', apply: APPLY_VIOLATION('rule-a') },
        { id: 'p-bad', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-b') },
        { id: 'p-link', check: 'lint', rule: 'rule-a', install: 'link', apply: APPLY_VIOLATION('rule-a') },
      ]);
      let active = 0;
      let peak = 0;
      const install = async (): Promise<{ ok: boolean; message: string }> => {
        active += 1;
        peak = Math.max(peak, active);
        await new Promise((done) => setTimeout(done, 250));
        active -= 1;
        return { ok: true, message: '' };
      };

      const report = await runSelftest({ root, jobs: 2, env: process.env, install });

      expect(byId(report.cases, 'p-good')?.status).toBe('passed');
      expect(byId(report.cases, 'p-bad')?.reason).toBe('wrong-rule');
      expect(byId(report.cases, 'p-link')?.status).toBe('passed');
      expect(peak).toBe(2);
      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );
});

describe('cleanupStaleWorktrees', () => {
  async function deadPid(): Promise<number> {
    const child = spawn(process.execPath, ['-e', ''], { stdio: 'ignore' });
    const pid = child.pid ?? 0;
    await new Promise((done) => child.on('close', done));
    return pid;
  }

  it(
    'retire le worktree d’un processus mort et garde celui d’un processus vivant',
    async () => {
      const root = await buildFixture('stale', []);
      const dead = join(scratch, `selftest-old-${String(await deadPid())}-abc123`);
      const live = join(scratch, `selftest-now-${String(process.pid)}-def456`);
      await git(root, 'worktree', 'add', '--detach', dead, 'HEAD');
      await git(root, 'worktree', 'add', '--detach', live, 'HEAD');

      const removed = await cleanupStaleWorktrees(root);

      expect(removed).toEqual([dead]);
      const left = await selftestWorktrees(root);
      expect(left).toHaveLength(1);
      expect(left[0]).toContain(live);
      await expect(access(dead)).rejects.toThrow(/ENOENT/);
      await git(root, 'worktree', 'remove', '--force', live);
    },
    LONG,
  );

  it(
    'prune l’entrée d’un worktree dont le dossier a disparu',
    async () => {
      const root = await buildFixture('pruned', []);
      const gone = join(scratch, `selftest-gone-${String(process.pid)}-aaaaaa`);
      await git(root, 'worktree', 'add', '--detach', gone, 'HEAD');
      await rm(gone, { recursive: true, force: true });

      await cleanupStaleWorktrees(root);

      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );
});

// --- CLI --------------------------------------------------------------------------------------

describe('CLI node quality/selftest/run.ts', () => {
  async function cli(root: string, ...args: string[]): Promise<{ code: number; stderr: string }> {
    const outcome = await runTool({
      command: process.execPath,
      args: [SELFTEST_CLI, '--root', root, ...args],
      cwd: ROOT,
      timeoutMs: 60_000,
    });
    return { code: outcome.code, stderr: outcome.stderr };
  }

  it(
    'sort en code 2 sans worktree ni rapport quand un élément de --case ne retient aucun cas',
    async () => {
      const root = await buildFixture('cli', [
        { id: 'ok-patch', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-a') },
      ]);
      const report = join(scratch, 'nomatch.json');

      const outcome = await cli(root, '--case', 'ok-*,zz-*', '--report', report);

      expect(outcome.code).toBe(2);
      expect(outcome.stderr).toContain('zz-*');
      await expect(access(report)).rejects.toThrow(/ENOENT/);
      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );

  it.each([
    ['un élément vide', ['--case', 'ok-patch,']],
    ['un nombre de jobs nul', ['--jobs', '0']],
    ['un nombre de jobs illisible', ['--jobs', 'abc']],
    ['une option inconnue', ['--inconnue']],
  ])('sort en code 2 pour %s', async (_label, args) => {
    const root = await buildFixture('cli-usage', [
      { id: 'ok-patch', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/violation.txt', 'rule-a') },
    ]);

    expect((await cli(root, ...args)).code).toBe(2);
  }, LONG);

  it(
    'sort en code 2 quand le dépôt ne porte aucun cas',
    async () => {
      const root = await buildFixture('cli-empty', []);

      expect((await cli(root)).code).toBe(2);
    },
    LONG,
  );
});

// --- Check `selftest` (déclencheur D-08) -------------------------------------------------------

async function buildBranchFixture(name: string, changed: Record<string, string>): Promise<string> {
  const root = await buildFixture(name, [], {
    'quality/protected-paths.json': '{"paths":["quality/thresholds.json","quality/old.json"]}\n',
    'quality/thresholds.json': '{"a":1}\n',
    'src/shared/money/money.ts': 'export const a = 1;\n',
  });
  await git(root, 'checkout', '-q', '-b', 'feature');
  await put(root, 'quality/protected-paths.json', '{"paths":["quality/thresholds.json"]}\n');
  for (const [rel, text] of Object.entries(changed)) {
    await put(root, rel, text);
  }
  await git(root, 'add', '-A');
  await git(root, 'commit', '-q', '-m', 'feature');
  return root;
}

function context(root: string, over: Partial<CheckContext>): CheckContext {
  return {
    root,
    profile: 'full',
    base: 'main',
    inCi: true,
    env: {},
    selected: false,
    ...over,
  };
}

describe('check selftest', () => {
  it('se déclare bloquant, sauté au pré-push', () => {
    expect([check.id, check.tool, check.severity, check.push]).toEqual([
      'selftest',
      'selftest',
      'blocking',
      'skip-ci-only',
    ]);
  });

  it(
    'se déclenche en CI quand le diff touche un chemin protégé',
    async () => {
      const root = await buildBranchFixture('trigger', { 'quality/thresholds.json': '{"a":2}\n' });

      expect(await isSelftestTriggered(context(root, {}))).toBe(true);
    },
    LONG,
  );

  it(
    'ne se déclenche pas en CI quand le diff ne touche que du domaine',
    async () => {
      const root = await buildBranchFixture('quiet', {
        'src/shared/money/money.ts': 'export const a = 2;\n',
      });

      expect(await isSelftestTriggered(context(root, {}))).toBe(false);
      const outcome = await check.run(context(root, {}));
      expect(outcome.status).toBe('passed');
      expect(outcome.note).toBe('non déclenché : aucun chemin protégé modifié (D-08)');
    },
    LONG,
  );

  it(
    'lit un chemin protégé retiré de la liste de la tête dans la liste de la base',
    async () => {
      const root = await buildBranchFixture('union', { 'quality/old.json': '{}\n' });

      expect(await isSelftestTriggered(context(root, {}))).toBe(true);
    },
    LONG,
  );

  it(
    'se déclenche hors CI seulement quand il est demandé ou forcé',
    async () => {
      const root = await buildBranchFixture('local', { 'quality/thresholds.json': '{"a":2}\n' });

      expect(await isSelftestTriggered(context(root, { inCi: false }))).toBe(false);
      expect(await isSelftestTriggered(context(root, { inCi: false, selected: true }))).toBe(true);
      expect(
        await isSelftestTriggered(context(root, { inCi: false, env: { GATE_FORCE_SELFTEST: '1' } })),
      ).toBe(true);
      expect(
        await isSelftestTriggered(context(root, { inCi: false, env: { GATE_FORCE_SELFTEST: '0' } })),
      ).toBe(false);
    },
    LONG,
  );

  it(
    'se déclenche en CI quand la base est introuvable (échec fermé)',
    async () => {
      const root = await buildBranchFixture('nobase', { 'src/shared/money/money.ts': 'x\n' });

      expect(await isSelftestTriggered(context(root, { base: 'origin/absente' }))).toBe(true);
    },
    LONG,
  );

  it(
    'échoue avec tool-error quand le runner est introuvable',
    async () => {
      const root = await buildBranchFixture('norunner', {});

      const outcome = await check.run(context(root, { selected: true }));

      expect(outcome.status).toBe('failed');
      expect(outcome.issues.map((issue) => issue.rule)).toEqual(['tool-error']);
    },
    LONG,
  );

  it('transforme chaque cas rouge en issue case-not-detected:<id>', () => {
    const red: CaseResult = {
      id: 'lint-x',
      check: 'lint',
      rule: 'r',
      status: 'failed',
      reason: 'wrong-rule',
      detail: 'règles vues : a',
      duration_ms: 1,
    };
    const green: CaseResult = { ...red, id: 'lint-y', status: 'passed', reason: 'detected' };

    const issues = casesToIssues([red, green]);

    expect(issues.map((issue) => issue.rule)).toEqual(['case-not-detected:lint-x']);
    expect(issues[0]?.message).toContain('wrong-rule');
  });
});
