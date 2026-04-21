# Why this exists — the Developer track

*Audience — the engineering team (~10 people) that owns the
reconciliation tool's code, ETL, and long-term extension. Both
dashboards are yours to keep working.*

## What you do today

Right now you are the reconciliation team. When accounting can't
explain a few dollars in a control account, or customer service
can't tell a merchant why their pay-out was short, the question
escalates to you. You pull the postings, walk the chain, and
reply with an answer — often the next day.

The tool you're about to own is an attempt to move most of that
work out of your inbox.

## What this tool does differently

The QuickSight dashboards (AR + PR) expose the *same traces you
run today* as sheets and drills. Accounting and customer service
can now run them without you:

- The dashboards read from **two base tables** (`transactions`,
  `daily_balances`). Every derived view — drift, suspense aging,
  settlement-to-payment mismatch — is a SQL view on top of those
  two tables.
- The ETL you own projects upstream feeds (core banking, Fed
  statements, processor reports, sweep-engine output) into those
  two tables. The dashboards see a uniform shape regardless of
  source.
- All exception detection is computed — no rules-engine, no
  hand-tuned thresholds. A "drift" row exists because
  `stored_balance != computed_balance`, full stop. A "stuck in
  suspense" row exists because Step 1 of a two-step transfer
  posted and Step 2 didn't.

Your role shifts from **running traces on demand** to **keeping
the feed correct and the views honest**. When a new exception
shape emerges that the tool doesn't yet catch, you add a view
(or a metadata key, or a transfer type) — not a one-off query.

## What you'll actually own

Three layers, from top to bottom:

1. **Dashboards (QuickSight analyses)** — the SPICE datasets and
   visuals the operator teams see. Changes here are QuickSight
   config, not Python. You edit these rarely.
2. **SQL views and the two-table contract** — the projection
   layer. Most operator-visible features live here: a new
   exception check is usually "another view." The contract is
   documented in [Schema v3](../../../docs/Schema_v3.md).
3. **ETL (Python)** — the projection from upstream SNB systems
   into the two tables. This is where most of your day-to-day
   work lands as new feeds come online or existing feeds change
   shape.

You will not meaningfully touch the QuickSight layer in
week-to-week work. You will live in the SQL views and the ETL.

## What we are *not* asking you to learn

- **Not QuickSight administration.** Dashboard publishing, SPICE
  refresh, user permissions — that stays with the platform team
  initially. Learn it if you want to; it's not on the critical
  path for owning the reconciliation logic.
- **Not a new stack.** PostgreSQL 17, Python, SQL views. No new
  language, no new ORM. The
  "[fancy queries](../../../docs/handbook/etl.md)"
  attitude from the upstream team matches yours.

## How to start

1. **Read the upstream [Data Integration
   Handbook](../../../docs/handbook/etl.md) end to
   end.** It's the canonical reference for the two-table contract,
   the ETL extension points, and the debug recipes for when a feed
   lands data but the dashboard doesn't show it. Everything below
   assumes you've read it.
2. Run the demo environment locally (the `quicksight-gen demo`
   CLI is documented in the upstream handbook). Seeing the
   planted data from scenarios 1–3 in context makes the operator
   tracks concrete.
3. Work through the four foundational walkthroughs linked from
   the upstream handbook, in order:
   - [How do I populate `transactions` from my core banking system?](../../../docs/walkthroughs/etl/how-do-i-populate-transactions.md)
   - [How do I prove my ETL is working before going live?](../../../docs/walkthroughs/etl/how-do-i-prove-my-etl-is-working.md)
   - [How do I tag a force-posted external transfer correctly?](../../../docs/walkthroughs/etl/how-do-i-tag-a-force-posted-transfer.md)
   - [How do I add a metadata key without breaking the dashboards?](../../../docs/walkthroughs/etl/how-do-i-add-a-metadata-key.md)
4. Read [extending.md](extending.md) in this track — it's the
   decision tree for *where* a new change lands (ETL vs. view
   vs. scenario doc).
5. Skim the operator tracks ([accounting](../for-accounting/),
   [customer service](../for-customer-service/)) and the three
   [seed scenarios](../scenarios/). When accounting escalates a
   question to you, you'll want to know which dashboard path
   they already tried.

## The concepts you'll want grounded

The concept pages were written for the operator teams, but the
invariants they describe are the invariants your ETL must
preserve. Most bugs you'll chase are violations of one of these:

- [Double-entry](../concepts/double-entry.md) — every money-
  movement leg has a matching counter-leg. `SUM(signed_amount)`
  over a complete transfer is zero. This is the single most
  important invariant; most exception checks are derivatives of
  it.
- [Sweep and net-settle](../concepts/sweep-net-settle.md) —
  intraday postings aggregate into EOD settlement legs.
  Understanding the cadence matters when you're writing the
  projection for sweep-engine output.
- [Escrow with reversal](../concepts/escrow-with-reversal.md) —
  two-step transfers that can succeed, fail cleanly, or get
  stuck. The AR "stuck in suspense" and "reversed without credit-
  back" checks exist because Step 2 can silently fail; your ETL
  has to emit both legs or the invariants break.
- [Eventual consistency](../concepts/eventual-consistency.md) —
  why the tool uses aging buckets rather than flag-on-arrival.
  Your feed should not swallow "pending" postings; they are part
  of the signal.

## What "good" looks like

After a few weeks of working with the tool:

- When accounting or customer service escalates a question, you
  can identify which *check* should have caught it before you
  touch any code. Most of the time, the check already does catch
  it, and the escalation is "how do I read this row."
- When a new upstream feed comes online, your first question is
  *which transfer_type, what's the projection, do the invariants
  still hold?* — not *how do I build another bespoke
  reconciliation query?*
- When a genuinely new exception shape shows up, you add a SQL
  view and (if needed) a scenario page, and hand it back to the
  operator team. You don't end up running the trace forever.
- When the tool surfaces a false positive, you can tell in under
  ten minutes whether it's a bad projection (fix the ETL), a
  bad view (fix the SQL), or an honest exception that operator
  workflow doesn't yet route (fix the handbook).

That's the acceptance bar. The aim isn't to make you QuickSight
experts; it's to make sure the tool is something you can
confidently extend when the business asks for more.
