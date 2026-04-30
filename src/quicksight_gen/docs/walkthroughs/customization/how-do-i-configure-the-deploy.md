# How do I configure the deploy for my AWS account?

*Customization walkthrough — Developer / Product Owner. Setup.*

## The story

You've decided the data side fits
([How do I map my production database?](how-do-i-map-my-database.md))
and you're ready to point the generator at your AWS account. The
deploy side is a single YAML file plus an existing QuickSight
datasource ARN — the same shape used in development, staging, and
production, distinguished by which file the CLI reads.

This walkthrough covers what each `config.yaml` field controls,
which fields are required vs optional, the env-var override
pattern for CI / multi-environment deploys, and the demo vs
production datasource distinction.

## The question

"What do I put in `config.yaml` for my AWS account, and what's
the minimum to get a first deploy through?"

## Where to look

Three reference points:

- **`examples/config.yaml`** — the canonical template. Every
  field documented inline. Copy it to your working directory
  and edit.
- **`src/quicksight_gen/common/config.py`** — the `Config`
  dataclass. Source of truth for field names, defaults, and
  env-var mappings.
- **`run/config.yaml`** (your own) — convention for keeping
  local production config out of git. The repo's `.gitignore`
  excludes `run/`; mount your real account ID, ARN, and
  principal there. Pass `-c run/config.yaml` on every CLI
  invocation, or `cd run/` to make it the default.

## What you'll see in the demo

The example config from `examples/config.yaml`:

```yaml
aws_account_id: "111122223333"
aws_region: "us-east-1"

datasource_arn: "arn:aws:quicksight:us-east-1:111122223333:datasource/example-datasource"

resource_prefix: "qs-gen"

# Theme is declared inline on the L2 institution YAML, not here
# (N.4.j). When the L2 instance carries no ``theme:`` block, AWS
# QuickSight CLASSIC takes over at deploy.

principal_arns:
  - "arn:aws:quicksight:us-east-1:111122223333:user/default/example-user"

# demo_database_url: "postgresql://user:password@host:5432/dbname"
```

Five required fields (account, region, datasource ARN, prefix,
at least one principal) and one optional demo field. That's
the entire deploy contract.

## What it means

Each field, what it controls, and what breaks if you set it wrong:

### Required for any deploy

- **`aws_account_id`** — the 12-digit AWS account ID where
  resources are created. The generator embeds this in every
  ARN and tag. Wrong value: deploy targets the wrong account
  (or fails with a permissions error, depending on your IAM
  setup).
- **`aws_region`** — the AWS region where QuickSight
  resources live. **Important:** this is the region of your
  *dashboard* deployment, not the QuickSight identity region
  (which is always `us-east-1`). Wrong value: deploy creates
  resources in the wrong region; the dashboard URL points
  somewhere your users can't access.
- **`datasource_arn`** — the ARN of an existing QuickSight
  datasource pointing at your warehouse. The generator does
  *not* create datasources for you — they require credentials
  and VPC config that don't belong in this tool. Pre-provision
  the datasource via the QuickSight console (or your IaC), then
  paste the ARN here.

### Required for production-grade deploys

- **`principal_arns`** — IAM principals granted permissions on
  every generated resource (theme, analyses, datasets,
  dashboards). Accept a single string or a list. Without at
  least one principal, the generated resources have no
  explicit permissions — the resource owner (the IAM user /
  role running the deploy) gets implicit access via
  CreateAnalysis but no other principal can see the dashboards.
  Production: list the QuickSight user / group ARNs that
  should have edit + view access.

### Common knobs

- **`resource_prefix`** (default `qs-gen`) — prefix prepended to
  every resource ID. Useful for multi-tenant deploys (one
  account hosting dashboards for multiple business units —
  `team-a-` / `team-b-` prefixes keep them visually separable
  in the QuickSight console). The cleanup command uses the
  `ManagedBy` tag, not the prefix, so changing the prefix is
  safe — it doesn't orphan old resources, just shifts where
  new ones land.
- **`extra_tags`** — dict of extra AWS tags to apply to every
  resource alongside the always-on `ManagedBy:quicksight-gen`
  tag. Use for cost allocation (`CostCenter: treasury`),
  ownership (`Owner: gl-recon`), or environment
  (`Environment: prod`). The deploy refreshes tags on every
  run.

> **Note (v3.8.0):** the prior `late_default_days` knob is gone.
> Lateness is now data-driven — each transaction row carries an
> optional `expected_complete_at` timestamp, and the generated
> SQL surfaces an `is_late` column that flips when
> `CURRENT_TIMESTAMP > COALESCE(expected_complete_at,
> posted_at + INTERVAL '1 day')`. See the ETL handbook section
> on `expected_complete_at` for the population contract.

### Demo-only

- **`demo_database_url`** — Postgres connection string for
  `demo apply` to write seed data. When set and
  `datasource_arn` is omitted, the generator derives the ARN
  automatically (`{aws_region}:{aws_account_id}:datasource/
  {resource_prefix}-demo-datasource`). In production, leave
  this unset and provide the explicit `datasource_arn`.

## Drilling in

A few patterns to know once the basic config works:

### Env-var overrides (CI / multi-environment)

Every field has a `QS_GEN_*` env var that overrides the YAML.
The mapping (from `config.py:90-98`):

| YAML field          | Env var                          |
|---------------------|----------------------------------|
| `aws_account_id`    | `QS_GEN_AWS_ACCOUNT_ID`          |
| `aws_region`        | `QS_GEN_AWS_REGION`              |
| `datasource_arn`    | `QS_GEN_DATASOURCE_ARN`          |
| `resource_prefix`   | `QS_GEN_RESOURCE_PREFIX`         |
| `principal_arns`    | `QS_GEN_PRINCIPAL_ARNS` (CSV)    |
| `demo_database_url` | `QS_GEN_DEMO_DATABASE_URL`       |

CI pattern: commit `examples/config.yaml` as the staging
template, override `QS_GEN_AWS_ACCOUNT_ID` /
`QS_GEN_DATASOURCE_ARN` per environment in the CI runner. No
per-environment YAML files to maintain.

### Production datasource ARN vs demo connection string

The two are mutually exclusive in practice:

- **Production**: `datasource_arn` points at a QuickSight
  datasource you've already created (typically a Postgres,
  Athena, or Redshift datasource via the QuickSight console
  or Terraform). The deploy never touches the datasource;
  it only references the ARN.
- **Demo**: `demo_database_url` is a Postgres connection
  string. `quicksight-gen demo apply` runs your schema +
  seed against this URL, then writes a `datasource.json`
  describing a QuickSight datasource pointing at the same
  Postgres. The deploy creates that datasource as part of
  the run.

If you set both, the explicit `datasource_arn` wins. If you
set neither, `Config.__post_init__` raises with a clear
"datasource_arn is required unless demo_database_url is set"
error.

### Principals — single string vs list

Accept both shapes:

```yaml
# Single string
principal_arns: "arn:aws:quicksight:us-east-1:111122223333:user/default/alice"

# List
principal_arns:
  - "arn:aws:quicksight:us-east-1:111122223333:user/default/alice"
  - "arn:aws:quicksight:us-east-1:111122223333:group/default/treasury"

# Legacy single key (still works)
principal_arn: "arn:aws:quicksight:us-east-1:111122223333:user/default/alice"
```

Group ARNs are valid; the deploy treats them identically to
user ARNs. For team-wide access, prefer one group ARN over
many user ARNs — easier to maintain when team members rotate.

### Why no `--profile` flag

The generator uses boto3's default credential resolution
(env vars → `~/.aws/credentials` → instance profile). To
target a specific profile, set `AWS_PROFILE` in the
environment before invoking. This keeps the generator's
config focused on what's *generated* rather than how the
caller authenticates.

## Next step

Once your `config.yaml` is in place:

1. **Generate to validate the config.** `quicksight-gen
   generate --all -c config.yaml -o out/` writes the JSON
   without touching AWS. Inspect `out/` — confirm the
   prefix, theme, and analysis name look right.
2. **Run a dry-run cleanup.** `quicksight-gen cleanup
   --dry-run -c config.yaml` lists what *would* be deleted
   under the `ManagedBy:quicksight-gen` tag. On a fresh
   account this is empty; if you see unexpected resources,
   investigate before running a real deploy.
3. **Walk
   [How do I run my first deploy?](how-do-i-run-my-first-deploy.md)** —
   the actual `deploy` invocation, what to watch for during
   the delete-then-create cycle, and how to confirm the
   dashboard renders.

## Related walkthroughs

- [How do I run my first deploy?](how-do-i-run-my-first-deploy.md) —
  the **next step**: actually invoking `deploy` with the
  config you've just written.
- [How do I reskin the dashboards for my brand?](how-do-i-reskin-the-dashboards.md) —
  the inline ``theme:`` block on the L2 institution YAML; how to
  declare your brand colors per institution.
- [How do I map my production database to the two base tables?](how-do-i-map-my-database.md) —
  the upstream prerequisite. Deploy assumes your data is
  already landing in the two base tables (or the warehouse
  views your custom dataset SQL points at).
