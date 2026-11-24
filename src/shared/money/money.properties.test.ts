import { fc, test } from '@fast-check/vitest';
import { expect } from 'vitest';
import { formatMoney, parseAmount } from './money.ts';

const LIMIT = 10n ** 15n;
const amounts = fc.bigInt({ min: -LIMIT, max: LIMIT });
const NBSP = '\u00a0';
const NNBSP = '\u202f';
const FORMAT = new RegExp(`^-?\\d{1,3}(${NNBSP}\\d{3})*,\\d{2}${NBSP}€$`);

test.prop([amounts])('parseAmount(formatMoney(m)) rend le montant d’origine', (amountMinor) => {
  const text = formatMoney({ amountMinor, currency: 'EUR' });
  expect(parseAmount(text)).toEqual({ ok: true, value: amountMinor });
});

test.prop([amounts])(
  'formatMoney rend toujours deux décimales, un € insécable et des milliers groupés',
  (amountMinor) => {
    expect(formatMoney({ amountMinor, currency: 'EUR' })).toMatch(FORMAT);
  },
);

test.prop([fc.bigInt({ min: 1n, max: LIMIT })])(
  'formatMoney de l’opposé ajoute seulement le signe',
  (amountMinor) => {
    const positive = formatMoney({ amountMinor, currency: 'EUR' });
    expect(formatMoney({ amountMinor: -amountMinor, currency: 'EUR' })).toBe(`-${positive}`);
  },
);
