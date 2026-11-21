import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { isRecord, runTool } from './tools.ts';

// Accès aux deux côtés d'une comparaison d'intégrité (base et tête), partagé par
// `integrity.ts`. Même contrainte : uniquement `node:*` et des modules de `quality/`.

export interface Sides {
  baseDir: string;
  headDir: string;
  baseFiles: Set<string>;
  headFiles: Set<string>;
}

export const byName = (a: string, b: string): number => a.localeCompare(b);

/** Valeur lisible dans un message, sans passer par la sérialisation par défaut d'un objet. */
export function show(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

/** Fichiers suivis et non suivis non ignorés d'un dossier (le worktree d'auto-test compris). */
export async function listFiles(dir: string): Promise<Set<string>> {
  const listed = await runTool({
    command: 'git',
    args: ['-C', dir, 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    cwd: dir,
    timeoutMs: 60_000,
  });
  if (listed.code !== 0) {
    throw new Error(`git ls-files a échoué dans ${dir} : ${listed.stderr.trim()}`);
  }
  return new Set(listed.stdout.split('\0').filter((path) => path !== ''));
}

async function readBytes(dir: string, path: string): Promise<Buffer | undefined> {
  try {
    return await readFile(join(dir, path));
  } catch {
    return undefined;
  }
}

export async function readText(dir: string, path: string): Promise<string | undefined> {
  return (await readBytes(dir, path))?.toString('utf8');
}

/** Empreinte sha256 du fichier ; `undefined` quand il est absent. */
export async function digest(dir: string, path: string): Promise<string | undefined> {
  const bytes = await readBytes(dir, path);
  return bytes === undefined ? undefined : createHash('sha256').update(bytes).digest('hex');
}

export async function readJson(
  dir: string,
  path: string,
): Promise<Record<string, unknown> | undefined> {
  const text = await readText(dir, path);
  if (text === undefined) {
    return undefined;
  }
  try {
    const parsed: unknown = JSON.parse(text);
    return isRecord(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

export function changeKind(before: string | undefined, after: string | undefined): string {
  if (before === undefined) {
    return 'ajouté';
  }
  return after === undefined ? 'supprimé' : 'modifié';
}
