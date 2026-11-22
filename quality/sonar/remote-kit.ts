import {
  COVERAGE_ERROR,
  ENGINE_ERROR,
  isEngine,
  parseCoverage,
  scannerRunArgs,
} from './sonar-kit.ts';
import type { Coverage, Engine } from './sonar-kit.ts';

// Mode SSH (D-16, décision du 2026-11-22) : l'analyse part du poste, le scanner tourne sur le serveur
// Sonar lui-même, qui n'écoute que sur sa boucle locale. Le jeton ne quitte jamais cette machine : il
// est lu dans un fichier d'environnement distant (0600) par `--env-file` et par `curl -K -`. Chaque
// script est un texte `sh` envoyé sur l'entrée standard de `ssh <hôte> sh -s`, bâti de valeurs déjà
// validées et citées par `shellQuote` ; aucun jeton n'apparaît dans un argument de commande.

export interface RemoteConfig {
  sshHost: string;
  envFile: string;
  engine: Engine;
  coverage: Coverage;
}

export interface Preflight {
  uid: number;
  gid: number;
  envFile: string;
}

export interface ScriptParams {
  image: string;
  dir: string;
  uid: number;
  gid: number;
  envFile: string;
}

const DEFAULT_HOST = 'kfzserver';
const DEFAULT_ENV_FILE = '.config/prosperity-sonar/env';
const HOST_PATTERN = /^(?!-)([A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9.-]*$/;
const ENV_FILE_PATTERN = /^(?!.*\.\.)\/?[A-Za-z0-9_.][A-Za-z0-9_./-]*$/;
const ABSOLUTE_PATH = /^\/[A-Za-z0-9_./-]+$/;
const TASK_ID = /^[A-Za-z0-9_-]+$/;
const SAFE_DIR = /^(\/[A-Za-z0-9._-]+)+\/prosperity-sonar\.[A-Za-z0-9]{6,}$/;
const PREFLIGHT_OK = /^ok (\d+) (\d+) (\/[A-Za-z0-9_./-]+)$/;

const PREFLIGHT_MESSAGES: Record<string, string> = {
  'env-file-missing': 'fichier d’environnement introuvable ou illisible sur la machine distante',
  'env-file-mode': 'le fichier d’environnement distant doit être en mode 0600',
  'env-file-keys': 'le fichier d’environnement distant doit définir SONAR_HOST_URL et SONAR_TOKEN',
  'env-file-format':
    'valeurs du fichier d’environnement distant : ni guillemet ni espace (format de --env-file)',
  'host-url-refused':
    'SONAR_HOST_URL distant doit être en https:// ou en http:// sur la boucle locale',
  'engine-missing': 'moteur de conteneur absent du PATH de la machine distante',
  'engine-access':
    'accès refusé au moteur de conteneur distant (démon injoignable ou utilisateur hors du groupe du moteur)',
};

/** Configuration du mode SSH : la cible est de la configuration, jamais un secret. */
export function validateRemoteConfig(
  vars: Record<string, string | undefined>,
): RemoteConfig | { error: string } {
  const sshHost = vars['SONAR_SSH_HOST'] ?? DEFAULT_HOST;
  if (!HOST_PATTERN.test(sshHost)) {
    return { error: 'SONAR_SSH_HOST doit être un nom d’hôte ou user@hôte (aucune option ssh)' };
  }
  const envFile = vars['SONAR_REMOTE_ENV_FILE'] ?? DEFAULT_ENV_FILE;
  if (!ENV_FILE_PATTERN.test(envFile)) {
    return {
      error:
        'SONAR_REMOTE_ENV_FILE doit être un chemin sans espace ni « .. » (relatif au dossier personnel distant, ou absolu)',
    };
  }
  const engine = vars['SONAR_CONTAINER_ENGINE'] ?? 'docker';
  if (!isEngine(engine)) {
    return { error: ENGINE_ERROR };
  }
  const coverage = parseCoverage(vars['SONAR_COVERAGE']);
  return coverage === undefined
    ? { error: COVERAGE_ERROR }
    : { sshHost, envFile, engine, coverage };
}

export function shellQuote(value: string): string {
  const escaped = value.replaceAll("'", "'\\''");
  return `'${escaped}'`;
}

export function sshInvocation(
  host: string,
  remoteCommand: string,
): { command: string; args: string[] } {
  return {
    command: 'ssh',
    args: ['-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '--', host, remoteCommand],
  };
}

/** Un dossier créé par `prepareScript`, jamais un autre : garde de `rm -rf` et de `tar -C`. */
export function isSafeRemoteDir(dir: string): boolean {
  return SAFE_DIR.test(dir) && !dir.includes('..');
}

function requireRemoteDir(dir: string): string {
  if (!isSafeRemoteDir(dir)) {
    throw new Error('dossier distant non conforme (attendu : dossier jetable prosperity-sonar.*)');
  }
  return shellQuote(dir);
}

function requireEnvFile(envFile: string): string {
  if (!ABSOLUTE_PATH.test(envFile) || envFile.includes('..')) {
    throw new Error('fichier d’environnement distant non conforme (chemin absolu attendu)');
  }
  return shellQuote(envFile);
}

export function parsePreflight(output: string): Preflight | { error: string } {
  const line = output.trim();
  const ok = PREFLIGHT_OK.exec(line);
  const [, uid, gid, envFile] = ok ?? [];
  if (uid !== undefined && gid !== undefined && envFile !== undefined) {
    return { uid: Number(uid), gid: Number(gid), envFile };
  }
  const message = PREFLIGHT_MESSAGES[line];
  return { error: message ?? 'sortie inattendue de la vérification distante' };
}

// Valeurs acceptées pour SONAR_HOST_URL côté serveur : https, ou http sur la boucle locale seulement.
const LOOPBACK_CASES = [
  'http://localhost',
  'http://localhost:*',
  'http://localhost/*',
  'http://127.0.0.1',
  'http://127.0.0.1:*',
  'http://127.0.0.1/*',
  "'http://[::1]'",
  "'http://[::1]:'*",
  "'http://[::1]/'*",
].join('|');

/** Vérifications sans effet de bord sur la machine distante ; sort un code, jamais une valeur du fichier. */
export function preflightScript(cfg: RemoteConfig): string {
  const engine = shellQuote(cfg.engine);
  return String.raw`set -u
f=${shellQuote(cfg.envFile)}
case "$f" in /*) ;; *) f="$HOME/$f" ;; esac
[ -r "$f" ] || { echo env-file-missing; exit 3; }
case "$(stat -c %a "$f")" in 600|400) ;; *) echo env-file-mode; exit 3 ;; esac
grep -q '^SONAR_HOST_URL=.' "$f" && grep -q '^SONAR_TOKEN=.' "$f" || { echo env-file-keys; exit 3; }
if grep -qE "^SONAR_(HOST_URL|TOKEN)=.*[[:space:]'\"]" "$f"; then echo env-file-format; exit 3; fi
url=$(sed -n 's/^SONAR_HOST_URL=//p' "$f" | head -n 1)
case "$url" in https://*|${LOOPBACK_CASES}) ;; *) echo host-url-refused; exit 3 ;; esac
command -v ${engine} >/dev/null 2>&1 || { echo engine-missing; exit 3; }
${engine} info >/dev/null 2>&1 || { echo engine-access; exit 3; }
echo "ok $(id -u) $(id -g) $f"
`;
}

/** Le scanner tourne sur la machine distante, avec le fichier d'environnement distant pour hôte et jeton. */
export function scannerScript(cfg: RemoteConfig, params: ScriptParams): string {
  requireRemoteDir(params.dir);
  const words = [
    cfg.engine,
    ...scannerRunArgs({
      engine: cfg.engine,
      image: params.image,
      root: params.dir,
      uid: params.uid,
      gid: params.gid,
      auth: ['--env-file', params.envFile],
      properties: [`-Dsonar.analysis.coverage=${cfg.coverage}`, '-Dsonar.scm.disabled=true'],
    }),
  ];
  requireEnvFile(params.envFile);
  return `set -eu\nexec ${words.map(shellQuote).join(' ')}\n`;
}

/** Lit l'adresse et le jeton dans le fichier distant ; le jeton va à `curl` par un fichier de configuration lu sur l'entrée. */
function curlScript(envFile: string, path: string, authenticated: boolean): string {
  const send = authenticated
    ? String.raw`tok=$(sed -n 's/^SONAR_TOKEN=//p' "$f" | head -n 1)
printf 'header = "Authorization: Bearer %s"\n' "$tok" | curl -fsS --max-time 30 -K - "$url${path}"`
    : `curl -fsS --max-time 15 "$url${path}"`;
  return String.raw`set -eu
f=${requireEnvFile(envFile)}
url=$(sed -n 's/^SONAR_HOST_URL=//p' "$f" | head -n 1 | sed 's#/*$##')
${send}
`;
}

export function pollScript(params: { envFile: string; taskId: string }): string {
  if (!TASK_ID.test(params.taskId)) {
    throw new Error('identifiant de tâche non conforme');
  }
  return curlScript(params.envFile, `/api/ce/task?id=${params.taskId}`, true);
}

export function versionScript(envFile: string): string {
  return curlScript(envFile, '/api/server/version', false);
}

/** Dossier jetable distant ; le chemin imprimé est ensuite validé par `isSafeRemoteDir`. */
export function prepareScript(): string {
  return 'set -eu\nmktemp -d -t prosperity-sonar.XXXXXX\n';
}

export function cleanupScript(dir: string): string {
  return `set -eu\nrm -rf -- ${requireRemoteDir(dir)}\n`;
}

/** Commande distante qui extrait l'archive reçue sur l'entrée standard dans le dossier jetable. */
export function uploadCommand(dir: string): string {
  return `tar -xf - --no-same-owner -C ${requireRemoteDir(dir)}`;
}

/** Archive des seules entrées demandées (jamais `.git`, `node_modules` ni les rapports volumineux). */
export function tarArgs(root: string, paths: readonly string[]): string[] {
  return ['-c', '-f', '-', '-C', root, ...paths];
}
