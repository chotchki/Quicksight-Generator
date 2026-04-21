# Non-Zero Transfers

*Per-check walkthrough — Account Reconciliation Today's Exceptions sheet.*

## The story

Every `transfer_id` in SNB's ledger represents one financial event —
an ACH, a wire, an internal transfer, a cash deposit, a sweep — that
posts as a set of legs (debit one account, credit another). The
double-entry invariant is that the non-failed legs of any transfer
must sum to zero. Money out of one account equals money into another.

When the non-failed legs *don't* sum to zero, one of three things
happened:

- **Failed leg.** A leg posted with `status='failed'`. The transfer
  is not in balance because the failed leg's amount didn't make it
  to its destination — the customer-facing money is short by exactly
  that amount.
- **Off amount.** Both legs posted successfully but with mismatched
  amounts (debit $1,000, credit $999). This is rarer but typically
  points at a fee miscalculation or a rounding bug in the upstream
  feed.
- **Stuck (one leg only).** Step 1 posted, Step 2 never arrived.
  Common in two-step internal transfers and external sweeps where
  the second leg is conditional on confirmation from another system.

The Non-Zero Transfers check catches all three at once. Each row is
a transfer that needs a person to look at it.

## The question

"Are there any transfers where the non-failed legs don't add up to
zero?"

## Where to look

Open the AR dashboard, **Today's Exceptions** sheet. In the Controls
strip at the top of the sheet, set **Check Type** to
`Non-Zero Transfer`. The **Total Exceptions** KPI recounts to just
this check's rows, the **Exceptions by Check** breakdown bar
collapses to a single yellow bar, and the **Open Exceptions** table
below shows every row for this check — one row per transfer whose
non-failed legs don't net to zero.

<details markdown><summary>Screenshot — Open Exceptions filtered to this check</summary>

![Open Exceptions table filtered to Non-Zero Transfer, 14 rows spanning failed-leg, off-amount, and stuck-step classes](../screenshots/ar/todays-exceptions-filtered-non-zero-transfers.png)

</details>

## What you'll see in the demo

Fourteen rows — each a distinct broken transfer. Unlike the drift
checks, this check doesn't roll forward day-over-day: one incident
contributes one row forever, not one row per day. Key columns to
read:

| column            | value for this check                                          |
|-------------------|---------------------------------------------------------------|
| `account_id`      | blank — non-zero is a transfer shape, not an account shape    |
| `account_level`   | `System`                                                      |
| `transfer_id`     | the broken transfer (e.g. `ar-xfer-0051`, `ar-on-us-step2-05`) |
| `transfer_type`   | the transfer class (wire, ach, on-us, clearing_sweep, etc.)   |
| `primary_amount`  | `net_amount` — total_debit + total_credit (zero means balanced; non-zero is the shortfall) |
| `secondary_amount`| blank — the transfer-total numbers sit in the per-check view, not the unified row |

The mix of error classes is visible right in the `transfer_id` and
`transfer_type` columns:

- Wire / ACH / cash transfers with a customer DDA as the counterparty
  and a non-zero `primary_amount` equal to the full transfer amount
  are failed-leg cases (e.g. `ar-xfer-0049/0050/0051/0052`).
- `clearing_sweep` rows with small non-zero `primary_amount`s
  (≈$120, $95) are the planted concentration-master sweep drift
  incidents (`ar-zba-sweep-0004/0017`).
- On-us rows with `primary_amount` equal to the full transfer
  (`ar-on-us-step2-05`, `ar-ledger-xfer-0006/0007/0008`) are stuck-
  step cases — Step 1 posted, Step 2 didn't.
- Small (a few dollars) non-zero on regular transfers
  (`ar-xfer-0053/0054/0055/0056`) are off-amount cases — fee or
  rounding mismatch.

## What it means

Each row is a transfer that didn't balance — money is out of place
by exactly `primary_amount` dollars. A failed leg means a customer
is short the failed amount; an off-amount means both sides booked
but disagree on how much; a stuck step means money posted to a
suspense account and never moved on.

The failed-leg cases are the loudest — large outbound debits with no
matching credit. The off-amount cases are smaller in dollars and
almost always trace back to either a fee assessment that didn't make
it into the credit leg or a rounding disagreement between two
upstream systems calculating the same transfer. The stuck-step cases
are Step 1 posted and Step 2 didn't — you see a credit with no
offsetting debit, or vice versa.

## Drilling in

The `transfer_id` cell renders as accent-colored text — that tint is
the dashboard's cue that the cell is clickable. **Left-click** any
`transfer_id` value. The drill switches to the **Transactions**
sheet filtered to that one transfer ID, showing every leg (posted
and failed). Reading the legs tells you the error class:

- One or more legs marked `status='failed'` → failed-leg case;
  resubmit or refund the failed leg.
- Two posted legs with mismatched amounts → off-amount case; the
  difference is the amount to investigate.
- One posted leg only → stuck-step case; chase the missing second
  leg in the originating system.

## Next step

Triage by error class:

- **Failed leg** → originating channel team (ACH Operations, Wire
  Operations, Cash Operations, Internal Transfer Operations). They
  resubmit the failed leg or initiate a refund.
- **Off amount** → typically a fee/rounding bug — escalate to the
  team that calculates the fee or the upstream system feeding the
  amount. The dollar gap is the diagnostic.
- **Stuck step** → see [Stuck in Internal Transfer Suspense](stuck-in-internal-transfer-suspense.md)
  for the on-us flavor; for sweep flavors see
  [Concentration Master Sweep Drift](concentration-master-sweep-drift.md).

Bucket 4+ (8 days and up) means the transfer has been out of balance
long enough that either the originator or the recipient has likely
noticed. Prioritize accordingly.

## Related walkthroughs

- [Stuck in Internal Transfer Suspense](stuck-in-internal-transfer-suspense.md) —
  the on-us-transfer flavor of the stuck-step class. `ar-on-us-step2-05`
  in this table is one of those rows; that walkthrough shows the
  full Step 1 / Step 2 picture.
- [Concentration Master Sweep Drift](concentration-master-sweep-drift.md) —
  the CMS-sweep flavor. The `ar-zba-sweep-*` rows in this table
  with small non-zero amounts are the same incidents that surface
  there as sweep-drift days.
- [Sub-Ledger Drift](sub-ledger-drift.md) — unrelated check (drift
  is a stored-vs-computed mismatch on an account; non-zero is a
  posting-vs-posting mismatch on a transfer). Different invariants,
  different diagnostic paths.
