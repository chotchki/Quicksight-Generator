# {{ vocab.institution.name }} — Transfer templates

A Transfer Template chains multiple Rail firings into a single
business-meaningful Transfer (e.g. "ACH origination cycle: customer
debit + sweep + Fed master credit"). The template's ``expected_net``
closes the bundle — every leg's signed amount MUST sum to that value
(L1 Conservation invariant).

Total: **{{ l2.transfer_templates|length }}** templates declared on
`{{ l2_instance_name }}.yaml`.

{% if l2.transfer_templates %}
{% for tt in l2.transfer_templates %}
## {{ tt.name }}

{{ tt.description or "_(no description on the L2 YAML)_" }}

- **Expected net:** `{{ tt.expected_net }}`
{%- if tt.leg_rails %}
- **Leg rails:** {{ tt.leg_rails|map(attribute="rail_name")|join(" → ") }}
{%- endif %}

{% endfor %}
{% else %}
*This L2 instance declares no transfer templates — every Rail fires
standalone.*
{% endif %}
