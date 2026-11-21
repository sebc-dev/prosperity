import fc from 'fast-check';

const DEFAULT_NUM_RUNS = 100;

function readNumRuns(raw: string | undefined): number {
  if (raw === undefined || raw === '') {
    return DEFAULT_NUM_RUNS;
  }
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`FAST_CHECK_NUM_RUNS invalide « ${raw} » (entier >= 1 attendu)`);
  }
  return parsed;
}

// 100 par défaut en local et en CI ; 1000 au nightly (FAST_CHECK_NUM_RUNS=1000).
// Quand une propriété échoue, sa seed et son chemin deviennent un exemple explicite
// dans le test concerné (seeds de régression committées).
fc.configureGlobal({ numRuns: readNumRuns(process.env['FAST_CHECK_NUM_RUNS']) });
