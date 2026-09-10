// Formatage monétaire fr-FR (ADR-0008, D05 : mono-devise EUR pour le v1). `Intl.NumberFormat`
// gère nativement le séparateur de milliers (espace insécable) et le signe négatif — pas de
// manipulation manuelle de chaîne.
const EUR_FORMATTER = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
})

// `amountCents` est un entier de centimes (colonne `amount_cents`, cf. schema Drizzle) → on
// divise par 100 avant de formater. `-500` → « -5,00 € » (signe porté par `Intl`).
export function formatCents(amountCents: number): string {
  return EUR_FORMATTER.format(amountCents / 100)
}
