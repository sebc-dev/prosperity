import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CheckContext } from '../gate-report.ts';
import type { ApprovalsReport } from '../verdict-rules.ts';
import { check } from './approvals.ts';

const VERIFIER = ['github', 'label-events@1'].join('-');
let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'check-approvals-test-'));
  await mkdir(join(scratch, 'reports'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

function context(over: Partial<CheckContext>): CheckContext {
  return { root: scratch, profile: 'full', base: 'origin/main', inCi: false, env: {}, ...over };
}

const pullRequest = { inCi: true, env: { GITHUB_EVENT_NAME: 'pull_request' } };

function report(over: Partial<ApprovalsReport> = {}): ApprovalsReport {
  return {
    approved: [],
    rejected: [],
    bootstrap: false,
    verifier: VERIFIER,
    approval: null,
    ...over,
  };
}

const writeReport = (content: unknown) =>
  writeFile(join(scratch, 'reports', 'approvals.json'), JSON.stringify(content));

describe('check approvals', () => {
  it('est bloquant et sauté en profil push', () => {
    expect(check).toMatchObject({ id: 'approvals', severity: 'blocking', push: 'skip-ci-only' });
  });

  it('est skipped ci-only en local', async () => {
    expect(await check.run(context({}))).toMatchObject({
      check: 'approvals',
      status: 'skipped',
      skipped_reason: 'ci-only',
    });
  });

  it('passe avec une note en CI hors pull_request', async () => {
    const result = await check.run(context({ inCi: true, env: { GITHUB_EVENT_NAME: 'push' } }));
    expect(result.status).toBe('passed');
    expect(result.note).toContain('pull_request');
  });

  it('échoue fermé en CI sur pull_request sans rapport', async () => {
    const result = await check.run(context(pullRequest));
    expect(result.status).toBe('failed');
    expect(result.issues.map((issue) => issue.rule)).toEqual(['missing-trusted-report']);
  });

  it.each([
    ['hors schéma', { approved: 'deps-approved' }],
    ['qui n est pas un objet', 'rapport'],
  ])('échoue fermé quand le rapport est %s', async (_name, content) => {
    await writeReport(content);
    const result = await check.run(context(pullRequest));
    expect(result.issues.map((issue) => issue.rule)).toEqual(['missing-trusted-report']);
  });
});

describe('check approvals : rapport de confiance', () => {
  it('passe avec la version du vérificateur quand le rapport est conforme', async () => {
    await writeReport(report({ approved: ['deps-approved'] }));
    const result = await check.run(context(pullRequest));
    expect(result).toMatchObject({
      check: 'approvals',
      tool: 'approvals',
      severity: 'blocking',
      status: 'passed',
      version: VERIFIER,
      issues: [],
    });
  });

  it('reprend chaque refus comme issue, la règle étant la raison', async () => {
    const rejected = [
      { kind: 'deps-approved', reason: 'approval-stale' },
      { kind: 'gate-change-approved', reason: 'approval-missing' },
    ];
    await writeReport(report({ rejected }));
    const result = await check.run(context(pullRequest));
    expect(result.status).toBe('passed');
    expect(result.issues.map((issue) => issue.rule)).toEqual([
      'approval-stale',
      'approval-missing',
    ]);
    expect(result.issues[0]?.message).toContain('deps-approved');
  });

  it('note l amorçage', async () => {
    await writeReport(report({ bootstrap: true }));
    const result = await check.run(context(pullRequest));
    expect(result.status).toBe('passed');
    expect(result.note).toContain('amorçage');
  });
});
