import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { runTool } from '../tools.ts';

const SCRIPT = resolve(import.meta.dirname, 'precommit-protected.ts');
const dirs: string[] = [];

afterAll(async () => {
  await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })));
});

/** Dépôt temporaire dont l'index contient exactement `files`. */
async function stage(files: string[]): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'gate-precommit-'));
  dirs.push(dir);
  await runTool({ command: 'git', args: ['init', '-q'], cwd: dir });
  for (const file of files) {
    await mkdir(dirname(join(dir, file)), { recursive: true });
    await writeFile(join(dir, file), 'x\n');
  }
  await runTool({ command: 'git', args: ['add', '--', ...files], cwd: dir });
  return dir;
}

function run(cwd: string, human: string): ReturnType<typeof runTool> {
  return runTool({
    command: process.execPath,
    args: [SCRIPT],
    cwd,
    env: { ...process.env, PROSPERITY_HUMAN_GATE_EDIT: human },
  });
}

describe('precommit-protected.ts', () => {
  it('refuse un commit qui touche un chemin protégé et nomme le geste humain', async () => {
    const result = await run(await stage(['.npmrc', 'src/a.ts']), '');
    expect(result.code).toBe(1);
    expect(result.stderr).toContain('.npmrc');
    expect(result.stderr).not.toContain('src/a.ts');
    expect(result.stderr).toContain('PROSPERITY_HUMAN_GATE_EDIT=1 git commit');
  });

  it('laisse passer le commit humain (PROSPERITY_HUMAN_GATE_EDIT=1)', async () => {
    const result = await run(await stage(['quality/x.ts']), '1');
    expect(result.code).toBe(0);
  });

  it('refuse encore quand la variable ne vaut pas 1', async () => {
    const result = await run(await stage(['mise.toml']), '0');
    expect(result.code).toBe(1);
  });

  it('laisse passer un commit qui ne touche aucun chemin protégé', async () => {
    const result = await run(await stage(['src/a.ts', '.claude/agents/x.md']), '');
    expect(result).toMatchObject({ code: 0, stderr: '' });
  });

  it('sort en 2 hors d’un dépôt git', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gate-precommit-'));
    dirs.push(dir);
    expect((await run(dir, '')).code).toBe(2);
  });
});
