import { readFile, rm, symlink } from 'node:fs/promises';
import { join } from 'node:path';
import { runTool } from '../tools.ts';
import { isInfrastructureRule, matchesExpected, parseObservedCheck } from './cases.ts';
import type { CaseResult, ObservedCheck, SelftestCase } from './cases.ts';
import { git, tail } from './context.ts';
import type { Failure, RunContext, Verdict } from './context.ts';
import { addWorktree, removeWorktree, worktreeName } from './worktrees.ts';

const CHECK_TIMEOUT_MS = 1_200_000;
const APPLY_TIMEOUT_MS = 120_000;
// Lance `apply.ts` hors du processus du runner : `argv` = [fichier, racine du worktree].
const APPLY_SCRIPT = `
import { pathToFileURL } from 'node:url';
const [file, root] = process.argv.slice(1);
const mod = await import(pathToFileURL(file).href);
if (typeof mod.default !== 'function') {
  throw new Error('apply.ts doit exporter par défaut une fonction apply(root)');
}
await mod.default(root);
`;

interface CheckRun {
  observed: ObservedCheck | undefined;
  stderr: string;
}

async function applyCase(
  ctx: RunContext,
  item: SelftestCase,
  dir: string,
): Promise<string | undefined> {
  const outcome =
    item.kind === 'patch'
      ? await git(dir, ['apply', '--index', join(item.dir, 'patch')], ctx.env)
      : await runTool({
          command: process.execPath,
          args: ['--input-type=module', '-e', APPLY_SCRIPT, join(item.dir, 'apply.ts'), dir],
          cwd: dir,
          env: ctx.env,
          timeoutMs: APPLY_TIMEOUT_MS,
        });
  return outcome.code === 0 ? undefined : tail(outcome.stderr);
}

/** Commit dans le worktree jetable ; les hooks y sont coupés (le cas secret doit pouvoir committer). */
async function commitCase(ctx: RunContext, dir: string): Promise<string | undefined> {
  const env = { ...ctx.env, LEFTHOOK: '0' };
  await git(dir, ['add', '-A'], env);
  const identity = ['-c', 'user.name=selftest', '-c', 'user.email=selftest@example.invalid'];
  const args = [...identity, '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'selftest'];
  const commit = await git(dir, args, env);
  return commit.code === 0
    ? undefined
    : `commit impossible (patch sans effet ?) : ${tail(commit.stderr)}`;
}

async function installCase(
  ctx: RunContext,
  item: SelftestCase,
  dir: string,
): Promise<string | undefined> {
  if (item.install === 'link') {
    try {
      await symlink(join(ctx.baseDir, 'node_modules'), join(dir, 'node_modules'), 'dir');
      return undefined;
    } catch (error) {
      return error instanceof Error ? error.message : 'lien node_modules impossible';
    }
  }
  const outcome = await ctx.install(dir, ctx.env);
  return outcome.ok ? undefined : outcome.message;
}

async function prepareCase(
  ctx: RunContext,
  item: SelftestCase,
  dir: string,
): Promise<Failure | undefined> {
  const applied = (await applyCase(ctx, item, dir)) ?? (await commitCase(ctx, dir));
  if (applied !== undefined) {
    return { reason: 'case-not-applicable', detail: applied };
  }
  const installed = await installCase(ctx, item, dir);
  return installed === undefined ? undefined : { reason: 'install-failed', detail: installed };
}

/** `node quality/run.ts --only <check>` dans `dir` ; le rapport périmé est supprimé avant le run. */
async function runCheck(ctx: RunContext, dir: string, check: string): Promise<CheckRun> {
  const report = join(dir, 'reports', 'gate.json');
  await rm(report, { force: true });
  const outcome = await runTool({
    command: process.execPath,
    args: [
      join('quality', 'run.ts'),
      '--only',
      check,
      '--profile',
      'full',
      '--base',
      ctx.headSha,
      '--report',
      report,
    ],
    cwd: dir,
    env: { ...ctx.env, GATE_BASE_DIR: ctx.baseDir, GATE_APPROVED_KINDS: '' },
    timeoutMs: CHECK_TIMEOUT_MS,
  });
  const text = await readFile(report, 'utf8').catch(() => '');
  return { observed: parseObservedCheck(text, check), stderr: tail(outcome.stderr) };
}

function rulesOf(observed: ObservedCheck): string {
  return observed.issues.map((issue) => issue.rule).join(', ');
}

/** Vert seulement si le check a échoué pour la règle attendue ; sinon la raison dit pourquoi pas. */
function judge(item: SelftestCase, run: CheckRun): Verdict {
  const { observed } = run;
  if (observed === undefined) {
    return { status: 'failed', reason: 'check-crashed', detail: run.stderr };
  }
  if (matchesExpected(observed, item)) {
    return { status: 'passed', reason: 'detected' };
  }
  if (observed.status !== 'failed') {
    return { status: 'failed', reason: 'not-detected', detail: `statut ${observed.status}` };
  }
  const infrastructure = observed.issues.every((issue) => isInfrastructureRule(issue.rule));
  return {
    status: 'failed',
    reason: infrastructure ? 'tool-failure' : 'wrong-rule',
    detail: `règles vues : ${rulesOf(observed)}`,
  };
}

export function toResult(item: SelftestCase, start: number, verdict: Verdict): CaseResult {
  return {
    id: item.id,
    check: item.check,
    rule: item.rule,
    status: verdict.status,
    reason: verdict.reason,
    ...(verdict.detail === undefined ? {} : { detail: verdict.detail }),
    duration_ms: Date.now() - start,
  };
}

/** Un cas : worktree jetable, une violation, le check visé seul, verdict par règle attendue. */
export async function runCase(
  ctx: RunContext,
  item: SelftestCase,
  control: string | undefined,
): Promise<CaseResult> {
  const start = Date.now();
  if (control !== undefined) {
    return toResult(item, start, { status: 'failed', reason: 'control-failed', detail: control });
  }
  const dir = join(ctx.runDir, worktreeName(item.id));
  try {
    await addWorktree(ctx.root, dir, ctx.headSha);
    const failure = await prepareCase(ctx, item, dir);
    if (failure !== undefined) {
      return toResult(item, start, { status: 'failed', ...failure });
    }
    return toResult(item, start, judge(item, await runCheck(ctx, dir, item.check)));
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'erreur inconnue';
    return toResult(item, start, { status: 'failed', reason: 'selftest-error', detail });
  } finally {
    await removeWorktree(ctx.root, dir);
  }
}

/** Contrôle de causalité : chaque check visé doit passer sur la copie propre. */
export async function runControls(
  ctx: RunContext,
  checks: readonly string[],
): Promise<Map<string, string>> {
  const failures = new Map<string, string>();
  for (const check of checks) {
    const { observed, stderr } = await runCheck(ctx, ctx.baseDir, check);
    if (observed === undefined) {
      failures.set(check, `contrôle sans rapport : ${stderr}`);
    } else if (observed.status !== 'passed') {
      failures.set(check, `contrôle ${observed.status} sur la copie propre : ${rulesOf(observed)}`);
    }
  }
  return failures;
}
