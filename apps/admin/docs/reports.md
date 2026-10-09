# Business reports («Հաշվետվություններ»)

Open **Հաշվետվություններ → Բիզնեսի հաշվետվություն**. Choose a category,
period, or inclusive custom dates and press **Հաշվարկել**. Presets cover 1,
7, 30, 90, and 365 days. Custom ranges allow up to 366 days; future dates
are rejected. Charts offer daily or monthly aggregation and metric selection.
The comparison is the immediately preceding period of equal duration. Monthly
chart buckets group the selected period's days and the matching offsets from
the preceding period; partial months are not normalized.

Definitions:

- Revenue: completed sale totals; credit sales are included.
- Cost of sales: active sale items' quantity × historical cost snapshot.
- Reported profit: revenue − cost of sales − finalized write-offs. Missing
  sale-item costs suppress the profit total and profit chart. It excludes
  unrecorded wages, rent, taxes, and other operating expenses.
- Received: revenue − credit-sale amount + customer repayments made in the period.
- Recorded cash flow: received − supplier payments made in the period. This
  combines payment methods and is not the physical cash drawer balance.
- Purchases: documents excluding drafts and cancellations, by purchase date.
  Purchases are not deducted again from profit.
- Write-offs: finalized documents, by lock date rather than draft creation date.
- Free goods: zero-total active sale lines, valued at known historical cost.
- Current inventory: recorded quantities × current cost / selling prices,
  including inactive products that still have balances. Missing cost and
  negative quantities are flagged. These are current valuations, not historical
  inventory balances or earned revenue.
- Current customer balance: completed credit sales − repayments.
- Current supplier balance: opening debt + valid purchases − supplier payments.
  Negative debt balances represent advances; counterparties are not filtered
  out simply because they have been deactivated.

Reports reflect the current state of edited documents, not an immutable
accounting ledger. Kitchen stock transformations are reflected in current product
balances; internal transfers are not treated as cash expenses. The app does not
record a complete ledger of operating expenses or cash withdrawals.

The repository executes two SELECTs: independently grouped transaction sources
combined with UNION ALL, followed by scalar balance aggregates. It returns at
most ten metrics per day for the selected and preceding periods, never full
transaction collections. The service only fills missing dates and combines these
aggregates. PostgreSQL groups timestamps in the configured business timezone;
range predicates use raw indexed timestamp columns with UTC bounds.

Apply the migrations with `alembic upgrade head` from `apps/admin` before running
the updated app. Revision `q7b8c9d0e1f2` adds report date and sale-item join indexes.
No migrations are run automatically at startup.

## Diagnostics

Background operation failures, including report loading and login, are recorded
with their screen name and traceback in `apps/admin/logs/app.log` and
`apps/admin/logs/error.log`, and in the console. `LOG_DIR` overrides that directory.
Each file rotates at 5 MiB with five backups. Startup logs the resolved directory.
Repeated logging setup replaces its own handlers to prevent duplicate entries.
Unhandled Python and Python-thread exceptions are also logged. The report UI
keeps database failure messages brief; inspect `error.log` for the SQL traceback.
