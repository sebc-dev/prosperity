import { readFile, stat } from 'node:fs/promises';
import { userInfo } from 'node:os';
import { join } from 'node:path';
import { runTool } from '../tools.ts';
import { tail } from './backend.ts';
import type { Backend } from './backend.ts';
import { redactInvocation, scannerInvocation } from './sonar-kit.ts';
import type { Failure, Invocation, SonarConfig } from './sonar-kit.ts';

// Mode local : l'adresse et le jeton viennent de l'environnement ou d'un fichier 0600 hors du dépôt ;
// le scanner tourne dans un conteneur de cette machine (c'est le mode du timer nightly du serveur).

const SCAN_TIMEOUT_MS = 1_800_000;
const REQUEST_TIMEOUT_MS = 30_000;

const isDirectory = (path: string): Promise<boolean> =>
  stat(path).then(
    (info) => info.isDirectory(),
    () => false,
  );

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

/** Invocation masquée pour `--dry-run` : ni le jeton ni l'adresse ne sont imprimés. */
function describe(cfg: SonarConfig, image: string, root: string): string[] {
  const line = redactInvocation(invocation(cfg, image, root, false), cfg.token)
    .split(cfg.hostUrl)
    .join('<SONAR_HOST_URL>');
  return [`mode local : scanner ${cfg.engine} sur ce poste`, `$ SONAR_TOKEN=*** ${line}`];
}

export function localBackend(cfg: SonarConfig, image: string, root: string): Backend {
  return {
    describe: () => describe(cfg, image, root),
    preflight: () => Promise.resolve(undefined),
    scan: () => scan(cfg, image, root),
    serverVersion: () => serverVersion(cfg),
    readReportTask: () =>
      readFile(join(root, 'reports', 'sonar', 'scannerwork', 'report-task.txt'), 'utf8').catch(
        () => undefined,
      ),
    fetchTask: (taskId) => fetchTask(cfg, taskId),
    dashboard: () => `${cfg.hostUrl}/dashboard?id=prosperity`,
    cleanup: () => Promise.resolve(),
  };
}
