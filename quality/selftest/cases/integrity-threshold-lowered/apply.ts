import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const BREAK_THRESHOLD = /("break"\s*:\s*)80\b/;

/** Baisse `mutation.break` de 80 à 70 ; échoue (« case-stale ») si le seuil n'est plus à 80. */
export default async function apply(root: string): Promise<void> {
  const path = join(root, 'quality', 'thresholds.json');
  const text = await readFile(path, 'utf8');
  const lowered = text.replace(BREAK_THRESHOLD, (_match, head: string) => `${head}70`);
  if (lowered === text) {
    throw new Error('case-stale : mutation.break à 80 introuvable dans quality/thresholds.json');
  }
  await writeFile(path, lowered, 'utf8');
}
