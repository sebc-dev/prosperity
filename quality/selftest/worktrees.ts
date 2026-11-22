import { randomBytes } from 'node:crypto';
import { rmSync } from 'node:fs';
import { rm, rmdir } from 'node:fs/promises';
import { basename, dirname } from 'node:path';
import { runTool } from '../tools.ts';

/** Dossier parent des worktrees d'un run : `mkdtemp` sur ce préfixe. */
export const RUN_DIR_PREFIX = 'gate-selftest-';

// `selftest-<étiquette>-<pid du lanceur>-<6 hexadécimaux>` : le pid dit si le lanceur est encore là.
const WORKTREE_NAME = /^selftest-.+-(\d+)-[0-9a-f]{6}$/;

// Worktrees et dossiers de run vivants, pour qu'un signal d'arrêt puisse les nettoyer.
const liveWorktrees = new Set<string>();
const liveRunDirs = new Set<string>();

// Les ajouts et retraits de worktree partagent le dossier git commun : on les sérialise.
let queueTail: Promise<void> = Promise.resolve();

function serialized<T>(task: () => Promise<T>): Promise<T> {
  const next = queueTail.then(task);
  queueTail = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

export function worktreeName(label: string): string {
  return `selftest-${label}-${String(process.pid)}-${randomBytes(3).toString('hex')}`;
}

/** Crée un worktree détaché au commit `ref` ; lève avec la sortie d'erreur de git sinon. */
export function addWorktree(root: string, dir: string, ref: string): Promise<void> {
  return serialized(async () => {
    const outcome = await runTool({
      command: 'git',
      args: ['worktree', 'add', '--detach', '--quiet', dir, ref],
      cwd: root,
      timeoutMs: 120_000,
    });
    if (outcome.code !== 0) {
      throw new Error(`git worktree add a échoué : ${outcome.stderr.trim()}`);
    }
    liveWorktrees.add(dir);
  });
}

export function trackRunDir(dir: string): void {
  liveRunDirs.add(dir);
}

export function untrackRunDir(dir: string): void {
  liveRunDirs.delete(dir);
}

/** Retire un worktree (échec silencieux : c'est un nettoyage), son dossier, puis prune. */
export function removeWorktree(root: string, dir: string): Promise<void> {
  return serialized(async () => {
    await runTool({
      command: 'git',
      args: ['worktree', 'remove', '--force', dir],
      cwd: root,
      timeoutMs: 120_000,
    });
    await rm(dir, { recursive: true, force: true });
    await runTool({ command: 'git', args: ['worktree', 'prune'], cwd: root, timeoutMs: 60_000 });
    liveWorktrees.delete(dir);
  });
}

/**
 * Variante synchrone, pour un gestionnaire de signal : supprime les dossiers créés par ce
 * processus. Les entrées de worktree restantes sont prunées au démarrage suivant.
 */
export function removeAllWorktreesSync(): void {
  for (const dir of [...liveWorktrees.keys(), ...liveRunDirs]) {
    rmSync(dir, { recursive: true, force: true });
  }
  liveWorktrees.clear();
  liveRunDirs.clear();
}

async function listWorktrees(root: string): Promise<string[]> {
  const outcome = await runTool({
    command: 'git',
    args: ['worktree', 'list', '--porcelain'],
    cwd: root,
    timeoutMs: 60_000,
  });
  return outcome.stdout
    .split('\n')
    .filter((line) => line.startsWith('worktree '))
    .map((line) => line.slice('worktree '.length));
}

function isPidAlive(pid: number): boolean {
  if (pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error instanceof Error && 'code' in error && error.code === 'EPERM';
  }
}

function isStale(dir: string): boolean {
  const match = WORKTREE_NAME.exec(basename(dir));
  const pid = Number.parseInt(match?.[1] ?? '', 10);
  return match !== null && !isPidAlive(pid);
}

/**
 * Prune les entrées dont le dossier a disparu, puis retire les worktrees `selftest-*` dont le
 * lanceur est mort (exécution interrompue). Ceux d'un lanceur vivant (autre run en parallèle)
 * sont laissés tels quels. Renvoie les dossiers retirés.
 */
export async function cleanupStaleWorktrees(root: string): Promise<string[]> {
  await runTool({ command: 'git', args: ['worktree', 'prune'], cwd: root, timeoutMs: 60_000 });
  const stale = (await listWorktrees(root)).filter(isStale);
  for (const dir of stale) {
    await removeWorktree(root, dir);
    if (basename(dirname(dir)).startsWith(RUN_DIR_PREFIX)) {
      await rmdir(dirname(dir)).catch(() => undefined);
    }
  }
  return stale;
}
