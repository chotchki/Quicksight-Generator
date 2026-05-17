# {{ vocab.institution.name }} — Accounts

The 1-of-1 singleton accounts on {{ vocab.institution.acronym }}'s
GL plus the 1-of-many account templates materialized at posting
time. Both kinds plug into the [hierarchy diagram on the
overview](index.md#topology-account-hierarchy-rollup) — singletons
form the backbone, templates fan out beneath their parent
singletons.

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
{% else %}
*This L2 instance declares no account templates — every account is a
1-of-1 singleton.*
{% endif %}
