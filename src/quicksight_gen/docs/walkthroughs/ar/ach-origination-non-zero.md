# ACH Origination Settlement Non-Zero EOD

*Per-check walkthrough — Account Reconciliation Today's Exceptions sheet.*

## The story

ACH Origination Settlement (`gl-1810`) is a transitory clearing
account: every ACH origination customers initiate during the day
debits this ledger (with the credit landing on the customer's DDA),
and at end of day an internal sweep moves the day's net out to
**Cash & Due From FRB** (`gl-1010`), zeroing `gl-1810` for the
overnight cycle.

In a healthy day, gl-1810's stored EOD balance is exactly zero. If
the EOD sweep doesn't fire (skipped, failed, or never scheduled),
the day's net ACH originations sit on gl-1810 overnight — and they
keep sitting there until a corrective sweep finally drains them.
The next day's normal sweep only handles that day's net; it doesn't
catch up the prior day's residual. So once gl-1810 is non-zero,
it stays non-zero every subsequent day until somebody intervenes.

## The question

"Did the ACH Origination Settlement ledger end yesterday at zero —
i.e., did the EOD sweep to FRB actually fire?"

## Where to look

Open the AR dashboard, **Today's Exceptions** sheet. In the Controls
strip at the top of the sheet, set **Check Type** to
`ACH Origination Settlement Non-Zero EOD`. The **Total Exceptions**
KPI recounts to just this check's rows, the **Exceptions by Check**
breakdown bar collapses to a single orange bar, and the **Open
Exceptions** table below shows every row for this check — one row
per non-zero EOD day.

<details markdown><summary>Screenshot — Open Exceptions filtered to this check</summary>

![Open Exceptions table filtered to ACH Origination Settlement Non-Zero EOD, five rows of stored_balance $3,440](../screenshots/ar/todays-exceptions-filtered-ach-origination-non-zero.png)

</details>

## What you'll see in the demo

Five rows, one per day the residual has been sitting there. Key
columns to read:

| column          | value for this check                                          |
|-----------------|---------------------------------------------------------------|
| `account_id`    | `gl-1810` on every row (the ACH Origination Settlement ledger) |
| `account_name`  | "ACH Origination Settlement"                                   |
| `account_level` | `Ledger`                                                       |
| `transfer_id`   | blank — this check is an EOD-balance shape, not a single-transfer shape |
| `primary_amount`| `stored_balance` — the non-zero EOD dollar amount             |

One planted skip in `_ACH_SWEEP_SKIP_PLANT` (days_ago=4 → Apr 15
2026) is the seed:

| exception_date | primary_amount | aging_bucket |
|----------------|---------------:|--------------|
| Apr 19 2026    |          3,440 | 1: 0-1 day   |
| Apr 18 2026    |          3,440 | 2: 2-3 days  |
| Apr 17 2026    |          3,440 | 2: 2-3 days  |
| Apr 16 2026    |          3,440 | 3: 4-7 days  |
| Apr 15 2026    |          3,440 | 3: 4-7 days  |

The Apr 15 skip left $3,440 of net ACH originations parked on
gl-1810. Each subsequent day's normal sweep only swept that day's
net (back to zero), so gl-1810 stays at $3,440 EOD every day
since.

## What it means

Each row says: at end of day on `exception_date`, gl-1810's stored
balance was `primary_amount` dollars (non-zero). The constant
$3,440 across all five rows is the smoking gun — that's the same
unswept net from a single missed cycle four days ago, sitting
there ever since.

Two error patterns to distinguish:

- **One incident, sticky residual** (this case). One day's sweep
  was skipped; every day after carries the same residual. Fix:
  fire a one-time corrective sweep for the residual amount.
- **Daily pattern, varying residual.** Multiple skipped days,
  each with a different residual; the EOD balance climbs day over
  day. Fix: investigate the sweep automation itself — it's not
  firing reliably.

A different residual jumping back toward zero day-over-day means
partial corrective sweeps are landing — the ops team is catching
up but isn't fully done.

## Drilling in

The `account_id` cell renders with a pale-green background — that
tint is the dashboard's cue that a right-click menu is available.
**Right-click** any `account_id` value and choose
**View Transactions for Account-Day** from the context menu.
QuickSight switches to the **Transactions** sheet and filters to
every posting that touched gl-1810 on that specific date — the
day's individual ACH origination debits, plus (if it fired) the
EOD sweep credit.

On the skip day (Apr 15), the EOD sweep credit will be missing.
Walking forward to the day before the residual finally clears
shows the corrective sweep — typically tagged differently from
normal nightly sweeps because it's an off-cycle correction.

The `transfer_id` column is left blank for this check because no
single transfer represents the non-zero balance — the residual is
the net of many postings across the day. The account-day scope is
the meaningful one.

## Next step

ACH origination non-zero rows go to **ACH Operations**:

- **Bucket 1** (today's residual) → confirm whether the sweep
  actually missed or whether the snapshot is mid-cycle.
- **Bucket 2-3 (2-7 days)** → fire a corrective sweep. The
  amount equals the carry-forward residual from the original
  skip day.
- **Bucket 4-5 (8+ days)** → root-cause the original skip
  before correcting. A week-old residual on a CMS clearing
  account suggests nobody is monitoring this ledger; the
  operational gap matters more than the dollar amount.

Pair this check with **ACH Sweep Without Fed Confirmation**. Both
check the ACH origination cycle; this one catches "internal sweep
didn't post," the other catches "internal sweep posted but Fed
never confirmed."

## Related walkthroughs

- [ACH Sweep Without Fed Confirmation](ach-sweep-no-fed-confirmation.md) —
  the next stage of the same ACH origination cycle. After the
  internal sweep posts, a Fed-side confirmation should follow;
  that check catches days where the bank thinks the cash moved
  but FRB has no record.
- [GL vs Fed Master Drift](gl-vs-fed-master-drift.md) — broader
  GL vs Fed reconciliation. ACH origination non-zero is
  internal-side only; GL vs Fed compares the SNB internal view
  to the Fed-observed reality.
