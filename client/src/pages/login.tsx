import { createFileRoute } from '@tanstack/react-router'

import { LoginForm } from '@/features/login/login-form'

// Route `/login` : fine route file-based montant la feature (logique + UI dans `features/login/`).
// Accessible sans session (exclue de la garde racine, cf. __root `beforeLoad`).
export const Route = createFileRoute('/login')({ component: LoginForm })
