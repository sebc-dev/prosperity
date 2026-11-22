// Squelette de la phase RED (TDD) : identité du check, aucun comportement.
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';

function run(_ctx: CheckContext): Promise<CheckResult> {
  return Promise.reject(new Error('non implémenté'));
}

export const check: CheckDefinition = {
  id: 'approvals',
  tool: 'approvals',
  severity: 'blocking',
  push: 'skip-ci-only',
  run,
};
