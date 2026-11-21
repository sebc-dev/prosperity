import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, readMisePins, runMiseTool } from '../tools.ts';

const META: CheckMeta = { id: 'sast', tool: 'semgrep', severity: 'blocking' };
const TOOL = META.tool;
const MISE_PIN_KEY = 'pipx:semgrep';
const SEMVER = /\d{1,6}\.\d{1,6}\.\d{1,6}/;
const RULES = 'semgrep/prosperity.yml';
const FIXTURE = 'semgrep/prosperity.ts';
const SCAN_ROOT = 'src';
const PACKS = ['p/typescript', 'p/nodejs', 'p/jwt', 'p/owasp-top-ten'];
const SCAN_FLAGS = ['--json', '--metrics=off', '--disable-version-check', '--quiet'];
const PROJECT_RULE_PREFIX = 'prosperity.';
const ERROR_SEVERITY = 'ERROR';

interface Finding {
  checkId: string;
  severity: string;
  issue: Issue;
}

function stringOf(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === 'string' ? value : '';
}

function toFinding(entry: unknown): Finding | undefined {
  if (!isRecord(entry)) {
    return undefined;
  }
  const extra = isRecord(entry['extra']) ? entry['extra'] : {};
  const start = isRecord(entry['start']) ? entry['start'] : {};
  const checkId = stringOf(entry, 'check_id');
  const issue: Issue = {
    rule: checkId,
    message: stringOf(extra, 'message'),
    file: stringOf(entry, 'path'),
  };
  if (typeof start['line'] === 'number') {
    issue.line = start['line'];
  }
  return { checkId, severity: stringOf(extra, 'severity'), issue };
}

/** Sortie `--json` : `results` (constats) et `errors` (erreurs de scan, dont les échecs d'analyse). */
function parseScan(stdout: string): { findings: Finding[]; errors: string[] } | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || !Array.isArray(parsed['results']) || !Array.isArray(parsed['errors'])) {
    return undefined;
  }
  const results: unknown[] = parsed['results'];
  const errors: unknown[] = parsed['errors'];
  return {
    findings: results.flatMap((entry) => toFinding(entry) ?? []),
    errors: errors.flatMap((entry) =>
      isRecord(entry) && entry['level'] === 'error' ? [stringOf(entry, 'message')] : [],
    ),
  };
}

/** Semgrep préfixe l'identifiant par le dossier de la config : on garde le suffixe `prosperity.<id>`. */
function projectRuleOf(checkId: string): string {
  const at = checkId.indexOf(PROJECT_RULE_PREFIX);
  return at === -1 ? checkId : checkId.slice(at);
}

/** Étape 1 : une règle qui ne mord plus ou qui mord à tort est un échec de la gate. */
async function testRules(ctx: CheckContext): Promise<Issue[]> {
  const test = await runMiseTool(TOOL, ['--test', '--config', RULES, FIXTURE], {
    cwd: ctx.root,
    timeoutMs: 120_000,
  });
  if (test.code === 0) {
    return [];
  }
  const detail = `${test.stdout}\n${test.stderr}`
    .split('\n')
    .filter((line) => line.includes('✖') || line.includes('missed') || line.includes('Error'))
    .join(' ')
    .slice(0, 300);
  return [
    {
      rule: 'semgrep-rule-test',
      message: `semgrep --test a échoué (code ${String(test.code)}) : ${detail}`,
      file: FIXTURE,
    },
  ];
}

/** Étape 2 : règles du projet, déterministes, ERROR bloquant. */
async function scanProject(ctx: CheckContext): Promise<Issue[] | Issue> {
  const scan = await runMiseTool(TOOL, ['scan', '--config', RULES, ...SCAN_FLAGS, SCAN_ROOT], {
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const parsed = scan.code === 0 ? parseScan(scan.stdout) : undefined;
  if (parsed === undefined) {
    return toolErrorIssue(TOOL, scan.code, scan.stderr);
  }
  const [firstError] = parsed.errors;
  if (firstError !== undefined) {
    return {
      rule: 'tool-error',
      message: `semgrep : erreur de scan : ${firstError.slice(0, 200)}`,
    };
  }
  return parsed.findings
    .filter((finding) => finding.severity === ERROR_SEVERITY)
    .map((finding) => ({ ...finding.issue, rule: projectRuleOf(finding.checkId) }));
}

/** Étape 3 (décision Q4, `packs-advisory`) : packs du registre, résultats ERROR listés sans effet sur le verdict. */
async function scanPacks(ctx: CheckContext): Promise<Issue[]> {
  const configs = PACKS.flatMap((pack) => ['--config', pack]);
  const scan = await runMiseTool(TOOL, ['scan', ...configs, ...SCAN_FLAGS, SCAN_ROOT], {
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const parsed = scan.code === 0 ? parseScan(scan.stdout) : undefined;
  if (parsed === undefined) {
    return [
      {
        rule: 'pack-scan-unavailable',
        message: `packs du registre non joués (code ${String(scan.code)}) : ${scan.stderr.trim().slice(0, 200)}`,
      },
    ];
  }
  return parsed.findings
    .filter((finding) => finding.severity === ERROR_SEVERITY)
    .map((finding) => ({ ...finding.issue, rule: `pack:${finding.checkId}` }));
}

/** Le pin de `mise.toml` s'appelle `pipx:semgrep`, l'exécutable `semgrep`. */
async function verifySemgrepVersion(
  root: string,
): Promise<{ ok: boolean; found: string; expected: string }> {
  const expected = (await readMisePins(root)).get(MISE_PIN_KEY) ?? '';
  const result = await runMiseTool(TOOL, ['--version'], { cwd: root, timeoutMs: 30_000 });
  const found = SEMVER.exec(`${result.stdout}\n${result.stderr}`)?.[0] ?? '';
  return { ok: expected !== '' && found === expected, found, expected };
}

function wantsPacks(ctx: CheckContext): boolean {
  return ctx.profile === 'full' || ctx.env['GATE_SEMGREP_PACKS'] === 'full';
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifySemgrepVersion(ctx.root);
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue(TOOL, version.found, version.expected),
      start,
    );
  }
  const blocking = await testRules(ctx);
  // Avant la première ligne de code (`src/` absent), il n'y a rien à scanner.
  const hasSources = existsSync(join(ctx.root, SCAN_ROOT));
  if (hasSources) {
    const scanned = await scanProject(ctx);
    blocking.push(...(Array.isArray(scanned) ? scanned : [scanned]));
  }
  const advisory = hasSources && wantsPacks(ctx) ? await scanPacks(ctx) : [];
  return buildResult(
    META,
    {
      status: blocking.length === 0 ? 'passed' : 'failed',
      version: version.found,
      issues: [...blocking, ...advisory],
      note: wantsPacks(ctx)
        ? 'règles du projet bloquantes ; packs du registre advisory (Q4 : packs-advisory)'
        : 'règles du projet bloquantes ; packs du registre non joués (profil push)',
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'run',
  run,
};
