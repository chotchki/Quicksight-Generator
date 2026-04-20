# Sub-Ledger Overdraft

*Per-check walkthrough — Account Reconciliation Exceptions sheet.*

## The story

A customer DDA or operating sub-account at SNB shouldn't end the day
with a negative stored balance. Real customers can't have negative
deposits; sub-accounts inside the sweep automation are supposed to
be funded before they originate. When the EOD snapshot lands with
`stored_balance < 0`, that's an overdraft — and it tends to be
sticky, just like drift, because once a balance crosses below zero
it usually takes a deliberate compensating credit (next-day cover,
sweep reversal, internal funding) to bring it back.

A single overdraft incident often appears as multiple consecutive
overdraft *days* in the count: the day the negative balance first
landed, plus every subsequent day the account stayed negative until
covered. So the day count grows quickly even when the underlying
incident set is small.

## The question

"Did any sub-ledger account end the day with a negative stored
balance — and if so, for how long has it been negative?"

## Where to look

Open the AR dashboard, **Exceptions** sheet. The KPI **Overdraft
Days** sits in the second KPI row, next to **Limit Breach Days**.

## What you'll see in the demo

The KPI shows **231** overdraft days.

<details markdown><summary>Screenshot — KPI</summary>

![Overdraft Days KPI showing the count 231](../screenshots/ar/sub-ledger-overdraft-01-kpi.png)

</details>

Three planted overdraft incidents in `_OVERDRAFT_PLANT` account for
the count. Each lands a single oversized outbound on a specific day,
driving that sub-ledger negative; the account then stays negative
for several days until a compensating credit lands:

| sub-ledger                                  | started     | drove negative |
|---------------------------------------------|-------------|---------------:|
| Harvest Moon Bakery — DDA                   | Apr 15 2026 |        $40,000 outbound |
| Sasquatch Sips — DDA                        | Apr 13 2026 |        $45,000 outbound |
| Cascade Timber Mill — ZBA Operating (a)     | Apr 10 2026 |        $35,000 outbound |

The detail table lists every (sub-ledger, date) cell where stored
balance < 0. Columns: `subledger_account_id`, `subledger_name`,
`ledger_name`, `balance_date`, `stored_balance`, `aging_bucket`.
Sorted newest-first.

<details markdown><summary>Screenshot — detail table</summary>

![Sub-Ledger Overdraft table sorted newest-first by balance_date](../screenshots/ar/sub-ledger-overdraft-02-table.png)

</details>

The aging bar chart shows bucket 4 (8-30 days) carrying the largest
share of the count — the older two plants (Apr 10 and Apr 13)
already aged into bucket 4. Bucket 3 (4-7 days) and bucket 5
(>30 days) carry smaller counts; bucket 1 (0-1 day) and bucket 2
(2-3 days) hold the most recent overdraft days.

<details markdown><summary>Screenshot — aging chart</summary>

![Overdrafts by Age aging bar chart with bucket 4 (8-30 days) dominant](../screenshots/ar/sub-ledger-overdraft-03-aging.png)

</details>

## What it means

Each row says: on `balance_date`, sub-ledger `subledger_name` ended
the day with `stored_balance` dollars (negative). The row recurs
every day the account stays negative — so a single overdraft
incident that lasted 12 days shows up as 12 rows.

A few patterns to watch for:

- **Same `stored_balance` across consecutive days** for one
  sub-ledger means no posting activity in between — the account is
  just sitting in overdraft, untouched.
- **`stored_balance` getting more negative day over day** means the
  account is continuing to send money out without funding — that's
  much more concerning than a flat overdraft.
- **`stored_balance` swinging back toward zero day over day** means
  partial cover is landing but isn't yet enough — the customer is
  catching up.

The two customer DDA overdrafts (Harvest Moon Bakery, Sasquatch
Sips) are likely insufficient-funds conditions; the ZBA operating
sub-account overdraft (Cascade Timber Mill) is a sweep-engine
funding gap — that account isn't supposed to overdraft because the
sweep is supposed to fund it before it originates.

## Drilling in

Click a `subledger_account_id` value in any row. The drill switches
to the **Transactions** sheet filtered to that sub-ledger and date.
The transfer that crossed the account into negative territory is
typically the largest debit on the day; identifying it is usually
a one-row scan.

Then walk forward day by day in the Transactions sheet to find the
posting that brings the balance back above zero (a credit large
enough to net the running balance positive). The day before that
credit is the last overdraft day for the incident.

## Next step

Triage by sub-ledger type:

- **Customer DDA overdraft** → **Customer Operations / Treasury
  Services**. The customer-relationship team contacts the customer
  about insufficient funds and arranges cover. Bucket 4+ overdrafts
  on a customer DDA usually mean either a returned deposit nobody
  caught or an automated outflow (recurring ACH debit) that should
  have been blocked.
- **ZBA operating sub-account overdraft** → **ZBA Admin / Sweep
  Automation**. The sweep should have funded the account before it
  originated. Long-running overdrafts on a sweep sub-account
  indicate the sweep engine has a sub-account in its funding plan
  that's not actually getting funded.
- **GL control overdraft** → if surfaced (none in the current
  demo), goes to **GL Reconciliation** — control accounts going
  negative is a structural issue that often signals a posting class
  is being misrouted.

Old overdrafts (bucket 5: >30 days) are escalation candidates —
both because the operational fix window is closing and because
30+ days uncovered overdraft on a customer DDA can have regulatory
implications (Reg E timing, customer-notification requirements).

## Related walkthroughs

- [Sub-Ledger Limit Breach](sub-ledger-limit-breach.md) — different
  invariant (exceeding policy, not going negative) but very similar
  drill flow (pick a sub-ledger, drill into Transactions, find the
  driving leg). Lives in the same KPI row.
- [Sub-Ledger Drift](sub-ledger-drift.md) — also a sub-ledger-level
  EOD-balance check; drift looks at stored vs computed mismatch,
  overdraft looks at stored < 0. The two checks are independent —
  a sub-ledger can drift without overdrafting and vice versa.
