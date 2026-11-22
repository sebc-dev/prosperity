import { stat } from 'node:fs/promises';
import { join } from 'node:path';
import { tail } from './backend.ts';
import type { Backend } from './backend.ts';
import {
  cleanupScript,
  isSafeRemoteDir,
  parsePreflight,
  pollScript,
  prepareScript,
  preflightScript,
  reportTaskScript,
  scannerScript,
  versionScript,
} from './remote-kit.ts';
import type { Preflight, RemoteConfig } from './remote-kit.ts';
import type { Failure } from './sonar-kit.ts';
import { sshRun, sshUpload } from './ssh.ts';

// Mode SSH : le scanner tourne sur la machine Sonar, d'où le serveur est joint sur sa boucle locale.

const SHELL = 'sh -s';
const SCAN_TIMEOUT_MS = 1_800_000;
// Seules ces entrées partent vers la machine distante : ni `.git`, ni `node_modules`, ni `.planning`.
const UPLOAD_PATHS = [
  'src',
  'quality',
  'test',
  'tsconfig.json',
  'package.json',
  'sonar-project.properties',
  'reports/sonar',
];

interface Session {
  cfg: RemoteConfig;
  image: string;
  root: string;
  identity: Preflight | undefined;
  dir: string;
}

const exists = (path: string): Promise<boolean> =>
  stat(path).then(
    () => true,
    () => false,
  );

async function uploadable(root: string): Promise<string[]> {
  const present = await Promise.all(UPLOAD_PATHS.map((path) => exists(join(root, path))));
  return UPLOAD_PATHS.filter((_path, index) => present[index] === true);
}

const run = (s: Session, text: string, timeoutMs?: number) =>
  sshRun(s.cfg.sshHost, SHELL, text, timeoutMs);

function identityOf(s: Session): Preflight {
  if (s.identity === undefined) {
    throw new Error('vérification distante non jouée');
  }
  return s.identity;
}

async function preflight(s: Session): Promise<Failure | undefined> {
  const ran = await run(s, preflightScript(s.cfg));
  const parsed = parsePreflight(ran.stdout);
  if ('error' in parsed) {
    return { error: ran.stdout.trim() === '' ? `ssh : ${tail(ran.stderr)}` : parsed.error };
  }
  s.identity = parsed;
  return undefined;
}

/** Dossier jetable distant, puis envoi des seules entrées utiles. */
async function stage(s: Session): Promise<Failure | undefined> {
  const made = await run(s, prepareScript());
  const dir = made.stdout.trim();
  if (made.code !== 0 || !isSafeRemoteDir(dir)) {
    return { error: `création du dossier distant impossible : ${tail(made.stderr)}` };
  }
  s.dir = dir;
  const sent = await sshUpload(s.cfg.sshHost, dir, s.root, await uploadable(s.root));
  return sent.code === 0
    ? undefined
    : { error: `envoi des sources impossible : ${tail(sent.stderr)}` };
}

async function scan(s: Session): Promise<Failure | undefined> {
  const staged = await stage(s);
  if (staged !== undefined) {
    return staged;
  }
  const { uid, gid, envFile } = identityOf(s);
  const params = { image: s.image, dir: s.dir, uid, gid, envFile };
  const ran = await run(s, scannerScript(s.cfg, params), SCAN_TIMEOUT_MS);
  if (ran.code === 0) {
    return undefined;
  }
  const output = tail(`${ran.stderr}\n${ran.stdout}`);
  return { error: `scanner en échec (code ${String(ran.code)}) :\n${output}` };
}

async function fetchTask(s: Session, taskId: string): Promise<unknown> {
  const ran = await run(s, pollScript({ envFile: identityOf(s).envFile, taskId }));
  if (ran.code !== 0) {
    throw new Error(`lecture de la tâche impossible (code ${String(ran.code)})`);
  }
  const body: unknown = JSON.parse(ran.stdout);
  return body;
}

function describe(s: Session): string[] {
  const dry = {
    image: s.image,
    dir: '/srv/prosperity-sonar.dryrun',
    uid: 1000,
    gid: 1000,
    envFile: '/home/utilisateur/.config/prosperity-sonar/env',
  };
  return [
    `mode SSH : scanner ${s.cfg.engine} sur « ${s.cfg.sshHost} » (aucune connexion en --dry-run)`,
    'jeton : lu sur la machine distante par --env-file, jamais transmis (SONAR_TOKEN=***)',
    `$ ssh ${s.cfg.sshHost} '${SHELL}' <<< (script de vérification, puis de préparation)`,
    `$ tar … | ssh ${s.cfg.sshHost} 'tar -xf - -C <dossier jetable>'`,
    `$ ssh ${s.cfg.sshHost} '${SHELL}' <<< (scanner)`,
    ...scannerScript(s.cfg, dry)
      .trimEnd()
      .split('\n')
      .map((line) => `  ${line}`),
  ];
}

export function remoteBackend(cfg: RemoteConfig, image: string, root: string): Backend {
  const s: Session = { cfg, image, root, identity: undefined, dir: '' };
  return {
    describe: () => describe(s),
    preflight: () => preflight(s),
    scan: () => scan(s),
    async serverVersion() {
      const ran = await run(s, versionScript(identityOf(s).envFile));
      return ran.code === 0 ? ran.stdout.trim() : undefined;
    },
    async readReportTask() {
      const ran = await run(s, reportTaskScript(s.dir));
      return ran.code === 0 ? ran.stdout : undefined;
    },
    fetchTask: (taskId) => fetchTask(s, taskId),
    dashboard: () => `projet « prosperity » du serveur Sonar de ${cfg.sshHost}`,
    async cleanup() {
      if (s.dir !== '') {
        await run(s, cleanupScript(s.dir));
        s.dir = '';
      }
    },
  };
}
