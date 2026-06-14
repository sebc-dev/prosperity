import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fieldValue } from '@/lib/form-data'
import { api } from '@/lib/api/client'
import { commitTokens } from '@/lib/auth/session'
import { decodeExp } from '@/lib/auth/token-store'

// Création du PREMIER admin (flux `/setup`, ADR 0010 lock-after-init) — SANS JWT préalable. Succès
// = TokenPair → auto-login (commitTokens) → redirection `/`. 404 (verrouillé / course perdue) →
// toast + retour `/login`. La page n'est rendue que si `GET /setup` est ouvert (garde `beforeLoad`).
export function SetupForm() {
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setPending(true)
    const form = new FormData(e.currentTarget)
    try {
      const { data, error } = await api.POST('/setup', {
        body: {
          email: fieldValue(form, 'email'),
          password: fieldValue(form, 'password'),
          display_name: fieldValue(form, 'display_name'),
          household_name: fieldValue(form, 'household_name'),
        },
      })
      if (error || !data) {
        // 404 : un admin existe déjà (init verrouillée ou course perdue) → retour login.
        toast.error('Configuration déjà effectuée.')
        await navigate({ to: '/login' })
        return
      }
      await commitTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        accessExp: decodeExp(data.access_token) ?? 0,
      })
      await navigate({ to: '/' })
    } catch {
      // Erreur réseau (non-HTTP) → toast générique, pas de crash.
      toast.error('Échec de la configuration. Réessayez.')
    } finally {
      setPending(false)
    }
  }

  return (
    <form
      onSubmit={(e) => void onSubmit(e)}
      className="mx-auto flex max-w-sm flex-col gap-4"
      aria-label="Configuration"
    >
      <Input name="email" type="email" required aria-label="Email" autoComplete="email" />
      <Input
        name="password"
        type="password"
        required
        minLength={12}
        aria-label="Mot de passe"
        autoComplete="new-password"
      />
      <Input name="display_name" type="text" required aria-label="Nom affiché" />
      <Input name="household_name" type="text" required aria-label="Nom du foyer" />
      <Button type="submit" disabled={pending}>
        Créer le premier administrateur
      </Button>
    </form>
  )
}
