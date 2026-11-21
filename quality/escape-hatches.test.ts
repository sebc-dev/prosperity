import { describe, expect, it } from 'vitest';
import {
  compareToBaseline,
  countEscapeHatches,
  ESCAPE_PATTERNS,
  isCountedPath,
} from './escape-hatches.ts';

// Un exemple minimal par motif : la ligne contient le motif et aucun autre.
const SAMPLES: readonly (readonly [string, string])[] = [
  ['@ts-ignore', '// @ts-ignore'],
  ['@ts-expect-error', '// @ts-expect-error: test'],
  ['@ts-nocheck', '// @ts-nocheck'],
  ['eslint-disable', '/* eslint-disable no-console */'],
  ['biome-ignore', '// biome-ignore lint/style: test'],
  ['as any', 'const a = b as any;'],
  ['as unknown as', 'const a = b as unknown as string;'],
  ['!.', 'const a = b!.c;'],
  ['.skip(', "it.skip('x', () => {});"],
  ['.todo(', "it.todo('x');"],
  ['vi.mock(', "vi.mock('x');"],
  ['Stryker disable', '// Stryker disable next-line all'],
  ['Stryker restore', '// Stryker restore all'],
  ['v8 ignore', '/* v8 ignore next */'],
  ['istanbul ignore', '/* istanbul ignore else */'],
  ['c8 ignore', '/* c8 ignore start */'],
  ['nosem', '// nosemgrep: prosperity.sql-concatenation'],
  ['gitleaks:allow', '// gitleaks:allow'],
  ['jscpd:ignore', '// jscpd:ignore-start'],
  ['@public', ' * @public'],
  ['@beta', ' * @beta'],
  ['@alias', ' * @alias'],
];

function total(counts: ReturnType<typeof countEscapeHatches>): number {
  return Object.values(counts).reduce((sum, entry) => sum + entry.count, 0);
}

describe('ESCAPE_PATTERNS', () => {
  it('liste les 22 motifs dans l’ordre du plan', () => {
    expect(ESCAPE_PATTERNS).toEqual(SAMPLES.map(([pattern]) => pattern));
  });
});

describe('countEscapeHatches : un cas par motif', () => {
  it.each(SAMPLES)('compte « %s » une fois, avec sa localisation', (pattern, line) => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: `export {};\n${line}\n` }]);
    expect(counts[pattern]).toEqual({ count: 1, locations: ['src/a.ts:2'] });
    expect(total(counts)).toBe(1);
  });

  it.each(['test/b.ts', 'vitest.config.ts', 'eslint.config.mjs', 'stryker.config.cjs'])(
    'compte aussi dans %s',
    (path) => {
      const counts = countEscapeHatches([{ path, content: '// @ts-ignore\n' }]);
      expect(counts['@ts-ignore']).toEqual({ count: 1, locations: [`${path}:1`] });
    },
  );

  it('renvoie une entrée à zéro pour chaque motif absent', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: 'export const a = 1;\n' }]);
    expect(Object.keys(counts)).toEqual([...ESCAPE_PATTERNS]);
    expect(total(counts)).toBe(0);
    expect(counts['vi.mock(']).toEqual({ count: 0, locations: [] });
  });

  it('compte chaque occurrence d’une même ligne', () => {
    const counts = countEscapeHatches([
      { path: 'src/a.ts', content: 'const a = (b as any) as any;\n' },
    ]);
    expect(counts['as any']).toEqual({ count: 2, locations: ['src/a.ts:1', 'src/a.ts:1'] });
  });

  it('ne confond pas un mot qui finit par le motif avec le motif', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '// has any value\n' }]);
    expect(counts['as any']).toEqual({ count: 0, locations: [] });
  });
});

describe('countEscapeHatches : casse et espacement', () => {
  it('compte « V8   Ignore » sous la forme canonique « v8 ignore »', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '/*  V8   Ignore next */\n' }]);
    expect(counts['v8 ignore']).toEqual({ count: 1, locations: ['src/a.ts:1'] });
  });

  it('compte « stryker  DISABLE » sous « Stryker disable »', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '// stryker  DISABLE all\n' }]);
    expect(counts['Stryker disable']).toEqual({ count: 1, locations: ['src/a.ts:1'] });
  });

  it('compte « AS\tUNKNOWN   AS » sous « as unknown as »', () => {
    const counts = countEscapeHatches([
      { path: 'src/a.ts', content: 'x = y AS\tUNKNOWN   AS z;\n' },
    ]);
    expect(counts['as unknown as']).toEqual({ count: 1, locations: ['src/a.ts:1'] });
  });

  it('compte « NOSEMGREP » sous « nosem »', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '// NoSemgrep: règle\n' }]);
    expect(counts['nosem']).toEqual({ count: 1, locations: ['src/a.ts:1'] });
  });
});

describe('countEscapeHatches : périmètre', () => {
  it.each(['quality/x.ts', 'semgrep/x.ts', '.planning/x.ts', '.claude/x.ts'])(
    'ne compte jamais %s (il cite les motifs)',
    (path) => {
      const counts = countEscapeHatches([{ path, content: '// @ts-ignore\nvi.mock("x");\n' }]);
      expect(total(counts)).toBe(0);
    },
  );

  it.each(['README.md', 'src/a.sql', 'docs/x.ts', 'ui/src/a.ts', 'package.json'])(
    'ne compte pas %s (hors src, test et configs racine)',
    (path) => {
      expect(isCountedPath(path)).toBe(false);
    },
  );

  it.each(['src/a/b.ts', 'src/c.tsx', 'test/setup/x.ts', 'a.mjs', 'b.cjs', 'c.ts', 'd.mts'])(
    'compte %s',
    (path) => {
      expect(isCountedPath(path)).toBe(true);
    },
  );
});

describe('compareToBaseline', () => {
  const zero = Object.fromEntries(ESCAPE_PATTERNS.map((pattern) => [pattern, 0]));

  it('ne signale rien quand les comptes égalent la base', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: 'export {};\n' }]);
    expect(compareToBaseline(counts, zero)).toEqual({ violations: [], notes: [] });
  });

  it('signale une violation par motif au-dessus de la base, avec ses localisations', () => {
    const counts = countEscapeHatches([
      { path: 'src/a.ts', content: '// @ts-expect-error: x\n' },
      { path: 'src/b.ts', content: '\n// @ts-expect-error: y\n' },
    ]);
    const { violations, notes } = compareToBaseline(counts, zero);
    expect(notes).toEqual([]);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.rule).toBe('@ts-expect-error');
    expect(violations[0]?.message).toContain('src/a.ts:1');
    expect(violations[0]?.message).toContain('src/b.ts:2');
    expect(violations[0]?.file).toBe('src/a.ts');
    expect(violations[0]?.line).toBe(1);
  });

  it('tolère un compte égal à une base non nulle', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '// @ts-ignore\n' }]);
    expect(compareToBaseline(counts, { ...zero, '@ts-ignore': 1 }).violations).toEqual([]);
  });

  it('note un cliquet abaissable quand le compte passe sous la base', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: 'export {};\n' }]);
    const { violations, notes } = compareToBaseline(counts, { ...zero, 'vi.mock(': 2 });
    expect(violations).toEqual([]);
    expect(notes).toEqual(['cliquet abaissable : « vi.mock( » compte 0, la base indique 2']);
  });

  it('traite un motif absent de la base comme un budget de zéro', () => {
    const counts = countEscapeHatches([{ path: 'src/a.ts', content: '// @beta\n' }]);
    expect(compareToBaseline(counts, {}).violations.map((issue) => issue.rule)).toEqual(['@beta']);
  });
});
