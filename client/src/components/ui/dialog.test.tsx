import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

// On ne re-teste pas le comportement d'ouverture de Radix (§5.1) : l'angle qui
// nous appartient est que le PORTAIL Radix s'instancie dans NOTRE jsdom (piège
// réel portail + cleanup Testing Library) sans throw.
test('le portail Dialog (Radix) monte dans notre jsdom', async () => {
  const user = userEvent.setup()
  render(
    <Dialog>
      <DialogTrigger>Ouvrir</DialogTrigger>
      <DialogContent>
        <DialogTitle>Titre</DialogTitle>
        <DialogDescription>Description</DialogDescription>
      </DialogContent>
    </Dialog>,
  )

  await user.click(screen.getByRole('button', { name: 'Ouvrir' }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})
