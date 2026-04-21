# Why this exists — the Customer Service track

*Audience — merchant support team (~2 people). Primary users of the
PR dashboard.*

## What you do today

A merchant calls and asks one of three things:

- "Where's my money? I haven't seen the deposit."
- "My pay-out was short this week — where's the rest?"
- "Why did this transaction bounce back?"

Today, answering those means routing the question to the
developers (who pull the data), waiting, calling the merchant
back, sometimes the next day. By then the merchant is annoyed and
the developer has been pulled off something else.

## What this tool does differently

The PR dashboard is laid out **left-to-right in the order money
moves through the pipeline**:

**Sales → Settlements → Payments → Payment Reconciliation.**

When a merchant calls, you set the merchant filter on the Sales
tab and walk forward through the pipeline, tab by tab, until you
find the stage where their money stalled. Every tab tells you
which stage owns the problem:

- Stuck on Sales → the settlement batch missed the sale.
- Stuck on Settlements → the dollar amounts don't add up or the
  settlement is still pending.
- Stuck on Payments → the pay-out went out but was returned.
- Stuck on Payment Reconciliation → the external system hasn't
  confirmed receipt yet.

Find the stall, and the answer to the merchant's question is
usually sitting right there on the row.

**The first time you take a call, pull up the dashboard while the
merchant is still on the line, and give them a specific answer
before hanging up — that's the proof this tool carries your
workflow.**

## What we are *not* asking you to learn

- **Not SQL.** Click filters, read rows. The querying is already
  done.
- **Not the full tool.** You'll use the PR dashboard. The AR
  dashboard belongs to accounting; the ETL internals belong to
  the developers.
- **Not every exception class.** There are seven or eight
  exception types on the PR Exceptions sheet. You'll use two or
  three heavily.

## How to start

1. Read [Dashboard literacy](../for-accounting/01-dashboard-literacy.md) —
   the shared 15-minute tour of QuickSight navigation, filters,
   and drill-downs. It's the same page the accounting team reads;
   everything in it applies to the PR dashboard too.
2. Work through [Scenario 3 — "Why don't the vouchers match the
   sales for this set of merchants?"](../scenarios/03-vouchers-dont-match-sales.md).
   It's the canonical pay-out-amount-mismatch trace, and it covers
   both the sale↔settlement and settlement↔payment failure shapes.
3. Read the upstream
   [Payment Reconciliation Handbook](../../../docs/handbook/pr.md) —
   specifically the **Common merchant questions** section. Those
   three walkthroughs (Where's My Money, Did All Merchants Get
   Paid, Why Is This External Unmatched) cover the vast majority
   of merchant call shapes.
4. When a merchant asks a question not on that list, check
   [Scenario 2 — "What happened to this transaction's
   money?"](../scenarios/02-what-happened-to-this-money.md). It's
   primarily an accounting scenario, but the transfer-stuck /
   reversed shapes apply here too.

## The concepts you'll want grounded

- [Eventual consistency](../concepts/eventual-consistency.md) —
  teaches the difference between "the merchant's money is in
  flight" (normal) and "stuck" (escalate). Read this before
  scenario 3.
- [Vouchering](../concepts/vouchering.md) — what vouchering is
  and how it maps to the Settlements → Payments pipeline in the
  demo. Read this if you handle voucher-flow merchants.

## What "good" looks like

After a few weeks of handling calls with the dashboard open:

- You're resolving most merchant questions while the merchant is
  still on the line.
- You're escalating to developers with a specific
  `payment_id` / `settlement_id` + dollar amount, not "merchant X
  has a problem".
- You know the expected settlement cadence for each merchant type
  by sight (daily franchises, weekly independents, monthly carts
  in the demo — your real program's cadences map equivalently).
- You're comfortable saying "I can tell you right now why this
  happened" without needing to circle back.

That's the acceptance bar.
