# {{ vocab.institution.name }} — Institution Tour

*Generated from the L2 institution YAML (`{{ l2_instance_name }}.yaml`).
Re-run the docs build (or point `QS_DOCS_L2_INSTANCE` at a different
YAML) to regenerate this page against another institution.*

{{ l2.description or "_(no institution description provided in the L2 YAML)_" }}

---

## At a glance

| What | Count |
|---|---|
| Singleton accounts ({{ vocab.institution.acronym }}'s GL + external counterparties) | **{{ l2.accounts|length }}** |
| Account templates (per-customer / per-merchant shapes) | **{{ l2.account_templates|length }}** |
| Rails (money-movement primitives) | **{{ l2.rails|length }}** |
| Transfer Templates (multi-rail bundles) | **{{ l2.transfer_templates|length }}** |
| Chains (parent → child firing rules) | **{{ l2.chains|length }}** |
| Limit Schedules (per-account / per-rail caps) | **{{ l2.limit_schedules|length }}** |

The diagrams below show how these pieces connect. Every section also
unfolds the per-row description text {{ vocab.institution.acronym }}'s
integrators put on the L2 YAML — that prose IS the source of truth for
how the institution treats each entity.

---

## Topology — accounts + rails

Every Rail draws an edge between its source-role account and its
destination-role account. Single-leg rails draw a self-loop on the leg-
role account. Internal {{ vocab.institution.acronym }} accounts are
blue; external counterparties are orange.

{{ diagram("l2_topology", kind="accounts") }}

---

## Topology — chains (parent → child firings)

Chains declare that when one Rail or Transfer Template fires, another
SHOULD fire too. Solid edges are required (validator catches a missing
firing); dashed edges are optional. XOR groups capture "any one of
these MUST fire — pick the right child by metadata".

{{ diagram("l2_topology", kind="chains") }}

---

## Topology — account hierarchy (rollup)

How the singleton accounts and templates roll up. Each edge points
from a child to its parent — the singleton ``Account`` whose ``role``
matches the child's ``parent_role``. Solid-bordered nodes are 1-of-1
singletons; dashed-bordered ``× N`` nodes are templates that
materialize many instances at runtime (e.g. one ``CustomerDDA`` per
customer, all rolling up to the ``DDAControl`` GL).

{{ diagram("l2_topology", kind="hierarchy") }}

---

## Singleton accounts

These are the 1-of-1 accounts {{ vocab.institution.acronym }} holds —
the GL control accounts on the asset/liability side, plus the named
external counterparties.

| ID | Role | Scope | Parent role | Description |
|---|---|---|---|---|
{% for a in l2.accounts -%}
| `{{ a.id }}` | {{ a.role or "—" }} | {{ a.scope }} | {{ a.parent_role or "—" }} | {{ (a.description or "—")|replace("\n", " ") }} |
{% endfor %}

{% if l2.account_templates %}
## Account templates

Templates declare the SHAPE of a 1-of-many account class — the
specific account instance is selected at posting time (typically from
``Transaction.Metadata``). Customer DDAs, merchant settlement
accounts, and per-product subledgers all live here.

| Role | Scope | Parent role | Description |
|---|---|---|---|
{% for t in l2.account_templates -%}
| {{ t.role }} | {{ t.scope }} | {{ t.parent_role or "—" }} | {{ (t.description or "—")|replace("\n", " ") }} |
{% endfor %}

{% endif %}
## Rails — money-movement primitives

Each Rail is a single money-movement primitive. **TwoLegRail** posts
one debit + one credit; **SingleLegRail** posts a single leg (must be
reconciled by a Transfer Template or aggregating rail).

{% for r in l2.rails %}
### {{ r.name }} — `{{ r.transfer_type }}`

{{ r.description or "_(no description on the L2 YAML)_" }}

- **Shape:** {% if r.__class__.__name__ == "TwoLegRail" %}Two-leg ({{ r.source_role }} → {{ r.destination_role }}){% else %}Single-leg ({{ r.leg_role }}, direction {{ r.leg_direction }}){% endif %}
{%- if r.posted_requirements %}
- **Posted requirements:** {{ r.posted_requirements|join(", ") }}
{%- endif %}
{%- if r.max_pending_age %}
- **Aging — pending:** legs SHOULD post within `{{ r.max_pending_age }}` (Stuck Pending matview surfaces violations)
{%- endif %}
{%- if r.max_unbundled_age %}
- **Aging — unbundled:** posted legs SHOULD bundle within `{{ r.max_unbundled_age }}` (Stuck Unbundled matview surfaces violations)
{%- endif %}
{%- if r.aggregating %}
- **Aggregating:** YES — bundles `{{ r.bundles_activity|join(", ") }}`
{%- endif %}
{%- if r.metadata_keys %}
- **Metadata keys:** {{ r.metadata_keys|join(", ") }}
{%- endif %}

{% endfor %}
{% if l2.transfer_templates %}
## Transfer Templates — multi-rail bundles

A Transfer Template chains multiple Rail firings into a single
business-meaningful Transfer (e.g. "ACH origination cycle: customer
debit + sweep + Fed master credit"). The template's ``expected_net``
closes the bundle — every leg's signed amount MUST sum to that value
(L1 Conservation invariant).

{% for tt in l2.transfer_templates %}
### {{ tt.name }}

{{ tt.description or "_(no description on the L2 YAML)_" }}

- **Expected net:** `{{ tt.expected_net }}`
{%- if tt.leg_rails %}
- **Leg rails:** {{ tt.leg_rails|map(attribute="rail_name")|join(" → ") }}
{%- endif %}

{% endfor %}
{% endif %}
{% if l2.chains %}
## Chains — required + optional firings

A chain entry declares "when {{ "{{" }} parent {{ "}}" }} fires, {{ "{{" }} child {{ "}}" }} SHOULD fire too".
Required chains gate L2 hygiene (the L2 Flow Tracing app's Chain
Orphans check); optional chains document expected patterns without
gating. XOR groups encode "exactly one of these children MUST fire".

| Parent | Child | Required | XOR group | Description |
|---|---|---|---|---|
{% for c in l2.chains -%}
| {{ c.parent }} | {{ c.child }} | {{ "✓" if c.required else "—" }} | {{ c.xor_group or "—" }} | {{ (c.description or "—")|replace("\n", " ") }} |
{% endfor %}

{% endif %}
{% if l2.limit_schedules %}
## Limit Schedules — per-(role, transfer_type) caps

Each Limit Schedule sets a daily outbound-flow cap for a (parent_role,
transfer_type) pair. The L1 ``limit_breach`` matview lists every
account/day where outbound activity exceeded the cap.

| Parent role | Transfer type | Cap | Description |
|---|---|---|---|
{% for ls in l2.limit_schedules -%}
| {{ ls.parent_role }} | {{ ls.transfer_type }} | `{{ ls.cap }}` | {{ (ls.description or "—")|replace("\n", " ") }} |
{% endfor %}

{% endif %}
---

## How the dashboards read this

- **L1 Reconciliation Dashboard** — surfaces the L1 invariant
  violations against the data this L2 declares: drift, overdraft,
  limit breach (using the Limit Schedules above), stuck pending /
  unbundled (using the Rails' aging caps), supersession audit.
- **L2 Flow Tracing** — walks the Rails / Chains / Transfer Templates
  diagrams above against runtime activity, surfacing
  declared-but-never-fired rails, chain orphans, and unmatched
  transfer types.
- **Investigation** — questions over the leaf-account / external-
  counterparty graph above (recipient fanout, volume anomalies, money
  trail, account network).
- **Executives** — coverage / volume / money-moved scorecard rolled up
  across {{ vocab.institution.acronym }}'s account roster.

For a per-app sheet-by-sheet walkthrough, see the
[Walkthroughs](walkthroughs/index.md) section.
