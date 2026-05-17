# Concepts — Accounting

Banking primitives the L1 invariants, the L2 model, and the per-app
sheets all assume the reader already understands.

The intended user is anyone touching the dashboards for the first time
— operators, integrators, ETL engineers, executives. Read these pages
before the per-app reference material if a term ("invariant", "escrow",
"sweep", "vouchering") is unfamiliar.

## Pages

- [Double-entry posting](double-entry.md) — debit / credit pair as the
  L1 invariant root.
- [Escrow with reversal](escrow-with-reversal.md) — three-state
  lifecycle for an in-flight transfer that holds in suspense.
- [Sweep / net / settle](sweep-net-settle.md) — the daily cycle behind
  concentration accounts.
- [Vouchering](vouchering.md) — voucher → settlement materialization.
- [Eventual consistency](eventual-consistency.md) — multi-day clear
  timelines and the aging-watch shape that surfaces them.
- [Open vs. closed loop](open-vs-closed-loop.md) — system-boundary
  distinction that shapes which reconciliation problems are even
  possible.

For the modeling primitives the L2 YAML uses to describe an
institution, see [Concepts → L2 model](../l2/index.md).
