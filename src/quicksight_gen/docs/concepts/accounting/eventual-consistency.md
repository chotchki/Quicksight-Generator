# Eventual consistency

*Background concept — money that lands over days, not seconds.*

{{ diagram("conceptual", name="eventual-consistency") }}

## What it is

Most money movement in a retail banking system doesn't settle
instantaneously. A sale posts today; the settlement to the
merchant's bank fires tomorrow; the card network clears the funds
two days after that; the external bank confirms receipt on day
four. At any moment, large amounts of money are **in flight** —
legitimately posted on one side of a transfer but not yet on the
other.

A system is **eventually consistent** when, given enough time and
no new activity, all in-flight balances will clear and the books
will agree across parties.

## The problem it solves

Non-instant settlement is a feature, not a bug. Batch processing
is vastly more efficient than real-time for most retail volumes;
external settlement calendars (ACH windows, Fed cutoffs, card
network cycles) are fixed facts that every institution has to
live with.

The operator's job, in an eventually consistent system, splits
into two:

1. **Distinguish in-flight from stuck.** A transfer that's one
   day out isn't broken; a transfer that's been "pending" for
   two weeks probably is. The threshold depends on the rail's
   declared `max_pending_age` / `max_unbundled_age`.
2. **Watch aging.** Once something is stuck, how long has it
   been stuck? Aging drives escalation — a three-day-old
   exception is routine follow-up, a thirty-day-old exception
   is a structural problem.

## How L1 surfaces this

The **Pending Aging** and **Unbundled Aging** sheets bucket
violations into 5 bands (0-1 day, 2-3 days, 4-7 days, 8-30 days,
>30 days). The buckets ARE the eventual-consistency machinery
made operational:

- **Bands 1-2 (0-3 days)** are usually in-flight; no action
  yet unless it's a transfer type that should have cleared.
- **Band 3 (4-7 days)** is starting to stick; escalate.
- **Bands 4-5 (8-30+ days)** are structural; stop working rows and
  ask why the automation hasn't cleared them.

See [L1 Reconciliation Dashboard](../../handbook/l1.md) for the
operator workflow, and the per-rail `max_pending_age` /
`max_unbundled_age` declarations in the L2 instance YAML.
