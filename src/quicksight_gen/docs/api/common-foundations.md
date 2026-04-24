# Common foundations

Persona-blind helpers + base AWS dataclasses that the tree builds on
top of. Most tree-API authors never touch these directly — the tree's
typed wrappers cover the construction surface — but they're documented
here for reference and for extension authors.

## Models

The dataclass mapping to the AWS QuickSight API JSON shapes
(`to_aws_json()` produces the exact dict shape `create-analysis` /
`create-dashboard` / `create-data-set` / `create-theme` /
`create-data-source` accept).

::: quicksight_gen.common.models

## Typed IDs

NewType wrappers for the URL-facing and analyst-facing identifiers
that stay explicit even after Phase L's auto-ID work for internal
IDs.

::: quicksight_gen.common.ids

## Dataset contracts

`DatasetContract` ties a SQL query's projection to a typed list of
expected columns; `build_dataset()` is the shared constructor used
by every per-app `datasets.py`.

::: quicksight_gen.common.dataset_contract

## Cross-app deep links

URL builder for the `CustomActionURLOperation` — used when a drill
needs to jump to another app's deployed dashboard with parameter
values pre-set in the URL. (Note: per the L.6.7 / K.4.7 finding, the
QuickSight URL parameter sync defect means controls don't update —
data filters but the on-screen widget label stays "All".)

::: quicksight_gen.common.drill

## Demo persona

`DemoPersona` is the single source of truth for whitelabel-substitutable
Sasquatch flavor strings. The companion `derive_mapping_yaml_text()`
builds `training/mapping.yaml.example` from the dataclass so the YAML
template can't drift from the in-code persona.

::: quicksight_gen.common.persona
