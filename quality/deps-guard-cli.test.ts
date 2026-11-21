import { mkdir, mkdtemp, readFile, rm, stat, symlink, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { runDepsGuardCli } from './deps-guard.ts';
import type { RegistryLookup } from './deps-guard.ts';
import { runTool } from './tools.ts';

const LOCK =
  "lockfileVersion: '9.0'\n\npackages:\n\n  a@1.0.0:\n    resolution: {integrity: sha512-a}\n";
const lookup: RegistryLookup = () =>
  Promise.resolve({ exists: true, createdAt: '2015-01-01T00:00:00.000Z' });
const io = { lookup, now: new Date('2026-11-21T00:00:00.000Z'), minAgeDays: 30 };

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'deps-guard-cli-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

async function tree(name: string, deps: Record<string, string>): Promise<string> {
  const dir = join(scratch, name);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, 'package.json'), JSON.stringify({ devDependencies: deps }));
  await writeFile(join(dir, 'pnpm-lock.yaml'), LOCK);
  return dir;
}

async function report(content: string): Promise<string> {
  const path = join(scratch, 'approvals.json');
  await writeFile(path, content);
  return path;
}

/** Arguments d'un ajout de `c` : base avec `a`, tête avec `a` et `c`. */
async function args(extra: string[]): Promise<string[]> {
  const baseDir = await tree('base', { a: '1.0.0' });
  const headDir = await tree('head', { a: '1.0.0', c: '3.0.0' });
  return [
    '--base-dir',
    baseDir,
    '--head-dir',
    headDir,
    '--out',
    join(scratch, 'deps.json'),
    ...extra,
  ];
}

const outExists = (): Promise<unknown> => stat(join(scratch, 'deps.json'));

describe('runDepsGuardCli : approbation', () => {
  it('sort 0 et écrit un rapport passed quand le rapport porte deps-approved', async () => {
    const approvals = await report(JSON.stringify({ approved: ['deps-approved'] }));
    expect(await runDepsGuardCli(await args(['--approvals-report', approvals]), io)).toBe(0);
    const written: unknown = JSON.parse(await readFile(join(scratch, 'deps.json'), 'utf8'));
    expect(written).toMatchObject({ check: 'deps', status: 'passed' });
  });

  it('sort 1 avec la règle dependency-added quand rien n est approuvé', async () => {
    expect(await runDepsGuardCli(await args(['--approved', 'gate-change-approved']), io)).toBe(1);
    expect(await readFile(join(scratch, 'deps.json'), 'utf8')).toContain(
      '"rule": "dependency-added"',
    );
  });

  it('accepte --approved avec deps-approved', async () => {
    expect(await runDepsGuardCli(await args(['--approved', 'deps-approved']), io)).toBe(0);
  });

  it('en amorçage, la base vide fait de chaque paquet un ajout', async () => {
    const approved = [...(await args(['--bootstrap'])), '--approved', 'deps-approved'];
    expect(await runDepsGuardCli(approved, io)).toBe(0);
    expect(await runDepsGuardCli(await args(['--bootstrap']), io)).toBe(1);
  });
});

describe('runDepsGuardCli : échec fermé', () => {
  it('sort 2 sans rapport quand le rapport d approbations est absent', async () => {
    const missing = join(scratch, 'absent.json');
    expect(await runDepsGuardCli(await args(['--approvals-report', missing]), io)).toBe(2);
    await expect(outExists()).rejects.toThrow('ENOENT');
  });

  it.each(['pas du json', '{"approved":"deps-approved"}', '{"approved":[1]}', '[]'])(
    'sort 2 sans rapport quand le rapport vaut %s',
    async (content) => {
      const approvals = await report(content);
      expect(await runDepsGuardCli(await args(['--approvals-report', approvals]), io)).toBe(2);
      await expect(outExists()).rejects.toThrow('ENOENT');
    },
  );

  it('sort 2 quand --approved et --approvals-report sont donnés ensemble', async () => {
    const approvals = await report(JSON.stringify({ approved: [] }));
    const argv = await args(['--approved', 'deps-approved', '--approvals-report', approvals]);
    expect(await runDepsGuardCli(argv, io)).toBe(2);
  });

  it('sort 2 quand un dossier de base ne contient pas package.json', async () => {
    const out = join(scratch, 'o.json');
    const argv = ['--base-dir', join(scratch, 'vide'), '--head-dir', scratch, '--out', out];
    expect(await runDepsGuardCli(argv, io)).toBe(2);
  });
});

describe('runDepsGuardCli : tête non fiable', () => {
  it('sort 2 quand package.json de la tête est un lien symbolique', async () => {
    const argv = await args(['--approved', 'deps-approved']);
    const head = join(scratch, 'head');
    await unlink(join(head, 'package.json'));
    await symlink(join(scratch, 'base', 'package.json'), join(head, 'package.json'));
    expect(await runDepsGuardCli(argv, io)).toBe(2);
  });
});

describe('processus quality/deps-guard.ts', () => {
  it('sort 2 sans rien écrire quand le rapport d approbations est absent', async () => {
    const dir = await tree('proc', { a: '1.0.0' });
    const out = join(scratch, 'proc-out.json');
    const result = await runTool({
      command: process.execPath,
      args: [
        resolve(import.meta.dirname, 'deps-guard.ts'),
        ...['--base-dir', dir, '--head-dir', dir, '--approvals-report', join(scratch, 'x.json')],
        ...['--out', out],
      ],
      cwd: scratch,
      timeoutMs: 30_000,
    });
    expect(result.code).toBe(2);
    await expect(stat(out)).rejects.toThrow('ENOENT');
  });
});
