import { createFileRoute } from '@tanstack/react-router'

// Route `/debts` (protégée). Placeholder — écran livré par une story E15 ultérieure.
// `validateSearch` déclare le contrat minimal `with` (id `users_public`, cf. docs/ui/screens-debts.md) :
// c'est la cible du clic sur une ligne de `DebtSummary` (SC-02e) — le filtrage effectif de la liste
// par cette contrepartie reste à l'écran réel (hors périmètre de ce ticket), pas ici.
export const Route = createFileRoute('/_authenticated/debts')({
  validateSearch: (search: Record<string, unknown>): { with?: string } => ({
    with: typeof search.with === 'string' ? search.with : undefined,
  }),
  component: () => <h1>Dettes — à venir</h1>,
})
