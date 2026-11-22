import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
const TOKEN_LENGTH = 36;

/**
 * Jeton au format d'un jeton d'accès personnel GitHub, tiré au moment de l'application : aucun
 * jeton littéral n'existe dans le dépôt, donc aucun scan du dépôt lui-même ne le voit (Pattern 3).
 */
function generateToken(): string {
  const body = Array.from(randomBytes(TOKEN_LENGTH), (byte) => ALPHABET[byte % ALPHABET.length]);
  return `ghp_${body.join('')}`;
}

export default async function apply(root: string): Promise<void> {
  const dir = join(root, 'src', 'shared');
  await mkdir(dir, { recursive: true });
  await writeFile(
    join(dir, 'selftest-token.ts'),
    `export const selftestToken = '${generateToken()}';\n`,
    'utf8',
  );
}
