# Balance Drift Timelines Rollup

*Rollup-level walkthrough — Account Reconciliation Exceptions Trends sheet.*

## The story

Two of SNB's daily reconciliation invariants compare totals from two
sides of a Fed relationship and expect them to match exactly:

- **Concentration Master sweep drift** (`gl-1850`) — every business
  day, operating sub-accounts under Cash Concentration Master sweep
  their EOD balances up to the master. The sum of sub-account
  outflows must equal the master's inflow. Anything else is a
  bookkeeping break in SNB's own internal sweep automation.
- **GL vs Fed Master drift** — every Fed-side card observation
  (external_force_posted into `ext-frb-snb-master`) should be matched
  by an SNB internal catch-up posting against `gl-1815`. Daily totals
  on both sides should equal each other to the dollar.

A healthy day is a zero. A non-zero day means the two sides of one
of these invariants diverged — and you can tell which one by the bar
color on the rollup chart.

The Balance Drift Timelines rollup overlays both checks on a single
date axis. It's the first thing an operator sees on the Exceptions
Trends sheet because drift over time is the strongest "something is
systemically wrong" signal — a single bad day is investigable, but a
multi-day pattern is a process problem.

## The question

"Across the last several weeks, did any day's reconciliation invariant
drift away from zero — and if so, which one?"

## Where to look

Open the AR dashboard, **Exceptions Trends** sheet (the sister sheet
to Today's Exceptions — Today's Exceptions is the row-level operational
view; Trends is the over-time / rollup view). The Balance Drift
Timelines rollup is the very first visual at the top — a clustered
vertical bar chart titled "**Balance Drift Timelines**" with two color
series.

## What you'll see in the demo

A clustered bar chart with date on the x-axis and drift dollars on
the y-axis. Two color series:

- **Concentration Master Sweep drift** — two non-zero days from the
  demo seed: 6 days back showing **+$120.00** (master leg posted long)
  and 11 days back showing **−$95.50** (master leg posted short).
  Mixed signs are intentional — drift can spike either direction.
- **GL vs Fed Master drift** — two non-zero days from card settlements
  where the Fed observation posted but the SNB internal catch-up
  didn't (4 days back and 9 days back). The drift dollar amount on
  those days equals the missing catch-up's value.

Healthy days show zero bars on both series. The non-zero days stand
out.

## What it means

Drift on either series is a *systemic* signal — not "one transfer is
stuck" but "two daily totals that should equal each other don't". The
fix is not to chase one transfer ID; it's to figure out which posting
path is silently dropping or duplicating activity, then backfill the
missing entries (or reverse the duplicates) so both sides agree
end-of-day.

Each series points at a different operational owner:

- Concentration Master Sweep drift → **ZBA Admin / Sweep Automation
  team**. The internal sweep engine is mis-posting one leg of a
  paired entry.
- GL vs Fed Master drift → **Card Operations / Fed Reconciliation
  team**. The internal catch-up posting against `gl-1815` is not
  firing on every Fed observation.

## Drilling in

This rollup is a chart, not a row table — there's no row-click drill
target. Use it to *see the pattern*; then switch to the **Today's
Exceptions** sheet and set **Check Type** in the Controls strip to the
specific check that owns the spike:

- **Concentration Master Sweep drift** spike → Check Type
  `Concentration Master Sweep Drift`. The Open Exceptions table will
  list each non-zero drift date with the dollar drift amount.
- **GL vs Fed Master drift** spike → Check Type
  `GL vs Fed Master Drift`. Same shape — one row per drift date with
  the dollar amount.

For the per-check view of the *underlying transfers* (not the daily
aggregate) cross-check via Check Type `Non-Zero Transfer` for the
sweep series, or `Fed Activity Without Internal Catch-Up` for the
GL/Fed series. Both of those carry the per-transfer IDs that are
clickable to drill down to the Transactions sheet.

The Trends sheet itself also carries an **Aging Matrix** and a
**Per-Check Daily Trend** below this rollup — useful for spotting
whether the spike is part of a broader staleness pattern or limited
to one check.

## Next step

If both series are flat at zero across the visible window: log clean
and move on. If one or both series have non-zero days:

- **One isolated spike on one series** → likely a single bad post.
  Switch to Today's Exceptions, filter by Check Type to the owning
  check, fix the offending transfer, and expect the next day to
  return to zero.
- **Multiple spikes on one series** → process problem. Escalate to
  the owning team (ZBA Admin or Card Operations) to trace why their
  posting path is dropping legs.
- **Spikes on both series simultaneously** → look for a shared
  upstream cause (often a posting-engine change deployed that day).

## Related walkthroughs

- [Two-Sided Post Mismatch Rollup](two-sided-post-mismatch-rollup.md) —
  the next rollup down on the Trends sheet. The GL-vs-Fed-Master
  spikes here are the per-day-dollar view of what shows up there as
  per-transfer count.
- [Concentration Master Sweep Drift](concentration-master-sweep-drift.md) —
  per-check view in Today's Exceptions for the sweep-leg-mismatch
  series.
- [GL vs Fed Master Drift](gl-vs-fed-master-drift.md) — per-check
  view in Today's Exceptions for the Fed-vs-internal series.
- [Expected-Zero EOD Rollup](expected-zero-eod-rollup.md) — third
  rollup on the Trends sheet. Different invariant class
  (control-account-should-be-zero) but the same morning-scan idiom:
  rollup tells you something's wrong, per-check rows tell you who
  to call.
