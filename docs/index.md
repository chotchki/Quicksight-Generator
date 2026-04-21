<div class="snb-hero">
  <img class="snb-hero__wordmark" src="img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>Reconciliation Handbook</h2>
  <p class="snb-hero__tagline">Operator walkthroughs for the Treasury and Merchant Services dashboards.</p>
</div>

# QuickSight Analysis Generator

Programmatic AWS QuickSight analysis generator for financial reporting.
Ships two independent dashboards sharing one theme, account, datasource,
and CLI surface.

## Operator handbooks

For the day-to-day users of the deployed dashboards.

- [Account Reconciliation Handbook](handbook/ar.md) — ledger /
  sub-ledger balances, transfers, and double-entry posting integrity
  for a community bank's treasury team.
- [Payment Reconciliation Handbook](handbook/pr.md) — sales,
  settlements, payments, and external-system matching for a merchant
  bank's payments team.

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
- [Schema v3 — Data Feed Contract](Schema_v3.md) — column specs,
  metadata key catalog, and ETL examples for the two base tables.
