import type { Issue } from './gate-report.ts';

export const ESCAPE_PATTERNS: readonly string[] = [
  '@ts-ignore',
  '@ts-expect-error',
  '@ts-nocheck',
  'eslint-disable',
  'biome-ignore',
  'as any',
  'as unknown as',
  '!.',
  '.skip(',
  '.todo(',
  'vi.mock(',
  'Stryker disable',
  'Stryker restore',
  'v8 ignore',
  'istanbul ignore',
  'c8 ignore',
  'nosem',
  'gitleaks:allow',
  'jscpd:ignore',
  '@public',
  '@beta',
  '@alias',
];

export interface HatchCount {
  count: number;
  locations: string[];
}

export function isCountedPath(_path: string): boolean {
  return false;
}

export function countEscapeHatches(
  _files: readonly { path: string; content: string }[],
): Record<string, HatchCount> {
  return {};
}

export function compareToBaseline(
  _counts: Record<string, HatchCount>,
  _baseline: Record<string, number>,
): { violations: Issue[]; notes: string[] } {
  return { violations: [], notes: [] };
}
