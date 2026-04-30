# {{ vocab.institution.name }} — Chains

A chain entry declares "when {{ "{{" }} parent {{ "}}" }} fires, {{ "{{" }} child {{ "}}" }} SHOULD fire too".
Required chains gate L2 hygiene (the L2 Flow Tracing app's Chain
Orphans check); optional chains document expected patterns without
gating. XOR groups encode "exactly one of these children MUST fire".

Total: **{{ l2.chains|length }}** chain entries declared on
`{{ l2_instance_name }}.yaml`. The chains diagram on the
[overview](index.md#topology-chains-parent-child-firings) shows the
edges visually.

{% if l2.chains %}
| Parent | Child | Required | XOR group | Description |
|---|---|---|---|---|
{% for c in l2.chains -%}
| {{ c.parent }} | {{ c.child }} | {{ "✓" if c.required else "—" }} | {{ c.xor_group or "—" }} | {{ (c.description or "—")|replace("\n", " ") }} |
{% endfor %}
{% else %}
*This L2 instance declares no chain entries — every Rail and Transfer
Template fires independently with no cross-referenced "SHOULD also
fire" rules.*
{% endif %}
