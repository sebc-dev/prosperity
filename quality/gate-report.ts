import { mkdir, rename, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';

export type Severity = 'blocking' | 'advisory';
type CheckStatus = 'passed' | 'failed' | 'skipped';
export type Profile = 'push' | 'full';

export interface Issue {
  rule: string;
  message: string;
  file?: string;
  line?: number;
}

export interface CheckResult {
  check: string;
  tool: string;
  version: string;
  severity: Severity;
  passed: boolean;
  status: CheckStatus;
  skipped_reason?: string;
  note?: string;
  issues: Issue[];
  duration_ms: number;
}

export interface GateReport {
  profile: Profile;
  commit: string;
  base: string;
  generated_at: string;
  verdict: 'pass' | 'fail';
  checks: CheckResult[];
}

export interface CheckContext {
  root: string;
  profile: Profile;
  base: string;
  inCi: boolean;
  env: NodeJS.ProcessEnv;
  /** Vrai quand le check figure explicitement dans `--only`. */
  selected: boolean;
}

export interface CheckDefinition {
  id: string;
  tool: string;
  severity: Severity;
  push: 'run' | 'skip-ci-only';
  run(ctx: CheckContext): Promise<CheckResult>;
}

const CI_ONLY_REASON = 'ci-only';

function blocksVerdict(profile: Profile, result: CheckResult, inCi: boolean): boolean {
  if (result.severity !== 'blocking') {
    return false;
  }
  if (result.status === 'failed') {
    return true;
  }
  if (result.status === 'skipped') {
    // Profil `full` en CI : aucun saut silencieux d'un check bloquant (D-12).
    if (profile === 'full' && inCi) {
      return true;
    }
    return result.skipped_reason !== CI_ONLY_REASON;
  }
  return false;
}

/**
 * Verdict pur : un check `advisory` n'influe jamais ; un bloquant `failed` fait
 * échouer ; un bloquant `skipped` fait échouer sauf en profil `push` hors CI
 * avec la raison `ci-only`.
 */
export function computeVerdict(
  profile: Profile,
  results: readonly CheckResult[],
  inCi: boolean,
): 'pass' | 'fail' {
  return results.some((result) => blocksVerdict(profile, result, inCi)) ? 'fail' : 'pass';
}

/**
 * Écriture atomique : fichier temporaire dans le même dossier puis `rename`,
 * pour qu'un lecteur ne voie jamais de rapport partiel.
 */
export async function writeJsonAtomic(path: string, data: unknown): Promise<void> {
  const dir = dirname(path);
  await mkdir(dir, { recursive: true });
  const tmp = join(dir, `.${basename(path)}.${String(process.pid)}.tmp`);
  await writeFile(tmp, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  await rename(tmp, path);
}

export function writeGateReport(path: string, report: GateReport): Promise<void> {
  return writeJsonAtomic(path, report);
}
