// @vitest-environment jsdom
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'

import { tokenStore } from '@/lib/auth/token-store'
import { renderWithProviders } from '@tests/render'

// Tests ROUTÉS : montent le VRAI __root → _authenticated → AppLayout. Le mock du singleton
// PowerSync évite wasm/OPFS. `useCurrentUser` est mocké pour piloter nom/rôle sans toucher la
// db Drizzle (le stub du mock client n'est pas une vraie db).
vi.mock('@/lib/powersync/client')
vi.mock('@/hooks/use-current-user', () => ({
  useCurrentUser: vi.fn(() => ({
    user: { id: 'u1', display_name: 'Alice', role: 'member' },
    isAdmin: false,
  })),
}))

test('header : logo + badge synchro + bascule thème + menu user, et la nav liste les sections', async () => {
  renderWithProviders(null, { route: '/' })
  expect(await screen.findByText('Prosperity')).toBeInTheDocument() // logo (≠ texte footer)
  expect(screen.getByRole('button', { name: /basculer le thème/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Alice' })).toBeInTheDocument() // déclencheur menu user
  expect(screen.getByRole('status')).toBeInTheDocument() // SyncStatusBadge
  expect(screen.getAllByRole('link', { name: /comptes/i }).length).toBeGreaterThan(0)
})

test('menu user : fermé par défaut → ouverture → Réglages + Se déconnecter', async () => {
  const user = userEvent.setup()
  renderWithProviders(null, { route: '/' })
  // Fermé par défaut : aucun item de menu rendu tant que le déclencheur n'est pas activé.
  await screen.findByRole('button', { name: 'Alice' })
  expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  // Ouverture → les items apparaissent (prouve que le clic change réellement l'état du dropdown).
  await user.click(screen.getByRole('button', { name: 'Alice' }))
  expect(await screen.findByRole('menuitem', { name: /réglages/i })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: /se déconnecter/i })).toBeInTheDocument()
})

test('déconnexion : purge le token et redirige vers /login', async () => {
  const user = userEvent.setup()
  renderWithProviders(null, { route: '/' }) // auth=authenticated par défaut → token seedé
  await user.click(await screen.findByRole('button', { name: 'Alice' }))
  await user.click(await screen.findByRole('menuitem', { name: /se déconnecter/i }))
  await waitFor(() => expect(tokenStore.get()).toBeNull()) // logout() a purgé
  expect(await screen.findByRole('button', { name: /se connecter/i })).toBeInTheDocument() // → /login
})

test('responsive : sidebar (desktop) ET barre basse (mobile) présentes dans le DOM', async () => {
  renderWithProviders(null, { route: '/' })
  // jsdom n'applique pas les media queries Tailwind → on vérifie la PRÉSENCE des deux variantes ;
  // le basculement réel relève de l'E2E (Playwright, S15.10).
  expect(
    await screen.findByRole('navigation', { name: 'Navigation principale' }),
  ).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: /mobile/i })).toBeInTheDocument()
})

test('lien actif : la section courante (/) porte aria-current="page"', async () => {
  renderWithProviders(null, { route: '/' })
  const links = await screen.findAllByRole('link', { name: /tableau de bord/i })
  expect(links.some((el) => el.getAttribute('aria-current') === 'page')).toBe(true)
})
