import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { diffDependencies, evaluateDependencies, runDepsGuardCli } from './deps-guard.ts';
import type { DepChange, RegistryLookup } from './deps-guard.ts';
import { runTool } from './tools.ts';

const NOW = new Date('2026-11-21T00:00:00.000Z');
const DAY_MS = 86_400_000;
const OLD = '2015-01-01T00:00:00.000Z';

function pkg(extra: Record<string, unknown> = {}): string {
  return JSON.stringify({ name: 'x', devDependencies: { a: '1.0.0' }, ...extra });
}

const LOCK_BASE = `lockfileVersion: '9.0'

importers:

  .:
    devDependencies:
      a:
        specifier: 1.0.0
        version: 1.0.0

packages:

  a@1.0.0:
    resolution: {integrity: sha512-aaa}

  '@scope/b@2.0.0':
    resolution: {integrity: sha512-bbb}

snapshots:

  a@1.0.0: {}

  '@scope/b@2.0.0': {}
`;

function lockWith(...keys: string[]): string {
  const entries = keys.map((key) => `  ${key}:\n    resolution: {integrity: sha512-zzz}\n`);
  return `lockfileVersion: '9.0'\n\npackages:\n\n${entries.join('\n')}\nsnapshots:\n\n  a@1.0.0(peer@1.0.0): {}\n`;
}

const base = { packageJson: pkg(), lockfile: LOCK_BASE };

describe('diffDependencies', () => {
  it('ne signale rien quand package.json et lockfile sont identiques', () => {
    expect(diffDependencies(base, base)).toEqual([]);
  });

  it('signale une devDependency ajoutée avec sa version', () => {
    const head = { ...base, packageJson: pkg({ devDependencies: { a: '1.0.0', c: '3.0.0' } }) };
    expect(diffDependencies(base, head)).toEqual([
      { name: 'c', to: '3.0.0', kind: 'dependency-added' },
    ]);
  });

  it('signale une version modifiée avec l ancienne et la nouvelle', () => {
    const head = { ...base, packageJson: pkg({ devDependencies: { a: '1.1.0' } }) };
    expect(diffDependencies(base, head)).toEqual([
      { name: 'a', from: '1.0.0', to: '1.1.0', kind: 'dependency-changed' },
    ]);
  });

  it('signale une dépendance retirée', () => {
    const head = { ...base, packageJson: pkg({ devDependencies: {} }) };
    expect(diffDependencies(base, head)).toEqual([
      { name: 'a', from: '1.0.0', kind: 'dependency-removed' },
    ]);
  });

  it('lit dependencies, optionalDependencies et peerDependencies', () => {
    const head = {
      ...base,
      packageJson: pkg({
        dependencies: { d: '1.0.0' },
        optionalDependencies: { o: '1.0.0' },
        peerDependencies: { p: '1.0.0' },
      }),
    };
    expect(diffDependencies(base, head).map((change) => change.name)).toEqual(['d', 'o', 'p']);
  });

  it('lit pnpm.overrides et en retient le paquet visé', () => {
    const head = {
      ...base,
      packageJson: pkg({ pnpm: { overrides: { 'foo@<2': '2.0.0', 'x>@scope/y': '1.0.0' } } }),
    };
    expect(diffDependencies(base, head).map((change) => change.name)).toEqual([
      'foo',
      '@scope/y',
    ]);
  });

  it('signale un nouveau nom de paquet du lockfile comme transitive-added', () => {
    const head = { ...base, lockfile: lockWith('a@1.0.0', "'@scope/b@2.0.0'", 'new-pkg@0.1.0') };
    expect(diffDependencies(base, head)).toEqual([
      { name: 'new-pkg', to: '0.1.0', kind: 'transitive-added' },
    ]);
  });

  it('signale une nouvelle version d un paquet transitif déjà présent', () => {
    const head = { ...base, lockfile: lockWith('a@1.0.0', "'@scope/b@2.0.0'", "'@scope/b@2.1.0'") };
    expect(diffDependencies(base, head)).toEqual([
      { name: '@scope/b', from: '2.0.0', to: '2.1.0', kind: 'dependency-changed' },
    ]);
  });

  it('ne double pas le signalement d une dépendance directe aussi présente au lockfile', () => {
    const head = {
      packageJson: pkg({ devDependencies: { a: '1.0.0', c: '3.0.0' } }),
      lockfile: lockWith('a@1.0.0', "'@scope/b@2.0.0'", 'c@3.0.0'),
    };
    expect(diffDependencies(base, head)).toEqual([
      { name: 'c', to: '3.0.0', kind: 'dependency-added' },
    ]);
  });

  it('lit les sections packages de chaque document YAML du lockfile', () => {
    const doc = "---\nlockfileVersion: '9.0'\n\npackages:\n\n  '@pnpm/exe@1.0.0':\n    resolution: {}\n";
    const head = { ...base, lockfile: `${doc}---\n${LOCK_BASE}` };
    expect(diffDependencies(base, head)).toEqual([
      { name: '@pnpm/exe', to: '1.0.0', kind: 'transitive-added' },
    ]);
  });

  it('traite une base vide comme un amorçage : tout est ajouté', () => {
    const empty = { packageJson: '{}', lockfile: '' };
    const kinds = diffDependencies(empty, base).map((change) => change.kind);
    expect(kinds).toEqual(['dependency-added', 'transitive-added']);
  });
});

const lookupOld: RegistryLookup = () => Promise.resolve({ exists: true, createdAt: OLD });

function opts(over: Partial<Parameters<typeof evaluateDependencies>[1]> = {}) {
  return { approvedKinds: ['deps-approved'], minAgeDays: 30, now: NOW, lookup: lookupOld, ...over };
}

const added: DepChange = { name: 'c', to: '3.0.0', kind: 'dependency-added' };

describe('evaluateDependencies : approbation', () => {
  it('passe sans changement et porte l identité du check', async () => {
    const result = await evaluateDependencies([], opts());
    expect(result).toMatchObject({
      check: 'deps',
      tool: 'deps-guard',
      severity: 'blocking',
      status: 'passed',
      passed: true,
      issues: [],
    });
  });

  it.each(['dependency-added', 'dependency-changed', 'transitive-added'] as const)(
    'refuse %s sans deps-approved',
    async (kind) => {
      const result = await evaluateDependencies([{ ...added, kind }], opts({ approvedKinds: [] }));
      expect(result.status).toBe('failed');
      expect(result.issues.map((issue) => issue.rule)).toEqual([kind]);
    },
  );

  it('accepte un ajout approuvé dont le paquet est ancien', async () => {
    const result = await evaluateDependencies([added], opts());
    expect(result.status).toBe('passed');
  });

  it('refuse une approbation qui ne porte pas la sorte deps-approved', async () => {
    const result = await evaluateDependencies([added], opts({ approvedKinds: ['gate-change-approved'] }));
    expect(result.status).toBe('failed');
  });

  it('ne demande aucune approbation pour un retrait et le note', async () => {
    const removed: DepChange = { name: 'a', from: '1.0.0', kind: 'dependency-removed' };
    const result = await evaluateDependencies([removed], opts({ approvedKinds: [] }));
    expect(result.status).toBe('passed');
    expect(result.note).toContain('dependency-removed');
  });
});

describe('evaluateDependencies : registre', () => {
  it('refuse un paquet absent du registre même approuvé', async () => {
    const lookup: RegistryLookup = () => Promise.resolve({ exists: false });
    const result = await evaluateDependencies([added], opts({ lookup }));
    expect(result.issues.map((issue) => issue.rule)).toEqual(['dependency-not-on-registry']);
  });

  it('refuse un paquet créé il y a 29 jours même approuvé', async () => {
    const createdAt = new Date(NOW.getTime() - 29 * DAY_MS).toISOString();
    const lookup: RegistryLookup = () => Promise.resolve({ exists: true, createdAt });
    const result = await evaluateDependencies([added], opts({ lookup }));
    expect(result.issues.map((issue) => issue.rule)).toEqual(['dependency-too-young']);
  });

  it('accepte un paquet créé il y a exactement 30 jours', async () => {
    const createdAt = new Date(NOW.getTime() - 30 * DAY_MS).toISOString();
    const lookup: RegistryLookup = () => Promise.resolve({ exists: true, createdAt });
    const result = await evaluateDependencies([added], opts({ lookup }));
    expect(result.status).toBe('passed');
  });

  it('échoue fermé quand la recherche lève ou que la date est illisible', async () => {
    const throwing: RegistryLookup = () => Promise.reject(new Error('réseau coupé'));
    const noDate: RegistryLookup = () => Promise.resolve({ exists: true, createdAt: 'hier' });
    for (const lookup of [throwing, noDate]) {
      const result = await evaluateDependencies([added], opts({ lookup }));
      expect(result.issues.map((issue) => issue.rule)).toEqual(['registry-lookup-failed']);
    }
  });

  it('ne cherche au registre que les paquets nouveaux, une fois chacun', async () => {
    const seen: string[] = [];
    const lookup: RegistryLookup = (name) => {
      seen.push(name);
      return Promise.resolve({ exists: true, createdAt: OLD });
    };
    const changes: DepChange[] = [
      added,
      { ...added, kind: 'transitive-added' },
      { name: 'a', from: '1.0.0', to: '1.1.0', kind: 'dependency-changed' },
    ];
    await evaluateDependencies(changes, opts({ lookup }));
    expect(seen).toEqual(['c']);
  });
});

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'deps-guard-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

async function tree(name: string, packageJson: string, lockfile: string): Promise<string> {
  const dir = join(scratch, name);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, 'package.json'), packageJson);
  await writeFile(join(dir, 'pnpm-lock.yaml'), lockfile);
  return dir;
}

async function report(name: string, content: string): Promise<string> {
  const path = join(scratch, name);
  await writeFile(path, content);
  return path;
}

const io = { lookup: lookupOld, now: NOW, minAgeDays: 30 };

describe('runDepsGuardCli', () => {
  async function args(extra: string[]): Promise<string[]> {
    const baseDir = await tree('base', pkg(), LOCK_BASE);
    const headDir = await tree(
      'head',
      pkg({ devDependencies: { a: '1.0.0', c: '3.0.0' } }),
      LOCK_BASE,
    );
    return ['--base-dir', baseDir, '--head-dir', headDir, '--out', join(scratch, 'deps.json'), ...extra];
  }

  it('sort 0 et écrit un rapport passed quand le rapport d approbations porte deps-approved', async () => {
    const approvals = await report('approvals.json', JSON.stringify({ approved: ['deps-approved'] }));
    expect(await runDepsGuardCli(await args(['--approvals-report', approvals]), io)).toBe(0);
    const written: unknown = JSON.parse(await readFile(join(scratch, 'deps.json'), 'utf8'));
    expect(written).toMatchObject({ check: 'deps', status: 'passed' });
  });

  it('sort 1 avec la règle dependency-added quand rien n est approuvé', async () => {
    expect(await runDepsGuardCli(await args(['--approved', 'gate-change-approved']), io)).toBe(1);
    const written = await readFile(join(scratch, 'deps.json'), 'utf8');
    expect(written).toContain('"rule": "dependency-added"');
  });

  it('accepte --approved avec deps-approved', async () => {
    expect(await runDepsGuardCli(await args(['--approved', 'deps-approved']), io)).toBe(0);
  });

  it('sort 2 sans rapport quand le rapport d approbations est absent', async () => {
    const missing = join(scratch, 'absent.json');
    expect(await runDepsGuardCli(await args(['--approvals-report', missing]), io)).toBe(2);
    await expect(stat(join(scratch, 'deps.json'))).rejects.toThrow('ENOENT');
  });

  it.each(['pas du json', '{"approved":"deps-approved"}', '{"approved":[1]}', '[]'])(
    'sort 2 sans rapport quand le rapport vaut %s',
    async (content) => {
      const approvals = await report('approvals.json', content);
      expect(await runDepsGuardCli(await args(['--approvals-report', approvals]), io)).toBe(2);
      await expect(stat(join(scratch, 'deps.json'))).rejects.toThrow('ENOENT');
    },
  );

  it('sort 2 quand --approved et --approvals-report sont donnés ensemble', async () => {
    const approvals = await report('approvals.json', JSON.stringify({ approved: [] }));
    const argv = await args(['--approved', 'deps-approved', '--approvals-report', approvals]);
    expect(await runDepsGuardCli(argv, io)).toBe(2);
  });

  it('sort 2 quand un dossier de base ne contient pas package.json', async () => {
    const argv = ['--base-dir', join(scratch, 'vide'), '--head-dir', scratch, '--out', join(scratch, 'o.json')];
    expect(await runDepsGuardCli(argv, io)).toBe(2);
  });

  it('en amorçage, la base vide fait de chaque paquet un ajout', async () => {
    const argv = [...(await args(['--bootstrap'])), '--approved', 'deps-approved'];
    expect(await runDepsGuardCli(argv, io)).toBe(0);
  });

  it('refuse un amorçage sans approbation avec dependency-added', async () => {
    expect(await runDepsGuardCli(await args(['--bootstrap']), io)).toBe(1);
  });
});

describe('processus quality/deps-guard.ts', () => {
  it('sort 2 sans rien écrire quand le rapport d approbations est absent', async () => {
    const dir = await tree('proc', pkg(), LOCK_BASE);
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
