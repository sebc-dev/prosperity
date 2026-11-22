import { readFile, realpath, stat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { runTool } from '../tools.ts';
import { validateRemoteConfig } from './remote-kit.ts';
import type { RemoteConfig } from './remote-kit.ts';
import { isFailure, parseEnvFile, validateSonarConfig } from './sonar-kit.ts';
import type { Failure, SonarConfig } from './sonar-kit.ts';

export type Mode = { kind: 'ssh'; cfg: RemoteConfig } | { kind: 'local'; cfg: SonarConfig };

const FILE_RIGHTS_MASK = 0o077;

/** Moteurs de conteneur présents dans le PATH : `<moteur> --version` réussit. */
async function findEngines(root: string): Promise<string[]> {
  const found: string[] = [];
  for (const name of ['podman', 'docker']) {
    const run = await runTool({ command: name, args: ['--version'], cwd: root, timeoutMs: 15_000 });
    if (run.code === 0) {
      found.push(name);
    }
  }
  return found;
}

/** Fichier d'environnement hors dépôt, en mode 0600 : jamais lu sous la racine ni lisible par d'autres. */
async function readEnvFile(root: string, path: string): Promise<Record<string, string> | Failure> {
  const info = await stat(path).catch(() => undefined);
  if (info === undefined) {
    return {};
  }
  const real = await realpath(path);
  if (real.startsWith(`${await realpath(root)}/`)) {
    return { error: 'le fichier d’environnement Sonar ne doit pas se trouver dans le dépôt' };
  }
  if ((info.mode & FILE_RIGHTS_MASK) !== 0) {
    return {
      error:
        'le fichier d’environnement Sonar doit être en mode 0600 (aucun droit au groupe ni aux autres)',
    };
  }
  return parseEnvFile(await readFile(real, 'utf8'));
}

async function localConfig(root: string, env: NodeJS.ProcessEnv): Promise<SonarConfig | Failure> {
  let vars: Record<string, string | undefined> = { ...env };
  if (env['SONAR_HOST_URL'] === undefined || env['SONAR_TOKEN'] === undefined) {
    const path = env['SONAR_ENV_FILE'] ?? join(homedir(), '.config', 'prosperity-sonar', 'env');
    const fromFile = await readEnvFile(root, path);
    if (isFailure(fromFile)) {
      return fromFile;
    }
    vars = { ...fromFile, ...env };
  }
  return validateSonarConfig(vars, await findEngines(root));
}

/** Mode par `SONAR_MODE` : `ssh` (défaut, scanner sur la machine Sonar) ou `local` (scanner ici). */
export async function loadMode(root: string, env: NodeJS.ProcessEnv): Promise<Mode | Failure> {
  const mode = env['SONAR_MODE'] ?? 'ssh';
  if (mode === 'ssh') {
    const cfg = validateRemoteConfig(env);
    return isFailure(cfg) ? cfg : { kind: 'ssh', cfg };
  }
  if (mode === 'local') {
    const cfg = await localConfig(root, env);
    return isFailure(cfg) ? cfg : { kind: 'local', cfg };
  }
  return { error: 'SONAR_MODE doit valoir ssh ou local' };
}
