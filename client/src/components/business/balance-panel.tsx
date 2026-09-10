import { Link } from '@tanstack/react-router'
import { Component, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAccountBalance } from '@/hooks/use-account-balance'
import { useAuth } from '@/hooks/useAuth'
import { useSyncStatus } from '@/hooks/use-sync-status'
import { useVisibleAccounts } from '@/hooks/use-visible-accounts'
import { formatCents } from '@/lib/format'

const BALANCE_ERROR_MESSAGE = 'Impossible de charger les soldes. Réessayez plus tard.'

function BalanceError() {
  return (
    <section aria-label="Solde">
      <p role="alert" className="text-destructive text-sm">
        {BALANCE_ERROR_MESSAGE}
      </p>
    </section>
  )
}

// Filet local (SC-01h) : un ÉCHEC SYNCHRONE pendant le rendu (ex. couche données pas encore
// prête) ne doit dégrader QUE ce widget, pas faire disparaître le reste du tableau de bord
// (les autres widgets, le header/nav de la coque `_authenticated`). Complète le cas `error`
// (asynchrone, `useQuery`) géré dans `BalancePanelContent` — deux surfaces d'échec distinctes,
// même message.
class BalanceErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  render() {
    return this.state.hasError ? <BalanceError /> : this.props.children
  }
}

// Fraîcheur dérivée de `useSyncStatus` (`lastSyncedAt`, patron déjà en place) — pas de nouveau
// mécanisme de fraîcheur. `undefined` (avant toute synchro) reste un libellé lisible.
function formatFreshness(lastSyncedAt: Date | undefined): string {
  if (!lastSyncedAt) return 'pas encore synchronisé'
  const minutes = Math.max(0, Math.round((Date.now() - lastSyncedAt.getTime()) / 60_000))
  // Sous la minute, le libellé imposé par `docs/ui/screens-dashboard.md` § Copy FR est
  // « à l'instant » — pas « il y a 0 min ».
  if (minutes < 1) return "à l'instant"
  return `synchronisé il y a ${minutes} min`
}

// Une ligne = un compte visible. Le solde est délégué à `useAccountBalance` (réutilisé tel
// quel, D8) : chaque ligne porte SA propre requête réactive, plutôt que de ré-agréger les
// soldes dans la requête de liste (`selectVisibleAccounts` ne liste QUE les comptes).
function AccountBalanceRow({ account }: { account: { id: string; name: string } }) {
  const { balanceCents, isLoading, error } = useAccountBalance(account.id)
  const { lastSyncedAt } = useSyncStatus()
  return (
    <li className="flex items-center justify-between gap-4 border-b py-2 last:border-b-0">
      <div>
        <p className="font-medium">{account.name}</p>
        <p className="text-muted-foreground text-xs">{formatFreshness(lastSyncedAt)}</p>
      </div>
      {/* Chemin argent : un solde en échec ou en cours de chargement ne doit JAMAIS s'afficher
          comme « 0,00 € » (valeur fabriquée, cf. le défaut `?? 0` de `useAccountBalance`). L'échec
          d'UNE ligne reste local — il ne déclenche pas le fallback global du widget. */}
      {error ? (
        <span role="alert" className="text-destructive text-sm">
          Solde indisponible
        </span>
      ) : isLoading ? (
        <Skeleton className="h-5 w-24" />
      ) : (
        <span className="font-semibold tabular-nums">{formatCents(balanceCents)}</span>
      )}
    </li>
  )
}

// Contenu du widget « Solde » (S15.3 / ticket 01) : solde réel (D8) par compte visible du membre
// courant (perso `owner_id` + commun `account_members`, hors archivés, ADR-0008 mono-devise).
// `userId` vient de `useAuth()` (JWT courant) — même patron que `useCurrentUser`.
//
// Non-Goal explicite : AUCUNE écriture ici. L'état vide navigue vers `/accounts` (CTA), il n'ouvre
// jamais de formulaire.
function BalancePanelContent() {
  const { userId } = useAuth()
  const { data: accounts, isLoading, error } = useVisibleAccounts(userId ?? '')

  if (error) {
    return <BalanceError />
  }

  if (isLoading) {
    return (
      <section aria-label="Solde" className="flex flex-col gap-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </section>
    )
  }

  if (accounts.length === 0) {
    return (
      <section aria-label="Solde" className="flex flex-col items-start gap-3">
        <p className="text-muted-foreground text-sm">Aucun compte pour l’instant.</p>
        <Button asChild size="sm">
          <Link to="/accounts">Créer un compte</Link>
        </Button>
      </section>
    )
  }

  return (
    <section aria-label="Solde">
      <ul>
        {accounts.map((account) => (
          <AccountBalanceRow key={account.id} account={account} />
        ))}
      </ul>
    </section>
  )
}

export function BalancePanel() {
  return (
    <BalanceErrorBoundary>
      <BalancePanelContent />
    </BalanceErrorBoundary>
  )
}
