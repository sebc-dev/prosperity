import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { collectApprovalEvidence, parseApprovalEvidence } from './approval-evidence.ts';
import { EXPECTED, fakeGh, IDS, SHA } from './approval-evidence-fixtures.ts';
import { runTool } from './tools.ts';

const CLI = resolve(import.meta.dirname, 'approval-evidence.ts');
const SECRETS = {
  GH_TOKEN: 'jeton-du-workflow',
  GATE_STATUS_TOKEN: 'jeton-app',
  GITHUB_TOKEN: 'autre',
};
let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'approval-evidence-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

describe('collectApprovalEvidence', () => {
  it('lance exactement trois lectures GET, sans option d écriture, et rend la forme normalisée', async () => {
    const env = { ...(await fakeGh(scratch)), ...SECRETS };
    const evidence = await collectApprovalEvidence({ ...IDS, env });
    expect(evidence).toEqual(EXPECTED);
    const calls = (await readFile(join(scratch, 'calls.log'), 'utf8'))
      .split('--END--\n')
      .filter((call) => call !== '')
      .map((call) => call.split('\n').filter((arg) => arg !== ''));
    expect(calls).toEqual([
      ['api', 'repos/o/r/pulls/300'],
      ['api', '--paginate', '--slurp', 'repos/o/r/issues/300/events'],
      [
        ...['api', '--paginate', '--slurp'],
        `repos/o/r/actions/runs?head_sha=${SHA}&event=pull_request&per_page=100`,
      ],
    ]);
    const writing = /^(-X|--method|-f|-F|--field|--raw-field|--input)$/;
    expect(calls.flat().filter((arg) => writing.test(arg))).toEqual([]);
  });

  it('transmet GH_TOKEN à gh mais retire GATE_STATUS_TOKEN et GITHUB_TOKEN', async () => {
    const env = { ...(await fakeGh(scratch)), ...SECRETS };
    await collectApprovalEvidence({ ...IDS, env });
    const seen = (await readFile(join(scratch, 'env.log'), 'utf8')).trim().split('\n');
    expect(seen).toEqual(Array<string>(3).fill('jeton-du-workflow|unset|unset'));
  });

  it('lève quand gh sort en erreur', async () => {
    const env = { ...(await fakeGh(scratch)), FAKE_EXIT: '1' };
    await expect(collectApprovalEvidence({ ...IDS, env })).rejects.toThrow('gh');
  });

  it.each([
    ['une sortie qui n est pas du JSON', { pull: 'pas du json' }],
    ['une réponse hors forme', { pull: { number: 300 } }],
  ])('lève sur %s', async (_name, fixtures) => {
    const env = await fakeGh(scratch, fixtures);
    await expect(collectApprovalEvidence({ ...IDS, env })).rejects.toThrow('réponse');
  });

  it.each([
    ['un dépôt invalide', { repository: 'pas un dépôt' }],
    ['un numéro nul', { pr: 0 }],
    ['un numéro non entier', { pr: 1.5 }],
    ['un SHA de 39 caractères', { headSha: SHA.slice(1) }],
  ])('refuse %s avant tout appel', async (_name, over) => {
    const env = await fakeGh(scratch);
    await expect(collectApprovalEvidence({ ...IDS, ...over, env })).rejects.toThrow('invalide');
    await expect(readFile(join(scratch, 'calls.log'), 'utf8')).rejects.toThrow('ENOENT');
  });
});

describe('quality/approval-evidence.ts en ligne de commande', () => {
  async function cli(args: string[], env: NodeJS.ProcessEnv) {
    return runTool({
      command: process.execPath,
      args: [CLI, ...args],
      cwd: scratch,
      env,
      timeoutMs: 60_000,
    });
  }
  const full = (out: string) => [
    ...['--repo', 'o/r', '--pr', '300', '--head-sha', SHA],
    ...['--out', out],
  ];

  it.each([
    ['sans --out', ['--repo', 'o/r', '--pr', '300', '--head-sha', SHA]],
    [
      'avec un numéro invalide',
      ['--repo', 'o/r', '--pr', 'x', '--head-sha', SHA, '--out', 'e.json'],
    ],
    [
      'avec un SHA invalide',
      ['--repo', 'o/r', '--pr', '300', '--head-sha', 'abc', '--out', 'e.json'],
    ],
    ['avec une option inconnue', ['--repo', 'o/r', '--zzz']],
  ])('sort 2 et n écrit rien %s', async (_name, args) => {
    const run = await cli(args, await fakeGh(scratch));
    expect(run.code).toBe(2);
  });

  it('sort 1 sans écrire de fichier quand gh échoue', async () => {
    const out = join(scratch, 'evidence.json');
    const run = await cli(full(out), { ...(await fakeGh(scratch)), FAKE_EXIT: '1' });
    expect(run.code).toBe(1);
    await expect(readFile(out, 'utf8')).rejects.toThrow('ENOENT');
  });

  it('sort 0 et écrit un fichier que parseApprovalEvidence relit', async () => {
    const out = join(scratch, 'evidence.json');
    const run = await cli(full(out), await fakeGh(scratch));
    expect({ code: run.code, stderr: run.stderr }).toEqual({ code: 0, stderr: '' });
    expect(parseApprovalEvidence(JSON.parse(await readFile(out, 'utf8')))).toEqual(EXPECTED);
  });
});
