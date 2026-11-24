import { copyFile, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CheckContext, CheckResult } from '../gate-report.ts';
import { check } from './deps.ts';

const QUALITY_ROOT = resolve(import.meta.dirname, '..', '..');
let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'check-deps-test-'));
  await mkdir(join(scratch, 'reports'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

function context(over: Partial<CheckContext>): CheckContext {
  return {
    root: scratch,
    profile: 'full',
    base: 'origin/main',
    inCi: false,
    env: {},
    selected: false,
    ...over,
  };
}

const pullRequest = { GITHUB_EVENT_NAME: 'pull_request' };

function report(over: Partial<CheckResult>): CheckResult {
  return {
    check: 'deps',
    tool: 'deps-guard',
    version: 'v26',
    severity: 'blocking',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 1,
    ...over,
  };
}

describe('check deps', () => {
  it('est bloquant et sauté en profil push', () => {
    expect(check).toMatchObject({ id: 'deps', severity: 'blocking', push: 'skip-ci-only' });
  });

  it('est skipped ci-only en local sans GATE_BASE_DIR', async () => {
    expect(await check.run(context({}))).toMatchObject({
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
    const result = await check.run(context({ inCi: true, env: pullRequest }));
    expect(result.issues.map((issue) => issue.rule)).toEqual(['missing-trusted-report']);
  });

  it('échoue fermé quand le rapport est illisible', async () => {
    await writeFile(join(scratch, 'reports', 'deps.json'), '{"check":"deps"}');
    const result = await check.run(context({ inCi: true, env: pullRequest }));
    expect(result.status).toBe('failed');
  });

  it('reprend le rapport de confiance mais impose bloquant et identité', async () => {
    const forged = report({
      severity: 'advisory',
      check: 'autre',
      status: 'failed',
      passed: false,
    });
    await writeFile(join(scratch, 'reports', 'deps.json'), JSON.stringify(forged));
    const result = await check.run(context({ inCi: true, env: pullRequest }));
    expect(result).toMatchObject({ check: 'deps', severity: 'blocking', status: 'failed' });
  });

  it('joue le garde réel en local avec GATE_BASE_DIR : base identique, rien à approuver', async () => {
    const base = join(scratch, 'base');
    await mkdir(base);
    for (const name of ['package.json', 'pnpm-lock.yaml']) {
      await copyFile(join(QUALITY_ROOT, name), join(base, name));
    }
    const env = { ...process.env, GATE_BASE_DIR: base };
    const result = await check.run(context({ root: QUALITY_ROOT, env }));
    expect(result).toMatchObject({ check: 'deps', status: 'passed', issues: [] });
  });
});
