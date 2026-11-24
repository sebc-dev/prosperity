import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CheckResult } from './gate-report.ts';
import { runTool } from './tools.ts';

const VERDICT = resolve(import.meta.dirname, 'verdict.ts');
const BARE_ENV = { PATH: process.env['PATH'] ?? '' };
let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'verdict-cli-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

function checkResult(id: string, rule?: string): CheckResult {
  const failed = rule !== undefined;
  return {
    check: id,
    tool: id,
    version: 'v26',
    severity: 'blocking',
    passed: !failed,
    status: failed ? 'failed' : 'passed',
    issues: failed ? [{ rule, message: 'refusé' }] : [],
    duration_ms: 1,
  };
}

/** Faux juges de la branche par défaut : chacun écrit son rapport dans `--out`, puis sort 0 ou 1. */
async function baseWith(integrityRule?: string): Promise<string> {
  const baseDir = join(scratch, 'base');
  await mkdir(join(baseDir, 'quality'), { recursive: true });
  await writeFile(join(baseDir, 'package.json'), '{"type":"module"}');
  const stub = (id: string, rule?: string): string =>
    `import { writeFileSync } from 'node:fs';
const out = process.argv[process.argv.indexOf('--out') + 1];
writeFileSync(out, ${JSON.stringify(JSON.stringify(checkResult(id, rule)))});
process.exit(${String(rule === undefined ? 0 : 1)});
`;
  await writeFile(join(baseDir, 'quality', 'integrity.ts'), stub('integrity', integrityRule));
  await writeFile(join(baseDir, 'quality', 'deps-guard.ts'), stub('deps'));
  return baseDir;
}

async function approvalsFile(over: Record<string, unknown> = {}): Promise<string> {
  const path = join(scratch, 'approvals.json');
  const report = { approved: [], rejected: [], bootstrap: false, verifier: 'v', approval: null };
  await writeFile(path, JSON.stringify({ ...report, ...over }));
  return path;
}

async function dryRun(base: string, extra: string[], over: Record<string, unknown> = {}) {
  const head = join(scratch, 'head');
  await mkdir(head, { recursive: true });
  const approvals = await approvalsFile(over);
  const out = join(scratch, 'verdict.json');
  const run = await runTool({
    command: process.execPath,
    args: [
      VERDICT,
      ...['--base-dir', base, '--work-dir', join(scratch, 'work'), '--out', out],
      ...['--dry-run', '--head-dir', head, '--approvals-report', approvals],
      ...extra,
    ],
    cwd: scratch,
    env: BARE_ENV,
    timeoutMs: 60_000,
  });
  const written: unknown = JSON.parse(await readFile(out, 'utf8'));
  return { run, written };
}

describe('quality/verdict.ts --dry-run', () => {
  it('imprime un statut success quand les juges et le rapport d approbations passent', async () => {
    const { run, written } = await dryRun(await baseWith(), []);
    expect({ code: run.code, stderr: run.stderr }).toEqual({ code: 0, stderr: '' });
    expect(JSON.parse(run.stdout)).toMatchObject({ state: 'success', context: 'quality' });
    expect(written).toMatchObject({ conclusion: 'success', reasons: [] });
  });

  it('refuse avec integrity-failed et reprend protected-path-changed', async () => {
    const { run, written } = await dryRun(await baseWith('protected-path-changed'), []);
    expect(JSON.parse(run.stdout)).toMatchObject({ state: 'failure' });
    expect(run.stdout).toContain('integrity-failed');
    expect(JSON.stringify(written)).toContain('protected-path-changed');
  });

  it('refuse un run gate en échec', async () => {
    const { run } = await dryRun(await baseWith(), ['--gate-conclusion', 'failure']);
    expect(run.stdout).toContain('gate-not-success');
  });

  it('refuse un rapport d approbations d amorçage', async () => {
    const { run } = await dryRun(await baseWith(), [], { bootstrap: true });
    expect(run.stdout).toContain('bootstrap-not-allowed');
  });
});

describe('quality/verdict.ts en mode normal', () => {
  async function live(env: Record<string, string>, event?: unknown) {
    const out = join(scratch, 'verdict.json');
    const eventPath = join(scratch, 'event.json');
    await writeFile(eventPath, JSON.stringify(event ?? {}));
    const run = await runTool({
      command: process.execPath,
      args: [
        VERDICT,
        ...['--base-dir', scratch, '--work-dir', join(scratch, 'work'), '--out', out],
      ],
      cwd: scratch,
      env: { ...BARE_ENV, GITHUB_EVENT_PATH: eventPath, ...env },
      timeoutMs: 60_000,
    });
    const written: unknown = JSON.parse(await readFile(out, 'utf8'));
    return { run, written };
  }

  it('sort 1 sans publier quand l environnement GitHub manque', async () => {
    const { run, written } = await live({ GITHUB_EVENT_PATH: '' });
    expect(run.code).toBe(1);
    expect(written).toMatchObject({ conclusion: 'failure', reasons: ['missing-environment'] });
  });

  it('sort 1 sans publier quand le SHA de la charge est invalide', async () => {
    const event = { workflow_run: { head_sha: 'pas-un-sha', pull_requests: [] } };
    const env = { GITHUB_REPOSITORY: 'o/r', GATE_STATUS_TOKEN: 'jeton' };
    const { run, written } = await live(env, event);
    expect(run.code).toBe(1);
    expect(written).toMatchObject({ reasons: ['invalid-head-sha'] });
  });

  it('sort 1 avec un message quand --out manque', async () => {
    const run = await runTool({
      command: process.execPath,
      args: [VERDICT, '--dry-run'],
      cwd: scratch,
      env: BARE_ENV,
    });
    expect(run.code).toBe(1);
    expect(run.stderr).toContain('--out');
  });
});
