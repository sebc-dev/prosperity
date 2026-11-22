import { spawn } from 'node:child_process';
import { access, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { CheckResult } from '../gate-report.ts';
import { runTool } from '../tools.ts';
import { buildFixture, git, newFilePatch, selftestWorktrees, useScratch } from './fixture.ts';
import { matchesExpected, selectCases } from './run.ts';
import { cleanupStaleWorktrees } from './worktrees.ts';

const ROOT = resolve(import.meta.dirname, '..', '..');
const SELFTEST_CLI = join(ROOT, 'quality', 'selftest', 'run.ts');
const LONG = 90_000;
const scratch = useScratch();

function failedWith(...rules: string[]): Pick<CheckResult, 'status' | 'issues'> {
  return { status: 'failed', issues: rules.map((rule) => ({ rule, message: 'm' })) };
}

describe('matchesExpected', () => {
  it.each([
    ['la règle exacte', failedWith('no-restricted-syntax'), 'no-restricted-syntax', true],
    ['la règle parmi d’autres', failedWith('a', 'exports'), 'exports', true],
    ['un suffixe après un point', failedWith('rules.prosperity.sql'), 'prosperity.sql', true],
    ['une autre règle', failedWith('exports'), 'files', false],
    ['un suffixe sans frontière', failedWith('tool-error'), 'error', false],
    ['tool-error', failedWith('tool-error'), 'github-pat', false],
    ['tool-error même attendu', failedWith('tool-error'), 'tool-error', false],
    ['tool-version-mismatch', failedWith('tool-version-mismatch'), 'github-pat', false],
    ['check-crashed même attendu', failedWith('check-crashed'), 'check-crashed', false],
    ['aucune issue', failedWith(), 'exports', false],
  ] as const)('pour %s', (_label, result, rule, expected) => {
    expect(matchesExpected(result, { rule })).toBe(expected);
  });

  it.each(['passed', 'skipped'] as const)('refuse un check au statut %s', (status) => {
    const issues = [{ rule: 'exports', message: 'm' }];

    expect(matchesExpected({ status, issues }, { rule: 'exports' })).toBe(false);
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
      const root = await buildFixture(scratch(), 'stale', []);
      const dead = join(scratch(), `selftest-old-${String(await deadPid())}-abc123`);
      const live = join(scratch(), `selftest-now-${String(process.pid)}-def456`);
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
      const root = await buildFixture(scratch(), 'pruned', []);
      const gone = join(scratch(), `selftest-gone-${String(process.pid)}-aaaaaa`);
      await git(root, 'worktree', 'add', '--detach', gone, 'HEAD');
      await rm(gone, { recursive: true, force: true });

      await cleanupStaleWorktrees(root);

      expect(await selftestWorktrees(root)).toEqual([]);
    },
    LONG,
  );
});

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

  const oneCase = [
    { id: 'ok-patch', check: 'lint', rule: 'rule-a', patch: newFilePatch('src/a.txt', 'rule-a') },
  ];

  it(
    'sort en code 2 sans worktree ni rapport quand un élément de --case ne retient aucun cas',
    async () => {
      const root = await buildFixture(scratch(), 'cli', oneCase);
      const report = join(scratch(), 'nomatch.json');

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
  ])(
    'sort en code 2 pour %s',
    async (_label, args) => {
      const root = await buildFixture(scratch(), 'cli-usage', oneCase);

      expect((await cli(root, ...args)).code).toBe(2);
    },
    LONG,
  );

  it(
    'sort en code 2 quand le dépôt ne porte aucun cas',
    async () => {
      const root = await buildFixture(scratch(), 'cli-empty', []);

      expect((await cli(root)).code).toBe(2);
    },
    LONG,
  );
});
