import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { writeJsonAtomic } from './deps-guard.ts';
import { isRecord, runTool } from './tools.ts';
import { isRepository } from './verdict-io.ts';

/** Preuves d'approbation par label (D-15) : données lues côté serveur, jugées par `approvals.ts`. */
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

const SHA_PATTERN = /^[0-9a-f]{40}$/;
const GH_TIMEOUT_MS = 60_000;
const WITHHELD = ['GATE_STATUS_TOKEN', 'GITHUB_TOKEN'];

const isInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value);
const isTimestamp = (value: unknown): value is string =>
  typeof value === 'string' && !Number.isNaN(Date.parse(value));

// --- Relecture validée ------------------------------------------------------

function parseList<T>(value: unknown, item: (entry: unknown) => T | undefined): T[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const entries: unknown[] = value;
  const parsed: T[] = [];
  for (const entry of entries) {
    const one = item(entry);
    if (one === undefined) {
      return undefined;
    }
    parsed.push(one);
  }
  return parsed;
}

function parseLabelEvent(value: unknown): LabelEvent | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { id, event, actor, label, createdAt } = value;
  const valid =
    isInteger(id) &&
    (event === 'labeled' || event === 'unlabeled') &&
    typeof actor === 'string' &&
    typeof label === 'string' &&
    isTimestamp(createdAt);
  return valid ? { id, event, actor, label, createdAt } : undefined;
}

function parseRun(value: unknown): RunInfo | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { createdAt, headSha, event, headBranch, headRepository } = value;
  const valid =
    isTimestamp(createdAt) &&
    typeof headSha === 'string' &&
    typeof event === 'string' &&
    typeof headBranch === 'string' &&
    typeof headRepository === 'string';
  return valid ? { createdAt, headSha, event, headBranch, headRepository } : undefined;
}

function parsePull(value: unknown): PullInfo | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { number, headSha, headRef, headRepository, baseOwner } = value;
  const labels = parseList(value['labels'], (name) =>
    typeof name === 'string' ? name : undefined,
  );
  const valid =
    isInteger(number) &&
    typeof headSha === 'string' &&
    SHA_PATTERN.test(headSha) &&
    typeof headRef === 'string' &&
    typeof headRepository === 'string' &&
    typeof baseOwner === 'string' &&
    labels !== undefined;
  return valid ? { number, headSha, headRef, headRepository, baseOwner, labels } : undefined;
}

/** Relecture validée champ par champ : toute forme inattendue donne `undefined`, jamais une exception. */
export function parseApprovalEvidence(value: unknown): ApprovalEvidence | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { repository, pr, headSha } = value;
  const pull = parsePull(value['pull']);
  const labelEvents = parseList(value['labelEvents'], parseLabelEvent);
  const forcePushes = parseList(value['forcePushes'], (at) => (isTimestamp(at) ? at : undefined));
  const runs = parseList(value['runs'], parseRun);
  const valid =
    typeof repository === 'string' &&
    isInteger(pr) &&
    pr > 0 &&
    typeof headSha === 'string' &&
    SHA_PATTERN.test(headSha) &&
    pull?.number === pr &&
    labelEvents !== undefined &&
    forcePushes !== undefined &&
    runs !== undefined;
  return valid ? { repository, pr, headSha, pull, labelEvents, forcePushes, runs } : undefined;
}

// --- Réponses de l'API → forme normalisée -----------------------------------

const field = (value: unknown, key: string): unknown => (isRecord(value) ? value[key] : undefined);

function pullFromApi(pull: unknown): unknown {
  const head = field(pull, 'head');
  const labels = field(pull, 'labels');
  return {
    number: field(pull, 'number'),
    headSha: field(head, 'sha'),
    headRef: field(head, 'ref'),
    headRepository: field(field(head, 'repo'), 'full_name'),
    baseOwner: field(field(field(field(pull, 'base'), 'repo'), 'owner'), 'login'),
    labels: Array.isArray(labels)
      ? labels.map((label: unknown) => field(label, 'name'))
      : undefined,
  };
}

/** Acteur supprimé ou absent : chaîne vide, que le juge refuse. */
const actorOf = (event: unknown): unknown => {
  const actor = field(event, 'actor');
  return actor === null || actor === undefined ? '' : field(actor, 'login');
};

/** Aplatit les pages de `--slurp` ; `undefined` si une page ou une entrée n'est pas ce qui est attendu. */
function flatten(pages: unknown, entries: (page: unknown) => unknown): unknown[] | undefined {
  if (!Array.isArray(pages)) {
    return undefined;
  }
  const lists: unknown[] = pages.map(entries);
  return lists.every(Array.isArray) ? lists.flat() : undefined;
}

function eventsFromApi(pages: unknown): { labelEvents: unknown; forcePushes: unknown } {
  const events = flatten(pages, (page) => (Array.isArray(page) ? page : undefined));
  const kept = (names: readonly unknown[]) =>
    events?.filter((event) => names.includes(field(event, 'event'))) ?? undefined;
  return {
    labelEvents: kept(['labeled', 'unlabeled'])?.map((event) => ({
      id: field(event, 'id'),
      event: field(event, 'event'),
      actor: actorOf(event),
      label: field(field(event, 'label'), 'name'),
      createdAt: field(event, 'created_at'),
    })),
    forcePushes: kept(['head_ref_force_pushed'])?.map((event) => field(event, 'created_at')),
  };
}

const orEmpty = (value: unknown): unknown => value ?? '';

function runsFromApi(pages: unknown): unknown {
  const runs = flatten(pages, (page) => {
    const list = field(page, 'workflow_runs');
    return Array.isArray(list) ? list : undefined;
  });
  return runs?.map((run) => ({
    createdAt: field(run, 'created_at'),
    headSha: field(run, 'head_sha'),
    event: field(run, 'event'),
    headBranch: orEmpty(field(run, 'head_branch')),
    headRepository: orEmpty(field(field(run, 'head_repository'), 'full_name')),
  }));
}

/** Réponses brutes de l'API (pages de `--slurp`) → preuves normalisées et validées ; `undefined` hors forme. */
export function evidenceFromApi(
  raw: { pull: unknown; eventPages: unknown; runPages: unknown },
  ids: { repository: string; pr: number; headSha: string },
): ApprovalEvidence | undefined {
  return parseApprovalEvidence({
    ...ids,
    pull: pullFromApi(raw.pull),
    ...eventsFromApi(raw.eventPages),
    runs: runsFromApi(raw.runPages),
  });
}

// --- Collecte (lectures GET seulement) --------------------------------------

function idsProblem(ids: { repository: string; pr: number; headSha: string }): string | undefined {
  if (!isRepository(ids.repository)) {
    return 'dépôt invalide';
  }
  if (!isInteger(ids.pr) || ids.pr <= 0) {
    return 'numéro de PR invalide';
  }
  return SHA_PATTERN.test(ids.headSha) ? undefined : 'SHA de tête invalide';
}

async function ghRead(args: readonly string[], env: NodeJS.ProcessEnv): Promise<unknown> {
  const result = await runTool({
    command: 'gh',
    args,
    cwd: process.cwd(),
    env,
    timeoutMs: GH_TIMEOUT_MS,
  });
  if (result.code !== 0) {
    throw new Error(
      `gh ${args.slice(-1).join('')} a échoué : ${result.stderr.trim().slice(0, 300)}`,
    );
  }
  try {
    const body: unknown = JSON.parse(result.stdout);
    return body;
  } catch {
    throw new Error('réponse de gh illisible (hors JSON)');
  }
}

/**
 * Trois lectures GET de l'API (PR, événements, runs du SHA de tête) avec le seul jeton `GH_TOKEN` :
 * `GATE_STATUS_TOKEN` et `GITHUB_TOKEN` sont retirés de l'environnement de `gh`. Aucune écriture.
 */
export async function collectApprovalEvidence(opts: {
  repository: string;
  pr: number;
  headSha: string;
  env: NodeJS.ProcessEnv;
}): Promise<ApprovalEvidence> {
  const { repository, pr, headSha } = opts;
  const problem = idsProblem(opts);
  if (problem !== undefined) {
    throw new Error(`collecte refusée : ${problem}`);
  }
  const env = Object.fromEntries(
    Object.entries(opts.env).filter(([name]) => !WITHHELD.includes(name)),
  );
  const repo = `repos/${repository}`;
  const runsQuery = `head_sha=${headSha}&event=pull_request&per_page=100`;
  const pull = await ghRead(['api', `${repo}/pulls/${String(pr)}`], env);
  const eventPages = await ghRead(
    ['api', '--paginate', '--slurp', `${repo}/issues/${String(pr)}/events`],
    env,
  );
  const runPages = await ghRead(
    ['api', '--paginate', '--slurp', `${repo}/actions/runs?${runsQuery}`],
    env,
  );
  const evidence = evidenceFromApi({ pull, eventPages, runPages }, { repository, pr, headSha });
  if (evidence === undefined) {
    throw new Error("réponse de l'API hors forme (preuves inexploitables)");
  }
  return evidence;
}

// --- Ligne de commande ------------------------------------------------------

function parseCli(argv: readonly string[]) {
  try {
    const { values } = parseArgs({
      args: [...argv],
      options: {
        repo: { type: 'string' },
        pr: { type: 'string' },
        'head-sha': { type: 'string' },
        out: { type: 'string' },
      },
      strict: true,
      allowPositionals: false,
    });
    const { repo, pr, 'head-sha': headSha, out } = values;
    if (repo === undefined || pr === undefined || headSha === undefined || out === undefined) {
      return undefined;
    }
    const ids = { repository: repo, pr: /^[1-9]\d*$/.test(pr) ? Number(pr) : 0, headSha };
    return idsProblem(ids) === undefined ? { ids, out: resolve(out) } : undefined;
  } catch {
    return undefined;
  }
}

/** Sortie 0 : fichier écrit ; 1 : `gh` en échec ou réponse hors forme, aucun fichier ; 2 : usage. */
async function main(argv: readonly string[], env: NodeJS.ProcessEnv): Promise<number> {
  const cli = parseCli(argv);
  if (cli === undefined) {
    process.stderr.write(
      'usage : approval-evidence.ts --repo <o/r> --pr <n> --head-sha <sha> --out <fichier>\n',
    );
    return 2;
  }
  try {
    await writeJsonAtomic(cli.out, await collectApprovalEvidence({ ...cli.ids, env }));
    return 0;
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    return 1;
  }
}

if (import.meta.main) {
  process.exitCode = await main(process.argv.slice(2), process.env);
}
