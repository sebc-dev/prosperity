import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runMiseTool, verifyMiseToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'cve', tool: 'osv-scanner', severity: 'blocking' };
const TOOL = META.tool;
const LOCKFILE = 'pnpm-lock.yaml';
/** Score CVSS à partir duquel une vulnérabilité est « high » (A9) : osv-scanner n'a pas de seuil natif. */
const BLOCKING_SCORE = 7;
const BLOCKING_AUDIT_LEVELS = new Set(['high', 'critical']);
// Code 1 = vulnérabilités trouvées : le verdict se lit dans le JSON, pas dans le code.
const NORMAL_CODES = new Set([0, 1]);

function stringsOf(value: unknown): string[] {
  const list: unknown[] = Array.isArray(value) ? value : [];
  return list.filter((item): item is string => typeof item === 'string');
}

function recordsOf(value: unknown): Record<string, unknown>[] {
  const list: unknown[] = Array.isArray(value) ? value : [];
  return list.filter(isRecord);
}

/** Un groupe d'alias : `rule` = premier `GHSA-`, à défaut le premier identifiant. */
function groupIssue(
  pkg: Record<string, unknown>,
  group: Record<string, unknown>,
): Issue | undefined {
  const ids = stringsOf(group['ids']);
  const aliases = stringsOf(group['aliases']);
  const score = Number.parseFloat(
    typeof group['max_severity'] === 'string' ? group['max_severity'] : '',
  );
  const info = isRecord(pkg['package']) ? pkg['package'] : {};
  const name = typeof info['name'] === 'string' ? info['name'] : 'inconnu';
  const version = typeof info['version'] === 'string' ? info['version'] : '?';
  const rule = ids.find((id) => id.startsWith('GHSA-')) ?? ids[0] ?? 'osv';
  if (Number.isNaN(score) || score < BLOCKING_SCORE) {
    return undefined;
  }
  return {
    rule,
    message: `${name}@${version} (score ${String(score)}) : ${[...new Set([...ids, ...aliases])].join(', ')}`,
    file: LOCKFILE,
  };
}

/** `results[].packages[].groups[].max_severity` ≥ 7.0 : un constat bloquant par groupe. */
function parseOsv(stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed)) {
    return undefined;
  }
  return recordsOf(parsed['results'])
    .flatMap((result) => recordsOf(result['packages']))
    .flatMap((pkg) => recordsOf(pkg['groups']).flatMap((group) => groupIssue(pkg, group) ?? []));
}

function auditIssue(key: string, advisory: Record<string, unknown>): Issue | undefined {
  const level = advisory['severity'];
  if (typeof level !== 'string' || !BLOCKING_AUDIT_LEVELS.has(level)) {
    return undefined;
  }
  const id = advisory['github_advisory_id'];
  const name = advisory['module_name'];
  const title = advisory['title'];
  return {
    rule: `pnpm-audit:${typeof id === 'string' ? id : key}`,
    message: `${typeof name === 'string' ? name : 'paquet'} (${level}) : ${typeof title === 'string' ? title : ''}`,
    file: 'package.json',
  };
}

/** `pnpm audit --prod --json` : `advisories` indexé par identifiant ; high/critical bloquent. */
function parseAudit(stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  const advisories = isRecord(parsed) ? parsed['advisories'] : undefined;
  if (!isRecord(advisories)) {
    return undefined;
  }
  return Object.entries(advisories).flatMap(([key, advisory]) => {
    const issue = isRecord(advisory) ? auditIssue(key, advisory) : undefined;
    return issue === undefined ? [] : [issue];
  });
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
  const osv = await runMiseTool(TOOL, ['scan', 'source', '-L', LOCKFILE, '--format', 'json'], {
    cwd: ctx.root,
    timeoutMs: 180_000,
  });
  const osvIssues = NORMAL_CODES.has(osv.code) ? parseOsv(osv.stdout) : undefined;
  if (osvIssues === undefined) {
    return failedResult(META, version.found, toolErrorIssue(TOOL, osv.code, osv.stderr), start);
  }
  const audit = await runMiseTool('pnpm', ['audit', '--prod', '--json'], {
    cwd: ctx.root,
    timeoutMs: 120_000,
  });
  const auditIssues = NORMAL_CODES.has(audit.code) ? parseAudit(audit.stdout) : undefined;
  if (auditIssues === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('pnpm audit', audit.code, audit.stderr),
      start,
    );
  }
  const issues = [...osvIssues, ...auditIssues];
  return buildResult(
    META,
    { status: issues.length === 0 ? 'passed' : 'failed', version: version.found, issues },
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
