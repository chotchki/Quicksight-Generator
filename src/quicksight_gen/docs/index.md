<div class="snb-hero">
  <img class="snb-hero__wordmark" src="img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>Reconciliation Handbook</h2>
  <p class="snb-hero__tagline">Operator walkthroughs for the Treasury and Merchant Services dashboards.</p>
</div>

# QuickSight Analysis Generator

Programmatic AWS QuickSight analysis generator for financial reporting.
Ships an L1 dashboard + an L2 flow-tracing dashboard fed by the L2
foundation, plus the legacy Investigation app, sharing one theme,
account, datasource, and CLI surface.

## Operator handbooks

For the day-to-day users of the deployed dashboards.

- [L1 Dashboard Handbook](handbook/l1.md) — L1 invariant violations
  (drift, overdraft, limit breach, stuck pending, stuck unbundled)
  surfaced from any L2 instance — the persona-blind operator view.
- [L2 Flow Tracing Handbook](handbook/l2_flow_tracing.md) — Rails,
  Chains, Transfer Templates, and L2 hygiene exceptions — for the
  integrator validating their L2 instance against the SPEC.
- [Investigation Handbook](handbook/investigation.md) — recipient
  fanout, volume anomalies, money-trail provenance, and account-network
  graphs for a bank's compliance / AML triage team.

## Engineering handbooks

For the teams loading data into and customizing the dashboards.

- [Data Integration Handbook](handbook/etl.md) — for the ETL engineer
  populating the two base tables (`transactions` + `daily_balances`)
  from upstream systems.
- [Customization Handbook](handbook/customization.md) — for the
  developer or product owner dropping the dashboards onto their own
  backend, brand, and AWS account.

## Reference

- [Account Structure](Training_Story.md) — how Sasquatch National
  Bank, the demo persona, and its accounts relate to each other.
- [Schema v3 — Data Feed Contract](Schema_v6.md) — column specs,
  metadata key catalog, and ETL examples for the two base tables.
