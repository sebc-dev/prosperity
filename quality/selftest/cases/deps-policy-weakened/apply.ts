import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const RELEASE_AGE = /^(minimumReleaseAge:\s*)10080\b/m;

/** Passe `minimumReleaseAge` de 10080 à 1440 ; « case-stale » si la valeur n'est plus 10080. */
export default async function apply(root: string): Promise<void> {
  const path = join(root, 'pnpm-workspace.yaml');
  const text = await readFile(path, 'utf8');
  const weakened = text.replace(RELEASE_AGE, (_match, head: string) => `${head}1440`);
  if (weakened === text) {
    throw new Error('case-stale : minimumReleaseAge à 10080 introuvable dans pnpm-workspace.yaml');
  }
  await writeFile(path, weakened, 'utf8');
}
