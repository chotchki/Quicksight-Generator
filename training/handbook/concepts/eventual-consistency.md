# Eventual consistency

*Background concept — money that lands over days, not seconds.*

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
   two weeks probably is. The threshold depends on the
   transfer type.
2. **Watch aging.** Once something is stuck, how long has it
   been stuck? Aging drives escalation — a three-day-old
   exception is routine follow-up, a thirty-day-old exception
   is a structural problem.

## In the SNB demo

Every AR and PR exception check in the demo carries a
`days_outstanding` column and an **aging bar chart** broken into
buckets (0-3 days, 4-7 days, 8-30 days, 30+ days). That's the
eventual-consistency machinery made operational:

- **Buckets 1-2 (0-7 days)** are usually in-flight; no action
  yet unless it's a transfer type that should have cleared.
- **Bucket 3 (8-30 days)** is starting to stick; escalate.
- **Bucket 4 (30+ days)** is structural; stop working rows and
  ask why the automation hasn't cleared them.

Every per-check walkthrough in the upstream handbook spells out
the expected aging profile for that check, so an operator can
tell at a glance whether today's counts look normal or off.

Further reading: [GL Reconciliation Handbook → morning routine](../../../docs/handbook/ar.md#the-morning-routine).
