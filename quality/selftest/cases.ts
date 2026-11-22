import type { CheckResult } from '../gate-report.ts';

export type InstallMode = 'frozen' | 'link';

export interface CaseExpectation {
  check: string;
  rule: string;
  install: InstallMode;
}

export interface SelftestCase extends CaseExpectation {
  id: string;
  dir: string;
  kind: 'patch' | 'apply';
}

export interface CaseResult {
  id: string;
  check: string;
  rule: string;
  status: 'passed' | 'failed';
  reason: string;
  detail?: string;
  duration_ms: number;
}

/** Erreur d'usage (sélection `--case` invalide) : la CLI sort en code 2 avant tout worktree. */
export class SelectionError extends Error {}

export function matchesExpected(
  _result: Pick<CheckResult, 'status' | 'issues'>,
  _expected: Pick<CaseExpectation, 'rule'>,
): boolean {
  return false;
}

export function selectCases(_ids: readonly string[], _spec: string | undefined): string[] {
  return [];
}
