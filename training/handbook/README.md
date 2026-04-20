# Reconciliation Tool — Cross-Training Handbook

*Operator training for the QuickSight reconciliation dashboards at
Sasquatch National Bank (SNB).*

This handbook is how our four operating teams learn to use the AR and
PR dashboards in place of today's aggregated-report workflow. It
doesn't teach accounting from scratch — it teaches how to ask the
questions you already ask today and get an answer from the dashboard
in under a minute, without escalating to the developers.

## Who this is for

Pick the track that matches your day job. Scenarios live in
[`scenarios/`](scenarios/) and are cross-linked from every track, so
reading a scenario from outside your own track is encouraged.

| Track | Team | Dashboard | Where to start |
|---|---|---|---|
| [Accounting](for-accounting/) | GL reconciliation| Account Reconciliation (AR) | [Why this exists](for-accounting/00-why-this-exists.md) → [Dashboard literacy](for-accounting/01-dashboard-literacy.md) → scenarios 1 + 2 |
| [Customer Service](for-customer-service/) | Merchant support| Payment Reconciliation (PR) | [Why this exists](for-customer-service/00-why-this-exists.md) → [Dashboard literacy](for-accounting/01-dashboard-literacy.md) → scenario 3 |
| [Developers](for-developers/) | Tool ownership + ETL | Both | [Why this exists](for-developers/00-why-this-exists.md) → the `../quicksight` ETL handbook |
| [Product Owner](for-product-owner/) | Presenter / train-the-trainer | Both | [How to present this](for-product-owner/00-how-to-present-this.md) |

## Background concepts

Short explainers on the industry-standard vocabulary the dashboards
use. Read them in any order; each one ends with "in the SNB demo,
you'll see this as …" so you can flip to the demo and make the
abstract concrete.

- [Double-entry accounting](concepts/double-entry.md)
- [Open vs. closed loop](concepts/open-vs-closed-loop.md)
- [Sweep and net-settle](concepts/sweep-net-settle.md)
- [Escrow with reversal](concepts/escrow-with-reversal.md)
- [Vouchering](concepts/vouchering.md)
- [Eventual consistency](concepts/eventual-consistency.md)

## The two environments

You have two QuickSight environments available:

- **Demo environment** — populated with Sasquatch National Bank
  seed data. Has planted exceptions so every dashboard check has
  rows to drill. Stable; use it to learn and to check what a clean
  dashboard looks like.
- **Production environment** — populated with your real feed.
  Shape is identical; the names, accounts, and amounts are yours.

Every scenario walks you through the demo first ("what you'll see
in the demo"), then points you at the same shape in production.
When in doubt, learn the pattern on the demo, then look for it in
production.

## Seed scenarios

Three operator questions the team asks today. Each is a full
walkthrough — symptom on the dashboard to the answer.

1. [Where did these few dollars in the pool come from?](scenarios/01-dollars-in-the-pool.md)
2. [What happened to this transaction's money?](scenarios/02-what-happened-to-this-money.md)
3. [Why don't the vouchers match the sales for this set of merchants?](scenarios/03-vouchers-dont-match-sales.md)

More scenarios will be added as the teams ask questions that aren't
yet covered. See [how to add a scenario](scenarios/extending-template.md).

## Cross-references into the upstream tool docs

The tool itself lives at `../quicksight` and ships a separate,
public handbook of its own at `docs/handbook/`. When a scenario
here says "open the existing walkthrough for X," that's where it
lives. Treat the upstream walkthroughs as the mechanical reference;
treat this handbook as the operator framing on top.

- [GL Reconciliation Handbook](../../docs/handbook/ar.md) — AR dashboard, full catalogue of per-check walkthroughs
- [Payment Reconciliation Handbook](../../docs/handbook/pr.md) — PR dashboard, organised by operator question
- [Data Integration Handbook](../../docs/handbook/etl.md) — feed contract, ETL examples, debug recipes
