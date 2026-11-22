import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { buildResult, failedResult } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';
import { readApprovalsReport } from '../verdict-rules.ts';
import type { ApprovalsReport } from '../verdict-rules.ts';

const META: CheckMeta = { id: 'approvals', tool: 'approvals', severity: 'blocking' };
const REPORT = 'reports/approvals.json';

/** Le rapport est écrit par l'étape de confiance, depuis une copie de la base ; illisible = absent. */
async function readTrustedReport(root: string): Promise<ApprovalsReport | undefined> {
  try {
    const parsed: unknown = JSON.parse(await readFile(join(root, REPORT), 'utf8'));
    return readApprovalsReport(parsed);
  } catch {
    return undefined;
  }
}

/**
 * Un refus d'approbation n'est pas un échec du check : l'intégrité et la garde des dépendances
 * exigent la sorte quand elle est nécessaire. Chaque refus est repris en issue informative.
 */
function fromReport(report: ApprovalsReport, start: number): CheckResult {
  return buildResult(
    META,
    {
      status: 'passed',
      version: report.verifier,
      issues: report.rejected.map((entry) => ({
        rule: entry.reason,
        message: `approbation ${entry.kind} refusée`,
      })),
      ...(report.bootstrap ? { note: 'amorçage : rapport jugé par le verdict de confiance' } : {}),
    },
    start,
  );
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  if (!ctx.inCi) {
    return {
      check: META.id,
      tool: META.tool,
      version: '',
      severity: META.severity,
      passed: false,
      status: 'skipped',
      skipped_reason: 'ci-only',
      issues: [],
      duration_ms: Date.now() - start,
    };
  }
  if (ctx.env['GITHUB_EVENT_NAME'] !== 'pull_request') {
    const note = 'hors pull_request : jugé par le verdict de confiance';
    return buildResult(META, { status: 'passed', version: '', issues: [], note }, start);
  }
  const report = await readTrustedReport(ctx.root);
  if (report === undefined) {
    const message = `${REPORT} absent, illisible ou hors schéma : l'étape de confiance ne l'a pas produit`;
    return failedResult(META, '', { rule: 'missing-trusted-report', message }, start);
  }
  return fromReport(report, start);
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
