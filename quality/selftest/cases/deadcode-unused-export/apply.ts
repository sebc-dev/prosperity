import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const TARGET = ['src', 'shared', 'money', 'money.ts'];
const UNUSED_EXPORT = 'export const SELFTEST_UNUSED_EXPORT = 1;\n';

/** Ajoute un export que personne n'importe à la fin de `money.ts` ; échoue (« case-stale ») si le fichier a disparu. */
export default async function apply(root: string): Promise<void> {
  const path = join(root, ...TARGET);
  let text: string;
  try {
    text = await readFile(path, 'utf8');
  } catch {
    throw new Error(`case-stale : ${TARGET.join('/')} introuvable`);
  }
  await writeFile(path, `${text}\n${UNUSED_EXPORT}`, 'utf8');
}
