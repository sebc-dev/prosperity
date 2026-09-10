import { describe, expect, test } from 'vitest'

import { formatCents } from './format'

// `Intl.NumberFormat('fr-FR', …)` insère une espace fine insécable (U+202F) comme séparateur de
// milliers et une espace insécable (U+00A0) avant le symbole monétaire — pas des espaces ASCII
// classiques. On fige ces caractères en dur (échappés, pour rester lisible dans un diff) afin de
// prouver le COMPORTEMENT réel rendu à l'écran, pas une supposition sur l'implémentation.
const THIN_NBSP = ' ' // séparateur de milliers fr-FR
const NBSP = ' ' // avant le symbole monétaire

describe('formatCents', () => {
  test('SC-01b — formatCents(123456) rend "1 234,56 €" (fr-FR, séparateur de milliers)', () => {
    expect(formatCents(123456)).toBe(`1${THIN_NBSP}234,56${NBSP}€`)
  })

  test('SC-01c — formatCents(-500) rend un montant négatif signé', () => {
    const result = formatCents(-500)
    expect(result.startsWith('-')).toBe(true)
    expect(result).toBe(`-5,00${NBSP}€`)
  })
})
