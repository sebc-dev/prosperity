import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { runTool } from '../tools.ts';

const ROOT = join(import.meta.dirname, '..', '..');
const JETON = 'jeton-factice-0123';

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'sonar-run-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

/** Vrai processus `node quality/sonar/run.ts` : environnement réduit, aucune variable du poste. */
function sonar(env: Record<string, string>, args: string[] = []): ReturnType<typeof runTool> {
  return runTool({
    command: process.execPath,
    args: ['quality/sonar/run.ts', ...args],
    cwd: ROOT,
    env: { HOME: scratch, ...env },
    timeoutMs: 60_000,
  });
}

describe('pnpm sonar : refus de configuration (sortie 2, avant toute action)', () => {
  it.each([['CI'], ['GITHUB_ACTIONS']])(
    'refuse de tourner quand %s est défini (D-16)',
    async (name) => {
      const ran = await sonar({ [name]: 'true' });
      expect(ran.code).toBe(2);
      expect(ran.stderr).toContain('D-16');
    },
  );

  it('refuse l’absence d’hôte, de jeton et de fichier d’environnement', async () => {
    const ran = await sonar({ SONAR_ENV_FILE: join(scratch, 'absent') });
    expect(ran.code).toBe(2);
    expect(ran.stderr).toContain('SONAR_HOST_URL');
  });

  it('refuse un fichier d’environnement lisible par d’autres', async () => {
    const file = join(scratch, 'env');
    await writeFile(file, `SONAR_HOST_URL=https://sonar.example\nSONAR_TOKEN=${JETON}\n`, {
      mode: 0o644,
    });
    const ran = await sonar({ SONAR_ENV_FILE: file });
    expect(ran.code).toBe(2);
    expect(ran.stderr).toContain('0600');
    expect(ran.stderr + ran.stdout).not.toContain(JETON);
  });

  it('refuse un fichier d’environnement placé dans le dépôt', async () => {
    const dir = join(ROOT, 'reports', `sonar-run-test-${String(process.pid)}`);
    await mkdir(dir, { recursive: true });
    try {
      const file = join(dir, 'env');
      await writeFile(file, `SONAR_HOST_URL=https://sonar.example\nSONAR_TOKEN=${JETON}\n`, {
        mode: 0o600,
      });
      const ran = await sonar({ SONAR_ENV_FILE: file });
      expect(ran.code).toBe(2);
      expect(ran.stderr).toContain('dépôt');
      expect(ran.stderr + ran.stdout).not.toContain(JETON);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
