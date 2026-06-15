import { createFileRoute } from '@tanstack/react-router'

// Route `/budgets` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/budgets')({
  component: () => <h1>Budgets — à venir</h1>,
})
