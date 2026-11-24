export type Result<T, E extends string> = { ok: true; value: T } | { ok: false; error: E };

export interface Money {
  readonly amountMinor: bigint;
  readonly currency: 'EUR';
}

// `\s` couvre les espaces, U+00A0 (insécable) et U+202F (insécable fine).
const WHITESPACE = /\s/g;
const TRAILING_EURO = /€$/;
const UNSIGNED_AMOUNT = /^\d+(?:[.,]\d+)?$/;
const DECIMAL_SEPARATOR = /[.,]/;
const CENTS_PER_UNIT = 100n;
const NBSP = '\u00a0';
const grouping = new Intl.NumberFormat('fr-FR');

/** Seule la devise `EUR` est acceptée en v1 ; le modèle reste multi-devise. */
export function money(
  amountMinor: bigint,
  currency: string,
): Result<Money, 'unsupported-currency'> {
  if (currency !== 'EUR') {
    return { ok: false, error: 'unsupported-currency' };
  }
  return { ok: true, value: { amountMinor, currency } };
}

/**
 * Chaîne vers centimes, sans flottant : espaces, U+00A0, U+202F et `€` final ignorés,
 * signe `-` initial, virgule ou point décimal, deux décimales au plus.
 */
export function parseAmount(input: string): Result<bigint, 'invalid-amount' | 'too-many-decimals'> {
  const text = input.replace(WHITESPACE, '').replace(TRAILING_EURO, '');
  const negative = text.startsWith('-');
  const unsigned = negative ? text.slice(1) : text;
  if (!UNSIGNED_AMOUNT.test(unsigned)) {
    return { ok: false, error: 'invalid-amount' };
  }
  const separator = unsigned.search(DECIMAL_SEPARATOR);
  const units = separator === -1 ? unsigned : unsigned.slice(0, separator);
  const decimals = separator === -1 ? '' : unsigned.slice(separator + 1);
  if (decimals.length > 2) {
    return { ok: false, error: 'too-many-decimals' };
  }
  const cents = BigInt(`${units}${decimals.padEnd(2, '0')}`);
  return { ok: true, value: negative ? -cents : cents };
}

/** « 84,00 € » : U+202F entre les milliers, U+00A0 avant `€`, deux chiffres de centimes. */
export function formatMoney(m: Money): string {
  const negative = m.amountMinor < 0n;
  const magnitude = negative ? -m.amountMinor : m.amountMinor;
  const units = grouping.format(magnitude / CENTS_PER_UNIT);
  const cents = (magnitude % CENTS_PER_UNIT).toString().padStart(2, '0');
  return `${negative ? '-' : ''}${units},${cents}${NBSP}€`;
}
