import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { digest } from './integrity-fs.ts';
import { isProtected } from './protected-paths.ts';

describe('isProtected : fichiers cachés (revue CR-01)', () => {
  it('protège un fichier caché sous un glob en **', () => {
    expect(isProtected('quality/checks/.evil.ts', ['quality/**'])).toBe(true);
    expect(isProtected('.github/workflows/.evil.yml', ['.github/**'])).toBe(true);
  });

  it('protège un dossier caché sous un glob en **', () => {
    expect(isProtected('quality/.hidden/check.ts', ['quality/**'])).toBe(true);
  });

  it('protège un fichier caché sous un glob en *', () => {
    expect(isProtected('deploy/.env', ['deploy/*'])).toBe(true);
  });

  it('garde la correspondance exacte des globs qui nomment un fichier caché', () => {
    expect(isProtected('.claude/settings.json', ['.claude/settings*.json'])).toBe(true);
    expect(isProtected('.gitignore', ['.gitignore'])).toBe(true);
    expect(isProtected('./quality/run.ts', ['quality/**'])).toBe(true);
  });

  it('ne protège pas un fichier caché hors des globs', () => {
    expect(isProtected('src/.hidden.ts', ['quality/**', '.github/**'])).toBe(false);
    expect(isProtected('.claude/agents/x.md', ['.claude/settings*.json'])).toBe(false);
  });
});

describe('digest : liens symboliques (revue WR-07)', () => {
  let root = '';

  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), 'gate-symlink-'));
    await mkdir(join(root, 'real'), { recursive: true });
    await writeFile(join(root, 'real', 'thresholds.json'), '{"break":80}\n', 'utf8');
  });

  afterEach(async () => {
    await rm(root, { recursive: true, force: true });
  });

  it("n'emprunte pas un lien sur le fichier : l'empreinte diffère de celle de la cible", async () => {
    await mkdir(join(root, 'quality'));
    await symlink(join(root, 'real', 'thresholds.json'), join(root, 'quality', 'thresholds.json'));

    const linked = await digest(root, 'quality/thresholds.json');
    const target = await digest(root, 'real/thresholds.json');

    expect(linked).not.toBe(target);
    expect(linked).toMatch(/^[0-9a-f]{64}$/);
  });

  it("n'emprunte pas un lien sur un dossier parent", async () => {
    await symlink(join(root, 'real'), join(root, 'quality'));

    const linked = await digest(root, 'quality/thresholds.json');
    const target = await digest(root, 'real/thresholds.json');

    expect(linked).not.toBe(target);
  });

  it('lit normalement un fichier ordinaire', async () => {
    expect(await digest(root, 'real/thresholds.json')).toMatch(/^[0-9a-f]{64}$/);
    expect(await digest(root, 'real/absent.json')).toBeUndefined();
  });
});
