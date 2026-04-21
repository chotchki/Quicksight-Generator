# Extending the tool

*For the engineering team. When a new question, feed, or
exception comes in, this is the decision tree for where the
change lands.*

The single biggest mistake we can make is answering every new
question with another bespoke script. The tool is structured so
that most new questions resolve to "add a view" or "add a
metadata key" — not to "write another ETL job." This page is the
decision tree.

## The layers, from cheap to expensive

1. **Handbook only** (this repo) — "the tool already answers
   this, we just need to write down how to ask."
2. **SQL view** (upstream tool) — the two base tables have the
   data, but no computed view exposes it in the shape the
   operator needs.
3. **Metadata key** (upstream tool, Schema v3 extension) — the
   projection doesn't yet carry the attribute a new check
   needs.
4. **New `transfer_type` or `account_type`** (upstream tool) —
   a genuinely new flow shape that existing discriminators
   don't cover.
5. **New ETL job** (upstream tool) — a brand-new upstream feed.
6. **QuickSight changes** (dashboard layer) — a new visual, new
   drill, new dataset in SPICE.

Always try layers 1–3 before 4–6. In practice we expect ~70% of
requests to land in layer 1 or 2.

## Decision tree

### "The operator team asked a new question."

Start here. Not every new question needs new code.

- **Is there an existing upstream walkthrough that covers it?**
  If yes → **add a scenario** in this repo wrapping the
  walkthrough. See [extending-template.md](../scenarios/extending-template.md).
  No tool change needed.
- **Does the answer live in `transactions` + `daily_balances`
  but no check currently surfaces it?** → **new SQL view** in
  the upstream tool, then a scenario in this repo. This is the
  most common real case.
- **Does the answer require an attribute the projection doesn't
  yet carry?** → **metadata key** (see the upstream
  [How do I add a metadata key walkthrough](../../../docs/walkthroughs/etl/how-do-i-add-a-metadata-key.md))
  + SQL view + scenario.
- **Does the answer require a flow shape we've never
  projected?** → you're in layer 4+. Talk to the PO before
  starting — a new `transfer_type` is load-bearing on the
  operator tracks and the scenario docs.

### "A new upstream feed is coming online."

- **Does it fit the existing `transfer_type` catalog?** Yes for
  nearly all bank feeds. Project it into the two-table contract.
  The upstream
  [populate-transactions walkthrough](../../../docs/walkthroughs/etl/how-do-i-populate-transactions.md)
  is the canonical pattern.
- **Does it fit but needs per-row attributes not in the
  contract?** → metadata key.
- **Does it represent a flow shape that breaks an invariant?**
  (Non-double-entry postings, asymmetric reversals, etc.) Stop.
  Don't project it until you've talked to the PO and the
  accounting team — the invariants the dashboard relies on have
  to survive.

### "A dashboard shows a false positive / false negative."

- **False positive** (an exception flagged that isn't really
  one): almost always an ETL projection bug. The view is
  computing `stored - computed = $5.00` because the projection
  didn't post the offsetting leg. Fix the ETL; the view is
  correct by construction.
- **False negative** (a real exception the dashboard missed):
  either the check doesn't exist (new view) or the projection
  dropped the row entirely (ETL bug — the upstream
  [six-recipe debug walkthrough](../../../docs/walkthroughs/etl/what-do-i-do-when-demo-passes-but-prod-fails.md)
  is the first place to look).

### "The operator wants the visual shaped differently."

This is the only case that routes to QuickSight changes. Before
touching dashboards: check whether a saved view on the existing
visual (with different filter defaults) would satisfy them.
Visual edits are the slowest-to-ship changes of any on this list.

## When to add a scenario page (in this repo)

Add one when:

- A new exception check lands in the upstream tool and a track
  (accounting, CS) needs to know how to use it. The check's
  own upstream walkthrough covers mechanics; the scenario
  frames *when* to reach for it.
- An existing check is being used in a way the current scenarios
  don't cover. "We started using this check for a new merchant-
  cadence question" is a scenario, not a code change.
- The PO asks for a practice walk-through for a specific team
  interaction.

Do *not* add a scenario for:

- A one-off debug session.
- A transient production issue (put it in the incident tracker).
- A tool change that hasn't been operator-tested yet (write it
  when a team has actually used it, not before).

See [extending-template.md](../scenarios/extending-template.md)
for the template and checklist.

## When to update the concept pages

Rarely. The concept pages (`handbook/concepts/`) cover
industry-standard vocabulary that predates this tool by decades.
Update them when:

- A real-world-program analogue the team uses has a name the
  page doesn't mention and it's causing confusion. Add a "you'll
  also hear this called …" line. Do not replace the existing
  vocabulary.
- A new SNB demo element maps cleanly to an existing concept —
  add it to the "in the SNB demo" block at the bottom of the
  page.

Do not add new concept pages for SNB-specific demo elements.
Those belong in the upstream `docs/` tree. Concept pages
in this handbook are for cross-cutting vocabulary that applies
to both the SNB demo and the real system.

## Coordinating across the two repos

- Code and upstream walkthroughs live in the parent repo
  (outside `training/`).
- Operator framing and scenarios live here.
- When you add a new check upstream, add the matching scenario
  here in the same PR cycle (ideally the same week). A check
  with no scenario is a check no operator will find.
- When you add a scenario here, the upstream walkthrough it
  wraps must already exist. If it doesn't, pause and write the
  upstream walkthrough first — this repo doesn't carry
  mechanical detail, it brackets it.

## What not to put in this repo

- ETL code or SQL migrations — those live in the parent repo
  (outside `training/`).
- Schema v3 changes — those live in `docs/Schema_v3.md`.
- Mechanical walkthroughs with screenshots and exact KPI numbers
  — those live in `docs/walkthroughs/` at the repo root.
- Production-specific data, account numbers, or names — those
  live in the real-system wiki after publish-time substitution,
  not in the source repo.

## Related

- Upstream [Data Integration Handbook](../../../docs/handbook/etl.md) — the
  canonical reference for everything in layers 2–5.
- [Schema v3](../../../docs/Schema_v3.md) — the two-table
  contract.
- [Scenario extending template](../scenarios/extending-template.md).
