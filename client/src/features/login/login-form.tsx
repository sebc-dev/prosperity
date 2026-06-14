import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fieldValue } from '@/lib/form-data'
import { useAuth } from '@/hooks/useAuth'

// Formulaire de connexion : POST /auth/login (via useAuth → session) → token stocké → redirection
// vers `/`. Erreur (401 OU réseau) → message inline `role="alert"` GÉNÉRIQUE (jamais « email
// inconnu » : le backend renvoie un 401 uniforme anti-énumération, on n'en révèle pas plus).
export function LoginForm() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setPending(true)
    const form = new FormData(e.currentTarget)
    try {
      await login(fieldValue(form, 'email'), fieldValue(form, 'password'))
      await navigate({ to: '/' })
    } catch {
      setError('Identifiants invalides.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form
      onSubmit={(e) => void onSubmit(e)}
      className="mx-auto flex max-w-sm flex-col gap-4"
      aria-label="Connexion"
    >
      <Input name="email" type="email" required aria-label="Email" autoComplete="email" />
      <Input
        name="password"
        type="password"
        required
        aria-label="Mot de passe"
        autoComplete="current-password"
      />
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        Se connecter
      </Button>
    </form>
  )
}
