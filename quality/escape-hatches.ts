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

const CODE_EXTENSION = /\.(?:[cm]?[jt]s|[jt]sx)$/;
// Ces dossiers citent les motifs (le compteur, ses tests, les règles, les patchs d'auto-test).
const EXCLUDED_PREFIXES = ['quality/', 'semgrep/', '.planning/', '.claude/'];
const REGEX_SPECIALS = /[.*+?^${}()|[\]\\]/g;
const STARTS_WITH_WORD_CHAR = /^[a-z0-9]/;

function normalize(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Expression de recherche d'un motif sur une ligne normalisée. Un motif qui
 * commence par une lettre ne se cherche pas au milieu d'un mot (« has any »
 * n'est pas « as any »). Pas de borne finale : `nosem` doit couvrir `nosemgrep`.
 */
function patternRegex(pattern: string): RegExp {
  const body = normalize(pattern).replace(REGEX_SPECIALS, '\\$&');
  const boundary = STARTS_WITH_WORD_CHAR.test(normalize(pattern)) ? '(?<![a-z0-9_])' : '';
  return new RegExp(`${boundary}${body}`, 'g');
}

const MATCHERS: readonly (readonly [string, RegExp])[] = ESCAPE_PATTERNS.map((pattern) => [
  pattern,
  patternRegex(pattern),
]);

/** Fichiers comptés : `src/**`, `test/**` et les configurations à la racine. */
export function isCountedPath(path: string): boolean {
  if (EXCLUDED_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return false;
  }
  if (!CODE_EXTENSION.test(path)) {
    return false;
  }
  return path.startsWith('src/') || path.startsWith('test/') || !path.includes('/');
}

/** Motifs présents sur une ligne brute, avec le nombre d'occurrences de chacun. */
function hitsOnLine(raw: string): (readonly [string, number])[] {
  const line = normalize(raw);
  return MATCHERS.map(([pattern, regex]) => [pattern, [...line.matchAll(regex)].length] as const);
}

function addHits(
  counts: Record<string, HatchCount>,
  hits: readonly (readonly [string, number])[],
  location: string,
): void {
  for (const [pattern, n] of hits) {
    const entry = counts[pattern];
    for (let hit = 0; hit < n && entry !== undefined; hit += 1) {
      entry.count += 1;
      entry.locations.push(location);
    }
  }
}

export function countEscapeHatches(
  files: readonly { path: string; content: string }[],
): Record<string, HatchCount> {
  const counts: Record<string, HatchCount> = Object.fromEntries(
    ESCAPE_PATTERNS.map((pattern) => [pattern, { count: 0, locations: [] }]),
  );
  for (const file of files.filter((entry) => isCountedPath(entry.path))) {
    for (const [index, raw] of file.content.split(/\r?\n/).entries()) {
      addHits(counts, hitsOnLine(raw), `${file.path}:${String(index + 1)}`);
    }
  }
  return counts;
}

function violationFor(pattern: string, entry: HatchCount, allowed: number): Issue {
  const first = entry.locations[0] ?? '';
  const cut = first.lastIndexOf(':');
  return {
    rule: pattern,
    message: `${String(entry.count)} occurrence(s), la base en autorise ${String(allowed)} : ${entry.locations.join(', ')}`,
    ...(cut > 0
      ? { file: first.slice(0, cut), line: Number.parseInt(first.slice(cut + 1), 10) }
      : {}),
  };
}

/** Cliquet : au-dessus de la base = violation, en dessous = note (la base peut baisser). */
export function compareToBaseline(
  counts: Record<string, HatchCount>,
  baseline: Record<string, number>,
): { violations: Issue[]; notes: string[] } {
  const violations: Issue[] = [];
  const notes: string[] = [];
  for (const pattern of ESCAPE_PATTERNS) {
    const entry = counts[pattern] ?? { count: 0, locations: [] };
    const allowed = baseline[pattern] ?? 0;
    if (entry.count > allowed) {
      violations.push(violationFor(pattern, entry, allowed));
    } else if (entry.count < allowed) {
      notes.push(
        `cliquet abaissable : « ${pattern} » compte ${String(entry.count)}, la base indique ${String(allowed)}`,
      );
    }
  }
  return { violations, notes };
}
