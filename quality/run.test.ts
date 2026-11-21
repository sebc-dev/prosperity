import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { check as lintCheck } from './checks/lint.ts';
import { computeVerdict, writeGateReport } from './gate-report.ts';
import type { CheckResult, GateReport } from './gate-report.ts';
import { runTool, verifyMiseToolVersion, verifyNpmToolVersion } from './tools.ts';

const ROOT = resolve(import.meta.dirname, '..');

function result(over: Partial<CheckResult>): CheckResult {
  return {
    check: 'fixture',
    tool: 'fixture-tool',
    version: '1.0.0',
    severity: 'blocking',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 0,
    ...over,
  };
}

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'gate-run-test-'));
});

afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(scratch, { recursive: true, force: true });
});

describe('computeVerdict', () => {
  it('fait échouer le profil full en CI quand un check bloquant est skipped', () => {
    const skipped = result({ status: 'skipped', passed: false, skipped_reason: 'ci-only' });
    expect(computeVerdict('full', [skipped], true)).toBe('fail');
  });

  it('accepte en profil push un check bloquant skipped avec la raison ci-only', () => {
    const skipped = result({ status: 'skipped', passed: false, skipped_reason: 'ci-only' });
    expect(computeVerdict('push', [skipped], false)).toBe('pass');
  });

  it('refuse en profil push un check bloquant skipped pour une autre raison', () => {
    const skipped = result({ status: 'skipped', passed: false, skipped_reason: 'oublié' });
    expect(computeVerdict('push', [skipped], false)).toBe('fail');
  });

  it('refuse un check bloquant skipped sans raison', () => {
    const skipped = result({ status: 'skipped', passed: false });
    expect(computeVerdict('push', [skipped], false)).toBe('fail');
  });

  it('ignore un check advisory en échec', () => {
    const advisory = result({ severity: 'advisory', status: 'failed', passed: false });
    expect(computeVerdict('full', [advisory], true)).toBe('pass');
  });

  it('fait échouer un check bloquant failed et laisse passer un check passed', () => {
    const failed = result({ status: 'failed', passed: false });
    expect(computeVerdict('push', [result({}), failed], false)).toBe('fail');
    expect(computeVerdict('push', [result({})], false)).toBe('pass');
  });
});

describe('writeGateReport', () => {
  it('écrit un rapport lisible et complet sans laisser de fichier temporaire', async () => {
    const report: GateReport = {
      profile: 'full',
      commit: 'abc123',
      base: 'origin/main',
      generated_at: '2026-11-21T00:00:00.000Z',
      verdict: 'pass',
      checks: [result({ note: 'seed 42' })],
    };
    const path = join(scratch, 'reports', 'gate.json');

    await writeGateReport(path, report);

    expect(JSON.parse(await readFile(path, 'utf8'))).toEqual(report);
    expect(await readdir(join(scratch, 'reports'))).toEqual(['gate.json']);
  });
});

describe('vérification de version des outils', () => {
  it("renvoie ok: false quand la version installée d'un paquet npm diffère du pin", async () => {
    await mkdir(join(scratch, 'node_modules', 'fixture-pkg'), { recursive: true });
    await writeFile(
      join(scratch, 'package.json'),
      JSON.stringify({ devDependencies: { 'fixture-pkg': '1.0.0' } }),
    );
    await writeFile(
      join(scratch, 'node_modules', 'fixture-pkg', 'package.json'),
      JSON.stringify({ version: '2.0.0' }),
    );

    expect(await verifyNpmToolVersion(scratch, 'fixture-pkg')).toEqual({
      ok: false,
      found: '2.0.0',
      expected: '1.0.0',
    });
  });

  it('fait échouer le check lint avec tool-version-mismatch quand eslint diffère de son pin', async () => {
    await mkdir(join(scratch, 'node_modules', 'eslint'), { recursive: true });
    await writeFile(
      join(scratch, 'package.json'),
      JSON.stringify({ devDependencies: { eslint: '1.0.0' } }),
    );
    await writeFile(
      join(scratch, 'node_modules', 'eslint', 'package.json'),
      JSON.stringify({ version: '2.0.0' }),
    );

    const outcome = await lintCheck.run({
      root: scratch,
      profile: 'full',
      base: 'origin/main',
      inCi: false,
      env: {},
    });

    expect(outcome.status).toBe('failed');
    expect(outcome.issues.map((issue) => issue.rule)).toEqual(['tool-version-mismatch']);
  });

  it('renvoie ok: false pour un mise.toml de fixture au pin volontairement faux', async () => {
    await writeFile(join(scratch, 'mise.toml'), '[tools]\nnode = "0.0.1"\n');
    // `node` est neutralisé côté mise : l'exécution retombe sur le node du PATH, jamais installé.
    vi.stubEnv('MISE_DISABLE_TOOLS', 'node');
    vi.stubEnv('MISE_TRUSTED_CONFIG_PATHS', scratch);

    const outcome = await verifyMiseToolVersion(scratch, 'node', ['--version']);

    expect(outcome.ok).toBe(false);
    expect(outcome.expected).toBe('0.0.1');
    expect(outcome.found).toMatch(/^\d+\.\d+\.\d+$/);
  });
});

describe('quality/run.ts', () => {
  it('sort en code 2 sur un identifiant de check inconnu', async () => {
    const outcome = await runTool({
      command: process.execPath,
      args: ['quality/run.ts', '--only', 'inexistant'],
      cwd: ROOT,
      timeoutMs: 60_000,
    });

    expect(outcome.code).toBe(2);
    expect(outcome.stderr).toContain('check inconnu : inexistant');
  });
});
