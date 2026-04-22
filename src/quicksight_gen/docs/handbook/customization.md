<div class="snb-hero">
  <img class="snb-hero__wordmark" src="../../img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>Customization Handbook</h2>
  <p class="snb-hero__tagline">Reshape the dashboards onto your own backend without rewriting the visual layer.</p>
</div>

This handbook is for the **developer or product owner** dropping
the Account Reconciliation and Payment Reconciliation dashboards
onto their own data — not the Data Integration ETL engineer
loading the two base tables (that's the
[Data Integration Handbook](etl.md)).

The product is built around a small, deliberate set of
*customer-mutable* surfaces. Swap the SQL behind a dataset, swap
the colors on a theme, point the deploy at a different AWS
account, or extend the metadata contract — each happens in one
place, with one test that catches the regression. The visual,
filter, and drill layer above the data binds to a stable column
contract; you change *what fills the contract*, not *how the
visuals consume it*.

## What stays stable

These are the surfaces this handbook documents. They're the parts
of the product that are deliberately small and don't churn under
new persona work or dashboard redesigns:

- **Two base tables** — `transactions` + `daily_balances`. Every
  app reads from these. Adding a new persona or a new exception
  check doesn't add a new base table; it adds a new dataset SQL
  view over the same two tables.
- **`DatasetContract`** — column name + type list per dataset.
  The SQL query is *one* implementation; you can swap the SQL
  while preserving the contract and the visual layer keeps
  working untouched.
- **`metadata` JSON column** — the per-app extension point.
  Add keys without schema migrations; read them with
  portable `JSON_VALUE` syntax.
- **Theme presets** — color tokens, fonts, naming prefix.
  Your brand drops in via one preset registration.
- **`config.yaml` + CLI** — account, region, principals,
  resource prefix, datasource ARN, all configurable from one
  file (or env vars). The CLI itself (`generate` / `deploy` /
  `cleanup` / `demo`) is the customer-facing surface and won't
  change shape without a major version bump.

## What this handbook does *not* cover

- **Per-visual customization.** The 32+ datasets and their
  visuals will continue to evolve as the persona work in
  Phase K (AR Exceptions redesign, persona dashboard split, new
  Fraud and AML surfaces) lands. Document those once they
  stabilize.
- **Per-dataset SQL enumeration.** Each dataset's SQL is in
  `apps/payment_recon/datasets.py` or `apps/account_recon/datasets.py`;
  read it as the source of truth. The pattern for *replacing*
  it is documented here once.
- **Per-sheet layout.** Sheet structure is part of the active
  product surface and may shift under persona-driven redesigns.

## Setup

<p class="snb-section-label">Get the dashboards landed against your data</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-map-my-database/">
    <h3>How do I map my production database to the two base tables?</h3>
    <p>Pattern-level mapping from your source system to <code>transactions</code> + <code>daily_balances</code>. The first walkthrough a new product owner reads.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-configure-the-deploy/">
    <h3>How do I configure the deploy for my AWS account?</h3>
    <p><code>config.yaml</code> fields, environment-variable overrides, production datasource ARN vs. demo connection string, principals + tags + naming prefix.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-run-my-first-deploy/">
    <h3>How do I run my first deploy?</h3>
    <p>The <code>generate</code> + <code>deploy</code> + <code>cleanup</code> loop, idempotent delete-then-create, dry-run before live, <code>ManagedBy</code> tag scoping.</p>
  </a>
</div>

## Reskinning + extending

<p class="snb-section-label">Make the product fit your environment</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-reskin-the-dashboards/">
    <h3>How do I reskin the dashboards for my brand?</h3>
    <p>Theme preset registry, color tokens (accent / primary_fg / link_tint), font sizes, the <code>analysis_name_prefix</code> for demo-vs-prod naming.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-swap-dataset-sql/">
    <h3>How do I swap the SQL behind a dataset without breaking the visuals?</h3>
    <p>The <code>DatasetContract</code> binding contract, the contract test that locks projection-vs-contract, when SQL swap is safe and when it forces a contract change.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-add-a-metadata-key/">
    <h3>How do I add an app-specific metadata key?</h3>
    <p>Reading metadata from dataset SQL, when to surface a key as a column vs. a filter, cross-link to the ETL-side walkthrough for the write path.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-extend-canonical-values/">
    <h3>How do I extend the schema with a new transfer_type or account_type?</h3>
    <p>Adding to the canonical value lists, downstream impact on filter dropdowns, why no new tables are needed.</p>
  </a>
</div>

## Testing your customization

<p class="snb-section-label">Catch regressions before they ship</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/customization/how-do-i-test-my-customization/">
    <h3>How do I run the test suite against my customized dataset SQL?</h3>
    <p>pytest layout, the <code>DatasetContract</code> assertion pattern, when to add an e2e test vs. a unit test for your custom SQL.</p>
  </a>
</div>

## Optional ETL extensions

A small set of feed columns are *optional* — leave them NULL and
the downstream views fall back to a sensible default; populate
them when you can give the dashboard rail-accurate signal:

- **`expected_complete_at`** (TIMESTAMP on `transactions`) — when
  your ETL knows the rail's settlement window (instant: same-day;
  ACH: T+2; cards: T+3), set it per leg. The dashboard's
  data-driven `is_late` predicate fires off this column with a
  `posted_at + INTERVAL '1 day'` fallback when it's NULL. Adopt
  one rail at a time; until then, every row uses the one-day
  default. Full contract: [Lateness as data](../Schema_v3.md#lateness-as-data)
  in the schema doc, plus the
  [`expected_complete_at` ETL section](etl.md#optional-expected_complete_at-lateness)
  in the ETL handbook.
- **`metadata`** (JSON TEXT on `transactions` and
  `daily_balances`) — the per-app extension column. Add
  app-specific keys without schema migrations; the
  *How do I add an app-specific metadata key?* walkthrough above
  is the read/write contract.

## Reference

- [Schema v3 — Data Feed Contract](../Schema_v3.md) — the column
  contract for the two base tables. Read this before mapping
  your source system.
- [Data Integration Handbook](etl.md) — the ETL-engineer view of
  the same surface. Useful when your customization spans both
  product wiring and the upstream feed.
- [GL Reconciliation Handbook](ar.md) — the AR analyst's view of
  what the dashboard looks like once your data is loaded.
- [Payment Reconciliation Handbook](pr.md) — the merchant
  support team's view.
