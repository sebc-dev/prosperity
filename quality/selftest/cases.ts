import { access, readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { matchesGlob } from 'node:path/posix';
import type { CheckResult, Issue } from '../gate-report.ts';
import { isRecord } from '../tools.ts';

type InstallMode = 'frozen' | 'link';

export interface CaseExpectation {
  check: string;
  rule: string;
  install: InstallMode;
}

export interface SelftestCase extends CaseExpectation {
  id: string;
  dir: string;
  kind: 'patch' | 'apply';
}

export interface CaseResult {
  id: string;
  check: string;
  rule: string;
  status: 'passed' | 'failed';
  reason: string;
  detail?: string;
  duration_ms: number;
}

/** Ce qu'on retient du résultat d'un check : son statut et ses issues. */
export type ObservedCheck = Pick<CheckResult, 'check' | 'status' | 'issues'>;

/** Erreur d'usage (sélection `--case` invalide) : la CLI sort en code 2 avant tout worktree. */
export class SelectionError extends Error {}

const CASES_DIR = join('quality', 'selftest', 'cases');

/**
 * Règles qui disent « le check n'a pas pu juger » (outil absent, configuration cassée, rapport
 * manquant) : elles ne comptent jamais comme une détection, même si un cas les attendait.
 */
const INFRASTRUCTURE_RULES: ReadonlySet<string> = new Set([
  'tool-error',
  'tool-version-mismatch',
  'check-crashed',
  'config-error',
  'invalid-base',
  'missing-trusted-report',
]);

function compareIds(a: string, b: string): number {
  return a.localeCompare(b);
}

export function isInfrastructureRule(rule: string): boolean {
  return INFRASTRUCTURE_RULES.has(rule);
}

function ruleMatches(rule: string, expected: string): boolean {
  if (isInfrastructureRule(rule)) {
    return false;
  }
  return rule === expected || rule.endsWith(`.${expected}`);
}

/**
 * Vrai seulement si le check a échoué (`failed`) et qu'une issue porte la règle attendue :
 * identique, ou se terminant par `.<règle>` (les identifiants Semgrep sont préfixés par le
 * dossier de règles). Un échec d'infrastructure n'est jamais une détection.
 */
export function matchesExpected(
  result: { status: CheckResult['status']; issues: readonly Issue[] },
  expected: Pick<CaseExpectation, 'rule'>,
): boolean {
  return (
    result.status === 'failed' &&
    result.issues.some((issue) => ruleMatches(issue.rule, expected.rule))
  );
}

/**
 * Sélection des cas : `spec` est une liste de globs séparés par des virgules ; le résultat est
 * l'union triée et dédoublonnée des cas retenus par chaque glob. Un élément vide ou qui ne
 * retient aucun cas lève une `SelectionError` qui le nomme.
 */
export function selectCases(ids: readonly string[], spec: string | undefined): string[] {
  const all = [...new Set(ids)].sort(compareIds);
  if (spec === undefined) {
    return all;
  }
  const selected = new Set<string>();
  spec.split(',').forEach((raw, index) => {
    const glob = raw.trim();
    if (glob === '') {
      throw new SelectionError(
        `élément vide (n° ${String(index + 1)}) dans la liste de cas « ${spec} »`,
      );
    }
    const hits = all.filter((id) => matchesGlob(id, glob));
    if (hits.length === 0) {
      throw new SelectionError(`aucun cas ne correspond à « ${glob} »`);
    }
    hits.forEach((hit) => selected.add(hit));
  });
  return [...selected].sort(compareIds);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value !== '';
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function readExpectation(dir: string, id: string): Promise<CaseExpectation> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(join(dir, 'expected.json'), 'utf8'));
  } catch {
    throw new Error(`cas ${id} : expected.json absent ou illisible`);
  }
  const install = isRecord(parsed) ? parsed['install'] : undefined;
  if (
    !isRecord(parsed) ||
    !nonEmptyString(parsed['check']) ||
    !nonEmptyString(parsed['rule']) ||
    (install !== 'frozen' && install !== 'link')
  ) {
    throw new Error(`cas ${id} : expected.json doit porter check, rule et install (frozen | link)`);
  }
  return { check: parsed['check'], rule: parsed['rule'], install };
}

async function loadCase(root: string, id: string): Promise<SelftestCase> {
  const dir = join(root, CASES_DIR, id);
  const expectation = await readExpectation(dir, id);
  const hasPatch = await exists(join(dir, 'patch'));
  const hasApply = await exists(join(dir, 'apply.ts'));
  if (hasPatch === hasApply) {
    throw new Error(`cas ${id} : exactement un fichier parmi patch et apply.ts est attendu`);
  }
  return { id, dir, kind: hasPatch ? 'patch' : 'apply', ...expectation };
}

/** Tous les cas du dépôt, triés par identifiant ; une définition invalide est une erreur franche. */
export async function loadCases(root: string): Promise<SelftestCase[]> {
  let entries;
  try {
    entries = await readdir(join(root, CASES_DIR), { withFileTypes: true });
  } catch {
    return [];
  }
  const ids = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort(compareIds);
  return Promise.all(ids.map((id) => loadCase(root, id)));
}

function toIssue(value: unknown): Issue | undefined {
  if (
    !isRecord(value) ||
    typeof value['rule'] !== 'string' ||
    typeof value['message'] !== 'string'
  ) {
    return undefined;
  }
  return { rule: value['rule'], message: value['message'] };
}

function toObserved(value: unknown): ObservedCheck | undefined {
  if (!isRecord(value) || typeof value['check'] !== 'string' || !Array.isArray(value['issues'])) {
    return undefined;
  }
  const status = value['status'];
  if (status !== 'passed' && status !== 'failed' && status !== 'skipped') {
    return undefined;
  }
  const raw: unknown[] = value['issues'];
  const issues = raw.map(toIssue);
  if (issues.some((issue) => issue === undefined)) {
    return undefined;
  }
  return { check: value['check'], status, issues: issues.filter((issue) => issue !== undefined) };
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** Résultat du check `checkId` dans un rapport `reports/gate.json` ; `undefined` s'il manque ou est illisible. */
export function parseObservedCheck(text: string, checkId: string): ObservedCheck | undefined {
  const parsed = parseJson(text);
  if (!isRecord(parsed) || !Array.isArray(parsed['checks'])) {
    return undefined;
  }
  const entries: unknown[] = parsed['checks'];
  return entries.map(toObserved).find((entry) => entry?.check === checkId);
}

function toCaseResult(value: unknown): CaseResult | undefined {
  if (
    !isRecord(value) ||
    !nonEmptyString(value['id']) ||
    typeof value['check'] !== 'string' ||
    typeof value['rule'] !== 'string' ||
    typeof value['reason'] !== 'string' ||
    typeof value['duration_ms'] !== 'number' ||
    (value['status'] !== 'passed' && value['status'] !== 'failed')
  ) {
    return undefined;
  }
  const detail = value['detail'];
  return {
    id: value['id'],
    check: value['check'],
    rule: value['rule'],
    status: value['status'],
    reason: value['reason'],
    duration_ms: value['duration_ms'],
    ...(typeof detail === 'string' ? { detail } : {}),
  };
}

/** Cas d'un rapport `reports/selftest.json` ; `undefined` si le rapport est illisible. */
export function parseSelftestReport(text: string): CaseResult[] | undefined {
  const parsed = parseJson(text);
  if (!isRecord(parsed) || !Array.isArray(parsed['cases'])) {
    return undefined;
  }
  const entries: unknown[] = parsed['cases'];
  const cases = entries.map(toCaseResult);
  return cases.some((entry) => entry === undefined)
    ? undefined
    : cases.filter((entry) => entry !== undefined);
}
