import type { ReactNode } from 'react'

import { SyncStatusBadge } from '@/components/business/sync-status-badge'
import { ThemeToggle } from '@/components/theme-toggle'
import { APP_LOGO_MARK, APP_NAME, APP_TAGLINE } from '@/config/branding'

import { AppNav } from './app-nav'
import { UserMenu } from './user-menu'

// Chrome applicatif des routes authentifiées (rendu par la route de layout `_authenticated`) :
// header (logo + badge de synchro + bascule thème + menu user), navigation responsive, footer.
// Les écrans publics (login/setup/accept-invite) ne passent PAS par ce layout (rendus nus).
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between gap-4 border-b p-4">
        <span className="flex items-center gap-2 text-lg font-semibold" style={{ fontFamily: 'var(--font-serif)' }}>
          <img src={APP_LOGO_MARK} alt="" aria-hidden width={28} height={28} />
          {APP_NAME}
        </span>
        <div className="flex items-center gap-2">
          <SyncStatusBadge />
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>
      <div className="flex flex-1">
        <AppNav />
        {/* pb-20 < md : laisse la place à la barre de nav basse fixe. */}
        <main className="flex-1 p-4 pb-20 md:pb-4">{children}</main>
      </div>
      <footer className="text-muted-foreground border-t p-4 text-center text-xs">
        {APP_NAME} — {APP_TAGLINE}
      </footer>
    </div>
  )
}
