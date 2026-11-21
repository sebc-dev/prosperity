import { readdir } from 'node:fs/promises';
import { availableParallelism } from 'node:os';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import type {
  CheckContext,
  CheckDefinition,
  CheckResult,
  GateReport,
  Profile,
} from './gate-report.ts';
import { computeVerdict, writeGateReport } from './gate-report.ts';
import { runTool } from './tools.ts';

const EXIT_PASS = 0;
const EXIT_FAIL = 1;
const EXIT_USAGE = 2;

class UsageError extends Error {}

interface Options {
  profile: Profile;
  only: string[] | undefined;
  report: string;
  base: string;
}

function isCheckDefinition(value: unknown): value is CheckDefinition {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  return (
    'id' in value &&
    typeof value.id === 'string' &&
    'tool' in value &&
    typeof value.tool === 'string' &&
    'severity' in value &&
    (value.severity === 'blocking' || value.severity === 'advisory') &&
    'push' in value &&
    (value.push === 'run' || value.push === 'skip-ci-only') &&
    'run' in value &&
    typeof value.run === 'function'
  );
}

function parseOptions(argv: readonly string[], env: NodeJS.ProcessEnv): Options {
  const { values } = parseArgs({
    args: [...argv],
    options: {
      profile: { type: 'string', default: 'full' },
      only: { type: 'string' },
      report: { type: 'string', default: 'reports/gate.json' },
      base: { type: 'string' },
    },
    strict: true,
    allowPositionals: false,
  });
  const profile = values.profile;
  if (profile !== 'push' && profile !== 'full') {
    throw new UsageError(`profil inconnu « ${String(profile)} » (attendu : push | full)`);
  }
  const baseRef = env['GITHUB_BASE_REF'];
  return {
    profile,
    only: values.only
      ?.split(',')
      .map((id) => id.trim())
      .filter((id) => id !== ''),
    report: values.report,
    base: values.base ?? `origin/${baseRef !== undefined && baseRef !== '' ? baseRef : 'main'}`,
  };
}

async function discoverChecks(root: string): Promise<CheckDefinition[]> {
  const dir = join(root, 'quality', 'checks');
  const names = (await readdir(dir))
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts'))
    .sort();
  const checks: CheckDefinition[] = [];
  for (const name of names) {
    const mod: unknown = await import(pathToFileURL(join(dir, name)).href);
    const definition: unknown =
      typeof mod === 'object' && mod !== null && 'check' in mod ? mod.check : undefined;
    if (!isCheckDefinition(definition)) {
      throw new Error(`quality/checks/${name} : l'export « check » n'est pas un CheckDefinition`);
    }
    checks.push(definition);
  }
  return checks.sort((a, b) => a.id.localeCompare(b.id));
}

function selectChecks(
  all: readonly CheckDefinition[],
  only: string[] | undefined,
): CheckDefinition[] {
  if (only === undefined) {
    return [...all];
  }
  const known = new Set(all.map((check) => check.id));
  const unknown = only.filter((id) => !known.has(id));
  if (unknown.length > 0) {
    throw new UsageError(
      `check inconnu : ${unknown.join(', ')} (disponibles : ${[...known].join(', ')})`,
    );
  }
  return all.filter((check) => only.includes(check.id));
}

function skippedCiOnly(check: CheckDefinition): CheckResult {
  return {
    check: check.id,
    tool: check.tool,
    version: '',
    severity: check.severity,
    passed: false,
    status: 'skipped',
    skipped_reason: 'ci-only',
    issues: [],
    duration_ms: 0,
  };
}

/** Un check qui lève ne peut jamais rendre `pass` : il devient un échec explicite. */
async function execute(check: CheckDefinition, ctx: CheckContext): Promise<CheckResult> {
  if (ctx.profile === 'push' && check.push === 'skip-ci-only') {
    return skippedCiOnly(check);
  }
  const start = Date.now();
  try {
    return await check.run(ctx);
  } catch (error) {
    return {
      check: check.id,
      tool: check.tool,
      version: '',
      severity: check.severity,
      passed: false,
      status: 'failed',
      issues: [
        {
          rule: 'check-crashed',
          message: error instanceof Error ? error.message : 'erreur inconnue',
        },
      ],
      duration_ms: Date.now() - start,
    };
  }
}

async function runPool(
  checks: readonly CheckDefinition[],
  ctx: CheckContext,
): Promise<CheckResult[]> {
  const results: CheckResult[] = [];
  const queue = [...checks];
  const workers = Array.from(
    { length: Math.min(4, availableParallelism(), queue.length) },
    async () => {
      for (let next = queue.shift(); next !== undefined; next = queue.shift()) {
        results.push(await execute(next, ctx));
      }
    },
  );
  await Promise.all(workers);
  return results.sort((a, b) => a.check.localeCompare(b.check));
}

async function gitOutput(root: string, args: readonly string[]): Promise<string | undefined> {
  const result = await runTool({ command: 'git', args, cwd: root, timeoutMs: 15_000 });
  const text = result.stdout.trim();
  return result.code === 0 && text !== '' ? text : undefined;
}

function printTable(results: readonly CheckResult[], verdict: string): void {
  const width = Math.max(5, ...results.map((r) => r.check.length));
  process.stdout.write(`${'check'.padEnd(width)}  ${'status'.padEnd(7)}  issues\n`);
  for (const r of results) {
    const suffix = r.status === 'skipped' ? `  (${r.skipped_reason ?? 'skipped'})` : '';
    process.stdout.write(
      `${r.check.padEnd(width)}  ${r.status.padEnd(7)}  ${String(r.issues.length)}${suffix}\n`,
    );
  }
  process.stdout.write(`verdict : ${verdict}\n`);
}

async function main(): Promise<number> {
  const root = resolve(import.meta.dirname, '..');
  const options = parseOptions(process.argv.slice(2), process.env);
  const checks = selectChecks(await discoverChecks(root), options.only);
  const inCi = process.env['GITHUB_ACTIONS'] === 'true';
  if (inCi && options.profile === 'full' && options.only !== undefined) {
    process.stderr.write('avertissement : --only en CI produit un rapport partiel\n');
  }
  const ctx: CheckContext = {
    root,
    profile: options.profile,
    base: options.base,
    inCi,
    env: process.env,
  };
  const results = await runPool(checks, ctx);
  const verdict = computeVerdict(options.profile, results, inCi);
  const report: GateReport = {
    profile: options.profile,
    commit: (await gitOutput(root, ['rev-parse', 'HEAD'])) ?? 'unknown',
    base:
      (await gitOutput(root, ['rev-parse', '--verify', '--quiet', options.base])) ?? options.base,
    generated_at: new Date().toISOString(),
    verdict,
    checks: results,
  };
  await writeGateReport(resolve(root, options.report), report);
  printTable(results, verdict);
  return verdict === 'pass' ? EXIT_PASS : EXIT_FAIL;
}

try {
  process.exitCode = await main();
} catch (error) {
  const message = error instanceof Error ? error.message : 'erreur inconnue';
  process.stderr.write(`${message}\n`);
  process.exitCode = EXIT_USAGE;
}
