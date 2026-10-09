# POS cash withdrawals

Implemented 2026-10-09 (Asia/Yerevan).

Apply the Admin schema migration before running the updated applications:

```sh
cd apps/admin
alembic upgrade head
```

Admin → Դրամարկղի դուրսբերումներ manages authorized recipients (add, rename, activate/deactivate) and displays permanent withdrawal documents with timestamp, recipient, amount, reason, cashier, session and document identifier. Deactivate recipients instead of deleting them to preserve history. Recipients are separate from employee login accounts.

In an active POS session, Գումար վերցնել selects an active recipient, requires a positive AMD amount and reason, and confirms before recording. The Admin database assigns the timestamp. Withdrawals require an Admin connection and are acknowledged only after database commit. The same request identifier can safely be retried without creating a second withdrawal.

Closing reports show individual withdrawals and reduce cash due by their total:

`cash due = cash sales + credit repayments − withdrawals`

`expected drawer = opening cash + cash due`

Credit sales remain excluded from cash due. Closing records retain the adjusted cash difference, and withdrawal documents remain linked to the original session. Printed closeout receipts include withdrawal details and adjusted totals. For example, 100,000 AMD cash sales and 50,000 AMD withdrawn produce 50,000 AMD due before any opening cash or drawer balance adjustments.
