# Where did these few dollars in the pool come from?

*Seed scenario — AR dashboard. Accounting team.*

## The story

You're walking your morning balance. One of your pool / control
accounts shows a small residual — a handful of dollars, maybe a
couple hundred — that you don't immediately recognize. The
amount is too small to be a material move, but too specific to
be rounding. Something posted that your mental model of the
day's activity didn't predict.

Today you'd ask the developers to trace the balance back. With
the AR dashboard, you can trace it yourself in two or three
clicks: the Exceptions sheet already knows which account drifted
from its posting history, and the drill walks you straight to
the offending entry.

This is the scenario that, once you work it end-to-end on the
demo, unlocks most small-dollar balance questions you handle
day-to-day.

## The question

"Where did these few dollars on this account come from — and why
isn't it zero?"

## Where to look

Open the AR dashboard in the **demo** environment first (learn
here before looking at production).

1. Go to **Exceptions**. Three rollups sit at the top — read
   them in the order they appear. The one most relevant for this
   scenario is **Balance Drift Timelines**, which plots stored-
   balance vs. computed-from-postings gaps over the last few
   weeks. A line trending away from zero is the visual signal
   that something drifted.
2. Scroll past the rollups to the baseline-checks block. Two
   KPIs own this scenario: **Sub-Ledger Drift Days** and
   **Ledger Drift Days**. Sub-ledger is customer-level and
   operating-account-level drift; ledger is the control-account
   rollup of sub-ledger drift.
3. If either KPI is non-zero, scroll down to its detail table.

## What you'll see in the demo

The demo carries four planted sub-ledger drift incidents, each a
specific dollar delta landing on a specific date and then
persisting forward:

| Sub-ledger | Start date | Delta |
|---|---|---|
| Big Meadow Dairy — DDA | Apr 17 2026 | −$75.00 |
| Bigfoot Brews — DDA | Apr 14 2026 | +$200.00 |
| Big Meadow Dairy — ZBA Operating (main) | Apr 9 2026 | −$150.50 |
| Cascade Timber Mill — DDA | Mar 30 2026 | +$450.00 |

The **Sub-Ledger Drift Days** KPI reads a much larger number (a
few hundred) because drift is *sticky*: once an account drifts
by $200, every EOD it stays that way adds another row to the
count. Four underlying incidents → hundreds of drift-days after
a couple of weeks.

The detail table columns: `subledger_account_id`,
`subledger_name`, `ledger_name`, `scope`, `balance_date`,
`stored_balance`, `computed_balance`, `drift`, `aging_bucket`.
Sort newest-first and you'll see the most recent drift first.

For the mechanical details (screenshots, exact KPI numbers),
open the upstream
[Sub-Ledger Drift walkthrough](../../../docs/walkthroughs/ar/sub-ledger-drift.md).

## What it means

Each row is one (sub-ledger, date) cell where the stored EOD
balance doesn't match the running sum of postings. Three shapes:

- **`drift > 0`** — stored is higher than postings explain. A
  posting is missing, or a stored credit landed without a
  backing transaction.
- **`drift < 0`** — stored is lower than postings explain. A
  posting is duplicated, or a stored debit landed without a
  backing transaction.
- **Same `drift` value across consecutive days for one account**
  — one underlying incident rolling forward. Do not treat each
  day as a separate break; find the *first* drift day.

The "few dollars" shape in your original question usually ties
to a single small incident whose delta is in the tens or low
hundreds of dollars. The drift check isolates it for you.

## Drilling in

Click any `subledger_account_id` value in the detail table. The
drill switches to the **Transactions** sheet filtered to that
account. From there:

1. Find the first drift day (the oldest entry in the drift
   table for that account).
2. On the Transactions sheet, look at the postings on and
   around that day.
3. Sum postings forward from a known-good day. The day the sum
   stops matching stored is the day the incident landed.
4. Read the posting(s) around that day. You're looking for
   either an unexpected stored-balance move (no matching
   posting) or an unexpected posting (no matching stored-balance
   move).

At that point you have the answer: which day, which account,
which side drifted, and exactly by how much.

## Next step

Hand off to the team that owns the upstream feed:

- **Customer-account drift** → the core banking / cardholder
  feed. They restate stored to match computed, or post the
  missing transaction.
- **Operating sub-account drift** (sweep-engine-managed
  accounts) → the sweep automation team. Stored and posting
  are both written by the same engine; if they disagree, the
  engine emitted one without the other.

Hand over three things: the `subledger_account_id`, the first
drift date, and the constant drift dollar amount. That's enough
for the owning team to fix it without a second round-trip.

## Related scenarios & walkthroughs

- [Scenario 2 — What happened to this transaction's money?](02-what-happened-to-this-money.md) —
  the complementary trace for transfers rather than balances.
- [Sub-Ledger Drift (upstream)](../../../docs/walkthroughs/ar/sub-ledger-drift.md) —
  mechanical walkthrough with screenshots and exact planted data.
- [Ledger Drift (upstream)](../../../docs/walkthroughs/ar/ledger-drift.md) —
  the control-account-level view when sub-ledger drift rolls up.
- [Balance Drift Timelines Rollup (upstream)](../../../docs/walkthroughs/ar/balance-drift-timelines-rollup.md) —
  the timeline view; a different shape of drift (SNB vs. external
  authority) that's often confused with sub-ledger drift but
  teaches a distinct invariant.
- Background: [Double-entry accounting](../concepts/double-entry.md).
