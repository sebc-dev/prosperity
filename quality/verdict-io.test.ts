import { chmod, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { runTool } from './tools.ts';
import { extractHeadFromGit, findPullRequest, githubPublisher, nodeJudge } from './verdict-io.ts';

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'verdict-io-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

const IDENTITY = {
  GIT_AUTHOR_NAME: 't',
  GIT_AUTHOR_EMAIL: 't@example.org',
  GIT_COMMITTER_NAME: 't',
  GIT_COMMITTER_EMAIL: 't@example.org',
};

async function git(dir: string, ...args: string[]): Promise<string> {
  const run = await runTool({
    command: 'git',
    args: ['-C', dir, ...args],
    cwd: scratch,
    env: { ...process.env, ...IDENTITY },
  });
  expect({ code: run.code, stderr: run.stderr }).toMatchObject({ code: 0 });
  return run.stdout.trim();
}

/** Origine avec deux commits dont la branche `pr` porte le second ; la base n'a cloné que le premier. */
async function repositories(): Promise<{ baseDir: string; headSha: string }> {
  const origin = join(scratch, 'origin');
  await mkdir(origin);
  await git(origin, 'init', '-q', '-b', 'main');
  await writeFile(join(origin, 'a.txt'), 'un');
  await git(origin, 'add', 'a.txt');
  await git(origin, 'commit', '-q', '-m', 'un');
  await git(origin, 'checkout', '-q', '-b', 'pr');
  await writeFile(join(origin, 'b.txt'), 'deux');
  await git(origin, 'add', 'b.txt');
  await git(origin, 'commit', '-q', '-m', 'deux');
  const headSha = await git(origin, 'rev-parse', 'HEAD');
  const baseDir = join(scratch, 'base');
  await git(scratch, 'clone', '-q', '--depth=1', '--branch', 'main', `file://${origin}`, baseDir);
  return { baseDir, headSha };
}

describe('extractHeadFromGit', () => {
  it('extrait la tête à la profondeur 2, sur le bon SHA, sans toucher à la base', async () => {
    const { baseDir, headSha } = await repositories();
    const workDir = join(scratch, 'work');
    await mkdir(workDir);
    const headDir = await extractHeadFromGit(baseDir, workDir, process.env)(headSha);
    expect(headDir).toBe(join(workDir, 'head'));
    expect(await readFile(join(headDir, 'b.txt'), 'utf8')).toBe('deux');
    expect(await git(headDir, 'rev-parse', 'HEAD')).toBe(headSha);
    expect((await git(headDir, 'rev-list', '--count', 'HEAD')).trim()).toBe('2');
    expect(await git(baseDir, 'status', '--porcelain')).toBe('');
  });

  it('refuse un SHA absent de l origine', async () => {
    const { baseDir } = await repositories();
    const workDir = join(scratch, 'work');
    await mkdir(workDir);
    await expect(extractHeadFromGit(baseDir, workDir, process.env)('b'.repeat(40))).rejects.toThrow(
      'git fetch',
    );
  });
});

const JUDGE = `import { writeFileSync } from 'node:fs';
const args = process.argv.slice(2);
const at = (flag) => (args.includes(flag) ? args[args.indexOf(flag) + 1] : undefined);
const exit = Number(at('--exit') ?? '0');
if (at('--out') !== undefined && exit < 2) {
  const seen = { cwd: process.cwd(), token: process.env.GATE_STATUS_TOKEN ?? null, gh: process.env.GH_TOKEN ?? null };
  writeFileSync(at('--out'), JSON.stringify(seen));
}
process.exit(exit);
`;

async function judgeBase(): Promise<string> {
  const baseDir = join(scratch, 'judges');
  await mkdir(join(baseDir, 'quality'), { recursive: true });
  await writeFile(join(baseDir, 'package.json'), '{"type":"module"}');
  for (const name of ['approvals.ts', 'integrity.ts', 'deps-guard.ts']) {
    await writeFile(join(baseDir, 'quality', name), JUDGE);
  }
  return baseDir;
}

describe('nodeJudge', () => {
  const env = { ...process.env, GATE_STATUS_TOKEN: 'secret-app', GH_TOKEN: 'secret-run' };

  async function judge() {
    const workDir = join(scratch, 'work');
    await mkdir(workDir, { recursive: true });
    return { workDir, run: nodeJudge(await judgeBase(), workDir, env) };
  }

  it('lance le juge depuis le dossier de travail, sans aucun jeton, et renvoie son rapport', async () => {
    const { workDir, run } = await judge();
    const report = await run('integrity', ['--out', join(workDir, 'integrity.json')]);
    expect(report).toEqual({ cwd: await realpath(workDir), token: null, gh: null });
  });

  it('accepte le code 1 de l intégrité et des dépendances, rapport écrit', async () => {
    const { workDir, run } = await judge();
    const report = await run('deps', ['--exit', '1', '--out', join(workDir, 'deps.json')]);
    expect(report).toMatchObject({ token: null });
  });

  it.each([
    ['integrity', '2'],
    ['approvals', '1'],
  ] as const)('refuse le code %s %s', async (name, exit) => {
    const { workDir, run } = await judge();
    await expect(run(name, ['--exit', exit, '--out', join(workDir, 'r.json')])).rejects.toThrow(
      'code',
    );
  });

  it('refuse des arguments sans --out', async () => {
    const { run } = await judge();
    await expect(run('approvals', ['--base-dir', '/x'])).rejects.toThrow('--out');
  });
});

/** Faux `gh` : enregistre ses arguments et le jeton reçu, répond selon les variables FAKE_*. */
async function fakeGh(): Promise<NodeJS.ProcessEnv> {
  const bin = join(scratch, 'bin');
  await mkdir(bin);
  const script = [
    '#!/bin/sh',
    'printf "%s\\n" "$@" > "$FAKE_ARGS"',
    'printf "%s" "$GH_TOKEN" > "$FAKE_TOKEN"',
    'printf "%s" "$FAKE_STDOUT"',
    'exit "${FAKE_EXIT:-0}"',
    '',
  ].join('\n');
  await writeFile(join(bin, 'gh'), script);
  await chmod(join(bin, 'gh'), 0o755);
  return {
    PATH: `${bin}:${process.env['PATH'] ?? ''}`,
    FAKE_ARGS: join(scratch, 'args.txt'),
    FAKE_TOKEN: join(scratch, 'token.txt'),
  };
}

describe('githubPublisher', () => {
  const body = {
    state: 'failure',
    context: 'quality',
    description: 'quality refusé : gate-not-success',
    target_url: 'https://github.com/o/r/actions/runs/1',
  } as const;

  it('publie avec le jeton de l application et sans shell', async () => {
    const env = await fakeGh();
    await githubPublisher('o/r', 'app-token', env)('a'.repeat(40), body);
    const args = (await readFile(join(scratch, 'args.txt'), 'utf8')).split('\n');
    expect(args).toEqual([
      ...['api', '--method', 'POST', `repos/o/r/statuses/${'a'.repeat(40)}`],
      ...['-f', 'state=failure', '-f', 'context=quality'],
      ...['-f', 'description=quality refusé : gate-not-success'],
      ...['-f', 'target_url=https://github.com/o/r/actions/runs/1', ''],
    ]);
    expect(await readFile(join(scratch, 'token.txt'), 'utf8')).toBe('app-token');
  });

  it('omet target_url vide et échoue quand gh échoue', async () => {
    const env = { ...(await fakeGh()), FAKE_EXIT: '1' };
    const publish = githubPublisher('o/r', 'app-token', env);
    await expect(publish('a'.repeat(40), { ...body, target_url: '' })).rejects.toThrow(
      'publication',
    );
    expect(await readFile(join(scratch, 'args.txt'), 'utf8')).not.toContain('target_url');
  });
});

describe('findPullRequest', () => {
  it('lit le premier numéro de PR rendu par l API', async () => {
    const env = { ...(await fakeGh()), FAKE_STDOUT: '[{"number":7},{"number":9}]' };
    expect(await findPullRequest('o/r', 'a'.repeat(40), env)).toBe(7);
  });

  it.each(['[]', 'pas du json', '[{"number":"7"}]', '{}'])(
    'rend undefined pour la réponse %s',
    async (stdout) => {
      const env = { ...(await fakeGh()), FAKE_STDOUT: stdout };
      expect(await findPullRequest('o/r', 'a'.repeat(40), env)).toBeUndefined();
    },
  );

  it('rend undefined quand gh échoue', async () => {
    const env = { ...(await fakeGh()), FAKE_EXIT: '1' };
    expect(await findPullRequest('o/r', 'a'.repeat(40), env)).toBeUndefined();
  });
});
