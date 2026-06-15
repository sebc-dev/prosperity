import { createFileRoute } from '@tanstack/react-router'

// Route `/` (protégée, sous le layout `_authenticated`). Placeholder : le vrai tableau de bord
// (solde réel + widgets) arrive en S15.3.
export const Route = createFileRoute('/_authenticated/')({
  component: () => <h1>Tableau de bord — à venir</h1>,
})
