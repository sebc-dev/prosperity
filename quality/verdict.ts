import type { CheckResult, Issue } from './gate-report.ts';

export interface VerdictTarget {
  headSha: string;
  pr: number | undefined;
  gateConclusion: string;
  gateEvent: string;
  gatePath: string;
  runUrl: string;
}

export interface ApprovalsReport {
  approved: string[];
  rejected: { kind: string; reason: string }[];
  bootstrap: boolean;
  verifier: string;
  approval: { commit: string; principal: string; keyType: string; flags: number | null } | null;
}

export interface VerdictDecision {
  conclusion: 'success' | 'failure';
  reasons: string[];
  issues: Issue[];
}

export interface StatusBody {
  state: 'success' | 'failure';
  context: 'quality';
  description: string;
  target_url: string;
}

export type JudgeName = 'approvals' | 'integrity' | 'deps';

export interface VerdictDeps {
  target: VerdictTarget;
  baseDir: string;
  workDir: string;
  extractHead(sha: string): Promise<string>;
  judge(name: JudgeName, args: readonly string[]): Promise<unknown>;
  publish(sha: string, body: StatusBody): Promise<void>;
}

// Squelette RED : signatures finales, comportement volontairement faux.
export function readApprovalsReport(_value: unknown): ApprovalsReport | undefined {
  return undefined;
}

export function parseTarget(_payload: unknown): VerdictTarget | { error: string } {
  return { error: '?' };
}

export function decideVerdict(_input: {
  target: VerdictTarget;
  expectedGatePath: string;
  integrity: CheckResult | undefined;
  deps: CheckResult | undefined;
  approvals: ApprovalsReport | undefined;
}): VerdictDecision {
  return { conclusion: 'failure', reasons: ['?'], issues: [] };
}

export function statusPayload(_decision: VerdictDecision, _runUrl: string): StatusBody {
  return { state: 'failure', context: 'quality', description: '?', target_url: '' };
}

export function runVerdict(_deps: VerdictDeps): Promise<VerdictDecision> {
  return Promise.resolve({ conclusion: 'failure', reasons: ['?'], issues: [] });
}
