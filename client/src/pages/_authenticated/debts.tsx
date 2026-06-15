import { createFileRoute } from '@tanstack/react-router'

// Route `/debts` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/debts')({
  component: () => <h1>Dettes — à venir</h1>,
})
