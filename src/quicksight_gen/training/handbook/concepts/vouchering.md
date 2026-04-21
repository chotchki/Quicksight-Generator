# Vouchering

*Background concept — pay-out instructions delivered via an external payment system.*

## What it is

**Vouchering** is a payment mechanism where the paying institution
doesn't originate an ACH itself; instead, it **sends a pay-out
instruction** (a "voucher") to an external payment system. That
external system then originates an ACH that pulls (or pushes) the
money from the paying institution's pool account.

The shape, left-to-right:

1. Merchant sale / settlement completes on the paying
   institution's books.
2. Institution generates a voucher — a structured pay-out
   instruction — and hands it to the external payment system.
3. The external system originates an ACH against the institution's
   pool account, sometime later (same day, next day, or further
   out depending on the system's schedule).
4. The institution observes the ACH landing against its pool
   account and reconciles it back to the originating voucher.

## The problem it solves

Some operators — particularly in government contexts — don't
originate outbound ACH directly. Either they're not an ACH
originator at all, or they're required to route large classes of
disbursement through a central government payment rail for
audit / compliance reasons. Vouchering lets the institution
initiate the economic intent (merchant X is owed \$Y) while the
external system owns the actual rail origination.

The reconciliation challenge: **the voucher and the resulting
external ACH are separated by time and by system**. A sale
settles today; the voucher fires today; the external ACH might
not hit the pool account until tomorrow or the day after. Until
the ACH lands, the voucher is "in flight" — the merchant is owed
money that the institution can see promised, but the pool account
doesn't show a matching debit yet.

When the voucher amount and the external ACH disagree, or when a
voucher fires but no ACH ever arrives, the operator needs to
trace both sides.

## In the SNB demo

The SNB demo doesn't model vouchering directly — SNB originates
its own outbound ACH for merchant payments. The closest
analogues to practice on:

- **Settlements → Payments pipeline** (PR dashboard): a
  settlement on day *T* produces a payment that hits the
  merchant's destination bank on day *T+1* to *T+5*. The "payment
  is in flight" window is the voucher analogue.
- **Sale-to-settlement mismatch** and **settlement-to-payment
  mismatch** exception checks catch the dollar-amount disagreement
  between adjacent pipeline stages — the same shape of error as
  voucher-vs-ACH disagreement.
- **Unmatched external transactions** check catches ACHs landing
  at the pool account with no corresponding internal payment /
  voucher — the "ACH arrived without a matching instruction"
  failure.

Further reading:

- [Why doesn't this payment match the settlement?](../../../docs/walkthroughs/pr/why-doesnt-this-payment-match-the-settlement.md)
- [Why is this external transaction unmatched?](../../../docs/walkthroughs/pr/why-is-this-external-transaction-unmatched.md)
