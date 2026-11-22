import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';

export async function isSelftestTriggered(_ctx: CheckContext): Promise<boolean> {
  return false;
}

export function casesToIssues(): never[] {
  return [];
}

export const check: CheckDefinition = {
  id: 'selftest',
  tool: 'selftest',
  severity: 'blocking',
  push: 'skip-ci-only',
  run(): Promise<CheckResult> {
    return Promise.reject(new Error('non implémenté'));
  },
};
