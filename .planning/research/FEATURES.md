# Feature Research

**Domain:** Personal finance management -- self-hosted, envelope budgeting, household/multi-user
**Researched:** 2026-03-28
**Confidence:** HIGH

## Competitive Landscape

Three key competitors inform the feature landscape:

| Product | Model | Budgeting Style | Multi-user | Self-hosted | Bank Sync |
|---------|-------|-----------------|------------|-------------|-----------|
| YNAB | SaaS ($14.99/mo) | Envelope (zero-based) | Shared budget (up to 5) | No | Plaid (US/CA/EU) |
| Actual Budget | Self-hosted (open source) | Envelope (zero-based) | Single-user (multi-device sync) | Yes | GoCardless (EU/UK), SimpleFIN (US/CA) |
| Firefly III | Self-hosted (open source) | Traditional budgets + piggy banks | Single-user per instance | Yes | GoCardless, Nordigen, Spectre |

**Prosperity's niche:** Self-hosted envelope budgeting with first-class multi-user/household support -- something neither Actual Budget nor Firefly III do well. YNAB handles shared budgets but is SaaS-only and expensive.

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or unusable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| User authentication (login/logout) | Security baseline for any multi-user app | MEDIUM | BFF cookie flow with httpOnly cookies, CSRF protection. All competitors have this. |
| Multi-account management | Every finance app supports multiple accounts | LOW | Personal + shared accounts. Distinction visuelle perso/commun. |
| Account access control | Household app = users see only their relevant accounts | MEDIUM | Per-user, per-account permissions (read/write/admin). Unique to household apps. |
| Transaction import (bank sync) | Manual entry is the #1 reason users abandon finance apps | HIGH | Plaid EU/FR with abstract interface. YNAB and Actual both offer this. |
| Transaction categorization | Impossible to budget without categories | LOW | Use Plaid categories as base, allow manual override. All competitors do this. |
| Manual transaction entry | Cash, inter-account transfers, corrections | LOW | Every competitor supports this. Essential for completeness. |
| Envelope budgets with allocation | Core value proposition -- the reason this app exists | HIGH | Create envelopes per account, allocate amounts. YNAB's entire model. |
| Rollover handling | Envelope budgeting without rollover is just category tracking | MEDIUM | Configurable per envelope: auto-rollover or reset to zero. YNAB does this well. |
| Overspending visibility | Users must see when they exceed an envelope | LOW | Visual indicator (red/yellow). YNAB distinguishes cash vs credit overspending. |
| Dashboard with account balances | First thing users look at when opening the app | MEDIUM | Consolidated view of all accessible accounts. All competitors have this. |
| Transaction search and filtering | Users need to find specific transactions | LOW | By date, amount, category, description. Table stakes for any transaction list. |
| Responsive/mobile access | Users check finances on the go | MEDIUM | PWA covers this. YNAB has native apps, Actual has responsive web. |

### Differentiators (Competitive Advantage)

Features that set Prosperity apart from competitors.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| First-class household multi-user | Neither Actual nor Firefly III handle households well. YNAB does but is SaaS. This is Prosperity's core differentiator. | HIGH | N users with personal + shared accounts, per-user permissions, shared envelopes on common accounts. |
| Internal debt tracking | Couples sharing expenses need to track who owes whom. No self-hosted competitor does this natively. | MEDIUM | Auto-calculated from shared account transactions. Goal = zero balance. Long-term history. |
| Setup wizard (first launch) | Self-hosted apps often have painful setup. A guided wizard reduces friction. | LOW | Admin creation, first account setup, Plaid connection. Actual has basic setup but not guided. |
| Transaction reconciliation (pointage) | Matches manual entries with bank imports -- catches errors and builds trust in data | MEDIUM | Manual matching in v1, auto-suggestion in v2. YNAB supports reconciliation, Actual has basic support. |
| Recurring transaction templates | Automate predictable expenses (rent, subscriptions) | LOW | Optional at entry. Actual has scheduled transactions, Firefly III has recurring transactions. Prosperity adds these as a convenience, not core. |
| Per-account envelope scoping | Simpler mental model than cross-account envelopes. Each account has its own budget. | LOW | Design decision already made (PROJECT.md). YNAB uses cross-account envelopes which is more flexible but more complex. |
| Configurable bank sync adapter | Abstract interface lets users swap Plaid for Powens/Salt Edge. No lock-in. | MEDIUM | Interface-based design. Firefly III supports multiple providers but hardcodes them. |

### Anti-Features (Deliberately NOT Building)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-currency support | Some users have accounts in different currencies | Massive complexity: exchange rates, conversion tracking, reporting in base currency. Euros-only covers the actual use case. | Out of scope. Add in v3+ only if real need emerges. |
| Native mobile apps (iOS/Android) | Users expect app store presence | Separate codebase to maintain, app store review process, duplicated logic. PWA covers mobile needs. | Angular PWA with service worker. Same build, installable. |
| Auto-categorization (ML/rules) | Reduces manual work | Requires training data that doesn't exist yet. Rule engines are complex to build and maintain. Premature in v1. | Manual categorization with Plaid categories as starting point. Add rules in v2 after data accumulates. |
| Real-time bank sync (webhooks) | Users want instant transaction visibility | Webhook infrastructure, deduplication races, Plaid webhook reliability issues. Batch is simpler and sufficient. | Batch sync (manual trigger + scheduled). Real-time in v2. |
| Cross-account envelopes | YNAB allows envelopes spanning all accounts | Significantly more complex domain model. Per-account envelopes are simpler and match the "separate accounts" mental model of a household. | Per-account envelopes in v1. Evaluate cross-account in v2 based on usage feedback. |
| Multi-household / SaaS mode | "Can I host this for friends?" | Tenant isolation, billing, support burden. Self-hosted single-foyer is the use case. | One instance per household. Not a SaaS product. |
| Advanced reports (net worth, trends, forecasting) | Power users want deep analytics | Significant UI/chart work, complex queries, edge cases. Not needed for daily use. | Basic dashboard charts in v1. Advanced reports in v2. |
| Notifications / alerts | "Tell me when I overspend" | Push notification infrastructure (service worker, backend scheduler, notification preferences). | Visual indicators in dashboard. Push notifications in v2. |
| Offline-first with sync | "Works without internet" | Conflict resolution, sync protocol, data integrity risks. PWA basic caching is sufficient. | PWA with basic service worker caching. Full offline-first in v2 if needed. |
| Investment / portfolio tracking | Some finance apps track investments | Entirely different domain (market data feeds, portfolio valuation, asset allocation). Out of scope for budgeting. | Not planned. Use a dedicated investment tracker. |
| Bill splitting with external people | "Split dinner with friends" | Social features, external user management, payment tracking outside household. | Internal debt tracking covers household splits. Use Splitwise for external. |

## Feature Dependencies

```
[F1: Authentication]
    └──requires──> (nothing -- foundation)

[F2: Administration]
    └──requires──> [F1: Authentication]

[F3: Account Management]
    └──requires──> [F1: Authentication]
    └──requires──> [F2: Administration] (admin creates accounts)

[F4: Account Access Control]
    └──requires──> [F1: Authentication]
    └──requires──> [F3: Account Management]

[F5: Envelope Budgets]
    └──requires──> [F3: Account Management] (envelopes belong to accounts)
    └──requires──> [F4: Account Access Control] (visibility rules)

[F6: Internal Debt]
    └──requires──> [F3: Account Management]
    └──requires──> [F8: Manual Transactions] (debt from shared expenses)

[F7: Plaid Import]
    └──requires──> [F3: Account Management] (import into which account)
    └──requires──> [F2: Administration] (Plaid connections managed by admin)

[F8: Manual Entry + Pointage]
    └──requires──> [F3: Account Management]

[F9: Dashboard]
    └──requires──> [F3: Account Management]
    └──enhances──> [F5: Envelope Budgets] (budget consumption charts)
    └──enhances──> [F7: Plaid Import] (recent transactions)

[F10: Backup]
    └──requires──> (nothing -- infrastructure only)
```

### Dependency Notes

- **F1 Authentication is the foundation:** Everything depends on knowing who the user is. Build first.
- **F3 Account Management before F5 Envelopes:** Envelopes are scoped to accounts. Accounts must exist first.
- **F7 Plaid Import before F8 Pointage:** Reconciliation only makes sense when there are imported transactions to match against manual entries. However, manual entry itself can exist independently.
- **F9 Dashboard is a consumer, not a producer:** It reads from accounts, envelopes, and transactions. Build last among features since it aggregates everything else.
- **F6 Internal Debt depends on transaction data:** Needs transactions on shared accounts to calculate balances. Build after transaction management is solid.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what the household needs to start tracking finances daily.

- [x] F1: Authentication -- Security foundation, multi-user access
- [x] F2: Administration -- User management, Plaid setup, system health
- [x] F3: Account Management -- Personal and shared bank accounts
- [x] F4: Account Access Control -- Users see only their accounts
- [x] F5: Envelope Budgets -- Core value proposition, per-account with rollover
- [x] F7: Plaid Import -- Automatic transaction import, eliminates manual drudgery
- [x] F8: Manual Entry + Pointage -- Cash transactions, reconciliation
- [x] F9: Dashboard -- Daily usage entry point, balance overview, budget status
- [x] F10: Backup -- Data safety baseline (pg_dump)

### Add After Validation (v1.x)

Features to add once the core is working and being used daily.

- [ ] F6: Internal Debt Tracking -- Add once shared account usage patterns are established
- [ ] Transaction rules for auto-categorization -- After enough manual categorization data exists
- [ ] Recurring transaction templates -- Convenience feature, not blocking daily use
- [ ] Advanced reconciliation suggestions -- Auto-matching imported vs manual transactions

### Future Consideration (v2+)

- [ ] Advanced reports (net worth, spending trends, year-over-year) -- Needs accumulated data
- [ ] Push notifications (budget alerts, low balance warnings) -- Needs push infrastructure
- [ ] Offline-first PWA with full sync -- Complex conflict resolution
- [ ] Cross-account envelope option -- Evaluate based on v1 usage feedback
- [ ] Additional bank connectors (Powens, Salt Edge) -- If Plaid coverage is insufficient

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| F1: Authentication | HIGH | MEDIUM | P0 |
| F2: Administration | HIGH | HIGH | P0 |
| F3: Account Management | HIGH | LOW | P0 |
| F4: Account Access Control | HIGH | MEDIUM | P1 |
| F5: Envelope Budgets | HIGH | HIGH | P1 |
| F7: Plaid Import | HIGH | HIGH | P1 |
| F8: Manual Entry + Pointage | MEDIUM | MEDIUM | P1 |
| F9: Dashboard | MEDIUM | MEDIUM | P2 |
| F6: Internal Debt | MEDIUM | MEDIUM | P2 |
| F10: Backup | LOW | LOW | P2 |

**Priority key:**
- P0: Infrastructure -- must exist before anything else works
- P1: Core value -- the features that make this app useful daily
- P2: Value-add -- enhances the experience but not blocking daily use

## Competitor Feature Analysis

| Feature | YNAB | Actual Budget | Firefly III | Prosperity (planned) |
|---------|------|---------------|-------------|---------------------|
| Envelope budgeting | Yes (core model) | Yes (core model) | Budgets + piggy banks (not true envelope) | Yes, per-account scoping |
| Rollover | Yes, auto | Yes | No (monthly reset) | Configurable per envelope |
| Multi-user/household | Shared budget (up to 5) | No (single user, multi-device) | No (single user) | Yes, N users with personal + shared accounts |
| Bank sync | Plaid (broad coverage) | GoCardless, SimpleFIN | GoCardless, Nordigen, Spectre | Plaid EU/FR with abstract adapter |
| Manual entry | Yes | Yes | Yes | Yes |
| Recurring transactions | Yes (scheduled) | Yes (schedules) | Yes (recurring) | Yes (templates) |
| Split transactions | Yes | Yes | Yes (split by journal) | Not in v1 (defer) |
| Categories | User-defined | User-defined | User-defined + tags | Plaid-based + manual override |
| Goals/targets | Yes (YNAB Targets) | Yes (goal templates) | Piggy banks | Envelope allocation serves this role |
| Reports | Basic (income/expense) | Custom reports | Advanced (many report types) | Basic dashboard charts (v1) |
| Reconciliation | Yes | Basic | No | Manual pointage (v1) |
| Internal debt | No | No | No | Yes (differentiator) |
| Self-hosted | No | Yes | Yes | Yes |
| Mobile | Native apps (iOS/Android) | Responsive web | Responsive web | PWA |
| API | No public API | Yes (REST) | Yes (REST JSON) | Yes (REST, hexagonal architecture) |
| Double-entry | No | No | Yes | No (not needed for envelope budgeting) |
| Multi-currency | No (single currency per budget) | No | Yes | No (euros only) |

## Key Takeaways for Roadmap

1. **Household multi-user is the killer feature.** No self-hosted competitor does this. It touches auth, accounts, access control, and envelopes -- meaning it must be designed into the foundation, not bolted on later.

2. **Envelope budgeting domain model is the hardest part.** YNAB has refined this over 20+ years. Prosperity must get allocation, rollover, and overspending right from day one. Prototyping the domain model early (as noted in PROJECT.md risks) is critical.

3. **Bank sync is high-effort but high-reward.** Without it, users will abandon the app within weeks. Plaid integration should come early, but behind the abstract interface to avoid lock-in.

4. **Dashboard is a consumer feature.** Build it last among MVP features since it depends on data from accounts, transactions, and envelopes.

5. **Internal debt tracking is a differentiator but not MVP-blocking.** Can ship v1 without it and add in v1.x once shared account patterns are established.

6. **Split transactions are notably absent from v1.** Every competitor has them. This is an acceptable deferral for MVP but should be high on the v1.x list since real-world purchases often span categories.

## Sources

- [YNAB Features](https://www.ynab.com/features) -- Feature overview
- [YNAB Overspending Guide](https://support.ynab.com/en_us/overspending-in-ynab-a-guide-ryWoxEyi) -- Rollover and overspending mechanics
- [YNAB Monthly Rollovers](https://www.ynab.com/blog/master-your-monthly-rollovers) -- Rollover behavior details
- [Actual Budget](https://actualbudget.org/) -- Feature overview and self-hosting
- [Actual Budget Schedules](https://actualbudget.org/docs/schedules/) -- Scheduled transaction documentation
- [Firefly III GitHub](https://github.com/firefly-iii/firefly-iii) -- Feature list and architecture
- [Firefly III Piggy Banks](https://docs.firefly-iii.org/explanation/financial-concepts/piggy-banks/) -- Savings goal feature
- [Firefly III Rules](https://docs.firefly-iii.org/how-to/firefly-iii/features/rules/) -- Automation engine
- [Actual Budget vs Firefly III](https://selfhosting.sh/compare/actual-budget-vs-firefly/) -- Self-hosted comparison
- [NerdWallet Best Budget Apps 2026](https://www.nerdwallet.com/finance/learn/best-budget-apps) -- Market overview

---
*Feature research for: Personal finance management (self-hosted, envelope budgeting, household)*
*Researched: 2026-03-28*
