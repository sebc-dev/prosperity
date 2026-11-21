// Squelette RED : signature finale, comportement volontairement faux (remplacé au GREEN).
import type { Money, Result } from './money.ts';

export function allocate(
  _total: Money,
  _weights: readonly bigint[],
): Result<Money[], 'invalid-weights'> {
  return { ok: false, error: 'invalid-weights' };
}
