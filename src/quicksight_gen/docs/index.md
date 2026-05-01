# QuickSight Analysis Generator

*Programmatic AWS QuickSight analysis generator for financial
reporting. Currently rendered against
**{{ vocab.institution.name }}** ({{ l2_instance_name }}).*

Ships **four independent QuickSight apps**, all L2-fed off one
institution YAML (account, datasource, theme, and per-instance
schema prefix), sharing the CLI surface:

- **L1 Reconciliation Dashboard** — persona-blind L1 invariant
  violation surface, configured by an L2 instance. Sheets:
    - Drift
    - Overdraft
    - Limit Breach
    - Stuck Pending
    - Stuck Unbundled
    - Supersession Audit
    - Today's Exceptions
    - Daily Statement
    - Transactions
- **L2 Flow Tracing** — for the integrator validating their L2
  instance against the SPEC. Sheets:
    - Rails
    - Chains
    - Transfer Templates
    - L2 Hygiene Exceptions
- **Investigation** — Compliance / AML triage flow. Sheets:
    - Recipient Fanout
    - Volume Anomalies
    - Money Trail
    - Account Network
- **Executives** — executive scorecard. Sheets:
    - Account Coverage
    - Transaction Volume
    - Money Moved

## Where to start

Pick the section that matches your role:

- **[For Your Role](for-your-role/index.md)** — role-oriented
  entry points; pick yours and the page funnels you in.
- **[Concepts](concepts/index.md)** — banking primitives every
  reader should know first:
    - Double-entry posting
    - Escrow with reversal
    - Sweep / net / settle
    - Vouchering
    - Eventual consistency
    - Open vs. closed loop
- **[Background](scenario/index.md)** — end-to-end tour of the
  institution's L2 model (accounts, rails, transfer templates,
  chains, limit schedules) grounded in the demo data.
- **[Walkthroughs](walkthroughs/index.md)** — task recipes:
  "I have X and want Y" or "I'm looking at this row, what do I do?"
- **[Reference](reference/index.md)** — per-app structural
  reference: which sheet shows what, which dataset backs it.
- **[API Reference](api/index.md)** — for building a custom app
  on the typed tree primitives.
