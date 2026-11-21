import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

export interface ToolResult {
  code: number;
  stdout: string;
  stderr: string;
}

export interface RunToolOptions {
  command: string;
  args: readonly string[];
  cwd: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 120_000;
const TOOLS_SECTION = /^\s*\[tools\]\s*$/;
const ANY_SECTION = /^\s*\[.+\]\s*$/;
const PIN_LINE = /^\s*(?:"([^"]+)"|([A-Za-z0-9_.-]+))\s*=\s*"([^"]*)"/;
const SEMVER = /\d+\.\d+\.\d+/;

/**
 * Lit les lignes `clé = "valeur"` de la section `[tools]` de `mise.toml`
 * (clés entre guillemets comprises, par exemple `"pipx:semgrep"`).
 */
export async function readMisePins(root: string): Promise<Map<string, string>> {
  const text = await readFile(join(root, 'mise.toml'), 'utf8');
  const pins = new Map<string, string>();
  let inTools = false;
  for (const line of text.split(/\r?\n/)) {
    if (TOOLS_SECTION.test(line)) {
      inTools = true;
      continue;
    }
    if (ANY_SECTION.test(line)) {
      inTools = false;
      continue;
    }
    if (!inTools) {
      continue;
    }
    const match = PIN_LINE.exec(line);
    const key = match?.[1] ?? match?.[2];
    const value = match?.[3];
    if (key !== undefined && value !== undefined) {
      pins.set(key, value);
    }
  }
  return pins;
}

/**
 * Lance un processus avec `spawn` sans shell : aucune interpolation possible,
 * stdout/stderr/code capturés, délai maximal appliqué (SIGKILL, code 124).
 */
export function runTool(opts: RunToolOptions): Promise<ToolResult> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return new Promise((resolve) => {
    const child = spawn(opts.command, [...opts.args], {
      cwd: opts.cwd,
      env: opts.env ?? process.env,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    let timedOut = false;
    let settled = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGKILL');
    }, timeoutMs);
    const finish = (code: number, extraStderr: string): void => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve({
        code,
        stdout: Buffer.concat(out).toString('utf8'),
        stderr: `${Buffer.concat(err).toString('utf8')}${extraStderr}`,
      });
    };
    child.stdout.on('data', (chunk: Buffer) => out.push(chunk));
    child.stderr.on('data', (chunk: Buffer) => err.push(chunk));
    child.on('error', (error: Error) => {
      finish(127, error.message);
    });
    child.on('close', (code: number | null) => {
      if (timedOut) {
        finish(124, `\ntimeout après ${String(timeoutMs)} ms`);
        return;
      }
      finish(code ?? 1, '');
    });
  });
}

/** Lance un outil épinglé par mise : `mise exec -- <tool> <args>`. */
export function runMiseTool(
  tool: string,
  args: readonly string[],
  opts: { cwd: string; env?: NodeJS.ProcessEnv; timeoutMs?: number },
): Promise<ToolResult> {
  return runTool({
    command: 'mise',
    args: ['exec', '--', tool, ...args],
    ...opts,
  });
}

/**
 * Compare la première version `x.y.z` de la sortie de l'outil au pin de
 * `mise.toml`. La clé du pin est le nom de l'outil.
 */
export async function verifyMiseToolVersion(
  root: string,
  tool: string,
  versionArgs: readonly string[],
): Promise<{ ok: boolean; found: string; expected: string }> {
  const pins = await readMisePins(root);
  const expected = pins.get(tool) ?? '';
  const result = await runMiseTool(tool, versionArgs, { cwd: root, timeoutMs: 30_000 });
  const found = SEMVER.exec(`${result.stdout}\n${result.stderr}`)?.[0] ?? '';
  return { ok: expected !== '' && found === expected, found, expected };
}
