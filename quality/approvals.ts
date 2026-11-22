import { readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { parseApprovalEvidence } from './approval-evidence.ts';
import type { ApprovalEvidence, LabelEvent } from './approval-evidence.ts';
import { writeJsonAtomic } from './deps-guard.ts';
import { isRecord } from './tools.ts';
import type { ApprovalsReport } from './verdict-rules.ts';

/** Sortes d'approbation, chacune portée par un label du même nom (D-15). */
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

type Decision = Pick<ApprovalsReport, 'approved' | 'rejected' | 'approval'>;

const SHA_PATTERN = /^[0-9a-f]{40}$/;

// --- Configuration : la copie de base, rien d'autre ------------------------

const isNames = (value: unknown): value is string[] =>
  Array.isArray(value) &&
  value.length > 0 &&
  value.every((name) => typeof name === 'string' && name !== '');

/**
 * Lit `<baseDir>/quality/approvers.json` et rien d'autre : ni le répertoire courant ni le dossier du
 * script, qui peuvent appartenir à la PR jugée. Un fichier absent, illisible ou invalide donne `undefined`.
 */
export async function loadApproversConfig(baseDir: string): Promise<ApproversConfig | undefined> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(join(baseDir, 'quality', 'approvers.json'), 'utf8'));
  } catch {
    return undefined;
  }
  const allowlist = isRecord(parsed) ? parsed['allowlist'] : undefined;
  const labels = isRecord(parsed) ? parsed['labels'] : undefined;
  return isNames(allowlist) && isNames(labels) ? { allowlist, labels } : undefined;
}

// --- Décision pure ----------------------------------------------------------

/**
 * Ancre « dernier push », côté serveur : le plus ancien run `pull_request` du SHA de tête sur la
 * branche et le dépôt de tête de la PR, relevé au dernier push forcé. Jamais la date d'un commit.
 */
export function lastPushAnchor(evidence: ApprovalEvidence): number | undefined {
  const { pull } = evidence;
  const firstRuns = evidence.runs
    .filter(
      (run) =>
        run.headSha === evidence.headSha &&
        run.event === 'pull_request' &&
        run.headRepository === pull.headRepository &&
        run.headBranch === pull.headRef,
    )
    .map((run) => Date.parse(run.createdAt));
  if (firstRuns.length === 0) {
    return undefined;
  }
  return Math.max(Math.min(...firstRuns), ...evidence.forcePushes.map((at) => Date.parse(at)));
}

function lastEvent(events: readonly LabelEvent[], label: string): LabelEvent | undefined {
  return events
    .filter((event) => event.label === label)
    .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt) || a.id - b.id)
    .at(-1);
}

function judgeLabel(
  label: string,
  input: { evidence: ApprovalEvidence; config: ApproversConfig },
  anchor: number | undefined,
): { reason: ApprovalRejection } | { actor: string } {
  const { evidence, config } = input;
  if (evidence.pull.headSha !== evidence.headSha) {
    return { reason: 'approval-head-moved' };
  }
  if (anchor === undefined) {
    return { reason: 'approval-no-anchor' };
  }
  const last = lastEvent(evidence.labelEvents, label);
  if (last === undefined) {
    return { reason: 'approval-missing' };
  }
  if (last.event === 'unlabeled' || !evidence.pull.labels.includes(label)) {
    return { reason: 'approval-removed' };
  }
  if (last.actor === '' || !config.allowlist.includes(last.actor)) {
    return { reason: 'approval-actor-not-allowed' };
  }
  return Date.parse(last.createdAt) <= anchor
    ? { reason: 'approval-stale' }
    : { actor: last.actor };
}

/** Une sorte est approuvée si son dernier événement est un `labeled` récent d'un acteur de la liste. */
export function decideApprovals(input: {
  evidence: ApprovalEvidence;
  config: ApproversConfig;
}): Decision {
  const anchor = lastPushAnchor(input.evidence);
  const approved: string[] = [];
  const rejected: Decision['rejected'] = [];
  const actors = new Set<string>();
  for (const label of input.config.labels) {
    const outcome = judgeLabel(label, input, anchor);
    if ('reason' in outcome) {
      rejected.push({ kind: label, reason: outcome.reason });
    } else {
      approved.push(label);
      actors.add(outcome.actor);
    }
  }
  const approval =
    approved.length === 0
      ? null
      : {
          commit: input.evidence.headSha,
          principal: [...actors].sort((a, b) => a.localeCompare(b, 'en')).join(','),
          keyType: 'github-label',
          flags: null,
        };
  return { approved, rejected, approval };
}

// --- Jugement et rapport ----------------------------------------------------

function refused(reason: ApprovalRejection, bootstrap: boolean): ApprovalsReport {
  return {
    approved: [],
    rejected: APPROVAL_KINDS.map((kind) => ({ kind, reason })),
    bootstrap,
    verifier: VERIFIER,
    approval: null,
  };
}

/**
 * Juge un fichier de preuves avec l'allowlist de la copie de base. En amorçage (la base n'a pas
 * encore la configuration), l'allowlist est le propriétaire du dépôt de base lu dans l'API.
 */
export async function judgeApprovals(opts: {
  baseDir: string;
  headSha: string;
  pr: number;
  evidence: unknown;
  bootstrap: boolean;
}): Promise<ApprovalsReport> {
  const { bootstrap } = opts;
  const loaded = await loadApproversConfig(opts.baseDir);
  if (loaded === undefined && !bootstrap) {
    return refused('approvers-config-missing', false);
  }
  const evidence = parseApprovalEvidence(opts.evidence);
  if (evidence?.pr !== opts.pr || evidence.headSha !== opts.headSha) {
    return refused('approval-evidence-invalid', bootstrap);
  }
  const config = loaded ?? { allowlist: [evidence.pull.baseOwner], labels: [...APPROVAL_KINDS] };
  return { ...decideApprovals({ evidence, config }), bootstrap, verifier: VERIFIER };
}

// --- Ligne de commande ------------------------------------------------------

interface CliInput {
  baseDir: string;
  evidencePath: string;
  headSha: string;
  pr: number;
  bootstrap: boolean;
  out: string;
}

function parseOptions(argv: readonly string[]) {
  try {
    return parseArgs({
      args: [...argv],
      options: {
        'base-dir': { type: 'string' },
        evidence: { type: 'string' },
        'head-sha': { type: 'string' },
        pr: { type: 'string' },
        bootstrap: { type: 'boolean', default: false },
        out: { type: 'string' },
      },
      strict: true,
      allowPositionals: false,
    }).values;
  } catch {
    return undefined;
  }
}

/** `pull_request.head.sha` et `pull_request.number` de l'événement GitHub, à défaut d'options. */
async function readEvent(env: NodeJS.ProcessEnv): Promise<{ headSha: unknown; pr: unknown }> {
  const path = env['GITHUB_EVENT_PATH'];
  if (path === undefined || path === '') {
    return { headSha: undefined, pr: undefined };
  }
  try {
    const event: unknown = JSON.parse(await readFile(path, 'utf8'));
    const pull = isRecord(event) ? event['pull_request'] : undefined;
    const head = isRecord(pull) ? pull['head'] : undefined;
    return {
      headSha: isRecord(head) ? head['sha'] : undefined,
      pr: isRecord(pull) ? pull['number'] : undefined,
    };
  } catch {
    return { headSha: undefined, pr: undefined };
  }
}

const POSITIVE_INTEGER = /^[1-9]\d*$/;

/** Numéro de PR : l'option (chaîne décimale) ou, à défaut, celui de l'événement GitHub. */
function prNumber(given: string | undefined, fromEvent: unknown): number | undefined {
  if (given !== undefined) {
    return POSITIVE_INTEGER.test(given) ? Number(given) : undefined;
  }
  return typeof fromEvent === 'number' && Number.isInteger(fromEvent) && fromEvent > 0
    ? fromEvent
    : undefined;
}

async function resolveInput(
  argv: readonly string[],
  env: NodeJS.ProcessEnv,
): Promise<CliInput | undefined> {
  const values = parseOptions(argv);
  if (values === undefined) {
    return undefined;
  }
  const { 'base-dir': baseDir, evidence, out, bootstrap } = values;
  const event = await readEvent(env);
  const headSha = values['head-sha'] ?? event.headSha;
  const pr = prNumber(values.pr, event.pr);
  if (
    baseDir === undefined ||
    evidence === undefined ||
    out === undefined ||
    pr === undefined ||
    typeof headSha !== 'string' ||
    !SHA_PATTERN.test(headSha)
  ) {
    return undefined;
  }
  return {
    baseDir: resolve(baseDir),
    evidencePath: resolve(evidence),
    headSha,
    pr,
    bootstrap,
    out: resolve(out),
  };
}

/** Fichier de preuves absent ou illisible : `undefined`, que le juge traduit en refus. */
async function readEvidence(path: string): Promise<unknown> {
  try {
    const evidence: unknown = JSON.parse(await readFile(path, 'utf8'));
    return evidence;
  } catch {
    return undefined;
  }
}

/** Sortie 0 après écriture du rapport (refuser n'est pas son rôle) ; 2 : usage ; 1 : écriture impossible. */
async function main(argv: readonly string[], env: NodeJS.ProcessEnv): Promise<number> {
  const input = await resolveInput(argv, env);
  if (input === undefined) {
    process.stderr.write(
      'usage : approvals.ts --base-dir <base> --evidence <fichier> [--head-sha <sha>] [--pr <n>] [--bootstrap] --out <fichier>\n',
    );
    return 2;
  }
  try {
    const { evidencePath, out, ...rest } = input;
    await writeJsonAtomic(
      out,
      await judgeApprovals({ ...rest, evidence: await readEvidence(evidencePath) }),
    );
    return 0;
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    return 1;
  }
}

if (import.meta.main) {
  process.exitCode = await main(process.argv.slice(2), process.env);
}
