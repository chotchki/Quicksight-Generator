# Account template

An **account template** declares the SHAPE of a 1-of-many account
class — *all customer demand-deposit accounts*, *all merchant
settlement accounts*, *all per-product subledgers*. The L2 YAML
declares the template once; the actual physical account instances
are selected at posting time, typically from
``Transaction.Metadata`` (``customer_id``, ``merchant_id``).

A template has a ``role``, a ``scope``, and an optional
``parent_role``. The template's ``parent_role`` MUST resolve to a
singleton [Account](account.md) — never another template. The
loader rejects templates that point at another template, per the
SPEC's "singleton parent only" rule.

The materialized instances all roll up to the template's parent
singleton — so e.g. every customer DDA aggregates into the
``DDAControl`` account on the GL, and the L1 drift checks compute
parent rollups against that control number.

Optional ``instance_id_template`` + ``instance_name_template`` let the
demo seed synthesize per-instance ids and display names with a
custom pattern (defaults: ``cust-{n:03d}`` / ``Customer {n}``). The
templates accept ``{role}`` and ``{n}`` as placeholders.

> Templates are why the L1 dashboard's drift sheet shows two views:
> the per-leaf drill (every individual customer DDA) AND the parent
> rollup (the sum across the control account). The parent rollup is
> what catches a "1-cent off across all 50,000 customers" drift that
> no single leaf would surface.

## Specific example for you

{{ l2_account_template_focus() }}
