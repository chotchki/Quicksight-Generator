# Double-entry posting

*Background concept — the invariant every L1 reconciliation check rests
on.*

{{ diagram("conceptual", name="double-entry") }}

## What it is

Every movement of money is recorded as **two equal and opposite
postings** — one debit, one credit. Sum them and they net to zero.
A "transfer" is the logical money-movement event; a "posting" (or
"leg") is one side of that event.

If $100 moves from Account A to Account B, the transfer produces two
rows:

- Account A: `signed_amount = -100` (money out)
- Account B: `signed_amount = +100` (money in)

Sum across the whole transfer: zero. That's the L1 Conservation
invariant.

## The problem it solves

Money can't be created or destroyed silently. If a row is missing a
counterpart, either it wasn't posted yet (in-flight), it failed (and
should be flagged, not quietly dropped), or someone's books have a
bug. Double-entry turns "where did this money come from?" from a
free-text question into a database query.

It also makes **eventual consistency observable**. A transfer that
clears over three days still has to net to zero across all its legs
on day three — on day one it looks "imbalanced" because only the
originator's leg has posted, and that temporary imbalance is itself
diagnostic.

## In the schema

- The `transactions` table stores one row per posting leg.
  `transfer_id` groups the legs of one transfer; `signed_amount`
  carries the sign (`+` money in, `−` money out, from the
  account-holder's perspective).
- Every L1 invariant works off sums of `signed_amount` — net-to-zero
  per transfer for L1 Conservation, sum-of-postings vs stored balance
  for L1 Drift, sum-of-outbound vs limit cap for L1 Limit Breach.
- The shared base layer is L1-clean by construction: drift / overdraft
  / limit-breach all rest on the double-entry invariant being held.

See also: [L1 Reconciliation Dashboard](../../handbook/l1.md) for the
visual surface, and the [Schema v6 contract](../../Schema_v6.md) for the
column definitions.
