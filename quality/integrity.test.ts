import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { evaluateIntegrity } from './integrity.ts';
import { isProtected, loadProtectedPaths } from './protected-paths.ts';
import thresholds from './thresholds.json' with { type: 'json' };
import { runTool } from './tools.ts';

const ROOT = resolve(import.meta.dirname, '..');
const APPROVED = ['gate-change-approved'];
const PNPM = await readFile(join(ROOT, 'pnpm-workspace.yaml'), 'utf8');
const BASE: Record<string, string | null> = {
  'quality/thresholds.json': `${JSON.stringify(thresholds, null, 2)}\n`,
  'quality/protected-paths.json': await readFile(
    join(ROOT, 'quality/protected-paths.json'),
    'utf8',
  ),
  'quality/baseline.json': '{"escapeHatches":{"vi.mock(":0,"as any":0}}\n',
  'pnpm-workspace.yaml': PNPM,
  'src/a.test.ts': 'expect(a).toBe(1);\nexpect.soft(b).toBe(2);\n',
  'test/x.int.test.ts': 'expect(x).toBe(1);\n',
  'db/migrations/0001_foundation.sql': 'SELECT 1;\n',
  'src/a.ts': 'export const a = 1;\n',
};

const dirs: string[] = [];

async function makeDir(files: Record<string, string | null>): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'gate-integrity-'));
  dirs.push(dir);
  for (const [path, content] of Object.entries(files)) {
    if (content !== null) {
      await mkdir(dirname(join(dir, path)), { recursive: true });
      await writeFile(join(dir, path), content);
    }
  }
  await runTool({ command: 'git', args: ['init', '-q'], cwd: dir });
  return dir;
}

afterAll(async () => {
  await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })));
});

async function judge(
  over: Record<string, string | null>,
  kinds: string[] = [],
  bootstrap = false,
): ReturnType<typeof evaluateIntegrity> {
  const baseDir = await makeDir(BASE);
  const headDir = await makeDir({ ...BASE, ...over });
  return evaluateIntegrity({ baseDir, headDir, approvedKinds: kinds, bootstrap });
}

const rules = (issues: readonly { rule: string }[]): string[] =>
  [...new Set(issues.map((issue) => issue.rule))].sort((a, b) => a.localeCompare(b));

function withThresholds(edit: (copy: typeof thresholds) => void): Record<string, string> {
  const copy = structuredClone(thresholds);
  edit(copy);
  return { 'quality/thresholds.json': `${JSON.stringify(copy, null, 2)}\n` };
}

describe('evaluateIntegrity : base et tête', () => {
  it('passe sans issue quand la tête égale la base', async () => {
    const result = await judge({});
    expect(result).toMatchObject({ check: 'integrity', tool: 'integrity', status: 'passed' });
    expect(result.issues).toEqual([]);
  });

  it('refuse un seuil abaissé sans approbation, et le liste avec approbation', async () => {
    const over = withThresholds((copy) => {
      copy.coverage.global.lines = 80;
    });
    const refused = await judge(over);
    expect(refused.status).toBe('failed');
    expect(rules(refused.issues)).toEqual(['protected-path-changed', 'threshold-lowered']);
    const approved = await judge(over, APPROVED);
    expect(approved.status).toBe('passed');
    expect(rules(approved.issues)).toEqual(['protected-path-changed', 'threshold-lowered']);
  });

  it('ne retient que le chemin protégé pour un seuil rendu plus strict', async () => {
    const result = await judge(
      withThresholds((copy) => {
        copy.lint.maxParams = 3;
      }),
    );
    expect(rules(result.issues)).toEqual(['protected-path-changed']);
  });

  it('refuse une clé de seuil supprimée', async () => {
    const result = await judge(
      withThresholds((copy) => {
        Reflect.deleteProperty(copy.mutation, 'break');
      }),
    );
    expect(rules(result.issues)).toContain('threshold-lowered');
  });

  it("n'accepte pas une autre sorte d'approbation", async () => {
    const over = { 'quality/baseline.json': '{"escapeHatches":{"vi.mock(":1,"as any":0}}\n' };
    expect((await judge(over, ['deps-approved'])).status).toBe('failed');
  });

  it.each(['.gitleaksignore', '.semgrepignore', '.npmrc', 'mise.local.toml'])(
    'refuse un %s ajouté à la tête',
    async (file) => {
      const result = await judge({ [file]: 'x\n' });
      expect(result.status).toBe('failed');
      expect(result.issues).toEqual([
        expect.objectContaining({ rule: 'protected-path-changed', file }),
      ]);
    },
  );

  it('lit la liste des chemins protégés dans la base, pas dans la tête', async () => {
    const result = await judge({
      'quality/protected-paths.json': '{"paths":[],"agentExempt":[]}\n',
      '.npmrc': 'x\n',
    });
    const files = result.issues.map((issue) => issue.file);
    expect(files).toEqual(expect.arrayContaining(['.npmrc', 'quality/protected-paths.json']));
  });
});

describe('evaluateIntegrity : assertions, cliquet, migrations', () => {
  it("signale un fichier de test dont le nombre d'expect baisse", async () => {
    const result = await judge({ 'src/a.test.ts': 'expect(a).toBe(1);\n' });
    expect(result.issues).toEqual([
      expect.objectContaining({ rule: 'assertion-removed', file: 'src/a.test.ts' }),
    ]);
    expect(result.issues[0]?.message).toContain('2');
  });

  it('signale un fichier de test supprimé', async () => {
    const result = await judge({ 'test/x.int.test.ts': null });
    expect(rules(result.issues)).toEqual(['assertion-removed']);
  });

  it('ne signale pas un test qui gagne des assertions', async () => {
    const result = await judge({ 'src/a.test.ts': 'expect(a).toBe(1);\n'.repeat(5) });
    expect(result.issues).toEqual([]);
  });

  it('signale une hausse de la base du compteur d’échappatoires', async () => {
    const result = await judge({ 'quality/baseline.json': '{"escapeHatches":{"vi.mock(":1}}\n' });
    expect(rules(result.issues)).toEqual([
      'escape-hatch-baseline-raised',
      'protected-path-changed',
    ]);
  });

  it('ne signale pas une baisse de la base', async () => {
    const result = await judge({ 'quality/baseline.json': '{"escapeHatches":{"as any":0}}\n' });
    expect(rules(result.issues)).toEqual(['protected-path-changed']);
  });

  it('signale une migration existante modifiée ou supprimée', async () => {
    const modified = await judge({ 'db/migrations/0001_foundation.sql': 'SELECT 2;\n' });
    expect(rules(modified.issues)).toEqual(['migration-modified']);
    const removed = await judge({ 'db/migrations/0001_foundation.sql': null });
    expect(rules(removed.issues)).toEqual(['migration-modified']);
  });

  it('accepte une nouvelle migration', async () => {
    const result = await judge({ 'db/migrations/0002_next.sql': 'SELECT 3;\n' });
    expect(result.issues).toEqual([]);
  });
});

const WEAKENED: readonly (readonly [string, string])[] = [
  ['minimumReleaseAge baissé', PNPM.replace('minimumReleaseAge: 10080', 'minimumReleaseAge: 1440')],
  ['minimumReleaseAgeStrict à false', PNPM.replace('AgeStrict: true', 'AgeStrict: false')],
  ['liste d’exclusion d’âge ajoutée', `${PNPM}minimumReleaseAgeExclude:\n  - left-pad\n`],
  ['allowBuilds passé à true', PNPM.replace('esbuild: false', 'esbuild: true')],
  [
    'blockExoticSubdeps à false',
    PNPM.replace('blockExoticSubdeps: true', 'blockExoticSubdeps: false'),
  ],
  ['trustPolicy changée', PNPM.replace('trustPolicy: no-downgrade', 'trustPolicy: off')],
];

describe('evaluateIntegrity : politique pnpm', () => {
  it.each(WEAKENED)('refuse : %s', async (_title, yaml) => {
    const result = await judge({ 'pnpm-workspace.yaml': yaml });
    expect(rules(result.issues)).toEqual([
      'protected-path-changed',
      'supply-chain-policy-weakened',
    ]);
  });

  it('accepte un âge minimal relevé et un commentaire ajouté', async () => {
    const stricter = PNPM.replace(
      'minimumReleaseAge: 10080',
      '# plus strict\nminimumReleaseAge: 20160',
    );
    const result = await judge({ 'pnpm-workspace.yaml': stricter });
    expect(rules(result.issues)).toEqual(['protected-path-changed']);
  });
});

describe('evaluateIntegrity : amorçage', () => {
  it('exige l’approbation quand la base ne contient pas quality/thresholds.json', async () => {
    const baseDir = await makeDir({ ...BASE, 'quality/thresholds.json': null });
    const headDir = await makeDir(BASE);
    const input = { baseDir, headDir, bootstrap: false };
    const refused = await evaluateIntegrity({ ...input, approvedKinds: [] });
    expect(refused.status).toBe('failed');
    expect(rules(refused.issues)).toContain('bootstrap');
    expect((await evaluateIntegrity({ ...input, approvedKinds: APPROVED })).status).toBe('passed');
  });

  it('exige l’approbation avec le drapeau d’amorçage', async () => {
    const result = await judge({}, [], true);
    expect(rules(result.issues)).toEqual(['bootstrap']);
    expect(result.status).toBe('failed');
  });
});

const PROTECTED = [
  '.gitleaksignore',
  '.semgrepignore',
  '.semgrep.yml',
  '.npmrc',
  'ui/.npmrc',
  '.pnpmfile.cjs',
  'mise.local.toml',
  'mise.ci.toml',
  '.mise.toml',
  '.mise/config.toml',
  '.mise/locks/pipx-semgrep/1.186.0',
  '.config/mise/config.toml',
  '.tool-versions',
  '.nvmrc',
  '.gitignore',
  'src/.gitignore',
  '.gitattributes',
  'lefthook-local.yml',
  '.lefthook.yml',
  'knip.config.ts',
  'stryker.conf.json',
  '.dependency-cruiser-known-violations.json',
  'biome.jsonc',
  'zizmor.yml',
  '.hadolint.yaml',
  'osv-scanner.toml',
  'test/setup/fast-check.ts',
  'test/global-setup.ts',
  'test/db.ts',
  'test/meta.int.test.ts',
  '.claude/settings.json',
  '.claude/settings.local.json',
  '.claude/CLAUDE.md',
  'quality/run.ts',
  '.github/workflows/quality.yml',
  'eslint.config.mjs',
];
const FREE = [
  'src/shared/money/money.ts',
  'test/foundation.int.test.ts',
  '.claude/agents/x.md',
  '.claude/hooks/gsd-x.js',
  '.claude/commands/x.md',
];

describe('isProtected sur la liste réelle', () => {
  it.each(PROTECTED)('protège %s', async (file) => {
    const { paths } = await loadProtectedPaths(ROOT);
    expect(isProtected(file, paths)).toBe(true);
  });

  it.each(FREE)('laisse %s libre (D-05)', async (file) => {
    const { paths } = await loadProtectedPaths(ROOT);
    expect(isProtected(file, paths)).toBe(false);
  });

  it('ne protège pas .claude/ en bloc et garde agentExempt vide', async () => {
    const loaded = await loadProtectedPaths(ROOT);
    expect(loaded.paths).not.toContain('.claude/**');
    expect(loaded.agentExempt).toEqual([]);
  });
});

describe('CLI de quality/integrity.ts', () => {
  async function cli(args: string[]): Promise<{ code: number; out: string }> {
    const baseDir = await makeDir(BASE);
    const headDir = await makeDir({ ...BASE, 'src/a.test.ts': 'expect(a).toBe(1);\n' });
    const out = join(await makeDir({}), 'integrity.json');
    const run = await runTool({
      command: process.execPath,
      args: [
        'quality/integrity.ts',
        '--base-dir',
        baseDir,
        '--head-dir',
        headDir,
        '--out',
        out,
        ...args,
      ],
      cwd: ROOT,
    });
    const text = await readFile(out, 'utf8').catch(() => '');
    return { code: run.code, out: text };
  }

  it('sort en 1 et écrit le résultat sur un écart non approuvé', async () => {
    const { code, out } = await cli([]);
    expect(code).toBe(1);
    expect(JSON.parse(out)).toMatchObject({ check: 'integrity', status: 'failed' });
  });

  it('sort en 0 avec --approved', async () => {
    expect((await cli(['--approved', 'deps-approved,gate-change-approved'])).code).toBe(0);
  });

  it('lit les sortes approuvées dans --approvals-report', async () => {
    const report = join(await makeDir({}), 'approvals.json');
    await writeFile(report, '{"approved":["gate-change-approved"],"rejected":[]}');
    expect((await cli(['--approvals-report', report])).code).toBe(0);
  });

  it('sort en 2 sans les dossiers à comparer', async () => {
    const run = await runTool({
      command: process.execPath,
      args: ['quality/integrity.ts'],
      cwd: ROOT,
    });
    expect(run.code).toBe(2);
  });
});
