import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { Backend } from './backend.ts';
import { loadMode } from './config.ts';
import { localBackend } from './local.ts';
import { remoteBackend } from './remote.ts';
import { produceReports } from './reports.ts';
import { forbiddenProperties, isFailure, parseReportTask, readScannerImage } from './sonar-kit.ts';
import type { Coverage } from './sonar-kit.ts';
import { waitForTask } from './wait.ts';

// `pnpm sonar` (D-16) : analyse SonarQube advisory, à la demande. Aucun check de `pnpm quality` ne la
// lit, aucun workflow GitHub ne la lance, elle refuse de tourner en CI. Sortie 0 : analyse traitée par
// le serveur (ou, en --dry-run, rapports produits) ; 1 : rapport manquant, scanner ou tâche en échec ;
// 2 : configuration refusée.

const ROOT = join(import.meta.dirname, '..', '..');
const POLL_INTERVAL_MS = 5000;
const POLL_TIMEOUT_MS = 600_000;

const say = (line: string): void => {
  process.stdout.write(`${line}\n`);
};
const complain = (line: string): void => {
  process.stderr.write(`${line}\n`);
};

/** Image épinglée et propriétés du projet : refus (sortie 2) au moindre écart. */
async function checkProject(): Promise<{ image: string } | { error: string }> {
  const scanner: unknown = JSON.parse(
    await readFile(join(ROOT, 'quality', 'sonar', 'scanner.json'), 'utf8'),
  );
  const image = readScannerImage(scanner);
  if (isFailure(image)) {
    return image;
  }
  const keys = forbiddenProperties(await readFile(join(ROOT, 'sonar-project.properties'), 'utf8'));
  return keys.length === 0
    ? image
    : { error: `sonar-project.properties ne doit pas définir : ${keys.join(', ')}` };
}

/** Attend la tâche du serveur ; 0 seulement quand elle est SUCCESS. */
async function awaitServer(backend: Backend): Promise<number> {
  const version = await backend.serverVersion();
  say(`serveur Sonar : version ${version ?? 'inconnue'}`);
  const task = parseReportTask((await backend.readReportTask()) ?? '');
  if (task === undefined) {
    complain('report-task.txt introuvable ou sans ceTaskId : analyse non confirmée');
    return 1;
  }
  const outcome = await waitForTask({
    fetchTask: () => backend.fetchTask(task.ceTaskId),
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    now: () => Date.now(),
    intervalMs: POLL_INTERVAL_MS,
    timeoutMs: POLL_TIMEOUT_MS,
  });
  if (outcome.state !== 'success') {
    complain(`analyse non traitée : ${outcome.state} (${outcome.status})`);
    return 1;
  }
  say(`analyse traitée (SUCCESS) : ${backend.dashboard()}`);
  return 0;
}

async function analyze(backend: Backend, coverage: Coverage, dryRun: boolean): Promise<number> {
  const preflight = dryRun ? undefined : await backend.preflight();
  if (preflight !== undefined) {
    complain(preflight.error);
    return 1;
  }
  const reports = await produceReports(ROOT, coverage);
  if (reports !== undefined) {
    complain(reports.error);
    return 1;
  }
  if (dryRun) {
    backend.describe().forEach(say);
    return 0;
  }
  const scan = await backend.scan();
  if (scan !== undefined) {
    complain(scan.error);
    return 1;
  }
  return awaitServer(backend);
}

export async function runSonar(argv: readonly string[], env: NodeJS.ProcessEnv): Promise<number> {
  if ((env['CI'] ?? '') !== '' || (env['GITHUB_ACTIONS'] ?? '') !== '') {
    complain('pnpm sonar ne tourne jamais en CI : analyse advisory du homelab (D-16, D-13)');
    return 2;
  }
  const mode = await loadMode(ROOT, env);
  if (isFailure(mode)) {
    complain(mode.error);
    return 2;
  }
  const project = await checkProject();
  if (isFailure(project)) {
    complain(project.error);
    return 2;
  }
  const image = project.image;
  const backend =
    mode.kind === 'ssh'
      ? remoteBackend(mode.cfg, image, ROOT)
      : localBackend(mode.cfg, image, ROOT);
  try {
    return await analyze(backend, mode.cfg.coverage, argv.includes('--dry-run'));
  } finally {
    await backend.cleanup();
  }
}

if (import.meta.main) {
  process.exitCode = await runSonar(process.argv.slice(2), process.env);
}
