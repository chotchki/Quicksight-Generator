# How do I run my first deploy?

*Customization walkthrough — Developer / Product Owner. Setup.*

## The story

Your data is landing in `transactions` + `daily_balances`
([How do I map my production database?](how-do-i-map-my-database.md)),
your `config.yaml` is in place
([How do I configure the deploy?](how-do-i-configure-the-deploy.md)),
and you're ready to push the dashboards to QuickSight for the
first time. This walkthrough is the actual deploy invocation —
what runs, what to watch for, and how to roll back if something
looks off.

The deploy is **idempotent and delete-then-create**: every run
deletes existing resources by ID and creates fresh ones. There's
no concept of "update" in this tool. Schema drift between an old
deploy and the current generate output never causes weird
half-updated states because nothing is updated — everything is
re-created from scratch on every run. The trade-off is a deploy
takes ~3-5 minutes (the asynchronous CREATE_ANALYSIS /
CREATE_DASHBOARD calls poll to terminal state); the win is no
state-divergence debugging, ever.

## The question

"What's the actual command sequence to get the dashboards
deployed to my AWS account, and how do I confirm they landed
cleanly?"

## Where to look

Three reference points:

- **`quicksight-gen --help`** — the CLI surface. Four commands:
  `generate`, `deploy`, `cleanup`, `demo`. Each accepts an app
  argument (`payment-recon` / `account-recon`) or `--all`.
- **`src/quicksight_gen/common/deploy.py`** — the deploy
  implementation. Read `deploy()` at line 233 to see the
  delete-then-create order.
- **The QuickSight console** (`https://quicksight.aws.amazon.com`)
  — the visual target. After deploy, your analyses + dashboards
  appear here under the configured prefix (default `qs-gen-*`).

## What you'll see in the demo

The minimum end-to-end run for both apps:

```bash
quicksight-gen deploy --all --generate -c config.yaml -o out/
```

`--generate` regenerates JSON before deploying — the standard
iteration loop. Without `--generate`, the deploy reads whatever
JSON is already in `out/` (useful when iterating on the deploy
step itself without re-running generate).

The output stream looks like:

```
==> qs-gen-payment-recon-analysis ... (regenerated)
==> qs-gen-account-recon-analysis ... (regenerated)
Deploying QuickSight resources from out
  Account: 111122223333
  Region:  us-east-2

--- Recreating all resources ---

==> Creating DataSource: qs-gen-demo-datasource
==> Creating Theme: qs-gen-theme
==> Creating Dataset: qs-gen-merchants-dataset
... (32 datasets total)
==> Creating Analysis: qs-gen-payment-recon-analysis
==> Creating Analysis: qs-gen-account-recon-analysis
==> Creating Dashboard: qs-gen-payment-recon-dashboard
==> Creating Dashboard: qs-gen-account-recon-dashboard

--- Waiting for async resources ---

==> Checking Analysis: qs-gen-payment-recon-analysis
    Status: CREATION_SUCCESSFUL
==> Checking Analysis: qs-gen-account-recon-analysis
    Status: CREATION_SUCCESSFUL
==> Checking Dashboard: qs-gen-payment-recon-dashboard
    Status: CREATION_SUCCESSFUL
==> Checking Dashboard: qs-gen-account-recon-dashboard
    Status: CREATION_SUCCESSFUL

Done. All resources deployed to 111122223333 in us-east-2.
```

Total wall time on a fresh account: 3-5 minutes. Most of it is
the analysis + dashboard polls (the 32+ datasets are synchronous
and complete in seconds).

## What it means

The deploy runs a fixed order of operations
(`common/deploy.py:259-272`):

### Phase 1 — Delete existing (in dependency order)

1. **Dashboards** — leaf resources, no dependents. Deleted first.
2. **Analyses** — backed by datasets. Deleted second.
3. **Datasets** — backed by theme + datasource. Deleted third.
4. **Theme** — referenced by datasets. Deleted fourth.
5. **Datasource** — referenced by datasets (demo only).
   Deleted last.

Each delete is best-effort — a `ResourceNotFoundException`
("nothing to delete") is treated as success. Fresh accounts
skip past the delete phase entirely; on the second deploy
they tear down what the first one created.

### Phase 2 — Create (in dependency order, reverse of delete)

1. **Datasource** (demo only) — created from
   `out/datasource.json`.
2. **Theme** — created from `out/theme.json`.
3. **Datasets** — created from `out/datasets/*.json` (32+ files).
4. **Analyses** — created from `out/<app>-analysis.json`.
5. **Dashboards** — created from `out/<app>-dashboard.json`.

Analyses and dashboards return immediately with a
`CREATION_IN_PROGRESS` status; the deploy then polls
`describe_analysis` / `describe_dashboard` every 5 seconds until
each reaches `CREATION_SUCCESSFUL` (success) or
`CREATION_FAILED` (failure). 60-attempt cap = 5-minute timeout
per resource.

### Phase 3 — Report

Exit code 0 on full success; 1 if any analysis or dashboard
ended in `CREATION_FAILED`. The error messages live in the
poll output — scroll back to find which resource failed and
why.

## Drilling in

A few patterns to know once the basic deploy works:

### Dry-run before live with `cleanup --dry-run`

Before your first real deploy on an existing account, run:

```bash
quicksight-gen cleanup --dry-run -c config.yaml
```

This enumerates every QuickSight resource tagged
`ManagedBy:quicksight-gen` in the account and prints what
*would* be deleted on a `cleanup --yes`. The deploy itself
also deletes-then-creates the resources it manages, but
`cleanup` finds *orphans* — resources from a previous deploy
that the current generate output no longer produces (a
dataset you removed, an analysis you renamed). Run it before
the real deploy to spot any unexpected state.

If the dry-run lists things you don't recognize, *do not*
proceed with `cleanup --yes` until you've investigated. The
`ManagedBy:quicksight-gen` tag scope is intentional — the
tool will never touch resources without that tag — but a
co-worker running a different prefix could have left
unrelated state.

### Iteration loop: `deploy --generate`

Once your first deploy works, the standard iteration loop is:

```bash
# Edit some Python (a visual, a SQL query, a theme color)
quicksight-gen deploy --all --generate -c config.yaml -o out/
# Refresh the QuickSight dashboard in your browser
```

`--generate` rolls `quicksight-gen generate --all` and
`quicksight-gen deploy --all` into one command. About 3-5
minutes per cycle for both apps. Single-app iteration:
`deploy account-recon --generate` cuts the cycle to ~2
minutes.

### Single-app deploy

Deploy one app at a time when you're iterating fast on it:

```bash
quicksight-gen deploy account-recon --generate -c config.yaml
```

The other app's analysis + dashboard remain untouched. Datasets
and theme are shared — the deploy still re-creates them, so a
single-app deploy doesn't isolate dataset changes between apps
(the apps share a base layer; dataset changes affect both).

### Cleanup after dropping a dataset

If you remove a dataset from a `datasets.py` file (a contract
revision or a Phase K consolidation), the next generate
correctly omits it from `out/datasets/`, but the deploy
deletes only the datasets it knows about — the orphan dataset
in QuickSight survives. Run:

```bash
quicksight-gen cleanup -c config.yaml
```

This enumerates `ManagedBy:quicksight-gen` resources, compares
against current `out/` contents, and deletes anything that's
no longer in the build. Always `--dry-run` first to see what
will go.

### What happens if a deploy fails mid-cycle

QuickSight is mostly atomic at the per-resource level — a
failed `create_analysis` doesn't leave partial state on that
analysis ID. But across resources, a failure mid-cycle can
leave some datasets created and others not yet attempted. The
re-run is the recovery: `deploy --all --generate` again. The
delete-then-create model means the second run cleanly tears
down whatever the first run partially built and starts over.
No manual cleanup typically required.

If a deploy keeps failing on the same resource, read the poll
output for the `Errors` field on the failing resource —
QuickSight surfaces dataset-projection errors,
column-type-mismatch errors, and missing-field errors here
verbatim. The most common production failure is a custom
dataset SQL whose column shape drifted from the contract; the
contract test
([How do I swap dataset SQL?](how-do-i-swap-dataset-sql.md))
catches this before deploy, but only if you ran it.

## Next step

Once your first deploy completes with all
`CREATION_SUCCESSFUL`:

1. **Open the dashboard in QuickSight.** Console → Dashboards
   → `qs-gen-account-recon-dashboard` (or your custom prefix).
   Click through the tabs. KPIs should populate; tables should
   render rows. Empty visuals usually mean the underlying
   dataset's SQL returned zero rows against your data — open
   the dataset directly to see the SQL and run it manually
   against your warehouse.
2. **Hand the dashboard URL to a small group of users first.**
   The principals you listed in `config.yaml` get edit + view
   access. Your treasury / GL recon team is the natural first
   audience — their feedback on visual layout, filter wiring,
   and exception KPIs informs the persona work in Phase K.
3. **Wire deploy into CI.** Once the deploy is reliable
   manually, automate it. The env-var override pattern from
   [How do I configure the deploy?](how-do-i-configure-the-deploy.md)
   lets one CI runner deploy to multiple environments by
   swapping `QS_GEN_AWS_ACCOUNT_ID` /
   `QS_GEN_DATASOURCE_ARN` per stage.

## Related walkthroughs

- [How do I configure the deploy for my AWS account?](how-do-i-configure-the-deploy.md) —
  the **prerequisite**: the `config.yaml` fields the deploy
  reads.
- [How do I swap the SQL behind a dataset?](how-do-i-swap-dataset-sql.md) —
  the most common deploy-failure root cause is a custom
  dataset whose column shape drifted from the contract. The
  contract test catches it pre-deploy.
- [How do I reskin the dashboards for my brand?](how-do-i-reskin-the-dashboards.md) —
  for when "the deploy worked but the colors are wrong."
