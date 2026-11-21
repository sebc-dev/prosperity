import type { CheckResult, Issue, Severity } from './gate-report.ts';

export interface CheckMeta {
  id: string;
  tool: string;
  severity: Severity;
}

export interface ResultPartial {
  status: 'passed' | 'failed';
  version: string;
  issues: Issue[];
  note?: string;
}

/** Assemble un `CheckResult` à partir de l'identité du check et du résultat partiel. */
export function buildResult(meta: CheckMeta, partial: ResultPartial, start: number): CheckResult {
  return {
    check: meta.id,
    tool: meta.tool,
    severity: meta.severity,
    passed: partial.status === 'passed',
    duration_ms: Date.now() - start,
    ...partial,
  };
}

/** Échec porteur d'une seule issue (outil absent, version fausse, sortie illisible). */
export function failedResult(
  meta: CheckMeta,
  version: string,
  issue: Issue,
  start: number,
): CheckResult {
  return buildResult(meta, { status: 'failed', version, issues: [issue] }, start);
}

export function versionMismatchIssue(tool: string, found: string, expected: string): Issue {
  return {
    rule: 'tool-version-mismatch',
    message: `${tool} ${found || 'introuvable'} trouvé, ${expected || 'aucun pin'} attendu`,
  };
}

export function toolErrorIssue(tool: string, code: number, stderr: string): Issue {
  return {
    rule: 'tool-error',
    message: `${tool} a échoué (code ${String(code)}) : ${stderr.trim().slice(0, 300)}`,
  };
}
