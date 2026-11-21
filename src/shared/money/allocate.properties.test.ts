import { fc, test } from '@fast-check/vitest';
import { expect } from 'vitest';
import { allocate } from './allocate.ts';

const LIMIT = 10n ** 15n;
const totals = fc.bigInt({ min: -LIMIT, max: LIMIT });
const weights = fc.array(fc.bigInt({ min: 1n, max: 1_000_000n }), { minLength: 1, maxLength: 12 });

function sum(values: readonly bigint[]): bigint {
  return values.reduce((acc, value) => acc + value, 0n);
}

function abs(value: bigint): bigint {
  return value < 0n ? -value : value;
}

function allocated(total: bigint, ws: readonly bigint[]): bigint[] {
  const result = allocate({ amountMinor: total, currency: 'EUR' }, ws);
  if (!result.ok) {
    throw new Error(`allocate devait réussir pour ${String(total)} et ${ws.join(',')}`);
  }
  return result.value.map((part) => part.amountMinor);
}

test.prop([totals, weights])('la somme des parts égale le total', (total, ws) => {
  expect(sum(allocated(total, ws))).toBe(total);
});

test.prop([totals, weights])(
  'chaque part s’écarte de moins d’un centime de la part exacte',
  (total, ws) => {
    const sumW = sum(ws);
    const shares = allocated(total, ws);
    // |part − total·w/Σw| < 1  ⇔  |part·Σw − total·w| < Σw (arithmétique entière exacte).
    const gaps = shares.map((part, index) => abs(part * sumW - total * (ws[index] ?? 0n)));
    expect(gaps.every((gap) => gap < sumW)).toBe(true);
  },
);

test.prop([totals, weights])(
  'les parts ont le signe du total et leur nombre égale celui des poids',
  (total, ws) => {
    const shares = allocated(total, ws);
    expect(shares).toHaveLength(ws.length);
    expect(shares.every((part) => (total >= 0n ? part >= 0n : part <= 0n))).toBe(true);
  },
);

test.prop([totals, weights])('répartir l’opposé donne les parts opposées', (total, ws) => {
  expect(allocated(-total, ws)).toEqual(allocated(total, ws).map((part) => -part));
});
