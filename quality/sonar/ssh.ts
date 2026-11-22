import { spawn } from 'node:child_process';
import type { Readable } from 'node:stream';
import type { ToolResult } from '../tools.ts';
import { childEnv } from './sonar-kit.ts';
import { sshInvocation, tarArgs, uploadCommand } from './remote-kit.ts';

const DEFAULT_TIMEOUT_MS = 120_000;
const TAR = '/usr/bin/tar';

function collect(stream: Readable): () => string {
  const chunks: Buffer[] = [];
  stream.on('data', (chunk: Buffer) => chunks.push(chunk));
  return () => Buffer.concat(chunks).toString('utf8');
}

/**
 * `ssh <hôte> <commande>` sans shell local ; `input` (texte) est envoyé sur l'entrée standard, ce qui
 * garde les scripts hors de la liste des processus de la machine distante. Aucun jeton n'y passe.
 */
export function sshRun(
  host: string,
  remoteCommand: string,
  input = '',
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<ToolResult> {
  const inv = sshInvocation(host, remoteCommand);
  return new Promise((resolve) => {
    const child = spawn(inv.command, inv.args, {
      env: childEnv(process.env),
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: timeoutMs,
    });
    const stdout = collect(child.stdout);
    const stderr = collect(child.stderr);
    child.on('error', (error: Error) => {
      resolve({ code: 127, stdout: '', stderr: error.message });
    });
    child.on('close', (code: number | null) => {
      resolve({ code: code ?? 124, stdout: stdout(), stderr: stderr() });
    });
    child.stdin.on('error', () => undefined);
    child.stdin.end(input);
  });
}

/** Archive locale (`tar`) envoyée vers le dossier jetable distant, sans fichier intermédiaire. */
export function sshUpload(
  host: string,
  dir: string,
  root: string,
  paths: readonly string[],
): Promise<ToolResult> {
  const inv = sshInvocation(host, uploadCommand(dir));
  return new Promise((resolve) => {
    const maker = spawn(TAR, tarArgs(root, paths), {
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const taker = spawn(inv.command, inv.args, {
      env: childEnv(process.env),
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 600_000,
    });
    const makerErr = collect(maker.stderr);
    const takerErr = collect(taker.stderr);
    let makerCode = 0;
    maker.on('close', (code: number | null) => {
      makerCode = code ?? 1;
    });
    maker.on('error', () => {
      makerCode = 127;
      taker.stdin.end();
    });
    taker.on('error', (error: Error) => {
      resolve({ code: 127, stdout: '', stderr: error.message });
    });
    taker.on('close', (code: number | null) => {
      const failed = makerCode !== 0 || (code ?? 1) !== 0;
      resolve({ code: failed ? 1 : 0, stdout: '', stderr: `${makerErr()}${takerErr()}` });
    });
    taker.stdin.on('error', () => undefined);
    maker.stdout.pipe(taker.stdin);
  });
}
