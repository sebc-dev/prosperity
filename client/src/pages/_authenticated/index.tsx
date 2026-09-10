import { createFileRoute } from '@tanstack/react-router'

import { BalancePanel } from '@/components/business/balance-panel'

// Route `/` (protégée, sous le layout `_authenticated`) : tableau de bord. Le premier widget
// (S15.3, ticket 01) est le solde réel par compte (`BalancePanel`) ; les widgets suivants
// (dettes, budgets, transactions récentes — tickets 02/03/04) rejoignent cette disposition.
export const Route = createFileRoute('/_authenticated/')({
  component: () => (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Tableau de bord</h1>
      <BalancePanel />
    </div>
  ),
})
