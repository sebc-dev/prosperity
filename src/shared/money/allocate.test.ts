import { describe, expect, it } from 'vitest';
import { allocate } from './allocate.ts';
import type { Money } from './money.ts';

function eur(amountMinor: bigint): Money {
  return { amountMinor, currency: 'EUR' };
}

function parts(...amounts: bigint[]): { ok: true; value: Money[] } {
  return { ok: true, value: amounts.map(eur) };
}

describe('allocate', () => {
  it.each([
    [8400n, [5000n, 5000n], [4200n, 4200n]],
    [100n, [1n, 1n, 1n], [34n, 33n, 33n]],
    [8401n, [6000n, 4000n], [5041n, 3360n]],
    [10n, [1n, 2n], [3n, 7n]],
    [10n, [2n, 1n], [7n, 3n]],
    [10n, [3n, 3n, 1n], [4n, 4n, 2n]],
    [2n, [1n, 1n, 1n], [1n, 1n, 0n]],
    [5n, [1n, 1n, 1n, 1n, 1n, 1n, 1n], [1n, 1n, 1n, 1n, 1n, 0n, 0n]],
    [0n, [1n, 2n], [0n, 0n]],
    [7n, [1n], [7n]],
  ])('répartit %s centimes selon %j', (total, weights, expected) => {
    expect(allocate(eur(total), weights)).toEqual(parts(...expected));
  });

  it('réapplique le signe : un total négatif se répartit comme son opposé', () => {
    expect(allocate(eur(-100n), [1n, 1n, 1n])).toEqual(parts(-34n, -33n, -33n));
    expect(allocate(eur(-10n), [1n, 2n])).toEqual(parts(-3n, -7n));
  });

  it('conserve la devise du total', () => {
    expect(allocate(eur(300n), [1n, 2n])).toEqual(parts(100n, 200n));
  });

  it('départage les restes égaux dans l’ordre des indices', () => {
    expect(allocate(eur(4n), [1n, 1n, 1n, 1n, 1n])).toEqual(parts(1n, 1n, 1n, 1n, 0n));
    expect(allocate(eur(1n), [5n, 5n])).toEqual(parts(1n, 0n));
  });

  it.each([[[]], [[0n]], [[-1n]], [[1n, 0n]], [[0n, 1n]], [[1n, -1n, 2n]], [[1n, 1n, -5n]]])(
    'refuse les poids %j avec invalid-weights',
    (weights) => {
      expect(allocate(eur(100n), weights)).toEqual({ ok: false, error: 'invalid-weights' });
    },
  );
});
