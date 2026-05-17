# Concepts

*If you arrived here directly, the [role pages](../for-your-role/index.md)
curate which concepts each role needs to ground first.*

The reasoning behind the dashboards. Two parts:

- **[Accounting](accounting/index.md)** — banking primitives the L1 invariants
  and the per-app sheets all assume the reader already understands
  (double-entry posting, escrow / suspense, sweep-net-settle,
  vouchering, eventual consistency, open vs. closed loop).
- **[L2 model](l2/index.md)** — the modeling vocabulary an integrator
  uses to declare an institution's shape: Account / AccountTemplate /
  Rail / TransferTemplate / Chain / LimitSchedule. Each page explains
  one primitive in isolation with a focused diagram pulled from the
  loaded L2 instance.

The intended user is anyone touching the dashboards or the L2 YAML
for the first time: operators, integrators, ETL engineers,
executives. Read these before the per-app reference material if a
term ("rail", "chain", "supersession", "double-entry posting") is
unfamiliar.
