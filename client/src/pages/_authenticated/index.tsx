import { createFileRoute } from '@tanstack/react-router'

import { BalancePanel } from '@/components/business/balance-panel'
import { DebtSummary } from '@/components/business/debt-summary'

// Route `/` (protégée, sous le layout `_authenticated`) : tableau de bord. Le premier widget
// (S15.3, ticket 01) est le solde réel par compte (`BalancePanel`) ; le ticket 02 ajoute la dette
// nette par contrepartie (`DebtSummary`) ; les widgets suivants (budgets, transactions récentes —
// tickets 03/04) rejoignent cette disposition.
export const Route = createFileRoute('/_authenticated/')({
  component: () => (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Tableau de bord</h1>
      <BalancePanel />
      <DebtSummary />
    </div>
  ),
})
