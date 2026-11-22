// Squelette de la phase RED (TDD) : signatures du contrat, aucun comportement.
import type { ApprovalEvidence } from './approval-evidence.ts';
import type { ApprovalsReport } from './verdict-rules.ts';

export const APPROVAL_KINDS = ['gate-change-approved', 'deps-approved'] as const;
export const VERIFIER = 'github-label-events@1';
export type ApprovalRejection =
  | 'approval-missing'
  | 'approval-removed'
  | 'approval-actor-not-allowed'
  | 'approval-stale'
  | 'approval-no-anchor'
  | 'approval-head-moved'
  | 'approval-evidence-invalid'
  | 'approvers-config-missing';
export interface ApproversConfig {
  allowlist: string[];
  labels: string[];
}

export function loadApproversConfig(_baseDir: string): Promise<ApproversConfig | undefined> {
  return Promise.reject(new Error('non implémenté'));
}

export function lastPushAnchor(_evidence: ApprovalEvidence): number | undefined {
  throw new Error('non implémenté');
}

export function decideApprovals(_input: {
  evidence: ApprovalEvidence;
  config: ApproversConfig;
}): Pick<ApprovalsReport, 'approved' | 'rejected' | 'approval'> {
  throw new Error('non implémenté');
}

export function judgeApprovals(_opts: {
  baseDir: string;
  headSha: string;
  pr: number;
  evidence: unknown;
  bootstrap: boolean;
}): Promise<ApprovalsReport> {
  return Promise.reject(new Error('non implémenté'));
}
