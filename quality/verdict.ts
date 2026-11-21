import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { parseCheckResult, writeJsonAtomic } from './deps-guard.ts';
import {
  extractHeadFromGit,
  findPullRequest,
  githubPublisher,
  isRepository,
  nodeJudge,
} from './verdict-io.ts';
import type { JudgeName } from './verdict-io.ts';
import {
  decideVerdict,
  EXPECTED_GATE_PATH,
  parseTarget,
  readApprovalsReport,
  statusPayload,
} from './verdict-rules.ts';
import type { StatusBody, VerdictDecision, VerdictTarget } from './verdict-rules.ts';

export { decideVerdict, parseTarget, readApprovalsReport, statusPayload } from './verdict-rules.ts';
export type {
  ApprovalsReport,
  StatusBody,
  VerdictDecision,
  VerdictTarget,
} from './verdict-rules.ts';

export interface VerdictDeps {
  target: VerdictTarget;
  baseDir: string;
  workDir: string;
  extractHead(sha: string): Promise<string>;
  judge(name: JudgeName, args: readonly string[]): Promise<unknown>;
  publish(sha: string, body: StatusBody): Promise<void>;
}

// --- Orchestration ----------------------------------------------------------

function checkArgs(
  deps: VerdictDeps,
  name: 'integrity' | 'deps',
  headDir: string,
  signed: boolean,
) {
  return [
    ...['--base-dir', deps.baseDir, '--head-dir', headDir],
    ...(signed ? ['--approvals-report', join(deps.workDir, 'approvals.json')] : []),
    ...['--out', join(deps.workDir, `${name}.json`)],
  ];
}

/**
 * Rejoue l'approbation signée, l'intégrité et les dépendances depuis la base sur la tête lue comme
 * données, puis publie `quality` exactement une fois, y compris quand un juge lève une erreur.
 */
export async function runVerdict(deps: VerdictDeps): Promise<VerdictDecision> {
  const { target, baseDir, workDir } = deps;
  const failed: string[] = [];
  const attempt = async <T>(name: string, run: () => Promise<T>): Promise<T | undefined> => {
    try {
      return await run();
    } catch {
      failed.push(name);
      return undefined;
    }
  };
  const headDir = await attempt('extract-head', () => deps.extractHead(target.headSha));
  const approvalsOut = join(workDir, 'approvals.json');
  const approvals = readApprovalsReport(
    await attempt('approvals', () =>
      deps.judge('approvals', [
        '--base-dir',
        baseDir,
        '--head-sha',
        target.headSha,
        '--out',
        approvalsOut,
      ]),
    ),
  );
  const judgeCheck = async (name: 'integrity' | 'deps') =>
    headDir === undefined
      ? undefined
      : parseCheckResult(
          await attempt(name, () =>
            deps.judge(name, checkArgs(deps, name, headDir, approvals !== undefined)),
          ),
        );
  const integrity = await judgeCheck('integrity');
  const depsReport = await judgeCheck('deps');
  const decided = decideVerdict({
    target,
    expectedGatePath: EXPECTED_GATE_PATH,
    integrity,
    deps: depsReport,
    approvals,
  });
  const errors = failed.map((name) => `judge-error:${name}`);
  const decision: VerdictDecision = {
    conclusion: errors.length === 0 ? decided.conclusion : 'failure',
    reasons: [...errors, ...decided.reasons],
    issues: [...errors.map((rule) => ({ rule, message: 'le juge a échoué' })), ...decided.issues],
  };
  await deps.publish(target.headSha, statusPayload(decision, target.runUrl));
  return decision;
}

// --- Ligne de commande ------------------------------------------------------

interface Options {
  baseDir: string;
  workDir: string;
  out: string;
  dryRun: boolean;
  headDir: string | undefined;
  gateConclusion: string;
  gatePath: string;
  gateEvent: string;
  approvalsReport: string | undefined;
}

function parseOptions(argv: readonly string[]): Options {
  const { values } = parseArgs({
    args: [...argv],
    options: {
      'base-dir': { type: 'string' },
      'work-dir': { type: 'string' },
      out: { type: 'string' },
      'dry-run': { type: 'boolean', default: false },
      'head-dir': { type: 'string' },
      'gate-conclusion': { type: 'string', default: 'success' },
      'gate-path': { type: 'string', default: EXPECTED_GATE_PATH },
      'gate-event': { type: 'string', default: 'pull_request' },
      'approvals-report': { type: 'string' },
    },
    strict: true,
    allowPositionals: false,
  });
  const { 'base-dir': baseDir, 'work-dir': workDir, out } = values;
  if (baseDir === undefined || workDir === undefined || out === undefined) {
    throw new Error('--base-dir, --work-dir et --out sont obligatoires');
  }
  return {
    baseDir: resolve(baseDir),
    workDir: resolve(workDir),
    out: resolve(out),
    dryRun: values['dry-run'],
    headDir: values['head-dir'],
    gateConclusion: values['gate-conclusion'],
    gatePath: values['gate-path'],
    gateEvent: values['gate-event'],
    approvalsReport: values['approvals-report'],
  };
}

/** Preuve locale : tête et rapport d'approbations fournis, intégrité et dépendances jouées pour de vrai. */
function dryRunDeps(opts: Options, env: NodeJS.ProcessEnv): VerdictDeps {
  const { headDir, approvalsReport } = opts;
  if (headDir === undefined) {
    throw new Error('--dry-run exige --head-dir');
  }
  const run = nodeJudge(opts.baseDir, opts.workDir, env);
  return {
    target: {
      headSha: '0'.repeat(40),
      pr: 1,
      gateConclusion: opts.gateConclusion,
      gateEvent: opts.gateEvent,
      gatePath: opts.gatePath,
      runUrl: '',
    },
    baseDir: opts.baseDir,
    workDir: opts.workDir,
    extractHead: () => Promise.resolve(resolve(headDir)),
    judge: async (name, args) => {
      if (name !== 'approvals') {
        return run(name, args);
      }
      if (approvalsReport === undefined) {
        throw new Error('--dry-run exige --approvals-report');
      }
      const content = await readFile(approvalsReport, 'utf8');
      await writeFile(join(opts.workDir, 'approvals.json'), content);
      const report: unknown = JSON.parse(content);
      return report;
    },
    publish: (_sha, body) => {
      process.stdout.write(`${JSON.stringify(body, null, 2)}\n`);
      return Promise.resolve();
    },
  };
}

const given = (value: string | undefined): value is string => value !== undefined && value !== '';

function liveEnvironment(env: NodeJS.ProcessEnv) {
  const { GITHUB_EVENT_PATH: eventPath, GITHUB_REPOSITORY: repo, GATE_STATUS_TOKEN: token } = env;
  return given(eventPath) && given(repo) && isRepository(repo) && given(token)
    ? { eventPath, repo, token }
    : undefined;
}

/** Mode normal : la charge `workflow_run` vient du fichier d'événement, jamais d'une entrée de PR. */
async function liveDeps(opts: Options, env: NodeJS.ProcessEnv): Promise<VerdictDeps | string> {
  const live = liveEnvironment(env);
  if (live === undefined) {
    return 'missing-environment';
  }
  const { eventPath, repo, token } = live;
  const parsed = parseTarget(JSON.parse(await readFile(eventPath, 'utf8')));
  if ('error' in parsed) {
    return parsed.error;
  }
  const pr = parsed.pr ?? (await findPullRequest(repo, parsed.headSha, env));
  const runId = env['GITHUB_RUN_ID'];
  const server = env['GITHUB_SERVER_URL'] ?? 'https://github.com';
  const runUrl = given(runId) ? `${server}/${repo}/actions/runs/${runId}` : parsed.runUrl;
  return {
    target: { ...parsed, pr, runUrl },
    baseDir: opts.baseDir,
    workDir: opts.workDir,
    extractHead: extractHeadFromGit(opts.baseDir, opts.workDir, env),
    judge: nodeJudge(opts.baseDir, opts.workDir, env),
    publish: githubPublisher(repo, token, env),
  };
}

async function main(argv: readonly string[], env: NodeJS.ProcessEnv): Promise<number> {
  const opts = parseOptions(argv);
  await mkdir(opts.workDir, { recursive: true });
  const deps = opts.dryRun ? dryRunDeps(opts, env) : await liveDeps(opts, env);
  if (typeof deps === 'string') {
    await writeJsonAtomic(opts.out, { conclusion: 'failure', reasons: [deps], issues: [] });
    process.stderr.write(`verdict impossible : ${deps}\n`);
    return 1;
  }
  const decision = await runVerdict(deps);
  await writeJsonAtomic(opts.out, {
    ...decision,
    headSha: deps.target.headSha,
    pr: deps.target.pr,
  });
  return 0;
}

/** Sortie 0 : statut publié (quelle que soit la conclusion) ; 1 : rien n'a pu être publié. */
export async function runVerdictCli(
  argv: readonly string[],
  env: NodeJS.ProcessEnv,
): Promise<number> {
  try {
    return await main(argv, env);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    return 1;
  }
}

if (import.meta.main) {
  process.exitCode = await runVerdictCli(process.argv.slice(2), process.env);
}
