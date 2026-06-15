import { createFileRoute } from '@tanstack/react-router'

// Route `/transactions` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/transactions')({
  component: () => <h1>Transactions — à venir</h1>,
})
