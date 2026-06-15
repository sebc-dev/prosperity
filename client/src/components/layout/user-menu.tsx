import { Link, useNavigate } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCurrentUser } from '@/hooks/use-current-user'
import { useAuth } from '@/hooks/useAuth'

// Menu user du header : nom affiché + accès Réglages + déconnexion. `logout()` (session.ts)
// révoque côté serveur ET purge token + storage + timer ; on navigue ensuite vers /login (la
// garde `_authenticated` redirigerait de toute façon, le token étant purgé — défense en profondeur).
export function UserMenu() {
  const { logout } = useAuth()
  const { user } = useCurrentUser()
  const navigate = useNavigate()
  const name = user?.display_name ?? 'Compte'

  const handleLogout = async () => {
    await logout()
    await navigate({ to: '/login' })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm">
          {name}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings">Réglages</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void handleLogout()}>Se déconnecter</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
