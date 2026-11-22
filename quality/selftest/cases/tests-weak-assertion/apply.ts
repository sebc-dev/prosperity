import { access, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const DIR = join('src', 'shared', 'money');
const SOURCE = join(DIR, 'allocate.ts');
const EXAMPLES = join(DIR, 'allocate.test.ts');
const PROPERTIES = join(DIR, 'allocate.properties.test.ts');

// Texte de remplacement constant : les appels sont faits, aucune part n'est vérifiée (seul `ok` l'est).
const WEAK_TEST = `import { describe, expect, it } from 'vitest';
import { allocate } from './allocate.ts';

describe('allocate', () => {
  it('[selftest:weak-allocate]', () => {
    const even = allocate({ amountMinor: 8400n, currency: 'EUR' }, [5000n, 5000n]);
    const thirds = allocate({ amountMinor: 100n, currency: 'EUR' }, [1n, 1n, 1n]);
    const uneven = allocate({ amountMinor: 8401n, currency: 'EUR' }, [6000n, 4000n]);
    const negative = allocate({ amountMinor: -100n, currency: 'EUR' }, [1n, 1n, 1n]);
    const empty = allocate({ amountMinor: 8400n, currency: 'EUR' }, []);
    expect(even.ok).toBe(true);
    expect(thirds.ok).toBe(true);
    expect(uneven.ok).toBe(true);
    expect(negative.ok).toBe(true);
    expect(empty.ok).toBe(false);
  });
});
`;

async function requirePresent(root: string, file: string): Promise<void> {
  try {
    await access(join(root, file));
  } catch {
    throw new Error(`case-stale : ${file} introuvable`);
  }
}

/**
 * Le « test faible » du canari (D-09) : retire les propriétés de `allocate` et remplace ses exemples
 * par un test qui appelle `allocate` sans vérifier aucune part. Seul `allocate.ts` est alors muté
 * (le fichier supprimé n'ajoute aucun source) et les mutants du calcul des parts survivent.
 */
export default async function apply(root: string): Promise<void> {
  await Promise.all([SOURCE, EXAMPLES, PROPERTIES].map((file) => requirePresent(root, file)));
  await rm(join(root, PROPERTIES));
  const before = await readFile(join(root, EXAMPLES), 'utf8');
  if (before === WEAK_TEST) {
    throw new Error(`case-stale : ${EXAMPLES} contient déjà le test faible`);
  }
  await writeFile(join(root, EXAMPLES), WEAK_TEST, 'utf8');
}
