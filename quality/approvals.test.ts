import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { lastPushAnchor } from './approvals.ts';
import {
  AFTER,
  ANCHOR,
  BEFORE,
  CONFIG,
  DEPS,
  decide,
  evidence,
  GATE,
  labelEvent,
  reasons,
  run,
  SHA,
} from './approvals-fixtures.ts';

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'approvals-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

// --- lastPushAnchor ---------------------------------------------------------

describe('lastPushAnchor', () => {
  it('prend le plus ancien run pull_request du SHA de tête sur la branche et le dépôt de la PR', () => {
    const runs = [
      run({ createdAt: '2026-11-22T10:20:00Z' }),
      run({ createdAt: ANCHOR }),
      run({ createdAt: '2026-11-22T10:10:00Z' }),
    ];
    expect(lastPushAnchor(evidence({ runs }))).toBe(Date.parse(ANCHOR));
  });

  it.each([
    ['une autre branche', { headBranch: 'autre' }],
    ['un autre dépôt', { headRepository: 'fork/r' }],
    ['un autre SHA', { headSha: 'b'.repeat(40) }],
    ['un autre événement', { event: 'push' }],
  ])('ignore un run plus ancien venu d %s', (_name, over) => {
    const runs = [run({ createdAt: BEFORE, ...over }), run({ createdAt: ANCHOR })];
    expect(lastPushAnchor(evidence({ runs }))).toBe(Date.parse(ANCHOR));
  });

  it('est relevée par un push forcé plus récent que le premier run', () => {
    const forcePushes = ['2026-11-22T10:03:00Z', '2026-11-22T09:00:00Z'];
    expect(lastPushAnchor(evidence({ forcePushes }))).toBe(Date.parse('2026-11-22T10:03:00Z'));
  });

  it('reste au premier run quand le push forcé est plus ancien', () => {
    expect(lastPushAnchor(evidence({ forcePushes: [BEFORE] }))).toBe(Date.parse(ANCHOR));
  });

  it('est indéfinie sans run retenu, même avec un push forcé', () => {
    expect(lastPushAnchor(evidence({ runs: [], forcePushes: [AFTER] }))).toBeUndefined();
  });
});

describe('decideApprovals : acteur, date et retrait', () => {
  it('approuve un label posé par un acteur de la liste après l ancre, label encore présent', () => {
    const verdict = decide(evidence({ labelEvents: [labelEvent()] }));
    expect(verdict.approved).toEqual([DEPS]);
    expect(verdict.approval).toEqual({
      commit: SHA,
      principal: 'sebc-dev',
      keyType: 'github-label',
      flags: null,
    });
  });

  it('refuse chaque sorte sans événement avec approval-missing et approval null', () => {
    expect(decide(evidence())).toEqual({
      approved: [],
      rejected: [
        { kind: GATE, reason: 'approval-missing' },
        { kind: DEPS, reason: 'approval-missing' },
      ],
      approval: null,
    });
  });

  it.each(['github-actions[bot]', ''])('refuse un label posé par « %s »', (actor) => {
    const labelEvents = [labelEvent({ actor })];
    expect(reasons(evidence({ labelEvents }))).toContainEqual([DEPS, 'approval-actor-not-allowed']);
  });

  it('refuse un acteur vide même si la liste contient une chaîne vide', () => {
    const verdict = decide(evidence({ labelEvents: [labelEvent({ actor: '' })] }), {
      ...CONFIG,
      allowlist: [''],
    });
    expect(verdict.approved).toEqual([]);
  });

  it.each([
    ['à l ancre', ANCHOR],
    ['avant l ancre', BEFORE],
  ])('refuse un label posé %s avec approval-stale', (_name, createdAt) => {
    const labelEvents = [labelEvent({ createdAt })];
    expect(reasons(evidence({ labelEvents }))).toContainEqual([DEPS, 'approval-stale']);
  });

  it('refuse un labeled suivi d un unlabeled avec approval-removed', () => {
    const labelEvents = [
      labelEvent(),
      labelEvent({ id: 2, event: 'unlabeled', createdAt: '2026-11-22T10:06:00Z' }),
    ];
    expect(reasons(evidence({ labelEvents }))).toContainEqual([DEPS, 'approval-removed']);
  });

  it('refuse un dernier labeled dont le label n est plus sur la PR', () => {
    const base = evidence({ labelEvents: [labelEvent()] });
    const pull = { ...base.pull, labels: [GATE] };
    expect(reasons({ ...base, pull })).toContainEqual([DEPS, 'approval-removed']);
  });

  it('approuve un label reposé après un retrait', () => {
    const labelEvents = [
      labelEvent({ id: 1 }),
      labelEvent({ id: 2, event: 'unlabeled', createdAt: '2026-11-22T10:06:00Z' }),
      labelEvent({ id: 3, createdAt: '2026-11-22T10:07:00Z' }),
    ];
    expect(decide(evidence({ labelEvents })).approved).toEqual([DEPS]);
  });
});

describe('decideApprovals : ordre, tête et ancre', () => {
  it('ne compte que le dernier événement du label : un bot qui repose le label est refusé', () => {
    const labelEvents = [
      labelEvent({ id: 1 }),
      labelEvent({ id: 2, event: 'unlabeled', createdAt: '2026-11-22T10:06:00Z' }),
      labelEvent({ id: 3, actor: 'github-actions[bot]', createdAt: '2026-11-22T10:07:00Z' }),
    ];
    expect(reasons(evidence({ labelEvents }))).toContainEqual([DEPS, 'approval-actor-not-allowed']);
  });

  it('trie par date puis par identifiant, quel que soit l ordre des événements', () => {
    const labelEvents = [
      labelEvent({ id: 9, event: 'unlabeled', createdAt: AFTER }),
      labelEvent({ id: 8, createdAt: AFTER }),
    ];
    expect(reasons(evidence({ labelEvents }))).toContainEqual([DEPS, 'approval-removed']);
    expect(reasons(evidence({ labelEvents: [...labelEvents].reverse() }))).toContainEqual([
      DEPS,
      'approval-removed',
    ]);
  });

  it('juge chaque label séparément et joint les acteurs approuvés, triés et uniques', () => {
    const labelEvents = [
      labelEvent({ id: 1, label: GATE, actor: 'zoe' }),
      labelEvent({ id: 2, label: DEPS, actor: 'abel' }),
    ];
    const verdict = decide(evidence({ labelEvents }), {
      allowlist: ['abel', 'zoe'],
      labels: [GATE, DEPS],
    });
    expect(verdict.approved).toEqual([GATE, DEPS]);
    expect(verdict.approval).toMatchObject({ principal: 'abel,zoe' });
    const same = [labelEvent({ id: 1, label: GATE }), labelEvent({ id: 2, label: DEPS })];
    expect(decide(evidence({ labelEvents: same })).approval).toMatchObject({
      principal: 'sebc-dev',
    });
  });
});

describe('decideApprovals : tête, ancre et configuration', () => {
  it('refuse tout avec approval-no-anchor quand aucun run n est retenu', () => {
    const verdict = decide(evidence({ runs: [], labelEvents: [labelEvent()] }));
    expect(verdict.rejected).toEqual([
      { kind: GATE, reason: 'approval-no-anchor' },
      { kind: DEPS, reason: 'approval-no-anchor' },
    ]);
  });

  it('refuse tout avec approval-head-moved quand la tête de la PR a changé', () => {
    const base = evidence({ labelEvents: [labelEvent()] });
    const pull = { ...base.pull, headSha: 'b'.repeat(40) };
    expect(decide({ ...base, pull }).rejected).toEqual([
      { kind: GATE, reason: 'approval-head-moved' },
      { kind: DEPS, reason: 'approval-head-moved' },
    ]);
  });

  it('un push forcé entre l ancre et le label rend le label périmé', () => {
    const labelEvents = [labelEvent({ createdAt: '2026-11-22T10:02:00Z' })];
    const forcePushes = ['2026-11-22T10:03:00Z'];
    expect(reasons(evidence({ labelEvents, forcePushes }))).toContainEqual([
      DEPS,
      'approval-stale',
    ]);
  });

  it('ignore un run plus ancien d une autre branche : le label posé avant le run de la PR est périmé', () => {
    const runs = [run({ createdAt: BEFORE, headBranch: 'autre' }), run()];
    const labelEvents = [labelEvent({ createdAt: '2026-11-22T09:58:00Z' })];
    expect(reasons(evidence({ runs, labelEvents }))).toContainEqual([DEPS, 'approval-stale']);
  });

  it('n approuve que les labels de la configuration', () => {
    const labelEvents = [labelEvent({ label: 'autre-label' })];
    expect(decide(evidence({ labelEvents }), { ...CONFIG, labels: [DEPS] }).rejected).toEqual([
      { kind: DEPS, reason: 'approval-missing' },
    ]);
  });
});
