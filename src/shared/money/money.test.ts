import { describe, expect, it } from 'vitest';
import { formatMoney, money, parseAmount } from './money.ts';

const NBSP = '\u00a0';
const NNBSP = '\u202f';

function ok(value: bigint): { ok: true; value: bigint } {
  return { ok: true, value };
}

describe('parseAmount', () => {
  it.each([
    ['84', 8400n],
    ['84,00', 8400n],
    ['84.00', 8400n],
    ['84.5', 8450n],
    ['84,5', 8450n],
    ['84,05', 8405n],
    ['-12,30', -1230n],
    ['-84', -8400n],
    ['0', 0n],
    ['0,05', 5n],
    ['-0,05', -5n],
    ['007', 700n],
    ['5,0', 500n],
    ['12.34', 1234n],
    ['123456789012345678901,99', 12345678901234567890199n],
  ])('lit « %s » comme %s centimes', (input, expected) => {
    expect(parseAmount(input)).toEqual(ok(expected));
  });

  it('ignore les espaces, U+00A0, U+202F et le € final', () => {
    expect(parseAmount(`1${NNBSP}234,56${NBSP}€`)).toEqual(ok(123456n));
    expect(parseAmount('1 234,56 €')).toEqual(ok(123456n));
    expect(parseAmount(`  84,00${NBSP}`)).toEqual(ok(8400n));
    expect(parseAmount('84€')).toEqual(ok(8400n));
  });

  it.each(['1,234', '1.500', '0,001', '12,345678'])(
    'refuse « %s » avec too-many-decimals',
    (input) => {
      expect(parseAmount(input)).toEqual({ ok: false, error: 'too-many-decimals' });
    },
  );

  it.each([
    '',
    ' ',
    'abc',
    '1e3',
    '12,',
    '12.',
    '--1',
    '-',
    ',5',
    '.5',
    '1,2,3',
    '1.2.3',
    '+5',
    '€',
    '€12',
    '12€3',
    '1-2',
    '12,3a',
    'a12',
    '1 2 3 a',
    '١٢',
  ])('refuse « %s » avec invalid-amount', (input) => {
    expect(parseAmount(input)).toEqual({ ok: false, error: 'invalid-amount' });
  });
});

describe('money', () => {
  it('accepte exactement la devise EUR', () => {
    expect(money(8400n, 'EUR')).toEqual({
      ok: true,
      value: { amountMinor: 8400n, currency: 'EUR' },
    });
  });

  it.each(['USD', 'eur', 'EUR ', ' EUR', 'EURO', ''])('refuse la devise « %s »', (currency) => {
    expect(money(1n, currency)).toEqual({ ok: false, error: 'unsupported-currency' });
  });
});

describe('formatMoney', () => {
  it.each([
    [8400n, `84,00${NBSP}€`],
    [123456789n, `1${NNBSP}234${NNBSP}567,89${NBSP}€`],
    [-1250n, `-12,50${NBSP}€`],
    [5n, `0,05${NBSP}€`],
    [0n, `0,00${NBSP}€`],
    [10n, `0,10${NBSP}€`],
    [99n, `0,99${NBSP}€`],
    [100n, `1,00${NBSP}€`],
    [1005n, `10,05${NBSP}€`],
    [99999n, `999,99${NBSP}€`],
    [100000n, `1${NNBSP}000,00${NBSP}€`],
    [-5n, `-0,05${NBSP}€`],
    [-123456789n, `-1${NNBSP}234${NNBSP}567,89${NBSP}€`],
    [
      12345678901234567890199n,
      `123${NNBSP}456${NNBSP}789${NNBSP}012${NNBSP}345${NNBSP}678${NNBSP}901,99${NBSP}€`,
    ],
  ])('rend %s centimes comme « %s »', (amountMinor, expected) => {
    expect(formatMoney({ amountMinor, currency: 'EUR' })).toBe(expected);
  });
});
