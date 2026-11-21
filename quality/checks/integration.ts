import { join } from 'node:path';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';
import { runVitestCheck } from '../vitest-kit.ts';

const META: CheckMeta = { id: 'integration', tool: 'vitest', severity: 'blocking' };

/**
 * Tests d'intégration sur un PostgreSQL 18 réel (Testcontainers), ordre aléatoire, seed dans la
 * note. Sans Docker : `failed` avec `docker-unavailable`, jamais `skipped` en profil full.
 */
function run(ctx: CheckContext): Promise<CheckResult> {
  return runVitestCheck(ctx, {
    meta: META,
    reportPath: join('reports', 'vitest-integration.json'),
    args: ['--project', 'integration'],
    env: {},
    needsDocker: true,
  });
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  // D-12 : l'intégration démarre un conteneur, elle est jouée en CI seulement.
  push: 'skip-ci-only',
  run,
};
