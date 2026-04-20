# Two-Sided Post Mismatch Rollup

*Rollup-level walkthrough — Account Reconciliation Exceptions sheet.*

## The story

Some money movements happen in two systems at once. SNB posts an entry
on its own books; the Federal Reserve posts a matching entry on the
master account. The two records describe the same dollars from opposite
sides of the relationship, and they are supposed to land within hours
of each other.

When only one side posts, your books and the Fed's books disagree on
what happened. *Which* side is missing tells you which team owns the
fix:

- **SNB sweep posted, Fed confirmation missing** — the daily ACH
  origination sweep cleared `gl-1810` internally, but the Fed never
  acknowledged the corresponding move on the FRB master. SNB thinks
  money left; the Fed has no record. Goes to ACH Operations / Fed
  reconciliation.
- **Fed observation posted, SNB internal catch-up missing** — the
  Federal Reserve recorded a card settlement landing in the FRB
  master, but the SNB internal force-post that should mirror it never
  fired. The Fed thinks money arrived; SNB's books don't reflect it.
  Goes to Card Operations.

The Two-Sided Post Mismatch rollup unions both flows into a single
view because they share a *shape*: one half of an expected pair posted,
the other never did. An operator can ask one question instead of two:
"is anything paired-but-half-posted right now?"

## The question

"Are there any expected SNB/Fed post pairs where one side landed but
the other didn't?"

## Where to look

Open the AR dashboard, **Exceptions** sheet. The Two-Sided Post
Mismatch rollup is the second block from the top — between the Balance
Drift Timelines chart at the very top and the Expected-Zero EOD rollup
below it. Look for a KPI titled "**Two-Sided Post Mismatch**" and a
detail table with the same title.

## What you'll see in the demo

The KPI shows a non-zero count. The detail table lists each transfer
where one side posted and the other didn't, with columns: transfer ID,
observed at, amount, side present, side missing, source check,
days outstanding, aging bucket. Sort is oldest-first by aging.

From the demo seed:

- **ACH internal sweep without Fed confirmation** — two days planted,
  both 8-12 days back, both landing in the **8-30 days** aging bucket.
  Each row shows side_present = "SNB internal sweep", side_missing =
  "Fed confirmation".
- **Fed activity without internal catch-up** — two card-settlement
  days planted, one 4 days back (**4-7 days** bucket) and one 9 days
  back (**8-30 days** bucket). Each row shows side_present = "Fed card
  observation", side_missing = "SNB internal catch-up".

## What it means

Each row is one transfer that did not complete its expected paired
posting. The longer it sits unmatched, the more your reconciled
position diverges from what the Fed shows on its statement — and the
greater the chance that what eventually closes the gap is a manual
journal entry rather than the automated catch-up that should have
fired.

The two source checks point at *different* upstream owners even though
the rollup's KPI counts them together. The point of the rollup is
pattern recognition (one-sided posts) — the per-check tables below tell
you which queue the work goes to.

## Drilling in

The detail table's `source check` column names the per-check view that
owns each row. Scroll down the Exceptions sheet to that section
(*ACH Sweep No Fed Confirmation* or *Fed Card No Internal Catch-Up*)
for the row-level context the upstream team needs — including the
matching transfer ID on the side that *did* post, so they can confirm
the divergence on both books.

## Next step

If the count is 0: log the morning check as clean. If non-zero: triage
by source check — sweep-without-Fed rows go to ACH Operations / Fed
reconciliation; Fed-without-internal-catchup rows go to Card
Operations. Hand off the transfer ID and the observed-at date so the
upstream team can pull their side of the pair and decide whether to
re-post or cancel.

Aging bucket matters here: bucket 1-2 (0-3 days) is "may still
reconcile naturally"; bucket 3+ (4 days and up) almost always needs
manual intervention.

## Related walkthroughs

- [ACH Sweep Without Fed Confirmation](ach-sweep-no-fed-confirmation.md) —
  per-check view of the SNB-side of the pair. Drill target for
  "side_present = SNB internal sweep" rows.
- [Fed Activity Without Internal Post](fed-card-no-internal-catchup.md) —
  per-check view of the Fed-side of the pair. Drill target for
  "side_present = Fed card observation" rows.
- [Balance Drift Timelines Rollup](balance-drift-timelines-rollup.md) —
  same Fed-vs-internal divergence, but viewed as per-day drift dollars
  instead of unmatched transfer count.
