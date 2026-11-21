import type { CheckResult, Issue } from './gate-report.ts';
import { isRecord } from './tools.ts';

export interface VerdictTarget {
  headSha: string;
  pr: number | undefined;
  gateConclusion: string;
  gateEvent: string;
  gatePath: string;
  runUrl: string;
}

/** Schéma de `reports/approvals.json`, fixé à l'identique dans le plan du juge d'approbation. */
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

export interface DecisionInput {
  target: VerdictTarget;
  expectedGatePath: string;
  integrity: CheckResult | undefined;
  deps: CheckResult | undefined;
  approvals: ApprovalsReport | undefined;
}

export const EXPECTED_GATE_PATH = '.github/workflows/quality.yml';
const SHA_PATTERN = /^[0-9a-f]{40}$/;
const DESCRIPTION_MAX = 140;

// --- Lecture de données non fiables -----------------------------------------

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function readRejected(value: unknown): ApprovalsReport['rejected'] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const rejected: ApprovalsReport['rejected'] = [];
  const entries: unknown[] = value;
  for (const entry of entries) {
    if (
      !isRecord(entry) ||
      typeof entry['kind'] !== 'string' ||
      typeof entry['reason'] !== 'string'
    ) {
      return undefined;
    }
    rejected.push({ kind: entry['kind'], reason: entry['reason'] });
  }
  return rejected;
}

/** `null` est une valeur valide (aucune approbation) ; `undefined` signale une forme invalide. */
function readApproval(value: unknown): ApprovalsReport['approval'] | undefined {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    return undefined;
  }
  const { commit, principal, keyType, flags } = value;
  const valid =
    typeof commit === 'string' &&
    typeof principal === 'string' &&
    typeof keyType === 'string' &&
    (flags === null || typeof flags === 'number');
  return valid ? { commit, principal, keyType, flags } : undefined;
}

/** Un rapport hors schéma (champ requis absent ou de mauvais type) vaut rapport absent. */
export function readApprovalsReport(value: unknown): ApprovalsReport | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { approved, bootstrap, verifier } = value;
  const rejected = readRejected(value['rejected']);
  const approval = readApproval(value['approval']);
  const valid =
    isStringArray(approved) &&
    typeof bootstrap === 'boolean' &&
    typeof verifier === 'string' &&
    rejected !== undefined &&
    approval !== undefined;
  return valid ? { approved, rejected, bootstrap, verifier, approval } : undefined;
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

/** `{ pr: undefined }` : aucune PR listée (fork) ; `undefined` : forme invalide. */
function readPullRequest(pulls: unknown): { pr: number | undefined } | undefined {
  if (pulls === undefined || pulls === null) {
    return { pr: undefined };
  }
  if (!Array.isArray(pulls)) {
    return undefined;
  }
  const first: unknown = pulls[0];
  if (first === undefined) {
    return { pr: undefined };
  }
  const number = isRecord(first) ? first['number'] : undefined;
  return typeof number === 'number' && Number.isInteger(number) && number > 0
    ? { pr: number }
    : undefined;
}

/** Charge `workflow_run` : SHA de 40 hexadécimaux et numéro de PR entier, sinon erreur. */
export function parseTarget(payload: unknown): VerdictTarget | { error: string } {
  const run = isRecord(payload) ? payload['workflow_run'] : undefined;
  if (!isRecord(run)) {
    return { error: 'invalid-payload' };
  }
  const sha = run['head_sha'];
  if (typeof sha !== 'string' || !SHA_PATTERN.test(sha)) {
    return { error: 'invalid-head-sha' };
  }
  const pulls = readPullRequest(run['pull_requests']);
  if (pulls === undefined) {
    return { error: 'invalid-pr-number' };
  }
  return {
    headSha: sha,
    pr: pulls.pr,
    gateConclusion: text(run['conclusion']),
    gateEvent: text(run['event']),
    gatePath: text(run['path']),
    runUrl: text(run['html_url']),
  };
}

// --- Décision ---------------------------------------------------------------

type Accumulator = Pick<VerdictDecision, 'reasons' | 'issues'>;

function reject(acc: Accumulator, reason: string, message: string): void {
  acc.reasons.push(reason);
  acc.issues.push({ rule: reason, message });
}

/** GitHub peut suffixer le chemin du workflow par `@<référence>` : seul le fichier compte. */
function workflowFile(path: string): string {
  const at = path.indexOf('@');
  return at === -1 ? path : path.slice(0, at);
}

function judgeCheck(
  acc: Accumulator,
  name: 'integrity' | 'deps',
  report: CheckResult | undefined,
): void {
  if (report === undefined) {
    reject(
      acc,
      `missing-trusted-report:${name}`,
      `rapport ${name} absent, illisible ou hors schéma`,
    );
  } else if (report.status !== 'passed') {
    reject(acc, `${name}-failed`, `${name} : ${report.status}`);
    acc.issues.push(...report.issues);
  }
}

function judgeApprovals(acc: Accumulator, report: ApprovalsReport | undefined): void {
  if (report === undefined) {
    reject(
      acc,
      'missing-trusted-report:approvals',
      'rapport approvals absent, illisible ou hors schéma',
    );
    return;
  }
  if (report.bootstrap) {
    reject(acc, 'bootstrap-not-allowed', 'le verdict ne juge pas un amorçage');
  }
  for (const entry of report.rejected) {
    acc.issues.push({ rule: entry.reason, message: `approbation ${entry.kind} refusée` });
  }
}

/** Le verdict vaut `failure` dès qu'une raison existe : aucun défaut ne devient un succès. */
export function decideVerdict(input: DecisionInput): VerdictDecision {
  const { target } = input;
  const acc: Accumulator = { reasons: [], issues: [] };
  if (target.gateConclusion !== 'success') {
    reject(acc, 'gate-not-success', `run gate : « ${target.gateConclusion} »`);
  }
  if (workflowFile(target.gatePath) !== input.expectedGatePath) {
    reject(acc, 'untrusted-gate-path', `run déclenché par ${target.gatePath}`);
  }
  if (target.gateEvent !== 'pull_request') {
    reject(acc, 'untrusted-gate-event', `run déclenché par l'événement ${target.gateEvent}`);
  }
  if (target.pr === undefined) {
    reject(acc, 'pr-not-found', 'aucune pull request associée à la tête');
  }
  judgeCheck(acc, 'integrity', input.integrity);
  judgeCheck(acc, 'deps', input.deps);
  judgeApprovals(acc, input.approvals);
  return { conclusion: acc.reasons.length === 0 ? 'success' : 'failure', ...acc };
}

export function statusPayload(decision: VerdictDecision, runUrl: string): StatusBody {
  const [first, ...others] = decision.reasons;
  const suffix = others.length === 0 ? '' : ` (+${String(others.length)})`;
  const description =
    decision.conclusion === 'success'
      ? 'quality : gate, intégrité, dépendances et approbations conformes'
      : `quality refusé : ${first ?? 'inconnu'}${suffix}`;
  return {
    state: decision.conclusion,
    context: 'quality',
    description: description.slice(0, DESCRIPTION_MAX),
    target_url: runUrl,
  };
}
