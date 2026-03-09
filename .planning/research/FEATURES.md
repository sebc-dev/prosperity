# Feature Research

**Domain:** Self-hosted personal finance management for couples
**Researched:** 2026-03-09
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete. Derived from analysis of Monarch Money, YNAB, Honeydue, Firefly III, Actual Budget, and Splitwise.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-user with separate logins | Every couples finance app (Monarch, YNAB, Honeydue) provides individual logins. Sharing a single password is unacceptable. | LOW | Already planned. 2 users, Admin + Standard roles. |
| Account types: personal + shared | Monarch's "yours, mine, ours" model is industry standard. Couples need private accounts AND shared visibility. | MEDIUM | Planned as Personal/Shared with visibility controls. Honeydue goes further with per-account privacy toggles (hide balance, hide transactions, hide entirely). |
| Manual transaction entry | Every app supports this. Must be the fallback when bank sync fails. | LOW | Planned. Include amount, description, date, category, account at minimum. |
| Bank sync / transaction import | Monarch, YNAB, Honeydue, Actual Budget all offer bank connections. Users expect automated imports, not manual-only. | HIGH | Plaid Link planned. This is the single highest-complexity table-stakes feature. |
| Transaction categorization | Universal across all finance apps. Users expect categories like groceries, transport, dining, etc. | LOW | Planned. Provide sensible defaults + custom categories. |
| Monthly budgets by category | YNAB, Monarch, Goodbudget, Firefly III all have category-based budgeting. Core expectation for any budgeting app. | MEDIUM | Planned with envelope and goal modes. |
| Budget progress tracking | Visual indicators of budget consumption (gauges, progress bars, color coding) are standard in every app reviewed. | LOW | Planned with progressive alerts at 75/90/100%. |
| Dashboard / financial overview | Every app has a home screen showing account balances, budget status, recent transactions. Users expect an "at a glance" view. | MEDIUM | Planned. Soldes, budgets, debts, recent transactions. |
| Transaction history with filters | Firefly III, Monarch, YNAB all provide searchable, filterable transaction lists. | LOW | Planned with date, category, account filters. |
| Mobile-responsive design | All modern finance apps work on mobile. Couples use phones for quick expense logging. | MEDIUM | PWA approach covers this. Mobile-first for entry, desktop for analysis. |
| Dark mode / theme support | Standard UX expectation in 2026. Every major app reviewed supports it. | LOW | Planned with system detection. |
| Data export | Firefly III and Actual Budget support CSV/JSON export. Self-hosted users especially expect data portability. | LOW | PRD mentions JSON/CSV export in Phase 3. Should be MVP -- self-hosted users care deeply about data ownership and portability. |
| Secure authentication | JWT, encrypted passwords, HTTPS. Non-negotiable for a financial app. | MEDIUM | Planned: JWT + refresh tokens, bcrypt 12 rounds, HTTPS via Caddy. |

### Differentiators (Competitive Advantage)

Features that set Prosperity apart from both SaaS apps and self-hosted alternatives.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Native internal debt tracking | This is Prosperity's core differentiator. No self-hosted app does this. Splitwise handles it but is not a finance manager. Honeydue has basic expense splitting but not running debt balances with settlement suggestions. | MEDIUM | Track "paid by X for the couple", calculate net balance, suggest settlement. This is the feature that justifies building Prosperity instead of using Firefly III. |
| Couple-native architecture (not bolted on) | Firefly III's multi-user is siloed. Actual Budget shares a single budget file. Neither was designed for couples from the ground up. Prosperity's data model treats "couple" as a first-class concept. | HIGH | Shared accounts, personal accounts, debt tracking, and budgets all designed around the couple relationship from day one. |
| Quick-add mobile entry (3 taps) | YNAB and Monarch require navigating through forms. Honeydue is faster but still 4-5 taps. A floating "+" with amount > favorite category > confirm is genuinely faster. | MEDIUM | Planned. Floating button, 6 favorite categories + "Other", pre-selected default account. Key for adoption by the non-technical partner. |
| Offline-first PWA with conflict resolution | No self-hosted competitor offers real offline-first with sync. Firefly III requires connectivity. Actual Budget has sync but not couple-aware conflict detection. | HIGH | Service Worker + IndexedDB + sync queue + duplicate detection (same amount +/-10%, 5-min window). This is technically ambitious but critical for mobile-first couples. |
| Self-hosted + couples + bank sync | No single self-hosted solution combines all three. Firefly III = self-hosted + bank sync but no couples. Actual Budget = self-hosted + budgeting but limited multi-user. Honeydue = couples + bank sync but SaaS. | HIGH | This combination IS the product. The integration of all three is the moat. |
| Budget modes: envelope + goal | YNAB uses zero-sum envelopes only. Firefly III uses flexible budgets. Prosperity offers both envelope (spend until empty) and goal (savings target) per category. | LOW | Small implementation lift, meaningful UX differentiation. Users choose per category. |
| Shared + individual budgets | Monarch shows household-level budgets. YNAB can do "yours, mine, ours" with separate budget files. Prosperity offers individual AND shared budgets in one view. | MEDIUM | Budget can be scoped to personal or shared, visible accordingly. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems, especially for a 2-user self-hosted app.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Investment / net worth tracking | Monarch and Personal Capital offer it. Feels like "complete financial picture." | Massive scope expansion. Requires different data models, market data feeds, portfolio tracking. For a couple's budgeting app, this is a different product. | Link to external portfolio tools. Focus on cash flow, not asset management. Add as v3+ if ever. |
| AI auto-categorization (MVP) | Monarch and Copilot Money use ML for categorization. Seems like a quick win. | Requires training data, creates black-box behavior, hard to debug for 2 users. The non-technical partner needs predictable behavior, not "AI decided this was dining." | Use rule-based auto-categorization (merchant name matching). Reserve AI for Phase 2 MCP integration where it is an explicit learning goal. |
| Push notifications / email alerts | Every SaaS app has them. Users expect budget alerts via push. | Requires notification infrastructure (web push service, email service), adds ops complexity. For 2 users on a self-hosted app, this is over-engineered. | In-app visual alerts (badge, banner, color changes on dashboard). The app is checked daily anyway. Add push in Phase 3 per the PRD. |
| Multi-currency support | Firefly III supports it. Useful for international couples. | Adds significant complexity: exchange rates, conversion logic, display formatting, budget calculations across currencies. The PRD specifies a single default currency. | Support one currency configurable at setup. If needed later, add as a dedicated feature. |
| Granular permission system | Enterprise apps have complex RBAC. Seems like "proper" access control. | 2 users do not need roles beyond Admin/Standard. Complex permissions create UX overhead and configuration burden. The non-technical partner should not have to think about permissions. | Keep it simple: Admin manages config + Plaid. Both users can manage their own accounts and shared accounts. Personal accounts are private by default. |
| Real-time sync between users | Seems like modern collaboration (Google Docs style). | WebSocket infrastructure, conflict resolution becomes exponentially harder, marginal value for 2 users who rarely edit simultaneously. | Poll-based refresh (30s-60s) or manual refresh button. Conflict detection on sync is sufficient. |
| Recurring transaction management | YNAB and Firefly III have scheduled/recurring transactions. Feels essential. | Tempting to over-engineer with complex recurrence rules (every 2nd Tuesday, quarterly, etc.). For MVP, the complexity does not match the value. | Manual entry or Plaid import handles recurring expenses naturally. Add simple monthly recurrence templates in v1.x, not MVP. |
| Receipt scanning / image attachments | Some apps (ezBookkeeping, Firefly III) support image uploads on transactions. | Storage management, image processing, mobile camera integration adds complexity. For 2 users, not worth the implementation cost at MVP. | Defer to v2+. Quick-add is faster than scanning a receipt anyway. |

## Feature Dependencies

```
[Authentication & Users]
    |-- requires --> [Database & Infrastructure]
    |
    |-- enables --> [Account Management (Personal/Shared)]
    |                   |
    |                   |-- enables --> [Manual Transactions]
    |                   |                   |
    |                   |                   |-- enables --> [Transaction Categorization]
    |                   |                   |                   |
    |                   |                   |                   |-- enables --> [Monthly Budgets]
    |                   |                   |                   |                   |
    |                   |                   |                   |                   |-- enables --> [Budget Alerts]
    |                   |                   |
    |                   |                   |-- enables --> [Internal Debt Tracking]
    |                   |
    |                   |-- enables --> [Plaid Bank Sync]
    |                                       |
    |                                       |-- enables --> [Transaction Deduplication]
    |
    |-- enables --> [Dashboard]
                        |-- aggregates --> [Account Balances]
                        |-- aggregates --> [Budget Status]
                        |-- aggregates --> [Debt Balances]
                        |-- aggregates --> [Recent Transactions]

[PWA / Offline-First]
    |-- requires --> [Manual Transactions] (must exist to cache)
    |-- requires --> [Dashboard] (must exist to cache)
    |-- enables --> [Quick-Add Mobile]
    |-- enables --> [Conflict Resolution]
```

### Dependency Notes

- **Budgets require Categories and Transactions:** Cannot track budget consumption without categorized transactions.
- **Internal Debt Tracking requires Transactions:** Debts are derived from transactions marked as "paid for the couple."
- **Dashboard requires everything else:** It aggregates data from accounts, budgets, debts, and transactions. Build last in the UI layer.
- **Plaid requires Account Management:** Must have accounts to link bank connections to.
- **PWA/Offline requires core features first:** Cannot cache and sync features that do not exist yet.
- **Conflict Resolution requires PWA + multi-user:** Only relevant when offline edits can collide with another user's online edits.
- **Quick-Add enhances Manual Transactions:** It is a streamlined UI for the same underlying transaction creation. Build the full form first, then the shortcut.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what is needed for the couple to start using the app daily.

- [ ] Authentication (2 users, JWT, roles) -- gate to everything
- [ ] Account CRUD (personal + shared, visibility rules) -- foundation for financial data
- [ ] Manual transaction entry with categorization -- data must flow in even without Plaid
- [ ] Transaction history with search and filters -- users need to review and correct entries
- [ ] Monthly budgets by category (envelope + goal modes) -- core value: budget tracking
- [ ] Budget progress visualization with alerts (75/90/100%) -- makes budgets actionable
- [ ] Internal debt tracking (mark as advance, net balance, settlement suggestions) -- primary differentiator
- [ ] Dashboard (balances, budgets, debts, recent transactions) -- the home screen, daily touchpoint
- [ ] Plaid Link integration (import, dedup, error handling) -- automation removes friction
- [ ] Mobile-responsive design -- couples use phones daily
- [ ] Dark/light theme -- low cost, high polish perception
- [ ] Docker deployment (db + api + web) -- self-hosted requirement
- [ ] Data export (JSON/CSV) -- self-hosted users expect data portability from day one

### Add After Validation (v1.x)

Features to add once the couple is using the app daily and pain points emerge.

- [ ] Quick-add mobile (3-tap entry) -- add when manual entry friction becomes the top complaint
- [ ] PWA offline-first with sync -- add when mobile usage patterns confirm the need for offline
- [ ] Conflict resolution (duplicate detection) -- add alongside PWA offline
- [ ] Recurring transaction templates -- add when users tire of re-entering the same monthly bills
- [ ] Category rules (auto-assign based on merchant name) -- add when categorization fatigue sets in
- [ ] Shared + individual budget views -- add when budget discussions reveal the need
- [ ] User preferences (favorite categories, default account) -- add to support quick-add

### Future Consideration (v2+)

Features to defer until the product is stable and learning goals shift.

- [ ] MCP/AI integration (auto-categorization, insights, reports) -- Phase 2 learning goal, not MVP
- [ ] Push/email notifications -- Phase 3, requires notification infrastructure
- [ ] Financial projections (3-6 month forecasts) -- Phase 3, requires sufficient historical data
- [ ] Advanced charts (spending trends, category breakdowns over time) -- Phase 3
- [ ] Receipt scanning / image attachments -- low priority, high complexity
- [ ] Multi-currency support -- only if the couple's situation demands it

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Authentication + users | HIGH | MEDIUM | P1 |
| Account management (personal/shared) | HIGH | MEDIUM | P1 |
| Manual transactions + categorization | HIGH | LOW | P1 |
| Transaction history + filters | HIGH | LOW | P1 |
| Monthly budgets (envelope + goal) | HIGH | MEDIUM | P1 |
| Budget progress + alerts | HIGH | LOW | P1 |
| Internal debt tracking | HIGH | MEDIUM | P1 |
| Dashboard | HIGH | MEDIUM | P1 |
| Plaid Link integration | HIGH | HIGH | P1 |
| Mobile-responsive design | HIGH | MEDIUM | P1 |
| Dark/light theme | MEDIUM | LOW | P1 |
| Docker deployment | HIGH | MEDIUM | P1 |
| Data export (JSON/CSV) | MEDIUM | LOW | P1 |
| Quick-add mobile (3 taps) | HIGH | MEDIUM | P2 |
| PWA offline-first + sync | MEDIUM | HIGH | P2 |
| Conflict resolution | MEDIUM | HIGH | P2 |
| Recurring transaction templates | MEDIUM | LOW | P2 |
| Category auto-rules (merchant matching) | MEDIUM | LOW | P2 |
| User preferences / favorites | MEDIUM | LOW | P2 |
| MCP/AI integration | MEDIUM | HIGH | P3 |
| Push/email notifications | LOW | MEDIUM | P3 |
| Financial projections | LOW | MEDIUM | P3 |
| Advanced charts/reports | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when validated by usage
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Firefly III | Actual Budget | YNAB | Honeydue | Monarch | Splitwise | Prosperity |
|---------|-------------|---------------|------|----------|---------|-----------|------------|
| Self-hosted | Yes | Yes | No | No | No | No | **Yes** |
| Multi-user (couple-native) | No (siloed users) | Experimental (shared file) | Shared budget, separate logins | Yes (built for couples) | Yes (household) | Yes (groups) | **Yes (designed for couples)** |
| Personal + shared accounts | No (single user view) | No | Via separate budgets | Yes (privacy toggles) | Yes ("yours, mine, ours") | No | **Yes (visibility rules)** |
| Bank sync | Yes (via data importer) | Yes (SimpleFIN, GoCardless) | Yes | Yes | Yes | No | **Yes (Plaid)** |
| Internal debt tracking | No | No | No | Basic (split expenses) | No | Yes (core feature) | **Yes (core feature)** |
| Monthly budgets | Yes (flexible) | Yes (zero-sum) | Yes (zero-sum) | Yes (category limits) | Yes (flex + category) | No | **Yes (envelope + goal)** |
| Offline-first | No | Partial (local-first) | No | No | No | No | **Planned (PWA)** |
| Quick mobile entry | No | No | Partial | Partial | Partial | Yes | **Planned (3-tap)** |
| In-app communication | No | No | No | Yes (chat + emoji on transactions) | Yes (tagging) | Yes (comments) | No (out of scope -- couples communicate directly) |
| AI features | No | No | No | No | Basic insights | No | **Phase 2 (MCP)** |
| Dark mode | No | Yes | Yes | Yes | Yes | Yes | **Yes** |
| Docker deployment | Yes | Yes | N/A | N/A | N/A | N/A | **Yes** |

### Key Competitive Insights

1. **No self-hosted app does couples well.** Firefly III is the gold standard for self-hosted finance but has no real multi-user collaboration. Actual Budget is catching up but multi-user is experimental. This is Prosperity's gap to fill.

2. **No couples app is self-hosted.** Honeydue and Monarch are the best couples finance apps, but both are SaaS with no self-hosting option. Privacy-conscious couples have no good option today.

3. **Debt tracking is siloed from budgeting everywhere.** Splitwise excels at "who owes whom" but has no budgets, accounts, or bank sync. Every other app treats debt tracking as an afterthought or ignores it. Integrating debt tracking into the budgeting workflow is Prosperity's unique value.

4. **In-app chat is an anti-feature for Prosperity.** Honeydue's chat and Monarch's tagging make sense for SaaS apps where couples may not be in the same room. For a 2-person self-hosted app, the couple communicates directly. Do not build a chat feature.

## Sources

- [Honeydue - Finance App for Couples](https://www.honeydue.com/)
- [Monarch Money for Couples](https://www.monarch.com/for-couples)
- [YNAB Together Guide](https://support.ynab.com/en_us/ynab-together-B1nS78Cki)
- [YNAB Budgeting as a Couple](https://www.ynab.com/guide/budgeting-as-a-couple)
- [Firefly III Multi-User Documentation](https://docs.firefly-iii.org/how-to/firefly-iii/features/multi-user/)
- [Firefly III Shared Accounts Issue #1783](https://github.com/firefly-iii/firefly-iii/issues/1783)
- [Actual Budget Multi-User Support](https://actualbudget.org/docs/config/multi-user/)
- [Actual Budget Joint Accounts Strategy](https://actualbudget.org/docs/budgeting/joint-accounts/)
- [ezBookkeeping Feature Comparison](https://ezbookkeeping.mayswind.net/comparison/)
- [US News Best Budget Apps for Couples 2025](https://money.usnews.com/money/personal-finance/articles/best-budget-apps-for-couples)
- [NerdWallet Best Budget Apps 2026](https://www.nerdwallet.com/finance/learn/best-budget-apps)
- [NerdWallet Honeydue Review](https://www.nerdwallet.com/finance/learn/honeydue-app-review)
- [InCharge Best Budget Apps for Couples 2026](https://www.incharge.org/tools-resources/best-budget-app-for-couples/)

---
*Feature research for: Self-hosted personal finance management for couples*
*Researched: 2026-03-09*
