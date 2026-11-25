import { readFile } from 'node:fs/promises';
import { matchesGlob } from 'node:path/posix';
import { join } from 'node:path';
import { isRecord } from './tools.ts';

export interface ProtectedPaths {
  paths: string[];
  agentExempt: string[];
}

function stringList(value: unknown, name: string): string[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error(`quality/protected-paths.json : « ${name} » doit être un tableau`);
  }
  const items: unknown[] = value;
  return items.map((item) => {
    if (typeof item !== 'string' || item === '') {
      throw new Error(`quality/protected-paths.json : « ${name} » ne contient que des chaînes`);
    }
    return item;
  });
}

/** Liste unique des chemins protégés, lue dans `<root>/quality/protected-paths.json`. */
export async function loadProtectedPaths(root: string): Promise<ProtectedPaths> {
  const parsed: unknown = JSON.parse(
    await readFile(join(root, 'quality', 'protected-paths.json'), 'utf8'),
  );
  if (!isRecord(parsed)) {
    throw new Error('quality/protected-paths.json : objet attendu');
  }
  return {
    paths: stringList(parsed['paths'], 'paths'),
    agentExempt: stringList(parsed['agentExempt'], 'agentExempt'),
  };
}

// `matchesGlob` ne fait jamais correspondre `*` ni `**` à un segment qui commence par un point
// (`quality/**` ne couvrait pas `quality/checks/.evil.ts`). Le point de tête de chaque segment est
// remplacé par ce marqueur, des deux côtés, avant une seconde comparaison : un fichier caché est
// protégé comme les autres, et un glob qui nomme un fichier caché (`.github/**`) reste exact.
const DOT_MARKER = '__dot__';

function revealDotSegments(value: string): string {
  return value
    .split('/')
    .map((segment) => (segment.startsWith('.') ? `${DOT_MARKER}${segment.slice(1)}` : segment))
    .join('/');
}

/** Vrai quand le chemin (relatif à la racine, séparateur `/`) correspond à un des globs. */
export function isProtected(relPath: string, globs: readonly string[]): boolean {
  const path = relPath.startsWith('./') ? relPath.slice(2) : relPath;
  const revealed = revealDotSegments(path);
  return globs.some(
    (glob) => matchesGlob(path, glob) || matchesGlob(revealed, revealDotSegments(glob)),
  );
}
