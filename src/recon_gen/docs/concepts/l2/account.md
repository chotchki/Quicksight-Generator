# Account

A **singleton account** — a single, named, 1-of-1 thing the institution
holds. Every Account has an ``id`` (the stable database identifier),
a ``role`` (the abstract slot the rest of the L2 model refers to —
e.g. ``CashDueFRB``, ``DDAControl``), and a ``scope`` of either
``internal`` (the institution's own ledger account) or ``external``
(a counterparty: the Federal Reserve, a card processor, a beneficiary
bank).

Accounts can roll up via ``parent_role``: a sub-ledger holding account
typically points to a control account that aggregates many sub-ledgers.
The drift, overdraft, and limit-breach matviews use the parent
relationship to compute parent-level rollups in addition to the leaf
view.

The two scopes drive different downstream behavior:

- **``internal`` accounts** participate in double-entry — every Rail
  that posts to one expects an offsetting credit/debit. They show up
  in the L1 invariant matviews (drift, overdraft) and in the per-day
  Daily Statement.
- **``external`` accounts** stand for counterparties; the institution
  does not own them. They appear as the *other side* of inbound /
  outbound flows, and the Investigation app's account-network sheet
  walks edges through them.

> An Account is a **physical, 1-of-1 thing**. For a 1-of-many shape
> (per-customer DDA, per-merchant settlement) you want an
> [Account template](account-template.md) instead.

## Specific example for you

{{ l2_account_focus() }}
