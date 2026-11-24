import { join } from 'node:path';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';
import { runVitestCheck } from '../vitest-kit.ts';

const META: CheckMeta = { id: 'unit', tool: 'vitest', severity: 'blocking' };

function run(ctx: CheckContext): Promise<CheckResult> {
  return runVitestCheck(ctx, {
    meta: META,
    reportPath: join('reports', 'vitest-unit.json'),
    args: ['--project', 'unit', '--coverage'],
    // Le périmètre est posé ici, jamais hérité de l'environnement de la gate.
    env: { GATE_COVERAGE_SCOPE: 'pure' },
    needsDocker: false,
  });
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'run',
  run,
};
