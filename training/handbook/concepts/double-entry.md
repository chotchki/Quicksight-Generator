# Double-entry accounting

*Background concept — the invariant every reconciliation check rests on.*

## What it is

Every movement of money is recorded as **two equal and opposite
postings** — one debit, one credit. Sum them and they net to zero.
A "transfer" is a logical unit of movement; a "posting" (or "leg")
is one side of that transfer.

If I move \$100 from Account A to Account B, the transfer produces
two rows:

- Account A: `signed_amount = -100` (credit)
- Account B: `signed_amount = +100` (debit)

Sum across the whole transfer: zero. That's the invariant.

## The problem it solves

Money can't be created or destroyed silently. If a row is missing
a counterpart, either it wasn't posted yet (in-flight), it failed
(and should be flagged, not quietly dropped), or someone's books
have a bug. Double-entry turns "where did this money come from?"
from a free-text question into a database query.

It also makes **eventual consistency observable**. A transfer that
clears over three days still has to net to zero across all its legs
on day three — on day one it looks "imbalanced" because only the
originator's leg has posted, and that temporary imbalance is
itself diagnostic.

## In the SNB demo

- The `transactions` table stores one row per posting leg.
  `transfer_id` groups the legs of one transfer; `signed_amount`
  carries the sign (+ debit, − credit).
- Every exception check in the AR dashboard works off sums of
  `signed_amount` — net-to-zero by transfer, stored balance vs.
  computed-from-postings balance, etc.
- The **Non-Zero Transfers** check is the purest example: it lists
  every `transfer_id` whose successful legs don't sum to zero.
  Clean books means that check reads zero rows.

Further reading: [GL Reconciliation Handbook → Non-Zero Transfers](../../../docs/walkthroughs/ar/non-zero-transfers.md).
