// @vitest-environment jsdom
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { expect, test, vi } from 'vitest'

import { getToken } from '@/lib/powersync/auth-token'
import { renderWithProviders } from '@tests/render'
import { server } from '@tests/msw/server'

const API = 'http://localhost:8000'

// __root monte PowerSyncProvider → mock du singleton (pas de wasm/OPFS).
vi.mock('@/lib/powersync/client')
// Toast mocké : on n'assertе que les MESSAGES, jamais l'UI Sonner réelle.
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))
const toastError = vi.mocked(toast.error)

async function fillAndSubmit() {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'admin@foyer.fr')
  await user.type(screen.getByLabelText('Mot de passe'), 'motdepasse123') // ≥ 12
  await user.type(screen.getByLabelText('Nom affiché'), 'Alice')
  await user.type(screen.getByLabelText('Nom du foyer'), 'Foyer Alice')
  await user.click(screen.getByRole('button', { name: /créer le premier administrateur/i }))
}

test('GET /setup ouvert (200) → le formulaire s’affiche', async () => {
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  expect(await screen.findByLabelText('Nom du foyer')).toBeInTheDocument()
})

test('GET /setup verrouillé (404) → redirection /login (pas de formulaire)', async () => {
  server.use(http.get(`${API}/setup`, () => new HttpResponse(null, { status: 404 })))
  renderWithProviders(null, { route: '/setup', auth: 'none' })

  // Redirigé vers /login → le champ « Nom du foyer » du setup n'apparaît jamais.
  expect(await screen.findByLabelText('Mot de passe')).toBeInTheDocument()
  expect(screen.queryByLabelText('Nom du foyer')).not.toBeInTheDocument()
})

test('submit valide → POST /setup → TokenPair → auto-login → navigation /', async () => {
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  await fillAndSubmit()

  await waitFor(() => expect(getToken()).toBeTruthy()) // auto-login (commitTokens)
  expect(await screen.findByRole('heading', { name: /composants/i })).toBeInTheDocument()
})

test('POST /setup → 404 (course perdue) → toast + redirection /login', async () => {
  server.use(http.post(`${API}/setup`, () => new HttpResponse(null, { status: 404 })))
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  await fillAndSubmit()

  await waitFor(() => expect(toastError).toHaveBeenCalledWith('Configuration déjà effectuée.'))
  expect(getToken()).toBeNull()
})

test('password : contrainte native minLength=12 câblée (miroir du min_length backend)', async () => {
  // jsdom n'implémente NI le blocage de soumission sur contrainte, NI la validité `tooShort` :
  // on assert donc le CÂBLAGE de la contrainte (`minLength=12`, requis), seul invariant
  // vérifiable en jsdom. Dans un navigateur réel, un mot de passe < 12 bloque la soumission ;
  // le backend (`SecretStr min_length=12`) reste de toute façon l'autorité (422 géré).
  renderWithProviders(null, { route: '/setup', auth: 'none' })
  const pwd = await screen.findByLabelText<HTMLInputElement>('Mot de passe')

  expect(pwd.minLength).toBe(12)
  expect(pwd.required).toBe(true)
})
