import { createFileRoute, redirect } from '@tanstack/react-router'

import { SetupForm } from '@/features/setup/setup-form'
import { api } from '@/lib/api/client'

// Route `/setup` : sonde `GET /setup` en `beforeLoad`. Ouvert (200) → rend le formulaire ;
// verrouillé (404, un admin existe déjà) → redirige vers `/login` (pas de page setup). Accessible
// sans session (exclue de la garde racine).
export const Route = createFileRoute('/setup')({
  beforeLoad: async () => {
    // Sonde l'état du flux. 404 (verrouillé) → un body vide laisse `error` indéfini sous
    // openapi-fetch : on teste `response.ok` (robuste à tout non-2xx) plutôt que `error`.
    const { response } = await api.GET('/setup')
    // `redirect()` lève un objet Redirect (contrat TanStack), pas une Error → exception au lint.
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    if (!response.ok) throw redirect({ to: '/login' })
  },
  component: SetupForm,
})
