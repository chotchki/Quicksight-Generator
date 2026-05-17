# Transfer template

A **transfer template** chains multiple [Rail](rail.md) firings into one
business-meaningful Transfer. The classic example: an
"ACH origination cycle" template fires three legs — debit the
customer DDA, credit the suspense holding GL, then debit suspense and
credit the Federal Reserve master account — and the template
guarantees those three legs happen together, with a deterministic
``expected_net`` close-out.

A template has:

- ``name`` — unique identifier referenced from
  ``Transaction.template_name`` so any leg of a templated bundle
  can be traced back to its parent template.
- ``leg_rails`` — ordered list of Rail names declaring which rails
  fire as part of the template. Each leg of a firing posts via the
  named Rail.
- ``expected_net`` — the **L1 Conservation invariant** for this
  template: the sum of every non-Failed leg's signed ``amount_money``
  MUST equal this value. Most templates use ``0`` (debit + credit
  pair nets to zero); a few use a non-zero value when an external
  system contributes the offsetting side (e.g. an ``ExternalForcePosted``
  leg lands a credit the institution's books don't include).

Templates are how the L1 dashboard knows a multi-leg cycle is "open"
— a leg has fired but the close-out leg hasn't yet, so the running
sum doesn't equal ``expected_net``. Stuck templates surface in the
Pending Aging + Unbundled Aging matviews depending on which leg's
late.

> Don't reach for a Transfer Template just because two rails *can*
> fire together. Use it when the rails MUST fire together as one
> business event — the template's ``expected_net`` is the binding
> close-out invariant. If two rails are independent, model them as
> two rails with a [chain](chain.md) edge instead.

## Specific example for you

{{ l2_transfer_template_focus() }}
