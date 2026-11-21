import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runMiseTool, verifyMiseToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'workflow-audit', tool: 'zizmor', severity: 'blocking' };
const TOOL = META.tool;
const WORKFLOWS_DIR = '.github/workflows';
const LEADING_DOT_SLASH = /^\.\//;

/** Cherche `a.b.c` dans des objets imbriqués ; `undefined` dès qu'un maillon manque. */
function dig(value: unknown, path: readonly string[]): unknown {
  let current: unknown = value;
  for (const key of path) {
    if (!isRecord(current)) {
      return undefined;
    }
    current = current[key];
  }
  return current;
}

/** La localisation principale d'un résultat (à défaut, la première). */
function primaryLocation(finding: Record<string, unknown>): unknown {
  const locations: unknown = finding['locations'];
  if (!Array.isArray(locations) || locations.length === 0) {
    return undefined;
  }
  const list: unknown[] = locations;
  return list.find((loc) => dig(loc, ['symbolic', 'kind']) === 'Primary') ?? list[0];
}

function toIssue(entry: unknown): Issue {
  if (!isRecord(entry)) {
    return { rule: 'tool-error', message: 'entrée zizmor illisible' };
  }
  const issue: Issue = {
    rule: typeof entry['ident'] === 'string' ? entry['ident'] : 'zizmor',
    message: typeof entry['desc'] === 'string' ? entry['desc'] : '',
  };
  const location = primaryLocation(entry);
  const file = dig(location, ['symbolic', 'key', 'Local', 'verbatim_path']);
  if (typeof file === 'string') {
    issue.file = file.replace(LEADING_DOT_SLASH, '');
  }
  const row = dig(location, ['concrete', 'location', 'start_point', 'row']);
  if (typeof row === 'number') {
    issue.line = row + 1;
  }
  return issue;
}

function parseZizmorOutput(stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  return Array.isArray(parsed) ? parsed.map(toIssue) : undefined;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyMiseToolVersion(ctx.root, TOOL, ['--version']);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue(TOOL, version.found, version.expected),
      start,
    );
  }
  // Audits en ligne (épinglage vérifié sur le dépôt distant) seulement avec un jeton fourni par la CI.
  const token = ctx.env['GH_TOKEN'];
  const online = token !== undefined && token !== '';
  // `--no-exit-codes` : 0 = audit mené (résultats dans le JSON), autre code = échec de l'outil.
  const audit = await runMiseTool(
    TOOL,
    ['--format', 'json', '--no-exit-codes', ...(online ? [] : ['--offline']), `./${WORKFLOWS_DIR}`],
    { cwd: ctx.root, env: ctx.env, timeoutMs: 120_000 },
  );
  const issues = audit.code === 0 ? parseZizmorOutput(audit.stdout) : undefined;
  if (issues === undefined) {
    return failedResult(META, version.found, toolErrorIssue(TOOL, audit.code, audit.stderr), start);
  }
  return buildResult(
    META,
    {
      status: issues.length === 0 ? 'passed' : 'failed',
      version: version.found,
      issues,
      note: online ? 'audits en ligne' : 'audits hors ligne (GH_TOKEN absent)',
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
