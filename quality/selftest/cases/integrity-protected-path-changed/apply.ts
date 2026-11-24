import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const TARGET = '.jscpd.json';
const MIN_TOKENS = /("minTokens"\s*:\s*)(\d+)/;
const STRICTER_BY = 10;

/**
 * Rend la détection de duplication plus stricte (`minTokens` abaissé de 10) : un changement de
 * configuration qui n'affaiblit rien, donc seule la règle de chemin protégé est attendue. Sert aussi
 * de changement de démonstration au plan 01-13. « case-stale » si `minTokens` a disparu.
 */
export default async function apply(root: string): Promise<void> {
  const path = join(root, TARGET);
  const text = await readFile(path, 'utf8');
  const stricter = text.replace(MIN_TOKENS, (_match, head: string, value: string) => {
    return `${head}${String(Number.parseInt(value, 10) - STRICTER_BY)}`;
  });
  if (stricter === text) {
    throw new Error(`case-stale : minTokens introuvable dans ${TARGET}`);
  }
  await writeFile(path, stricter, 'utf8');
}
