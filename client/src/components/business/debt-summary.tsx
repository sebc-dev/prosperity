import { Link } from '@tanstack/react-router'
import { ArrowDownRightIcon, ArrowUpRightIcon } from 'lucide-react'
import { Component, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebtSummary } from '@/hooks/use-debt-summary'
import { useAuth } from '@/hooks/useAuth'
import { formatCents } from '@/lib/format'

const DEBT_ERROR_MESSAGE = 'Impossible de charger les dettes. Réessayez plus tard.'

function DebtError() {
  return (
    <section aria-label="Dettes">
      <p role="alert" className="text-destructive text-sm">
        {DEBT_ERROR_MESSAGE}
      </p>
    </section>
  )
}

// Filet local (même patron que `BalanceErrorBoundary`, SC-01h/SC-02f) : un échec SYNCHRONE de
// rendu dégrade CE widget seul, pas le reste du tableau de bord. Complète le cas `error`
// asynchrone (`useQuery`) géré dans `DebtSummaryContent`.
class DebtErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  render() {
    return this.state.hasError ? <DebtError /> : this.props.children
  }
}

// Sens de la dette (SC-02b, copy FR imposée par docs/ui/screens-dashboard.md) : net négatif =
// l'utilisateur courant est débiteur net (« vous devez », `formatCents` porte déjà le signe `-`
// via `Intl`) ; net positif = créancier net (« vous prête », signe `+` ajouté ici car `Intl` ne
// préfixe pas les nombres positifs). Le sens est DOUBLÉ par une icône + une couleur SÉMANTIQUE
// (tokens `text-success` / `text-destructive`, jamais de couleur en dur) — a11y : le libellé
// texte porte déjà le sens, l'icône reste `aria-hidden`.
function DebtRow({
  row,
}: {
  row: { counterpartyId: string; counterpartyName: string; netCents: number }
}) {
  const isCreditor = row.netCents > 0
  const label = isCreditor ? 'vous prête' : 'vous devez'
  const amount = isCreditor ? `+${formatCents(row.netCents)}` : formatCents(row.netCents)
  const Icon = isCreditor ? ArrowUpRightIcon : ArrowDownRightIcon
  const colorClass = isCreditor ? 'text-success' : 'text-destructive'

  return (
    <li className="border-b last:border-b-0">
      {/* Ligne cliquable entière (SC-02e) : un VRAI lien (pas un `onClick` sur `<li>`), navigable
          au clavier et annoncé par les lecteurs d'écran. `/debts` déclare `validateSearch` pour
          accepter `with` (filtre appliqué par l'écran dédié, hors périmètre de ce ticket). */}
      <Link
        to="/debts"
        search={{ with: row.counterpartyId }}
        className="flex items-center justify-between gap-4 py-2"
      >
        <span className="font-medium">{row.counterpartyName}</span>
        <span className={`flex items-center gap-1 font-semibold tabular-nums ${colorClass}`}>
          <Icon aria-hidden className="size-4" />
          {label} {amount}
        </span>
      </Link>
    </li>
  )
}

// Contenu du widget « Dettes » (S15.3 / ticket 02) : dette nette par contrepartie, lue depuis la
// table-projection `debts` synchronisée (ADR-0002 — le client n'agrège QUE le net à partir des
// rows déjà matérialisées côté serveur, aucun recalcul de la dette elle-même). Le masquage
// débiteur (`account_id`/`source_transaction_id`) est déjà porté par la projection/sync rules
// (ADR-0003) : rien à masquer ici. `userId` vient de `useAuth()`, même patron que `BalancePanel`.
//
// Non-Goal explicite : AUCUNE écriture ici. L'état vide navigue vers `/debts` (CTA), il n'ouvre
// jamais de formulaire.
function DebtSummaryContent() {
  const { userId } = useAuth()
  const { data: rows, isLoading, error } = useDebtSummary(userId ?? '')

  if (error) {
    return <DebtError />
  }

  if (isLoading) {
    return (
      <section aria-label="Dettes" className="flex flex-col gap-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </section>
    )
  }

  if (rows.length === 0) {
    return (
      <section aria-label="Dettes" className="flex flex-col items-start gap-3">
        <p className="text-muted-foreground text-sm">Aucune dette pour l’instant.</p>
        <Button asChild size="sm">
          <Link to="/debts">Voir les dettes</Link>
        </Button>
      </section>
    )
  }

  return (
    <section aria-label="Dettes">
      <ul>
        {rows.map((row) => (
          <DebtRow key={row.counterpartyId} row={row} />
        ))}
      </ul>
    </section>
  )
}

export function DebtSummary() {
  return (
    <DebtErrorBoundary>
      <DebtSummaryContent />
    </DebtErrorBoundary>
  )
}
