import { createFileRoute } from '@tanstack/react-router'

// Route `/categories` (protégée). Placeholder — écran livré par une story E15 ultérieure.
export const Route = createFileRoute('/_authenticated/categories')({
  component: () => <h1>Catégories — à venir</h1>,
})
