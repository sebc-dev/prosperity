import type { Money, Result } from './money.ts';

interface Share {
  readonly index: number;
  readonly base: bigint;
  readonly remainder: bigint;
}

/** Plus grand reste d'abord ; à égalité, l'indice le plus petit d'abord. */
function byLargestRemainder(a: Share, b: Share): number {
  if (a.remainder !== b.remainder) {
    return a.remainder > b.remainder ? -1 : 1;
  }
  return a.index - b.index;
}

/**
 * Répartition au plus grand reste : parts de base = quotient entier de |total|·wᵢ / Σw,
 * le reste en centimes va un à un aux plus grands restes. Le signe du total est réappliqué,
 * si bien que Σ parts = total. Les poids (points de base, ppm) sont des `bigint` strictement positifs.
 */
export function allocate(
  total: Money,
  weights: readonly bigint[],
): Result<Money[], 'invalid-weights'> {
  if (weights.length === 0 || weights.some((weight) => weight <= 0n)) {
    return { ok: false, error: 'invalid-weights' };
  }
  const negative = total.amountMinor < 0n;
  const magnitude = negative ? -total.amountMinor : total.amountMinor;
  const weightSum = weights.reduce((acc, weight) => acc + weight, 0n);
  const shares: Share[] = weights.map((weight, index) => {
    const scaled = magnitude * weight;
    return { index, base: scaled / weightSum, remainder: scaled % weightSum };
  });
  const leftover = magnitude - shares.reduce((acc, share) => acc + share.base, 0n);
  const winners = new Set(
    [...shares]
      .sort(byLargestRemainder)
      .filter((_, rank) => BigInt(rank) < leftover)
      .map((share) => share.index),
  );
  return {
    ok: true,
    value: shares.map((share) => {
      const part = share.base + (winners.has(share.index) ? 1n : 0n);
      return { amountMinor: negative ? -part : part, currency: total.currency };
    }),
  };
}
