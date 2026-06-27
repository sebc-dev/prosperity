import { createFileRoute } from '@tanstack/react-router'

// Route `/accounts` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/accounts')({
  component: () => <h1>Comptes — à venir</h1>,
})
