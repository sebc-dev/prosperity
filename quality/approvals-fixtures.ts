import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { ApprovalEvidence, LabelEvent, RunInfo } from './approval-evidence.ts';
import { decideApprovals } from './approvals.ts';
import type { ApproversConfig } from './approvals.ts';

export const SHA = 'a'.repeat(40);
export const GATE = 'gate-change-approved';
export const DEPS = 'deps-approved';
export const CONFIG: ApproversConfig = { allowlist: ['sebc-dev'], labels: [GATE, DEPS] };
export const ANCHOR = '2026-11-22T10:00:00Z';
export const AFTER = '2026-11-22T10:05:00Z';
export const BEFORE = '2026-11-22T09:55:00Z';

export const run = (over: Partial<RunInfo> = {}): RunInfo => ({
  createdAt: ANCHOR,
  headSha: SHA,
  event: 'pull_request',
  headBranch: 'feat/x',
  headRepository: 'o/r',
  ...over,
});

export function labelEvent(over: Partial<LabelEvent> = {}): LabelEvent {
  return {
    id: 1,
    event: 'labeled',
    actor: 'sebc-dev',
    label: DEPS,
    createdAt: AFTER,
    ...over,
  };
}

export function evidence(over: Partial<ApprovalEvidence> = {}): ApprovalEvidence {
  return {
    repository: 'o/r',
    pr: 300,
    headSha: SHA,
    pull: {
      number: 300,
      headSha: SHA,
      headRef: 'feat/x',
      headRepository: 'o/r',
      baseOwner: 'o',
      labels: [GATE, DEPS],
    },
    labelEvents: [],
    forcePushes: [],
    runs: [run()],
    ...over,
  };
}

export const decide = (e: ApprovalEvidence, config: ApproversConfig = CONFIG) =>
  decideApprovals({ evidence: e, config });
export const reasons = (e: ApprovalEvidence) => decide(e).rejected.map((r) => [r.kind, r.reason]);

export async function writeConfig(dir: string, content: unknown): Promise<void> {
  await mkdir(join(dir, 'quality'), { recursive: true });
  await writeFile(join(dir, 'quality', 'approvers.json'), JSON.stringify(content));
}
