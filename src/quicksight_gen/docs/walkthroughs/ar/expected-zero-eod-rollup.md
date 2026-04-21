# Expected-Zero EOD Rollup

*Rollup-level walkthrough — Account Reconciliation Exceptions Trends sheet.*

## The story

Several SNB control accounts exist *only* to hold money in flight for a
few hours. By end-of-day, they should drain back to zero — every dollar
that came in should have left to its real destination. If a control
account carries a balance overnight, something didn't complete its
journey: a sweep didn't fire, a confirmation didn't arrive, a transfer
got stuck in suspense.

Four of SNB's accounts have this expected-zero property:

- `gl-1810` ACH Origination Settlement — drains to FRB Master each EOD
- `gl-1830` Internal Transfer Suspense — drains to recipient DDAs
- `gl-1850` Cash Concentration Master — receives sweep totals; sub-accounts drain to zero
- ZBA operating sub-accounts — sweep up to the Concentration Master

The Expected-Zero EOD rollup unions all four checks into a single view
so an operator can ask one question at the start of the day: "did
anything fail to drain last night?"

## The question

"Of the accounts that should have ended yesterday at zero, are any
carrying a balance?"

## Where to look

Open the AR dashboard, **Exceptions Trends** sheet (the sister sheet
to Today's Exceptions). The three cross-check rollups sit at the top
of the sheet in order: Balance Drift Timelines (chart), Two-Sided
Post Mismatch (KPI + table), Expected-Zero EOD (KPI + table).
Expected-Zero is the third rollup: a KPI titled "**Accounts Expected
Zero at EOD**" and a detail table with the same title.

## What you'll see in the demo

The KPI shows a non-zero count. The detail table lists each account-day
where the balance should have been zero but wasn't, with columns:
account, balance date, residual balance, source check, days outstanding,
aging bucket.

Multiple rows from the demo seed contribute:

- ACH Origination Settlement carrying balances on days where the EOD
  sweep didn't post (planted scenarios in `_generate_ach_origination_cycle`)
- Internal Transfer Suspense holding balances from the two stuck
  transfers (Cascade Timber Mill $4,275 and Pinecrest Vineyards
  $1,880 — see [Stuck in Internal Transfer Suspense](stuck-in-internal-transfer-suspense.md))
- Concentration Master sweep target rows where one of the operating
  sub-accounts didn't sweep clean

## What it means

This rollup tells you the *shape* of what's wrong — money sitting
where it shouldn't — but not yet the *why*. Different sources point at
different upstream owners (sweep automation, internal transfer system,
ZBA configuration). The rollup's job is to make you stop and look; the
per-check views tell you who to call.

## Drilling in

The detail table's `source_check` column names the per-check view that
owns each row. Switch to the **Today's Exceptions** sheet and set
**Check Type** in the Controls strip to that check name:

- `source_check = "sweep_target_nonzero"` → set Check Type to
  `Sweep Target Non-Zero EOD`. The Open Exceptions table will list
  each operating sub-account that didn't sweep clean; right-click
  the `account_id` cell for the per-account-day Transactions drill.
- `source_check = "ach_orig_settlement_nonzero"` → set Check Type to
  `ACH Origination Settlement Non-Zero EOD`. Same row shape — `gl-1810`
  carrying balance overnight, right-click drill on `account_id`.
- `source_check = "internal_transfer_suspense_nonzero"` → set Check
  Type to `Internal Transfer Suspense Non-Zero EOD`. `gl-1830` carrying
  the stuck-transfer residual, right-click drill on `account_id`.

The per-check view is what the upstream team needs (the specific
account / date / dollars) to start the work.

## Next step

If the count is 0: log the morning check as clean and move on. If
non-zero: triage by source — sweep target failures usually go to the
ZBA admin team, ACH non-zero EOD goes to ACH Operations, suspense
non-zero goes to Internal Transfer Operations. Use the per-check
views in Today's Exceptions to pull the specific account / transfer
ID for the handoff.

## Related walkthroughs

- [Sweep Target Non-Zero EOD](sweep-target-non-zero.md) — per-check
  view of operating sub-accounts that failed to sweep clean. One
  source of rows in this rollup.
- [ACH Origination Settlement Non-Zero EOD](ach-origination-non-zero.md) —
  per-check view of `gl-1810` carrying balance overnight. Another
  source of rows.
- [Internal Transfer Suspense Non-Zero EOD](internal-transfer-suspense-non-zero.md) —
  per-check view of `gl-1830` carrying balance overnight (typically
  from stuck on-us transfers). Third source of rows.
- [Stuck in Internal Transfer Suspense](stuck-in-internal-transfer-suspense.md) —
  per-transfer view of the originating incidents that drive the
  Internal Transfer Suspense rows here.
- [Two-Sided Post Mismatch Rollup](two-sided-post-mismatch-rollup.md) —
  the rollup above this one on the Trends sheet. Different shape
  (paired-but-half-posted rather than expected-zero-but-non-zero), but
  the same triage idiom: rollup tells you *something* is wrong;
  per-check view in Today's Exceptions tells you *who to call*.
- [Balance Drift Timelines Rollup](balance-drift-timelines-rollup.md) —
  the first rollup at the top of the Trends sheet. Different invariant
  class (two-sided drift over time) but co-located with this one in
  the morning three-rollup scan.
