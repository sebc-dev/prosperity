// Squelette de la phase RED (TDD) : signatures du contrat, aucun comportement.
export interface LabelEvent {
  id: number;
  event: 'labeled' | 'unlabeled';
  actor: string;
  label: string;
  createdAt: string;
}
export interface RunInfo {
  createdAt: string;
  headSha: string;
  event: string;
  headBranch: string;
  headRepository: string;
}
export interface PullInfo {
  number: number;
  headSha: string;
  headRef: string;
  headRepository: string;
  baseOwner: string;
  labels: string[];
}
export interface ApprovalEvidence {
  repository: string;
  pr: number;
  headSha: string;
  pull: PullInfo;
  labelEvents: LabelEvent[];
  forcePushes: string[];
  runs: RunInfo[];
}

export function evidenceFromApi(
  _raw: { pull: unknown; eventPages: unknown; runPages: unknown },
  _ids: { repository: string; pr: number; headSha: string },
): ApprovalEvidence | undefined {
  throw new Error('non implémenté');
}

export function parseApprovalEvidence(_value: unknown): ApprovalEvidence | undefined {
  throw new Error('non implémenté');
}

export function collectApprovalEvidence(_opts: {
  repository: string;
  pr: number;
  headSha: string;
  env: NodeJS.ProcessEnv;
}): Promise<ApprovalEvidence> {
  return Promise.reject(new Error('non implémenté'));
}
