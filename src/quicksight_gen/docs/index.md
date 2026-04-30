# QuickSight Analysis Generator

*Programmatic AWS QuickSight analysis generator for financial
reporting. Currently rendered against
**{{ vocab.institution.name }}** ({{ l2_instance_name }}).*

Ships **four independent QuickSight apps**, all L2-fed off one
institution YAML (account, datasource, theme, and per-instance
schema prefix), sharing the CLI surface:

- **L1 Reconciliation Dashboard** — persona-blind L1 invariant
  violation surface (drift / overdraft / limit breach / stuck
  pending / stuck unbundled / supersession audit / today's
  exceptions / daily statement / transactions). Configured by an
  L2 instance.
- **L2 Flow Tracing** — Rails / Chains / Transfer Templates /
  L2 Hygiene Exceptions for the integrator validating their L2
  instance against the SPEC.
- **Investigation** — Recipient Fanout / Volume Anomalies / Money
  Trail / Account Network. Compliance / AML triage flow.
- **Executives** — Account Coverage / Transaction Volume / Money
  Moved. Executive scorecard.

## Where to start

Pick the section that matches your role:

- **[Concepts](concepts/index.md)** — banking primitives every
  reader should know first (double-entry, escrow, sweep / settle,
  vouchering, eventual consistency, open vs closed loop).
- **[Reference](reference/index.md)** — per-app structural
  reference: which sheet shows what, which dataset backs it.
- **[Walkthroughs](walkthroughs/index.md)** — task recipes:
  "I have X and want Y" or "I'm looking at this row, what do I do?"
- **[For Your Role](for-your-role/index.md)** — role-oriented
  entry points; pick yours and the page funnels you in.
- **[Scenarios](scenario/index.md)** — end-to-end stories
  grounded in the demo data.
- **[API Reference](api/index.md)** — for building a custom app
  on the typed tree primitives.
