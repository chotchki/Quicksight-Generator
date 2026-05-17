# {{ vocab.institution.name }} — Chains

A chain row declares "when {{ "{{" }} parent {{ "}}" }} fires, one of these
{{ "{{" }} children {{ "}}" }} SHOULD fire too". A row with one child encodes
"required" (every parent firing must invoke that child); a row with
two or more children encodes "XOR" alternation (exactly one of the
listed children MUST fire per parent invocation). The L2 Flow
Tracing app's Chain Orphans check fails when the expected child
firing is missing.

Total: **{{ l2.chains|length }}** chain rows declared on
`{{ l2_instance_name }}.yaml`. The chains diagram on the
[overview](index.md#topology-chains-parent-child-firings) shows the
edges visually.

{% if l2.chains %}
| Parent | Children | Cardinality | Description |
|---|---|---|---|
{% for c in l2.chains -%}
| {{ c.parent }} | {{ c.children|join(", ") }} | {{ "required" if c.children|length == 1 else "xor" }} | {{ (c.description or "—")|replace("\n", " ") }} |
{% endfor %}
{% else %}
*This L2 instance declares no chain rows — every Rail and Transfer
Template fires independently with no cross-referenced "SHOULD also
fire" rules.*
{% endif %}
