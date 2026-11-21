import { readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { isRecord, runTool } from './tools.ts';
import type { StatusBody } from './verdict-rules.ts';

export type JudgeName = 'approvals' | 'integrity' | 'deps';

const REPOSITORY = /^[\w.-]+\/[\w.-]+$/;
const SECRET_NAMES = new Set(['GATE_STATUS_TOKEN', 'GH_TOKEN', 'GITHUB_TOKEN']);
const GIT_TIMEOUT_MS = 120_000;
const JUDGE_TIMEOUT_MS = 180_000;

export const isRepository = (value: string): boolean => REPOSITORY.test(value);

function withoutSecrets(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return Object.fromEntries(Object.entries(env).filter(([name]) => !SECRET_NAMES.has(name)));
}

/** Authentification de `git fetch` par l'environnement : le jeton n'apparaît dans aucun argument. */
function gitAuthEnv(token: string | undefined): NodeJS.ProcessEnv {
  if (token === undefined || token === '') {
    return {};
  }
  const basic = Buffer.from(`x-access-token:${token}`).toString('base64');
  return {
    GIT_CONFIG_COUNT: '1',
    GIT_CONFIG_KEY_0: 'http.https://github.com/.extraheader',
    GIT_CONFIG_VALUE_0: `AUTHORIZATION: basic ${basic}`,
  };
}

/**
 * Récupère la tête à la profondeur 2 (le juge d'approbation lit aussi le parent) puis l'extrait
 * dans un dossier de travail : la tête n'est jamais installée ni exécutée, seulement lue.
 */
export function extractHeadFromGit(
  baseDir: string,
  workDir: string,
  env: NodeJS.ProcessEnv,
): (sha: string) => Promise<string> {
  const base = { ...withoutSecrets(env), GIT_LFS_SKIP_SMUDGE: '1', GIT_TERMINAL_PROMPT: '0' };
  const git = async (dir: string, args: readonly string[], extra: NodeJS.ProcessEnv = {}) => {
    const run = await runTool({
      command: 'git',
      args: ['-C', dir, ...args],
      cwd: workDir,
      env: { ...base, ...extra },
      timeoutMs: GIT_TIMEOUT_MS,
    });
    if (run.code !== 0) {
      throw new Error(`git ${args.slice(0, 2).join(' ')} : ${run.stderr.trim().slice(0, 300)}`);
    }
    return run.stdout.trim();
  };
  return async (sha) => {
    const headDir = join(workDir, 'head');
    await git(
      baseDir,
      ['fetch', '--no-tags', '--depth=2', 'origin', sha],
      gitAuthEnv(env['GH_TOKEN']),
    );
    await git(baseDir, ['worktree', 'add', '--detach', headDir, sha]);
    if ((await git(headDir, ['rev-parse', 'HEAD'])) !== sha) {
      throw new Error(`la tête extraite n'est pas ${sha}`);
    }
    return headDir;
  };
}

function outputPath(args: readonly string[]): string {
  const at = args.indexOf('--out');
  const path = at === -1 ? undefined : args[at + 1];
  if (path === undefined) {
    throw new Error('--out manquant dans les arguments du juge');
  }
  return path;
}

/**
 * Lance un juge depuis la copie de la branche par défaut, sans shell, avec `cwd` hors de la tête et
 * sans aucun jeton dans l'environnement ; renvoie le rapport écrit par `--out`.
 */
export function nodeJudge(
  baseDir: string,
  workDir: string,
  env: NodeJS.ProcessEnv,
): (name: JudgeName, args: readonly string[]) => Promise<unknown> {
  const judgeEnv = withoutSecrets(env);
  return async (name, args) => {
    const out = outputPath(args);
    await rm(out, { force: true });
    const script = join(baseDir, 'quality', name === 'deps' ? 'deps-guard.ts' : `${name}.ts`);
    const run = await runTool({
      command: process.execPath,
      args: [script, ...args],
      cwd: workDir,
      env: judgeEnv,
      timeoutMs: JUDGE_TIMEOUT_MS,
    });
    // L'intégrité et les dépendances sortent 1 sur refus (rapport écrit) ; le juge d'approbation sort 0.
    if (run.code > (name === 'approvals' ? 0 : 1)) {
      throw new Error(
        `${name} a rendu le code ${String(run.code)} : ${run.stderr.trim().slice(0, 300)}`,
      );
    }
    const report: unknown = JSON.parse(await readFile(out, 'utf8'));
    return report;
  };
}

/** Publie le statut avec le jeton de l'application dédiée ; le dernier statut d'un contexte fait foi. */
export function githubPublisher(
  repo: string,
  token: string,
  env: NodeJS.ProcessEnv,
): (sha: string, body: StatusBody) => Promise<void> {
  return async (sha, body) => {
    const fields = [
      `state=${body.state}`,
      `context=${body.context}`,
      `description=${body.description}`,
      ...(body.target_url === '' ? [] : [`target_url=${body.target_url}`]),
    ];
    const run = await runTool({
      command: 'gh',
      args: [
        'api',
        '--method',
        'POST',
        `repos/${repo}/statuses/${sha}`,
        ...fields.flatMap((f) => ['-f', f]),
      ],
      cwd: process.cwd(),
      env: { ...env, GH_TOKEN: token },
      timeoutMs: 60_000,
    });
    if (run.code !== 0) {
      throw new Error(`publication du statut : ${run.stderr.trim().slice(0, 300)}`);
    }
  };
}

/** Numéro de la PR d'une tête quand `workflow_run.pull_requests` est vide (PR de fork). */
export async function findPullRequest(
  repo: string,
  sha: string,
  env: NodeJS.ProcessEnv,
): Promise<number | undefined> {
  const run = await runTool({
    command: 'gh',
    args: ['api', `repos/${repo}/commits/${sha}/pulls`],
    cwd: process.cwd(),
    env,
    timeoutMs: 60_000,
  });
  if (run.code !== 0) {
    return undefined;
  }
  let pulls: unknown;
  try {
    pulls = JSON.parse(run.stdout);
  } catch {
    return undefined;
  }
  const first: unknown = Array.isArray(pulls) ? pulls[0] : undefined;
  const number = isRecord(first) ? first['number'] : undefined;
  return typeof number === 'number' && Number.isInteger(number) && number > 0 ? number : undefined;
}
