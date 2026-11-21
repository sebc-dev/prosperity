// Squelette RED : signatures finales, comportement volontairement faux (remplacé au GREEN).
export type Result<T, E extends string> = { ok: true; value: T } | { ok: false; error: E };

export interface Money {
  readonly amountMinor: bigint;
  readonly currency: 'EUR';
}

export function money(
  _amountMinor: bigint,
  _currency: string,
): Result<Money, 'unsupported-currency'> {
  return { ok: false, error: 'unsupported-currency' };
}

export function parseAmount(
  _input: string,
): Result<bigint, 'invalid-amount' | 'too-many-decimals'> {
  return { ok: false, error: 'invalid-amount' };
}

export function formatMoney(_m: Money): string {
  return '';
}
