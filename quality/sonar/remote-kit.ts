import type { Engine } from './sonar-kit.ts';

export interface RemoteConfig {
  sshHost: string;
  envFile: string;
  engine: Engine;
  coverage: 'full' | 'unit';
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

// Squelette du cycle RED : signatures finales, comportement volontairement absent.
export function validateRemoteConfig(
  vars: Record<string, string | undefined>,
): RemoteConfig | { error: string } {
  return { error: String(Object.keys(vars).length) };
}

export function shellQuote(value: string): string {
  return value;
}

export function sshInvocation(
  host: string,
  remoteCommand: string,
): { command: string; args: string[] } {
  return { command: host, args: [remoteCommand] };
}

export function isSafeRemoteDir(dir: string): boolean {
  return dir === '';
}

export function parsePreflight(output: string): Preflight | { error: string } {
  return { error: output };
}

export function preflightScript(cfg: RemoteConfig): string {
  return cfg.sshHost;
}

export function scannerScript(cfg: RemoteConfig, params: ScriptParams): string {
  return `${cfg.sshHost}${params.dir}`;
}

export function pollScript(params: { envFile: string; taskId: string }): string {
  return params.envFile;
}

export function versionScript(envFile: string): string {
  return envFile;
}

export function prepareScript(): string {
  return '';
}

export function cleanupScript(dir: string): string {
  return dir;
}

export function uploadCommand(dir: string): string {
  return dir;
}

export function tarArgs(root: string, paths: readonly string[]): string[] {
  return [root, ...paths];
}
