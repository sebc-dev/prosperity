import { runMiseTool, runTool } from '../tools.ts';
import type { ToolResult } from '../tools.ts';

const INSTALL_TIMEOUT_MS = 600_000;
const GIT_TIMEOUT_MS = 120_000;
// En CI les checks jouent en mode « confiance » (rapports pré-calculés) : les cas doivent jouer en local.
const CI_VARIABLES: ReadonlySet<string> = new Set([
  'GITHUB_ACTIONS',
  'CI',
  'GITHUB_EVENT_NAME',
  'GITHUB_BASE_REF',
  'GATE_FORCE_SELFTEST',
  'GATE_SELFTEST_CASES',
]);

export interface InstallOutcome {
  ok: boolean;
  message: string;
}

export type Installer = (dir: string, env: NodeJS.ProcessEnv) => Promise<InstallOutcome>;

/** Ce que partagent le runner et l'exécution d'un cas pendant un run. */
export interface RunContext {
  root: string;
  runDir: string;
  baseDir: string;
  headSha: string;
  env: NodeJS.ProcessEnv;
  install: Installer;
}

export interface Verdict {
  status: 'passed' | 'failed';
  reason: string;
  detail?: string;
}

export interface Failure {
  reason: string;
  detail: string;
}

export function tail(text: string): string {
  return text.trim().slice(-300);
}

export function git(
  dir: string,
  args: readonly string[],
  env: NodeJS.ProcessEnv,
): Promise<ToolResult> {
  return runTool({ command: 'git', args, cwd: dir, env, timeoutMs: GIT_TIMEOUT_MS });
}

/** Installation depuis le lockfile gelé : hors ligne d'abord, avec le réseau en repli. */
export async function pnpmInstall(dir: string, env: NodeJS.ProcessEnv): Promise<InstallOutcome> {
  const options = { cwd: dir, env, timeoutMs: INSTALL_TIMEOUT_MS };
  const offline = await runMiseTool('pnpm', ['install', '--frozen-lockfile', '--offline'], options);
  if (offline.code === 0) {
    return { ok: true, message: '' };
  }
  const online = await runMiseTool('pnpm', ['install', '--frozen-lockfile'], options);
  return { ok: online.code === 0, message: tail(online.stderr) };
}

/** Environnement des processus fils : local (jamais CI), sans variables git héritées, mise de confiance. */
export function localEnv(env: NodeJS.ProcessEnv, runDir: string): NodeJS.ProcessEnv {
  const kept = Object.entries(env).filter(
    ([name]) => !CI_VARIABLES.has(name) && !name.startsWith('GIT_'),
  );
  const trusted = env['MISE_TRUSTED_CONFIG_PATHS'];
  return {
    ...Object.fromEntries(kept),
    MISE_TRUSTED_CONFIG_PATHS:
      trusted === undefined || trusted === '' ? runDir : `${trusted}:${runDir}`,
  };
}
