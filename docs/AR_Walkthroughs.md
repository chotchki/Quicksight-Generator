# Account Recon — Exception Walkthroughs

Step-by-step guides for finding each known exception class in the AR
dashboard, anchored on the deterministic demo seed. Two purposes:

1. **Training material** — concrete walkthroughs the GL Reconciliation
   team can follow on the demo dashboard before applying the same moves
   to production data.
2. **Dashboard usability audit** — any walkthrough that's awkward to
   write step-by-step is design feedback for Phase H. A check that needs
   three paragraphs of "now scroll way down past the chart and look for
   the third KPI from the left" is a check whose surfacing is wrong.

Walkthroughs reference the demo seed (`Sasquatch National Bank — CMS`,
anchor date hard-coded in `demo_data.py`). Row counts and dollar
amounts below come from the deterministic generator and will match
what's on the deployed demo dashboard byte-for-byte until the seed
changes. Every dollar amount in this doc is one you can verify.

This is a **starter doc**: two walkthroughs (one rollup-level, one
per-check) drafted for format review. The remaining 12 follow once the
shape is right.

---

## Expected-Zero EOD Rollup *(rollup-level walkthrough)*

### The story

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

### The question

"Of the accounts that should have ended yesterday at zero, are any
carrying a balance?"

### Where to look

Open the AR dashboard, **Exceptions** sheet. Scroll past the Balance
Drift Timelines rollup at the top. The Expected-Zero rollup is the
second block: a KPI ("**Accounts Expected Zero at EOD**") and a detail
table with the same title.

### What you'll see in the demo

The KPI shows a non-zero count. The detail table lists each account-day
where the balance should have been zero but wasn't, with columns:
account, balance date, residual balance, source check, days outstanding,
aging bucket.

Multiple rows from the demo seed contribute:

- ACH Origination Settlement carrying balances on days where the EOD
  sweep didn't post (planted scenarios in `_generate_ach_origination_cycle`)
- Internal Transfer Suspense holding balances from the two stuck
  transfers (Cascade Timber Mill $4,275 and Pinecrest Vineyards
  $1,880 — see the per-check walkthrough below)
- Concentration Master sweep target rows where one of the operating
  sub-accounts didn't sweep clean

### What it means

This rollup tells you the *shape* of what's wrong — money sitting
where it shouldn't — but not yet the *why*. Different sources point at
different upstream owners (sweep automation, internal transfer system,
ZBA configuration). The rollup's job is to make you stop and look; the
per-check details below tell you who to call.

### Drilling in

The detail table's `source check` column names the per-check view that
owns each row. Scroll down the Exceptions sheet to that section
(Sweep Target Non-Zero EOD, ACH Origination Settlement Non-Zero EOD,
Internal Transfer Suspense Non-Zero EOD) for the row-level context the
upstream team needs.

### Next step

If the count is 0: log the morning check as clean and move on. If
non-zero: triage by source — sweep target failures usually go to the
ZBA admin team, ACH non-zero EOD goes to ACH Operations, suspense
non-zero goes to Internal Transfer Operations. Use the per-check
sections to pull the specific account / transfer ID for the handoff.

---

## Stuck in Internal Transfer Suspense *(per-check walkthrough)*

### The story

When an SNB customer initiates an on-us transfer to another SNB
customer, money moves in two steps. Step 1 debits the originator's
DDA and credits `gl-1830` Internal Transfer Suspense. Step 2 then
settles by debiting suspense and crediting the recipient's DDA — *or*
by reversing back to the originator if the transfer fails.

If only Step 1 posts and Step 2 never arrives, the money is stuck.
The originator can't see it (already debited from their DDA), the
recipient hasn't received it, and `gl-1830` carries a non-zero balance
that grows older every day.

### The question

"Are there any internal transfers where Step 1 posted but Step 2 never
did?"

### Where to look

Exceptions sheet, scroll past the rollups, past the baseline checks
(ledger / sub-ledger drift, non-zero transfers, limit breaches,
overdrafts), past the ACH and Fed-card sections. The check is titled
**Stuck in Internal Transfer Suspense** with a KPI, detail table, and
aging bar chart.

### What you'll see in the demo

The KPI shows **2** stuck transfers. The detail table:

| originator                   | recipient                  | originated | days stuck | amount   |
|------------------------------|----------------------------|------------|------------|----------|
| Cascade Timber Mill          | Big Meadow Dairy           | T-11       | 11         | $4,275.00 |
| Pinecrest Vineyards LLC      | Harvest Moon Bakery        | T-23       | 23         | $1,880.00 |

The aging bar chart shows both rows in the **8-30 days** bucket — well
past the 1-3 day "normal in-flight" window.

### What it means

The originating customer has been short the funds for the indicated
number of days. The recipient never got their money. Suspense is
carrying $6,155.00 in stuck balances that should have settled the day
they originated. This is a customer-facing problem on at least two
counts: the originator may be calling about a failed payment, and the
recipient may be calling about a missing payment.

### Drilling in

Click the row in the detail table. The drill switches to the
**Transactions** sheet filtered to that `transfer_id`, showing the
Step 1 originate posting (debit suspense, credit originator DDA) with
no matching Step 2. The absence of Step 2 is the diagnosis — the
internal transfer system stopped halfway.

### Next step

Stuck-in-suspense rows always go to **Internal Transfer Operations**.
Hand off the `transfer_id` (visible on the drilled Transactions sheet)
plus the originator name and amount. They check the transfer system
log for why Step 2 didn't fire — common causes are recipient account
flagged for review, intra-day system restart that lost the in-flight
state, or a NSF check that didn't trigger the reversal path.

After 30 days, stuck transfers escalate to legal / compliance — money
held that long without resolution is a regulatory issue.
