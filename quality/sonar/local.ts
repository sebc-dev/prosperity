import { readFile, stat } from 'node:fs/promises';
import { userInfo } from 'node:os';
import { join } from 'node:path';
import { runTool } from '../tools.ts';
import { redactInvocation, scannerInvocation } from './sonar-kit.ts';
import type { Failure, Invocation, SonarConfig } from './sonar-kit.ts';

// Scanner local (D-16) : l'adresse et le jeton viennent de l'environnement ou d'un fichier 0600 hors du
// dépôt ; le scanner tourne dans un conteneur de cette machine et joint le serveur Sonar du homelab
// par son adresse HTTPS du tailnet. Le jeton ne passe que par l'environnement du processus du moteur
// (`-e SONAR_TOKEN` sans valeur) et par l'en-tête de la lecture de la tâche.

export interface Analysis {
  /** Lignes imprimées par `--dry-run` : ni le jeton ni l'adresse. */
  describe: () => string[];
  scan: () => Promise<Failure | undefined>;
  serverVersion: () => Promise<string | undefined>;
  readReportTask: () => Promise<string | undefined>;
  fetchTask: (taskId: string) => Promise<unknown>;
  dashboard: () => string;
}

const SCAN_TIMEOUT_MS = 1_800_000;
const REQUEST_TIMEOUT_MS = 30_000;

const isDirectory = (path: string): Promise<boolean> =>
  stat(path).then(
    (info) => info.isDirectory(),
    () => false,
  );

/** Fin de sortie d'un outil, secrets masqués : de quoi diagnostiquer sans rien divulguer. */
function tail(text: string, secrets: readonly string[]): string {
  const masked = secrets
    .filter((secret) => secret !== '')
    .reduce((line, secret) => line.split(secret).join('***'), text.trim());
  return masked.slice(-800);
}

function invocation(
  cfg: SonarConfig,
  image: string,
  root: string,
  scmDisabled: boolean,
): Invocation {
  const { uid, gid } = userInfo();
  return scannerInvocation(cfg, { image, root, uid, gid, scmDisabled });
}

async function scan(cfg: SonarConfig, image: string, root: string): Promise<Failure | undefined> {
  const scmDisabled = !(await isDirectory(join(root, '.git')));
  const inv = invocation(cfg, image, root, scmDisabled);
  const ran = await runTool({
    command: inv.command,
    args: inv.args,
    cwd: root,
    env: { ...process.env, ...inv.env },
    timeoutMs: SCAN_TIMEOUT_MS,
  });
  if (ran.code === 0) {
    return undefined;
  }
  const output = tail(`${ran.stderr}\n${ran.stdout}`, [cfg.token, cfg.hostUrl]);
  return { error: `scanner en échec (code ${String(ran.code)}) :\n${output}` };
}

async function fetchTask(cfg: SonarConfig, taskId: string): Promise<unknown> {
  const response = await fetch(`${cfg.hostUrl}/api/ce/task?id=${taskId}`, {
    headers: { Authorization: `Bearer ${cfg.token}` },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`lecture de la tâche refusée (HTTP ${String(response.status)})`);
  }
  const body: unknown = await response.json();
  return body;
}

async function serverVersion(cfg: SonarConfig): Promise<string | undefined> {
  const response = await fetch(`${cfg.hostUrl}/api/server/version`, {
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  return response.ok ? (await response.text()).trim() : undefined;
}

function describe(cfg: SonarConfig, image: string, root: string): string[] {
  const line = redactInvocation(invocation(cfg, image, root, false), cfg.token)
    .split(cfg.hostUrl)
    .join('<SONAR_HOST_URL>');
  return [`scanner ${cfg.engine} sur ce poste`, `$ SONAR_TOKEN=*** ${line}`];
}

export function localAnalysis(cfg: SonarConfig, image: string, root: string): Analysis {
  return {
    describe: () => describe(cfg, image, root),
    scan: () => scan(cfg, image, root),
    serverVersion: () => serverVersion(cfg),
    readReportTask: () =>
      readFile(join(root, 'reports', 'sonar', 'scannerwork', 'report-task.txt'), 'utf8').catch(
        () => undefined,
      ),
    fetchTask: (taskId) => fetchTask(cfg, taskId),
    dashboard: () => `${cfg.hostUrl}/dashboard?id=prosperity`,
  };
}
