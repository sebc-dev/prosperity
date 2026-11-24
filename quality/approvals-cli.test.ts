import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { APPROVAL_KINDS, VERIFIER } from './approvals.ts';
import { CONFIG, DEPS, evidence, labelEvent, SHA, writeConfig } from './approvals-fixtures.ts';
import { runTool } from './tools.ts';
import { readApprovalsReport } from './verdict-rules.ts';

const CLI = resolve(import.meta.dirname, 'approvals.ts');
const BARE_ENV = { PATH: process.env['PATH'] ?? '' };
let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'approvals-cli-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

async function cli(args: string[], cwd: string, env: NodeJS.ProcessEnv = BARE_ENV) {
  return runTool({ command: process.execPath, args: [CLI, ...args], cwd, env, timeoutMs: 60_000 });
}

async function files(e: unknown) {
  const evidencePath = join(scratch, 'evidence.json');
  await writeFile(evidencePath, JSON.stringify(e));
  return { evidencePath, out: join(scratch, 'approvals.json') };
}

async function base(content: unknown = CONFIG): Promise<string> {
  const dir = join(scratch, 'base');
  await writeConfig(dir, content);
  return dir;
}

const common = ['--base-dir', '.', '--evidence', 'e.json', '--out', 'o.json'];

describe('quality/approvals.ts : usage invalide', () => {
  it('sort 2 sans rapport quand --base-dir manque, même dans un dossier « tête » permissif', async () => {
    const head = join(scratch, 'head');
    await writeConfig(head, { allowlist: ['github-actions[bot]'], labels: [DEPS] });
    const { evidencePath, out } = await files(evidence({ labelEvents: [labelEvent()] }));
    const args = ['--evidence', evidencePath, '--head-sha', SHA, '--pr', '300', '--out', out];
    expect((await cli(args, head)).code).toBe(2);
    await expect(readFile(out, 'utf8')).rejects.toThrow('ENOENT');
  });

  it.each([
    ['--evidence manque', ['--base-dir', '.', '--head-sha', SHA, '--pr', '300', '--out', 'o.json']],
    ['--out manque', ['--base-dir', '.', '--evidence', 'e.json', '--head-sha', SHA, '--pr', '300']],
    ['le SHA est trop court', [...common, '--head-sha', SHA.slice(1), '--pr', '300']],
    ['le numéro de PR est invalide', [...common, '--head-sha', SHA, '--pr', '0']],
    ['une option est inconnue', ['--zzz']],
  ])('sort 2 quand %s', async (_name, args) => {
    expect((await cli(args, scratch)).code).toBe(2);
  });
});

describe('quality/approvals.ts : rapport écrit', () => {
  const given = (baseDir: string, evidencePath: string) => [
    ...['--base-dir', baseDir, '--evidence', evidencePath],
    ...['--head-sha', SHA, '--pr', '300'],
  ];

  it('sort 0 et écrit un rapport approuvé lu par readApprovalsReport', async () => {
    const { evidencePath, out } = await files(evidence({ labelEvents: [labelEvent()] }));
    const result = await cli([...given(await base(), evidencePath), '--out', out], scratch);
    expect({ code: result.code, stderr: result.stderr }).toEqual({ code: 0, stderr: '' });
    expect(readApprovalsReport(JSON.parse(await readFile(out, 'utf8')))).toMatchObject({
      approved: [DEPS],
      verifier: VERIFIER,
    });
  });

  it('lit --head-sha et --pr dans GITHUB_EVENT_PATH quand ils manquent', async () => {
    const { evidencePath, out } = await files(evidence({ labelEvents: [labelEvent()] }));
    const eventPath = join(scratch, 'event.json');
    const event = { pull_request: { number: 300, head: { sha: SHA } } };
    await writeFile(eventPath, JSON.stringify(event));
    const args = ['--base-dir', await base(), '--evidence', evidencePath, '--out', out];
    const result = await cli(args, scratch, { ...BARE_ENV, GITHUB_EVENT_PATH: eventPath });
    expect(result.code).toBe(0);
    expect(readApprovalsReport(JSON.parse(await readFile(out, 'utf8')))?.approved).toEqual([DEPS]);
  });

  it('sort 0 avec approval-evidence-invalid quand le fichier de preuves manque', async () => {
    const out = join(scratch, 'approvals.json');
    const absent = join(scratch, 'absent.json');
    const result = await cli([...given(await base(), absent), '--out', out], scratch);
    expect(result.code).toBe(0);
    const report = readApprovalsReport(JSON.parse(await readFile(out, 'utf8')));
    expect(report?.rejected.map((r) => r.reason)).toEqual(
      APPROVAL_KINDS.map(() => 'approval-evidence-invalid'),
    );
  });

  it('porte bootstrap: true avec --bootstrap', async () => {
    const labelEvents = [labelEvent({ actor: 'o' })];
    const { evidencePath, out } = await files(evidence({ labelEvents }));
    const result = await cli(
      [...given(scratch, evidencePath), ...['--bootstrap', '--out', out]],
      scratch,
    );
    expect(result.code).toBe(0);
    expect(readApprovalsReport(JSON.parse(await readFile(out, 'utf8')))).toMatchObject({
      bootstrap: true,
      approved: [DEPS],
    });
  });
});
