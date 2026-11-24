import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const PACKAGE = 'ms';
const VERSION = '2.1.3';

/**
 * Ajoute `ms@2.1.3` (paquet ancien, existant) aux dépendances de `package.json`, sans toucher au
 * lockfile : seule l'approbation `deps-approved` manquante doit faire échouer le check `deps`.
 */
export default async function apply(root: string): Promise<void> {
  const path = join(root, 'package.json');
  const manifest: unknown = JSON.parse(await readFile(path, 'utf8'));
  if (typeof manifest !== 'object' || manifest === null || !('dependencies' in manifest)) {
    throw new Error('case-stale : package.json sans section dependencies');
  }
  const { dependencies } = manifest;
  if (typeof dependencies !== 'object' || dependencies === null || PACKAGE in dependencies) {
    throw new Error(`case-stale : dependencies illisible ou contient déjà ${PACKAGE}`);
  }
  const sorted = Object.entries({ ...dependencies, [PACKAGE]: VERSION }).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const updated = { ...manifest, dependencies: Object.fromEntries(sorted) };
  await writeFile(path, `${JSON.stringify(updated, null, 2)}\n`, 'utf8');
}
