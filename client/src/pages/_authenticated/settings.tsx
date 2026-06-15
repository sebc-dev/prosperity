import { createFileRoute } from '@tanstack/react-router'

// Route `/settings` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/settings')({
  component: () => <h1>Réglages — à venir</h1>,
})
