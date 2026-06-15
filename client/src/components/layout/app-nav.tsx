import { Link } from '@tanstack/react-router'

import { useCurrentUser } from '@/hooks/use-current-user'
import { cn } from '@/lib/utils'

import { NAV_ITEMS, visibleNavItems } from './nav-items'

// Navigation principale, rendue en DEUX présentations CSS-only (Tailwind) à partir de la MÊME
// source `NAV_ITEMS` : sidebar verticale ≥ md, barre basse < md. jsdom n'applique pas les media
// queries → les tests vérifient la PRÉSENCE des deux variantes, pas le basculement (responsive
// réel = Playwright, S15.10).
function NavLinks({ orientation }: { orientation: 'sidebar' | 'bottom' }) {
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
          className={cn(
            'flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:text-foreground',
            orientation === 'bottom' && 'flex-col gap-1 text-xs',
          )}
        >
          <Icon className="size-5" aria-hidden />
          <span>{label}</span>
        </Link>
      ))}
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
        <NavLinks orientation="sidebar" />
      </nav>
      {/* Mobile : barre de navigation basse.
          ⚠️ À VALIDER (#240) : 7 items en barre basse, c'est dense sur petit écran — le pattern
          usuel plafonne à ~5 (le reste → menu « Plus »). Arbitrage UI/UX en attente. */}
      <nav
        aria-label="Navigation principale (mobile)"
        className="fixed inset-x-0 bottom-0 flex justify-around border-t bg-background p-2 md:hidden"
      >
        <NavLinks orientation="bottom" />
      </nav>
    </>
  )
}
