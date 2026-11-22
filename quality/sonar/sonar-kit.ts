import { isRecord } from '../tools.ts';

// Fonctions pures de `pnpm sonar` (D-16) : aucune E/S, aucune lecture de l'environnement du processus.
// Aucun message d'erreur ne cite l'adresse du serveur ni le jeton.

export type Engine = 'docker' | 'podman';
export type Coverage = 'full' | 'unit';

export interface SonarConfig {
  hostUrl: string;
  token: string;
  coverage: Coverage;
  engine: Engine;
}

export interface Failure {
  error: string;
}

export interface ScannerOptions {
  image: string;
  root: string;
  uid: number;
  gid: number;
  scmDisabled: boolean;
}

export interface Invocation {
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface TaskDecision {
  state: 'pending' | 'success' | 'failed';
  status: string;
}

export interface RunArgsOptions {
  engine: Engine;
  image: string;
  root: string;
  uid: number;
  gid: number;
  /** Façon de transmettre l'hôte et le jeton au conteneur : `-e NOM` (sans valeur) ou `--env-file`. */
  auth: readonly string[];
  properties: readonly string[];
}

export const COVERAGE_ERROR = 'SONAR_COVERAGE doit valoir full ou unit';
export const ENGINE_ERROR =
  'SONAR_CONTAINER_ENGINE doit désigner un moteur de conteneur : docker ou podman';

const FORBIDDEN_KEYS = new Set(['sonar.host.url', 'sonar.token', 'sonar.login', 'sonar.password']);
const FORBIDDEN_PREFIXES = ['sonar.scanner.proxy', 'http.proxy', 'https.proxy'];
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);
const IMAGE_PATTERN =
  /^docker\.io\/sonarsource\/sonar-scanner-cli:[A-Za-z0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}$/;
const SERVER_HOSTED_STATUSES = new Set(['PENDING', 'IN_PROGRESS']);

const fail = (error: string): Failure => ({ error });

export function isFailure(value: unknown): value is Failure {
  return isRecord(value) && typeof value['error'] === 'string';
}

export function isEngine(value: string): value is Engine {
  return value === 'docker' || value === 'podman';
}

function trimTrailingSlashes(text: string): string {
  let end = text.length;
  while (end > 0 && text[end - 1] === '/') {
    end -= 1;
  }
  return text.slice(0, end);
}

/** Lit `CLÉ=valeur` ; ignore lignes vides et commentaires `#` ; retire une paire de guillemets. */
export function parseEnvFile(text: string): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const eq = line.indexOf('=');
    const name = line.slice(0, eq).trim();
    if (eq < 1 || !/^[A-Za-z_]\w*$/.test(name)) {
      continue;
    }
    const raw = line.slice(eq + 1).trim();
    const quoted = /^(["'])(.*)\1$/.exec(raw);
    vars[name] = quoted?.[2] ?? raw;
  }
  return vars;
}

function checkHostUrl(
  raw: string | undefined,
  allowInsecure: boolean,
): { hostUrl: string } | Failure {
  if (raw === undefined || raw.trim() === '') {
    return fail('SONAR_HOST_URL manquant');
  }
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    return fail('SONAR_HOST_URL n’est pas une adresse valide');
  }
  if (url.search !== '' || url.hash !== '' || url.username !== '' || url.password !== '') {
    return fail('SONAR_HOST_URL ne doit porter ni requête, ni fragment, ni identifiants');
  }
  const secure = url.protocol === 'https:';
  const tolerated = url.protocol === 'http:' && (LOOPBACK_HOSTS.has(url.hostname) || allowInsecure);
  if (!secure && !tolerated) {
    return fail(
      'SONAR_HOST_URL doit être en https:// (http:// seulement sur la boucle locale, ou avec SONAR_ALLOW_INSECURE_HTTP=1)',
    );
  }
  return { hostUrl: trimTrailingSlashes(`${url.origin}${url.pathname}`) };
}

/** `undefined` quand la valeur n'est ni `full` ni `unit` ; une valeur absente donne `full`. */
export function parseCoverage(value: string | undefined): Coverage | undefined {
  if (value === undefined || value === 'full') {
    return 'full';
  }
  return value === 'unit' ? 'unit' : undefined;
}

function pickEngine(
  requested: string | undefined,
  engines: readonly string[],
): { engine: Engine } | Failure {
  if (requested !== undefined && requested !== '') {
    if (!isEngine(requested)) {
      return fail(ENGINE_ERROR);
    }
    return engines.includes(requested)
      ? { engine: requested }
      : fail(`le moteur de conteneur demandé (${requested}) est introuvable dans le PATH`);
  }
  const found = ['podman', 'docker'].find((name) => engines.includes(name));
  return found !== undefined && isEngine(found)
    ? { engine: found }
    : fail('aucun moteur de conteneur (podman ou docker) dans le PATH');
}

/** Valide la configuration (mode local) ; l'erreur ne cite jamais l'adresse ni le jeton. */
export function validateSonarConfig(
  vars: Record<string, string | undefined>,
  engines: readonly string[],
): SonarConfig | Failure {
  const host = checkHostUrl(vars['SONAR_HOST_URL'], vars['SONAR_ALLOW_INSECURE_HTTP'] === '1');
  if (isFailure(host)) {
    return host;
  }
  const token = vars['SONAR_TOKEN'];
  if (token === undefined || token === '' || /\s/.test(token)) {
    return fail('SONAR_TOKEN manquant, vide ou contenant une espace');
  }
  const coverage = parseCoverage(vars['SONAR_COVERAGE']);
  if (coverage === undefined) {
    return fail(COVERAGE_ERROR);
  }
  const picked = pickEngine(vars['SONAR_CONTAINER_ENGINE'], engines);
  if (isFailure(picked)) {
    return picked;
  }
  return { hostUrl: host.hostUrl, token, coverage, engine: picked.engine };
}

/** Contenu de `quality/sonar/scanner.json` : seule l'image officielle épinglée par digest passe. */
export function readScannerImage(value: unknown): { image: string } | Failure {
  const image = isRecord(value) ? value['image'] : undefined;
  if (typeof image !== 'string' || !IMAGE_PATTERN.test(image) || image.includes(':latest@')) {
    return fail(
      'image du scanner absente, non officielle ou non épinglée par digest (quality/sonar/scanner.json)',
    );
  }
  return { image };
}

function isForbiddenKey(key: string): boolean {
  return FORBIDDEN_KEYS.has(key) || FORBIDDEN_PREFIXES.some((prefix) => key.startsWith(prefix));
}

/** Clés de `sonar-project.properties` qui pourraient détourner l'hôte, le jeton ou le réseau. */
export function forbiddenProperties(propertiesText: string): string[] {
  const found = new Set<string>();
  for (const raw of propertiesText.split(/\r?\n/)) {
    const line = raw.trim();
    if (line === '' || line.startsWith('#') || line.startsWith('!')) {
      continue;
    }
    const key = /^[^\s=:]+/.exec(line)?.[0];
    if (key !== undefined && isForbiddenKey(key)) {
      found.add(key);
    }
  }
  return [...found];
}

const underRoot = (root: string): string => `${trimTrailingSlashes(root)}/`;

export function relativizeLcov(text: string, root: string): string {
  const base = underRoot(root);
  return text
    .split('\n')
    .map((line) => (line.startsWith(`SF:${base}`) ? `SF:${line.slice(3 + base.length)}` : line))
    .join('\n');
}

export function relativizeEslintReport(value: unknown, root: string): unknown {
  if (!Array.isArray(value)) {
    return value;
  }
  const base = underRoot(root);
  const entries: unknown[] = value;
  return entries.map((entry) => {
    const filePath = isRecord(entry) ? entry['filePath'] : undefined;
    return isRecord(entry) && typeof filePath === 'string' && filePath.startsWith(base)
      ? { ...entry, filePath: filePath.slice(base.length) }
      : entry;
  });
}

/** Environnement des processus de lint et de tests : le jeton n'est transmis qu'au scanner. */
export function childEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return Object.fromEntries(
    Object.entries(env).filter(([name]) => name !== 'SONAR_TOKEN' && name !== 'SONAR_HOST_URL'),
  );
}

/** Arguments de `<moteur> run` communs au mode local et au mode SSH. */
export function scannerRunArgs(o: RunArgsOptions): string[] {
  const user =
    o.engine === 'podman' ? ['--userns=keep-id'] : ['--user', `${String(o.uid)}:${String(o.gid)}`];
  return [
    'run',
    '--rm',
    '--network',
    'host',
    ...user,
    ...o.auth,
    '-e',
    'SONAR_USER_HOME=/usr/src/reports/sonar/cache',
    '-v',
    `${o.root}:/usr/src`,
    o.image,
    ...o.properties,
  ];
}

/** Mode local : l'hôte et le jeton passent par l'environnement du processus (`-e NOM`, sans valeur). */
export function scannerInvocation(cfg: SonarConfig, opts: ScannerOptions): Invocation {
  const args = scannerRunArgs({
    engine: cfg.engine,
    image: opts.image,
    root: opts.root,
    uid: opts.uid,
    gid: opts.gid,
    auth: ['-e', 'SONAR_HOST_URL', '-e', 'SONAR_TOKEN'],
    properties: [
      `-Dsonar.host.url=${cfg.hostUrl}`,
      `-Dsonar.analysis.coverage=${cfg.coverage}`,
      ...(opts.scmDisabled ? ['-Dsonar.scm.disabled=true'] : []),
    ],
  });
  return {
    command: cfg.engine,
    args,
    env: { SONAR_HOST_URL: cfg.hostUrl, SONAR_TOKEN: cfg.token },
  };
}

export function redactInvocation(inv: { command: string; args: string[] }, token: string): string {
  const line = [inv.command, ...inv.args].join(' ');
  return token === '' ? line : line.split(token).join('***');
}

/** Lit l'identifiant de la tâche du serveur dans `report-task.txt` ; refuse tout ce qui n'en est pas un. */
export function parseReportTask(text: string): { ceTaskId: string } | undefined {
  const id = /^ceTaskId=([A-Za-z0-9_-]+)\s*$/m.exec(text)?.[1];
  return id === undefined ? undefined : { ceTaskId: id };
}

/** Réponse de `GET /api/ce/task` : en cours, réussie ou perdue (FAILED, CANCELED, inconnue). */
export function ceTaskDecision(response: unknown): TaskDecision {
  const task = isRecord(response) ? response['task'] : undefined;
  const status = isRecord(task) ? task['status'] : undefined;
  if (typeof status !== 'string') {
    return { state: 'failed', status: 'illisible' };
  }
  if (status === 'SUCCESS') {
    return { state: 'success', status };
  }
  return { state: SERVER_HOSTED_STATUSES.has(status) ? 'pending' : 'failed', status };
}
