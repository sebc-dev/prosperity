import { expect, test } from 'vitest'

import { cn } from '@/lib/utils'

// `cn` = clsx + tailwind-merge : invariant réel (non tautologique, §12).
test('cn fusionne les classes Tailwind en conflit (tailwind-merge gagne le dernier)', () => {
  expect(cn('px-2', 'px-4')).toBe('px-4')
})

test('cn évalue les classes conditionnelles (clsx)', () => {
  const disabled = false
  expect(cn('a', disabled && 'b', 'c')).toBe('a c')
})
