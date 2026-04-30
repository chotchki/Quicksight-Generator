# Chain

A **chain entry** declares "when ``parent`` fires, ``child`` SHOULD
also fire". Each chain edge is one piece of L2 hygiene the system
checks against runtime data: did the child actually fire when the
parent did?

Each chain entry has:

- ``parent`` and ``child`` — both reference either a
  [Rail](rail.md) name or a [Transfer Template](transfer-template.md)
  name. The endpoints can mix-and-match (rail → rail, rail →
  template, template → rail, template → template).
- ``required`` — boolean. ``true`` means the L2 Flow Tracing app's
  Chain Orphans check fails when a parent fires without the child.
  ``false`` means the chain documents an expected pattern but
  doesn't gate; the orphans check ignores it.
- ``xor_group`` — optional string. Multiple chain entries sharing
  the same ``xor_group`` value encode "exactly one of these
  children MUST fire when the parent fires". Used for branching
  cycles (e.g. an ACH return MUST fire as one of "NSF",
  "stop-pay", "duplicate" — not zero, not two).

Chains are the modeling tool for "this rail's firing has downstream
consequences" without forcing those downstream firings to be inside
the same atomic Transfer Template. Use a Transfer Template when the
legs MUST be one transaction; use a chain when they can be separate
transactions but you want hygiene to check the second one happened.

> Chain Orphans rolls into the L2 Flow Tracing app's L2 Exceptions
> sheet under ``check_type='Chain Orphans'``. A required-but-missing
> child firing surfaces with the parent firing's id + timestamp so
> you can investigate why the chain broke (rail SQL error, missing
> data, manual posting that bypassed automation, etc).

## Specific example for you

{{ l2_chain_focus() }}
