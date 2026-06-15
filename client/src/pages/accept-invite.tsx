import { createFileRoute } from '@tanstack/react-router'

// Route PUBLIQUE `/accept-invite` (l'invité n'a pas encore de session) → hors `_authenticated`.
// Placeholder — le flux (preview token + soumission display_name/password) est livré par S15.2.
export const Route = createFileRoute('/accept-invite')({
  component: () => <h1>Accepter l’invitation — à venir</h1>,
})
