import {
  ArrowLeftRight,
  HandCoins,
  LayoutDashboard,
  PiggyBank,
  Settings,
  Tags,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

// Module NON-composant (pas de JSX) : `NAV_ITEMS` y vit isolé pour ne pas déclencher
// `react-refresh/only-export-components` (override actif sur `components/ui/**` seulement).

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Masqué de la nav pour les non-admins (masquage UI, pas autorisation — enforcement S15.9). */
  adminOnly?: boolean
}

// Sections MVP (E15). Aucune entrée n'est `adminOnly` au MVP : les écrans admin (Invitations /
// Household) sont des onglets INTERNES à `/settings` (S15.9), pas des entrées de nav. Le champ
// `adminOnly` + `visibleNavItems` sont livrés et testés pour S15.9.
export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Tableau de bord', icon: LayoutDashboard },
  { to: '/accounts', label: 'Comptes', icon: Wallet },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/budgets', label: 'Budgets', icon: PiggyBank },
  { to: '/debts', label: 'Dettes', icon: HandCoins },
  { to: '/categories', label: 'Catégories', icon: Tags },
  { to: '/settings', label: 'Réglages', icon: Settings },
]

// Filtre pur (testable isolément) : retire les entrées `adminOnly` quand l'utilisateur n'est pas
// admin. Fail-safe : `isAdmin` faux par défaut tant que le rôle n'est pas confirmé (cf. useCurrentUser).
export function visibleNavItems(items: readonly NavItem[], isAdmin: boolean): readonly NavItem[] {
  return items.filter((item) => !item.adminOnly || isAdmin)
}
