import { lstat, mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { buildResult } from './check-kit.ts';
import type { CheckMeta } from './check-kit.ts';
import { diffDependencies } from './deps-diff.ts';
import type { DepChange, DependencySnapshot } from './deps-diff.ts';
import type { CheckResult, Issue } from './gate-report.ts';
import thresholds from './thresholds.json' with { type: 'json' };
import { isRecord } from './tools.ts';

export { diffDependencies } from './deps-diff.ts';
export type { DepChange, DependencySnapshot } from './deps-diff.ts';

export type RegistryLookup = (name: string) => Promise<{ exists: boolean; createdAt?: string }>;

interface EvaluateOptions {
  approvedKinds: readonly string[];
  minAgeDays: number;
  now: Date;
  lookup: RegistryLookup;
}

const META: CheckMeta = { id: 'deps', tool: 'deps-guard', severity: 'blocking' };
const APPROVAL_KIND = 'deps-approved';
const NPM_REGISTRY = 'https://registry.npmjs.org';
const NAME_SEGMENT = /^[\w~-][\w.~-]*$/;
const DAY_MS = 86_400_000;
const LOOKUP_CHUNK = 8;
const EMPTY: DependencySnapshot = { packageJson: '{}', lockfile: '' };

// --- Évaluation -------------------------------------------------------------

async function checkRegistry(name: string, opts: EvaluateOptions): Promise<Issue | undefined> {
  let found: Awaited<ReturnType<RegistryLookup>>;
  try {
    found = await opts.lookup(name);
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'erreur inconnue';
    return { rule: 'registry-lookup-failed', message: `${name} : ${reason}` };
  }
  if (!found.exists) {
    return {
      rule: 'dependency-not-on-registry',
      message: `${name} est introuvable sur le registre npm`,
    };
  }
  const created = Date.parse(found.createdAt ?? '');
  if (Number.isNaN(created)) {
    return { rule: 'registry-lookup-failed', message: `${name} : date de création illisible` };
  }
  const ageDays = (opts.now.getTime() - created) / DAY_MS;
  return ageDays < opts.minAgeDays
    ? {
        rule: 'dependency-too-young',
        message: `${name} a ${String(Math.floor(ageDays))} jours, ${String(opts.minAgeDays)} exigés`,
      }
    : undefined;
}

async function registryIssues(names: readonly string[], opts: EvaluateOptions): Promise<Issue[]> {
  const found: (Issue | undefined)[] = [];
  for (let i = 0; i < names.length; i += LOOKUP_CHUNK) {
    const chunk = names.slice(i, i + LOOKUP_CHUNK);
    found.push(...(await Promise.all(chunk.map((name) => checkRegistry(name, opts)))));
  }
  return found.filter((issue) => issue !== undefined);
}

function describeChange(entry: DepChange): string {
  const versions = [entry.from, entry.to].filter((v) => v !== undefined).join(' → ');
  return versions === '' ? entry.name : `${entry.name} (${versions})`;
}

/**
 * Toute dépendance ajoutée ou modifiée exige la sorte `deps-approved` ; un paquet nouveau doit
 * exister sur le registre et y avoir été créé depuis assez longtemps, approuvé ou non.
 */
export async function evaluateDependencies(
  changes: readonly DepChange[],
  opts: EvaluateOptions,
): Promise<CheckResult> {
  const start = Date.now();
  const needing = changes.filter((entry) => entry.kind !== 'dependency-removed');
  const issues: Issue[] = opts.approvedKinds.includes(APPROVAL_KIND)
    ? []
    : needing.map((entry) => ({
        rule: entry.kind,
        message: `${describeChange(entry)} exige le label ${APPROVAL_KIND} (posé par un humain après le dernier push, D-15)`,
      }));
  const fresh = needing.filter(
    (e) => e.kind === 'dependency-added' || e.kind === 'transitive-added',
  );
  issues.push(...(await registryIssues([...new Set(fresh.map((e) => e.name))], opts)));
  const removed = changes.filter((entry) => entry.kind === 'dependency-removed');
  return buildResult(
    META,
    {
      status: issues.length === 0 ? 'passed' : 'failed',
      version: process.version,
      issues,
      ...(removed.length === 0
        ? {}
        : { note: `dependency-removed : ${removed.map((e) => e.name).join(', ')}` }),
    },
    start,
  );
}

// --- Entrées/sorties --------------------------------------------------------

/** Un nom npm : `nom` ou `@portée/nom`, rien d'autre n'atteint l'URL du registre. */
function isNpmName(name: string): boolean {
  const scoped = name.startsWith('@');
  const parts = (scoped ? name.slice(1) : name).split('/');
  return parts.length === (scoped ? 2 : 1) && parts.every((part) => NAME_SEGMENT.test(part));
}

export function registryLookup(baseUrl: string): RegistryLookup {
  return async (name) => {
    if (!isNpmName(name)) {
      return { exists: false };
    }
    const response = await fetch(`${baseUrl}/${name.replace('/', '%2F')}`, {
      signal: AbortSignal.timeout(20_000),
    });
    if (response.status === 404) {
      return { exists: false };
    }
    if (!response.ok) {
      throw new Error(`registre : HTTP ${String(response.status)}`);
    }
    const body: unknown = await response.json();
    const time = isRecord(body) ? body['time'] : undefined;
    const created = isRecord(time) ? time['created'] : undefined;
    return typeof created === 'string' ? { exists: true, createdAt: created } : { exists: true };
  };
}

/** Écriture atomique : fichier temporaire dans le même dossier puis `rename`. */
export async function writeJsonAtomic(path: string, value: unknown): Promise<void> {
  const dir = dirname(path);
  await mkdir(dir, { recursive: true });
  const tmp = join(dir, `.${basename(path)}.${String(process.pid)}.tmp`);
  await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await rename(tmp, path);
}

function isIssue(value: unknown): value is Issue {
  return (
    isRecord(value) && typeof value['rule'] === 'string' && typeof value['message'] === 'string'
  );
}

/** Valide un `CheckResult` relu depuis un fichier : toute forme inattendue donne `undefined`. */
export function parseCheckResult(value: unknown): CheckResult | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const { check, tool, version, severity, passed, status, issues, duration_ms } = value;
  const valid =
    typeof check === 'string' &&
    typeof tool === 'string' &&
    typeof version === 'string' &&
    (severity === 'blocking' || severity === 'advisory') &&
    typeof passed === 'boolean' &&
    (status === 'passed' || status === 'failed' || status === 'skipped') &&
    Array.isArray(issues) &&
    issues.every(isIssue) &&
    typeof duration_ms === 'number';
  if (!valid) {
    return undefined;
  }
  const result: CheckResult = {
    check,
    tool,
    version,
    severity,
    passed,
    status,
    issues,
    duration_ms,
  };
  const { skipped_reason: reason, note } = value;
  if (typeof reason === 'string') {
    result.skipped_reason = reason;
  }
  if (typeof note === 'string') {
    result.note = note;
  }
  return result;
}

async function readApprovedKinds(path: string): Promise<string[]> {
  const parsed: unknown = JSON.parse(await readFile(path, 'utf8'));
  const approved = isRecord(parsed) ? parsed['approved'] : undefined;
  if (!Array.isArray(approved) || !approved.every((kind) => typeof kind === 'string')) {
    throw new Error(`${path} : le champ « approved » n'est pas un tableau de chaînes`);
  }
  return approved;
}

/** Lit un fichier de dépendances sans suivre de lien symbolique : la tête d'une PR n'est que des données. */
async function readPlain(path: string): Promise<string> {
  if ((await lstat(path)).isSymbolicLink()) {
    throw new Error(`${path} est un lien symbolique`);
  }
  return readFile(path, 'utf8');
}

async function readSnapshot(dir: string): Promise<DependencySnapshot> {
  const packageJson = await readPlain(join(dir, 'package.json'));
  const lockfile = await readPlain(join(dir, 'pnpm-lock.yaml')).catch((error: unknown) => {
    if (error instanceof Error && 'code' in error && error.code === 'ENOENT') {
      return '';
    }
    throw error;
  });
  return { packageJson, lockfile };
}

export interface CliIo {
  lookup: RegistryLookup;
  now: Date;
  minAgeDays: number;
}

async function execute(argv: readonly string[], io: CliIo): Promise<number> {
  const { values } = parseArgs({
    args: [...argv],
    options: {
      'base-dir': { type: 'string' },
      'head-dir': { type: 'string' },
      approved: { type: 'string' },
      'approvals-report': { type: 'string' },
      bootstrap: { type: 'boolean', default: false },
      out: { type: 'string' },
    },
    strict: true,
    allowPositionals: false,
  });
  const { 'base-dir': baseDir, 'head-dir': headDir, out } = values;
  if (baseDir === undefined || headDir === undefined || out === undefined) {
    throw new Error('--base-dir, --head-dir et --out sont obligatoires');
  }
  if (values.approved !== undefined && values['approvals-report'] !== undefined) {
    throw new Error('--approved et --approvals-report sont exclusifs');
  }
  const report = values['approvals-report'];
  const approvedKinds =
    report === undefined
      ? (values.approved ?? '')
          .split(',')
          .map((kind) => kind.trim())
          .filter((kind) => kind !== '')
      : await readApprovedKinds(report);
  const base = values.bootstrap ? EMPTY : await readSnapshot(baseDir);
  const changes = diffDependencies(base, await readSnapshot(headDir));
  const result = await evaluateDependencies(changes, { ...io, approvedKinds });
  await writeJsonAtomic(resolve(out), result);
  return result.passed ? 0 : 1;
}

/** Sortie 0 : conforme ; 1 : refus (rapport écrit) ; 2 : usage ou lecture impossible (aucun rapport, échec fermé). */
export async function runDepsGuardCli(argv: readonly string[], io: CliIo): Promise<number> {
  try {
    return await execute(argv, io);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    return 2;
  }
}

if (import.meta.main) {
  process.exitCode = await runDepsGuardCli(process.argv.slice(2), {
    lookup: registryLookup(NPM_REGISTRY),
    now: new Date(),
    minAgeDays: thresholds.supplyChain.packageMinAgeDays,
  });
}
