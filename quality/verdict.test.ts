import { describe, expect, it } from 'vitest';
import type { CheckResult } from './gate-report.ts';
import {
  decideVerdict,
  parseTarget,
  readApprovalsReport,
  runVerdict,
  statusPayload,
} from './verdict.ts';
import type { ApprovalsReport, VerdictTarget } from './verdict.ts';

const SHA = 'a'.repeat(40);
const GATE_PATH = '.github/workflows/quality.yml';

function payload(run: Record<string, unknown> = {}): unknown {
  return {
    action: 'completed',
    workflow_run: {
      head_sha: SHA,
      conclusion: 'success',
      event: 'pull_request',
      path: GATE_PATH,
      pull_requests: [{ number: 12 }],
      html_url: 'https://github.com/o/r/actions/runs/1',
      ...run,
    },
  };
}

function target(over: Partial<VerdictTarget> = {}): VerdictTarget {
  return {
    headSha: SHA,
    pr: 12,
    gateConclusion: 'success',
    gateEvent: 'pull_request',
    gatePath: GATE_PATH,
    runUrl: 'https://github.com/o/r/actions/runs/1',
    ...over,
  };
}

function check(id: string, over: Partial<CheckResult> = {}): CheckResult {
  return {
    check: id,
    tool: id,
    version: 'v26',
    severity: 'blocking',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 1,
    ...over,
  };
}

function approvals(over: Partial<ApprovalsReport> = {}): ApprovalsReport {
  return {
    approved: [],
    rejected: [],
    bootstrap: false,
    verifier: 'approvals@1',
    approval: null,
    ...over,
  };
}

const failedCheck = (id: string, rule: string): CheckResult =>
  check(id, { status: 'failed', passed: false, issues: [{ rule, message: 'refusé' }] });

function decide(over: Partial<Parameters<typeof decideVerdict>[0]> = {}) {
  return decideVerdict({
    target: target(),
    expectedGatePath: GATE_PATH,
    integrity: check('integrity'),
    deps: check('deps'),
    approvals: approvals(),
    ...over,
  });
}

describe('parseTarget', () => {
  it('lit une charge workflow_run complète', () => {
    expect(parseTarget(payload())).toEqual(target());
  });

  it.each(['abc', 'A'.repeat(40), 'g'.repeat(40), 42, undefined])(
    'refuse le SHA %s avec invalid-head-sha',
    (sha) => {
      expect(parseTarget(payload({ head_sha: sha }))).toEqual({ error: 'invalid-head-sha' });
    },
  );

  it.each(['12', 1.5, 0, null])('refuse le numéro de PR %s avec invalid-pr-number', (number) => {
    expect(parseTarget(payload({ pull_requests: [{ number }] }))).toEqual({
      error: 'invalid-pr-number',
    });
  });

  it('laisse la PR indéterminée quand pull_requests est vide (PR de fork)', () => {
    expect(parseTarget(payload({ pull_requests: [] }))).toMatchObject({ pr: undefined });
  });

  it('refuse une charge qui n est pas un workflow_run', () => {
    expect(parseTarget('x')).toEqual({ error: 'invalid-payload' });
    expect(parseTarget({ workflow_run: 3 })).toEqual({ error: 'invalid-payload' });
  });

  it('range une conclusion nulle en chaîne vide', () => {
    expect(parseTarget(payload({ conclusion: null }))).toMatchObject({ gateConclusion: '' });
  });
});

describe('decideVerdict', () => {
  it('rend success quand tout est conforme', () => {
    expect(decide()).toEqual({ conclusion: 'success', reasons: [], issues: [] });
  });

  it.each(['failure', 'cancelled', 'timed_out', ''])(
    'rend failure gate-not-success pour la conclusion « %s »',
    (gateConclusion) => {
      const verdict = decide({ target: target({ gateConclusion }) });
      expect(verdict).toMatchObject({ conclusion: 'failure', reasons: ['gate-not-success'] });
    },
  );

  it('refuse un run déclenché par un autre fichier de workflow', () => {
    const verdict = decide({ target: target({ gatePath: '.github/workflows/evil.yml' }) });
    expect(verdict.reasons).toEqual(['untrusted-gate-path']);
  });

  it('accepte le chemin suivi de la référence que GitHub y ajoute', () => {
    const gatePath = `${GATE_PATH}@refs/pull/12/merge`;
    expect(decide({ target: target({ gatePath }) }).conclusion).toBe('success');
  });

  it('refuse un événement autre que pull_request', () => {
    const verdict = decide({ target: target({ gateEvent: 'push' }) });
    expect(verdict.reasons).toEqual(['untrusted-gate-event']);
  });

  it('reprend les issues d une intégrité refusée (protected-path-changed)', () => {
    const verdict = decide({ integrity: failedCheck('integrity', 'protected-path-changed') });
    expect(verdict.reasons).toEqual(['integrity-failed']);
    expect(verdict.issues.map((issue) => issue.rule)).toContain('protected-path-changed');
  });

  it('refuse des dépendances en échec avec deps-failed', () => {
    const verdict = decide({ deps: failedCheck('deps', 'dependency-added') });
    expect(verdict.reasons).toEqual(['deps-failed']);
  });

  it.each(['integrity', 'deps', 'approvals'] as const)(
    'refuse un rapport %s absent avec missing-trusted-report',
    (name) => {
      const verdict = decide({ [name]: undefined });
      expect(verdict.reasons).toEqual([`missing-trusted-report:${name}`]);
    },
  );

  it('refuse un rapport d approbations d amorçage', () => {
    expect(decide({ approvals: approvals({ bootstrap: true }) }).reasons).toEqual([
      'bootstrap-not-allowed',
    ]);
  });

  it('refuse une PR introuvable', () => {
    expect(decide({ target: target({ pr: undefined }) }).reasons).toEqual(['pr-not-found']);
  });

  it('reprend les refus d approbation comme issues sans changer la conclusion', () => {
    const rejected = [{ kind: 'deps-approved', reason: 'approval-stale' }];
    const verdict = decide({ approvals: approvals({ rejected }) });
    expect(verdict.conclusion).toBe('success');
    expect(verdict.issues.map((issue) => issue.rule)).toEqual(['approval-stale']);
  });
});

describe('readApprovalsReport', () => {
  const valid = approvals({ approved: ['deps-approved'], rejected: [{ kind: 'k', reason: 'r' }] });

  it('lit un rapport conforme au schéma', () => {
    expect(readApprovalsReport(valid)).toEqual(valid);
    const signed = { commit: 'c', principal: 'p', keyType: 'sk-ssh-ed25519@openssh.com', flags: 5 };
    expect(readApprovalsReport({ ...valid, approval: signed })).toMatchObject({ approval: signed });
  });

  it.each([
    ['approved absent', { ...valid, approved: undefined }],
    ['approved de mauvais type', { ...valid, approved: 'deps-approved' }],
    ['rejected mal formé', { ...valid, rejected: [{ kind: 1 }] }],
    ['bootstrap de mauvais type', { ...valid, bootstrap: 'non' }],
    ['approval mal formé', { ...valid, approval: { commit: 1 } }],
    ['pas un objet', 'rapport'],
  ])('rend undefined pour un rapport hors schéma : %s', (_name, report) => {
    expect(readApprovalsReport(report)).toBeUndefined();
  });
});

describe('statusPayload', () => {
  const url = 'https://github.com/o/r/actions/runs/9';

  it('reflète un succès sur le contexte quality', () => {
    expect(statusPayload(decide(), url)).toMatchObject({
      state: 'success',
      context: 'quality',
      target_url: url,
    });
  });

  it('nomme la première raison et reste sous 140 caractères', () => {
    const verdict = decide({ target: target({ gateConclusion: 'failure' }), deps: undefined });
    const body = statusPayload(verdict, url);
    expect(body.state).toBe('failure');
    expect(body.description).toContain('gate-not-success');
    const long = { conclusion: 'failure' as const, reasons: ['x'.repeat(300)], issues: [] };
    expect(statusPayload(long, url).description).toHaveLength(140);
  });
});

function harness(
  over: { judge?: (name: string) => unknown; extract?: () => Promise<string> } = {},
) {
  const calls: { name: string; args: readonly string[] }[] = [];
  const published: { sha: string; state: string }[] = [];
  const reports: Record<string, unknown> = {
    approvals: approvals(),
    integrity: check('integrity'),
    deps: check('deps'),
  };
  return {
    calls,
    published,
    deps: {
      target: target(),
      baseDir: '/base',
      workDir: '/work',
      extractHead: over.extract ?? (() => Promise.resolve('/work/head')),
      judge: (name: 'approvals' | 'integrity' | 'deps', args: readonly string[]) => {
        calls.push({ name, args });
        const result = over.judge?.(name) ?? reports[name];
        return result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
      },
      publish: (sha: string, body: { state: string }) => {
        published.push({ sha, state: body.state });
        return Promise.resolve();
      },
    },
  };
}

describe('runVerdict', () => {
  it('lance chaque juge depuis la base et publie une seule fois sur le SHA de tête', async () => {
    const { calls, published, deps } = harness();
    expect((await runVerdict(deps)).conclusion).toBe('success');
    expect(published).toEqual([{ sha: SHA, state: 'success' }]);
    const byName = Object.fromEntries(calls.map((call) => [call.name, call.args]));
    expect(byName['approvals']).toEqual([
      ...['--base-dir', '/base', '--head-sha', SHA, '--out', '/work/approvals.json'],
    ]);
    expect(byName['integrity']).toEqual([
      ...['--base-dir', '/base', '--head-dir', '/work/head'],
      ...['--approvals-report', '/work/approvals.json', '--out', '/work/integrity.json'],
    ]);
    expect(byName['deps']).toContain('/work/head');
  });

  it('publie failure avec judge-error quand un juge lève', async () => {
    const { published, deps } = harness({
      judge: (name) => (name === 'integrity' ? new Error('boum') : undefined),
    });
    const verdict = await runVerdict(deps);
    expect(verdict.conclusion).toBe('failure');
    expect(verdict.reasons).toContain('judge-error:integrity');
    expect(published).toEqual([{ sha: SHA, state: 'failure' }]);
  });

  it('publie failure quand l extraction de la tête échoue', async () => {
    const { published, deps } = harness({ extract: () => Promise.reject(new Error('fetch')) });
    const verdict = await runVerdict(deps);
    expect(verdict.reasons).toContain('judge-error:extract-head');
    expect(published).toHaveLength(1);
  });

  it('traite un rapport d approbations hors schéma comme absent', async () => {
    const { deps } = harness({
      judge: (name) => (name === 'approvals' ? { approved: 3 } : undefined),
    });
    expect((await runVerdict(deps)).reasons).toContain('missing-trusted-report:approvals');
  });
});
