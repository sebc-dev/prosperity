export type Engine = 'docker' | 'podman';

export interface SonarConfig {
  hostUrl: string;
  token: string;
  coverage: 'full' | 'unit';
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

// Squelette du cycle RED : signatures finales, comportement volontairement absent.
export function parseEnvFile(text: string): Record<string, string> {
  return { text };
}

export function validateSonarConfig(
  vars: Record<string, string | undefined>,
  engines: readonly string[],
): SonarConfig | Failure {
  return { error: `${String(Object.keys(vars).length)} ${String(engines.length)}` };
}

export function readScannerImage(value: unknown): string | Failure {
  return { error: typeof value };
}

export function forbiddenProperties(propertiesText: string): string[] {
  return [propertiesText];
}

export function relativizeLcov(text: string, root: string): string {
  return `${root}${text}`;
}

export function relativizeEslintReport(value: unknown, root: string): unknown {
  return [value, root];
}

export function childEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return env;
}

export function scannerInvocation(cfg: SonarConfig, opts: ScannerOptions): Invocation {
  return { command: cfg.engine, args: [opts.image], env: {} };
}

export function redactInvocation(inv: { command: string; args: string[] }, token: string): string {
  return `${inv.command}${token}`;
}

export function parseReportTask(text: string): { ceTaskId: string } | undefined {
  return { ceTaskId: text };
}

export function ceTaskDecision(response: unknown): TaskDecision {
  return { state: 'pending', status: typeof response };
}
