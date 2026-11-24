import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { InstallOutcome } from './context.ts';
import {
  APPLY_STALE,
  applyViolation,
  buildFixture,
  byId,
  field,
  git,
  INAPPLICABLE_PATCH,
  isBaseRun,
  newFilePatch,
  noInstall,
  readLog,
  selftestWorktrees,
  useScratch,
} from './fixture.ts';
import { runSelftest } from './run.ts';

const LONG = 90_000;
const scratch = useScratch();

/** Environnement d'un run en CI : l'auto-test doit le neutraliser pour les cas. */
function ciEnv(log: string): NodeJS.ProcessEnv {
  return {
    ...process.env,
    FIXTURE_LOG: log,
    GITHUB_ACTIONS: 'true',
    CI: 'true',
    GITHUB_EVENT_NAME: 'pull_request',
    GITHUB_BASE_REF: 'main',
    GATE_APPROVED_KINDS: 'deps-approved',
  };
}

describe('runSelftest : verdict par règle attendue', () => {
  it(
    'ne rend vert que le cas dont le check échoue pour la règle attendue',
    async () => {
      const lint = { check: 'lint', rule: 'rule-a' };
      const root = await buildFixture(scratch(), 'verdicts', [
        { id: 'ok-patch', ...lint, patch: newFilePatch('src/violation.txt', 'rule-a') },
        { id: 'ok-apply', ...lint, apply: applyViolation('rule-a') },
        { id: 'wrong-rule', ...lint, patch: newFilePatch('src/violation.txt', 'rule-b') },
        { id: 'tool-broken', ...lint, patch: newFilePatch('src/broken-tool.txt', 'x') },
        { id: 'not-detected', ...lint, patch: newFilePatch('src/harmless.txt', 'x') },
        { id: 'stale', ...lint, apply: APPLY_STALE },
        { id: 'bad-patch', ...lint, patch: INAPPLICABLE_PATCH },
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
});

describe('runSelftest : contrôle de causalité', () => {
  it(
    'joue le contrôle propre une fois par check avant les cas, avec l’environnement local',
    async () => {
      const root = await buildFixture(scratch(), 'control', [
        { id: 'one', check: 'lint', rule: 'rule-a', apply: applyViolation('rule-a') },
        { id: 'two', check: 'lint', rule: 'rule-a', apply: applyViolation('rule-a') },
        { id: 'three', check: 'secrets', rule: 'rule-a', apply: applyViolation('rule-a') },
      ]);
      const log = join(scratch(), 'trace.jsonl');
      const head = await git(root, 'rev-parse', 'HEAD');

      const report = await runSelftest({ root, jobs: 1, env: ciEnv(log), install: noInstall });

      expect(report.cases.map((entry) => entry.status)).toEqual(['passed', 'passed', 'passed']);
      const runs = await readLog(log);
      const controls = runs.filter(isBaseRun);
      expect(
        controls.map((entry) => field(entry, 'only')).sort((a, b) => a.localeCompare(b)),
      ).toEqual(['lint', 'secrets']);
      expect(runs.slice(0, 2).every(isBaseRun)).toBe(true);
      const caseRuns = runs.filter((entry) => !isBaseRun(entry));
      expect(caseRuns).toHaveLength(3);
      for (const entry of caseRuns) {
        expect(entry['profile']).toBe('full');
        expect(entry['base']).toBe(head);
        expect([entry['github'], entry['ci'], entry['event'], entry['baseRef']]).toEqual([
          null,
          null,
          null,
          null,
        ]);
        expect(entry['kinds']).toBe('');
        expect(field(entry, 'baseDir')).toContain('selftest-base-');
      }
    },
    LONG,
  );

  it(
    'rend rouge, avec control-failed, tous les cas d’un check déjà rouge sur la copie propre',
    async () => {
      const root = await buildFixture(
        scratch(),
        'control-failed',
        [{ id: 'victim', check: 'lint', rule: 'rule-a', apply: applyViolation('rule-a') }],
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
});

describe('runSelftest : installation et parallélisme', () => {
  it(
    'rend rouge un cas dont l’installation échoue',
    async () => {
      const root = await buildFixture(scratch(), 'install-failed', [
        { id: 'victim', check: 'lint', rule: 'rule-a', apply: applyViolation('rule-a') },
      ]);
      let calls = 0;
      const install = (): Promise<InstallOutcome> => {
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
      const lint = { check: 'lint', rule: 'rule-a' };
      const root = await buildFixture(scratch(), 'parallel', [
        { id: 'p-good', ...lint, apply: applyViolation('rule-a') },
        { id: 'p-bad', ...lint, patch: newFilePatch('src/violation.txt', 'rule-b') },
        { id: 'p-link', ...lint, install: 'link', apply: applyViolation('rule-a') },
      ]);
      // Barrière : chaque installation attend que l'autre ait démarré (plafond 20 s), au lieu
      // d'une fenêtre fixe de 250 ms que la création d'un worktree sous charge dépassait (peak 1).
      // Un runner séquentiel laisse la première attendre en vain : peak reste 1, le test échoue.
      let active = 0;
      let peak = 0;
      let release: () => void = () => undefined;
      const bothStarted = new Promise<void>((done) => {
        release = done;
      });
      const install = async (): Promise<InstallOutcome> => {
        active += 1;
        peak = Math.max(peak, active);
        if (active === 2) {
          release();
        }
        await Promise.race([bothStarted, new Promise((done) => setTimeout(done, 20_000))]);
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
