import { describe, expect, it } from 'vitest';
import type { CheckContext } from '../gate-report.ts';
import type { CaseResult } from '../selftest/cases.ts';
import { buildFixture, git, put, useScratch } from '../selftest/fixture.ts';
import { casesToIssues, check, isSelftestTriggered } from './selftest.ts';

const LONG = 90_000;
const scratch = useScratch();

async function buildBranchFixture(name: string, changed: Record<string, string>): Promise<string> {
  const root = await buildFixture(scratch(), name, [], {
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
  return { root, profile: 'full', base: 'main', inCi: true, env: {}, selected: false, ...over };
}

describe('check selftest : déclencheur D-08', () => {
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
      const changed = { 'src/shared/money/money.ts': 'export const a = 2;\n' };
      const root = await buildBranchFixture('quiet', changed);

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
    'se déclenche en CI quand la base est introuvable (échec fermé)',
    async () => {
      const root = await buildBranchFixture('nobase', { 'src/shared/money/money.ts': 'x\n' });

      expect(await isSelftestTriggered(context(root, { base: 'origin/absente' }))).toBe(true);
    },
    LONG,
  );
});

describe('check selftest : demande explicite et exécution', () => {
  it(
    'se déclenche hors CI seulement quand il est demandé ou forcé',
    async () => {
      const root = await buildBranchFixture('local', { 'quality/thresholds.json': '{"a":2}\n' });
      const local = (over: Partial<CheckContext>): CheckContext =>
        context(root, { inCi: false, ...over });

      expect(await isSelftestTriggered(local({}))).toBe(false);
      expect(await isSelftestTriggered(local({ selected: true }))).toBe(true);
      expect(await isSelftestTriggered(local({ env: { GATE_FORCE_SELFTEST: '1' } }))).toBe(true);
      expect(await isSelftestTriggered(local({ env: { GATE_FORCE_SELFTEST: '0' } }))).toBe(false);
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
