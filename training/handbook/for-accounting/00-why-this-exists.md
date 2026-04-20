# Why this exists — the Accounting track

*Audience — GL reconciliation / accounting team (~4 people). Primary
users of the AR dashboard.*

## What you do today

You run the aggregated text report every morning, cross-check it
against the daily bank statement, and circle the numbers that don't
line up. When one doesn't, the answers you actually need — which
account drifted, which transfer didn't settle, which posting is
missing its counterpart — aren't on the report you're holding.

So you open a ticket with the developers. They pull the data for
you, sometimes within the hour, sometimes not until tomorrow. By
the time you hear back, the issue has often aged another day. If
the answer leads to another question ("OK but where did *that*
entry come from?"), it's another ticket.

## What this tool does differently

The AR dashboard is the same underlying data, laid out so you can
answer those follow-up questions yourself. Every KPI on the
Exceptions sheet is a single class of problem. Every row in the
detail tables is the specific break. Every clickable cell drills
to the underlying transactions.

**The first time you finish a trace in under two minutes — the
kind of trace you used to wait a day for — that's the proof that
this tool has the answers your current process hides.**

## What we are *not* asking you to learn

- **Not SQL.** You won't write queries. The Python code behind the
  dashboard does the querying; you're reading the results.
- **Not a new accounting framework.** The dashboards use the
  industry-standard vocabulary you already know — debits, credits,
  balances, transfers, drift, aging.
- **Not the whole tool.** You'll use the AR dashboard and a small
  number of tabs inside it. The PR dashboard and the tool's ETL
  internals belong to other teams; skim them, don't study them.

## How to start

1. Read [Dashboard literacy](01-dashboard-literacy.md) — 15 minute
   tour of how to navigate any QuickSight dashboard, focused on the
   AR one. It's the shared starting point for you and customer
   service.
2. Work through [Scenario 1 — "Where did these few dollars in the
   pool come from?"](../scenarios/01-dollars-in-the-pool.md) on
   the demo environment. It's the exact shape of question you
   currently escalate to the developers for a balance trace. Do it
   end-to-end; when you're done you'll know the balance-drift
   mechanics cold.
3. Work through [Scenario 2 — "What happened to this transaction's
   money?"](../scenarios/02-what-happened-to-this-money.md). This
   one covers the in-flight / stuck / reversed diagnostic tree.
4. Bookmark the upstream
   [GL Reconciliation Handbook](../../../docs/handbook/ar.md).
   It's the reference — every check on the Exceptions sheet has a
   walkthrough behind it. The two scenarios above teach the
   *pattern*; the handbook is where you look up the specific check
   that fired today.

## The concepts you'll want grounded

Each of these is a ~5 minute read. Come back to them as the
scenarios reference them; don't front-load all of them.

- [Double-entry accounting](../concepts/double-entry.md) — the
  invariant every exception check rests on.
- [Escrow with reversal](../concepts/escrow-with-reversal.md) —
  the shape behind scenario 2.
- [Sweep and net-settle](../concepts/sweep-net-settle.md) — why
  the sweep accounts should end every day at zero.
- [Eventual consistency](../concepts/eventual-consistency.md) —
  how to tell in-flight from stuck.

## What "good" looks like

After a couple of weeks of using the dashboard daily:

- You're opening fewer developer tickets for traces.
- You're finding exceptions before the afternoon instead of the
  next morning.
- When you do escalate, you hand over a specific
  `transfer_id` / `subledger_account_id` + date, not a vague
  "something's off in the pool".
- You're comfortable saying "the dashboard answered this" without
  needing a developer to confirm.

That's the acceptance bar. The tool works when the team trusts
it to carry the load.
