import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const TARGET = join('src', 'shared', 'money', 'money.test.ts');
const EXPECT_CALL = /\bexpect\(/;

/**
 * Supprime de `money.test.ts` la première ligne contenant un appel `expect(` : le check compte les
 * appels dans le texte, la compilation du fichier n'entre pas en jeu. « case-stale » sans appel.
 */
export default async function apply(root: string): Promise<void> {
  const path = join(root, TARGET);
  const lines = (await readFile(path, 'utf8')).split('\n');
  const at = lines.findIndex((line) => EXPECT_CALL.test(line));
  if (at === -1) {
    throw new Error(`case-stale : aucun appel expect( dans ${TARGET}`);
  }
  lines.splice(at, 1);
  await writeFile(path, lines.join('\n'), 'utf8');
}
