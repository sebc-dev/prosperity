import { LayoutDashboard } from 'lucide-react'
import { describe, expect, test } from 'vitest'

import { visibleNavItems, type NavItem } from './nav-items'

// Filtre RBAC PUR (le masquage admin réel des entrées de nav, livré pour S15.9). Une entrée
// `adminOnly` de test est utilisée ici car aucune entrée MVP n'active le flag.
const ITEMS: NavItem[] = [
  { to: '/', label: 'Accueil', icon: LayoutDashboard },
  { to: '/settings/invitations', label: 'Invitations', icon: LayoutDashboard, adminOnly: true },
]

describe('visibleNavItems', () => {
  test('member (isAdmin=false) : masque les entrées adminOnly', () => {
    expect(visibleNavItems(ITEMS, false).map((i) => i.to)).toEqual(['/'])
  })

  test('admin (isAdmin=true) : montre tout', () => {
    expect(visibleNavItems(ITEMS, true).map((i) => i.to)).toEqual(['/', '/settings/invitations'])
  })
})
