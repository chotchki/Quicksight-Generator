# Concepts

The reasoning behind the dashboards — banking primitives that the L1
invariants, the L2 model, and the per-app sheets all assume the reader
already understands.

The intended user is anyone touching the dashboards for the first time:
operators, integrators, ETL engineers, executives. Read these pages
before the per-app reference material if a term ("invariant", "rail",
"chain", "supersession", "double-entry posting") is unfamiliar.

## Pages

Phase O.1.e populates this section. Until then the conceptual material
lives in `training/handbook/concepts/` (extract via
`quicksight-gen export training`).

The planned set:

- Double-entry posting — debit / credit pair as the L1 invariant root.
- Escrow with reversal — the lifecycle of a held leg.
- Sweep / net / settle — the daily cycle behind concentration accounts.
- Vouchering — voucher → settlement materialization.
- Eventual consistency — multi-day clear timelines.
- Open vs closed loop — network shape implications.
