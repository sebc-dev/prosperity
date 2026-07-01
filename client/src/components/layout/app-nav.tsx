import { MoreHorizontal } from 'lucide-react'
import { Link } from '@tanstack/react-router'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCurrentUser } from '@/hooks/use-current-user'

import { NAV_ITEMS, PRIMARY_NAV_COUNT, visibleNavItems } from './nav-items'

// Navigation principale en DEUX présentations : sidebar verticale ≥ md, barre basse < md.
// La barre basse n'affiche que PRIMARY_NAV_COUNT entrées directes ; le reste est accessible
// via le bouton « Plus » (DropdownMenu). jsdom n'applique pas les media queries → les tests
// vérifient la PRÉSENCE des deux variantes, pas le basculement (responsive réel = Playwright, S15.10).

function NavLinks() {
  const { isAdmin } = useCurrentUser()
  const items = visibleNavItems(NAV_ITEMS, isAdmin)
  return (
    <>
      {items.map(({ to, label, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          activeOptions={{ exact: to === '/' }}
          activeProps={{ 'aria-current': 'page', className: 'text-foreground font-medium' }}
          inactiveProps={{ className: 'text-muted-foreground' }}
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:text-foreground"
        >
          <Icon className="size-5" aria-hidden />
          <span>{label}</span>
        </Link>
      ))}
    </>
  )
}

function MobileNav() {
  const { isAdmin } = useCurrentUser()
  const items = visibleNavItems(NAV_ITEMS, isAdmin)
  const primary = items.slice(0, PRIMARY_NAV_COUNT)
  const overflow = items.slice(PRIMARY_NAV_COUNT)

  return (
    <>
      {primary.map(({ to, label, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          activeOptions={{ exact: to === '/' }}
          activeProps={{ 'aria-current': 'page', className: 'text-foreground font-medium' }}
          inactiveProps={{ className: 'text-muted-foreground' }}
          className="flex flex-col items-center gap-1 rounded-md px-3 py-2 text-xs hover:text-foreground"
        >
          <Icon className="size-5" aria-hidden />
          <span>{label}</span>
        </Link>
      ))}
      {overflow.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex flex-col items-center gap-1 rounded-md px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
              aria-label="Plus d'options de navigation"
            >
              <MoreHorizontal className="size-5" aria-hidden />
              <span>Plus</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top">
            {overflow.map(({ to, label, icon: Icon }) => (
              <DropdownMenuItem key={to} asChild>
                <Link to={to} className="flex items-center gap-2">
                  <Icon className="size-4" aria-hidden />
                  {label}
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  )
}

export function AppNav() {
  return (
    <>
      {/* Desktop : sidebar verticale */}
      <nav
        aria-label="Navigation principale"
        className="hidden w-56 shrink-0 flex-col gap-1 border-r p-3 md:flex"
      >
        <NavLinks />
      </nav>
      {/* Mobile : barre de navigation basse (PRIMARY_NAV_COUNT items directs + « Plus »). */}
      <nav
        aria-label="Navigation principale (mobile)"
        className="fixed inset-x-0 bottom-0 flex justify-around border-t bg-background p-2 md:hidden"
      >
        <MobileNav />
      </nav>
    </>
  )
}
