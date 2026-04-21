# Sweep and net-settle

*Background concept — how intraday activity accumulates, then clears in one wire.*

## What it is

A **sweep account** holds intraday activity. Each individual posting
lands there; at end of day, the accumulated net balance is moved to
the bank's authoritative position account in one transfer. The
sweep account is expected to end every day at **zero**.

A typical sweep cycle:

1. Throughout the day: debits / credits accumulate in the sweep
   account as customer activity posts.
2. End of day: the net balance is wired to the position account,
   clearing the sweep to zero.
3. The external counterparty (the Fed, a processor, etc.)
   confirms the settlement on their side.

## The problem it solves

Sweeping aggregates many small movements into one external
settlement. Without a sweep, every individual ACH origination
would need its own external wire — expensive, slow, and hard to
reconcile. With a sweep, the bank emits one wire a day that
represents the day's net activity.

The cost of aggregation is the reconciliation burden. Three
things have to hold:

1. The sweep account has to reach zero EOD (activity actually
   cleared, not just looks like it did).
2. The sweep amount has to match the sum of the day's intraday
   postings (the aggregation is right).
3. The counterparty has to confirm the wire (the external side
   landed).

Any one of those failing is a distinct class of exception.

## In the SNB demo

Two sweep cycles are modeled:

- **ACH Origination Settlement** (`gl-1810`) sweeps to **Cash & Due
  From FRB** (`gl-1010`) EOD. The **ACH Origination Non-Zero EOD**
  and **ACH Sweep Without Fed Confirmation** checks watch this
  cycle.
- **Cash Concentration Master** (`gl-1850`) sweeps each
  operating sub-account to the master EOD. The **Sweep Target
  Non-Zero EOD** and **Concentration Master Sweep Drift** checks
  watch this cycle.

Open the AR Exceptions sheet; scroll to the CMS-specific section.
If any of those four checks are non-zero, a sweep cycle didn't
complete cleanly yesterday.

Further reading:

- [ACH Origination Non-Zero EOD](../../../docs/walkthroughs/ar/ach-origination-non-zero.md)
- [Sweep Target Non-Zero EOD](../../../docs/walkthroughs/ar/sweep-target-non-zero.md)
- [Concentration Master Sweep Drift](../../../docs/walkthroughs/ar/concentration-master-sweep-drift.md)
