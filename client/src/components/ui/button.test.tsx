import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { Button } from '@/components/ui/button'

// Smoke de MONTAGE uniquement (§5.1) : on prouve que notre intégration de la
// primitive (alias `@/`, `cn`, `cva`, Tailwind) monte sans throw dans notre
// setup — pas de re-test du comportement Radix/React (le clic→handler est exercé
// sur NOTRE code en P14.2.3, theme-toggle.test).
test('Button monte et applique le variant via cva', () => {
  render(<Button variant="secondary">OK</Button>)
  const button = screen.getByRole('button', { name: 'OK' })
  expect(button).toBeInTheDocument()
  // On asserte une classe RÉELLEMENT produite par cva (sortie, pas un passe-plat
  // de la prop) → couvre l'intégration cva sans être tautologique (§12).
  expect(button).toHaveClass('bg-secondary')
})
