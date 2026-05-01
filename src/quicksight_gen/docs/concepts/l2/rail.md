# Rail

A **rail** is the smallest indivisible money-movement primitive — one
"thing the institution does that posts to the ledger". Two shapes:

- **TwoLegRail** — posts a debit + a credit pair atomically.
  Declares ``source_role`` and ``destination_role``; every firing
  produces two Transaction rows that net to zero per the
  Conservation invariant.
- **SingleLegRail** — posts a single leg. The other side comes
  from elsewhere — either bundled into a multi-leg
  [Transfer Template](transfer-template.md), aggregated into a
  parent firing of an ``aggregating`` rail, or
  ``ExternalForcePosted`` (the institution's view doesn't include
  the offsetting side at all, like a Fed-side credit on an inbound
  wire).

Every Rail has:

- ``transfer_type`` — the discriminator that ties posted Transactions
  to this Rail (e.g. ``ach``, ``wire``, ``cash``, ``settlement``).
- ``posted_requirements`` — optional list of metadata keys that MUST
  be populated on the Transaction (``card_brand``, ``cashier``, etc).
  L1 surfaces violations as posted-requirements drift.
- ``max_pending_age`` / ``max_unbundled_age`` — optional aging caps
  the Stuck Pending / Stuck Unbundled matviews use to surface legs
  that took too long to post or to bundle.
- ``aggregating`` — flag marking a rail as a bundler (an aggregating
  ``settlement`` rail, for example, picks up many ``sale`` leg firings
  and emits one net-settled credit / debit pair).

> The Rail-to-Transaction binding is implicit: a posted Transaction's
> ``(transfer_type, role)`` tuple identifies which Rail it came from.
> A pending P.9b task tightens this with a load-time uniqueness rule
> so two rails sharing a discriminator can't ambiguously claim the
> same Transaction.

## Specific example for you

{{ l2_rail_focus() }}
