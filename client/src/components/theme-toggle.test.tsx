import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { expect, test } from 'vitest'

import { ThemeProvider } from '@/app/theme-provider'
import { ThemeToggle } from '@/components/theme-toggle'
import { THEME_STORAGE_KEY } from '@/hooks/use-theme'

const html = () => document.documentElement

function renderToggle(wrap: (node: React.ReactNode) => React.ReactNode = (n) => n) {
  return render(
    wrap(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    ),
  )
}

// Le regex /thème/i est couplé à l'`aria-label="Basculer le thème"` du ThemeToggle.
const clickToggle = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: /thème/i }))

// Thème par défaut : sombre (décision #240). Le toggle part donc de dark → clair.
// C'est ICI qu'on teste clic→handler (sur NOTRE code), pas dans button.test (§5.1).
test('le toggle bascule la classe .dark sur <html>', async () => {
  const user = userEvent.setup()
  renderToggle()
  expect(html().classList.contains('dark')).toBe(true) // défaut sombre

  await clickToggle(user)
  expect(html().classList.contains('dark')).toBe(false) // basculé vers clair
})

test('persistance : le clic écrit le nouveau thème dans localStorage', async () => {
  const user = userEvent.setup()
  renderToggle()

  await clickToggle(user) // dark → light
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
})

test("idempotence : deux clics ramènent à l'état initial", async () => {
  const user = userEvent.setup()
  renderToggle()

  await clickToggle(user) // dark → light
  await clickToggle(user) // light → dark
  expect(html().classList.contains('dark')).toBe(true)
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
})

// L'app monte en <StrictMode> (main.tsx) : le double-mount/effet de React 19 ne
// doit pas produire d'état incohérent (pas de double-toggle).
test('montage sous <StrictMode> : classList et localStorage convergent', () => {
  renderToggle((node) => <StrictMode>{node}</StrictMode>)
  expect(html().classList.contains('dark')).toBe(true) // défaut sombre
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
})
