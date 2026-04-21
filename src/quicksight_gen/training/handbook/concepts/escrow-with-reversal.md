# Escrow with reversal

*Background concept — holding accounts that must net to zero, even when a transfer fails.*

## What it is

An **escrow** (or "suspense") account is a temporary holding spot
for an in-flight transfer. A multi-step transfer moves money *into*
escrow from the originator, then *out* of escrow to the recipient.
If the recipient-side leg fails — bad account, compliance hold,
NSF — the transfer **reverses**: the money moves back from escrow
to the originator.

A complete transfer cycle has three possible shapes:

- **Success**: originator → escrow → recipient. Escrow nets to zero.
- **Failure + reversal**: originator → escrow → back to originator. Escrow nets to zero.
- **Stuck**: originator → escrow, then nothing. Escrow is non-zero and the money is in limbo.

The healthy state: escrow account balance = zero every EOD.

## The problem it solves

Escrow lets a transfer be posted atomically from the originator's
perspective ("my money is gone") while the recipient side clears
asynchronously. This is essential when the recipient-side leg
involves external validation (compliance, account-status check,
funds availability).

The failure mode to watch for: the recipient leg fails silently,
or the reversal doesn't post. The originator's money is "in
escrow" indefinitely, but no one tells them, and the escrow
account slowly accumulates stuck balances.

Two independent checks catch the two failure shapes:

1. **Stuck-in-escrow**: a transfer entered escrow but neither
   settled nor reversed.
2. **Reversed-but-not-credited**: a transfer reversed out of
   escrow, but the credit-back to the originator never landed.
   The escrow cleared but the customer is missing money.

## In the SNB demo

The SNB demo models this with **Internal Transfer Suspense**
(`gl-1830`) — SNB's on-us customer-to-customer transfer account.

- **Success cycle**: customer A's DDA → `gl-1830` → customer B's
  DDA.
- **Failure cycle**: customer A's DDA → `gl-1830` → back to
  customer A's DDA.
- **Stuck**: step 1 posts, step 2 never does. Detected by the
  **Stuck in Internal Transfer Suspense** check.
- **Reversed-but-not-credited**: step 1 + a reversal out of
  `gl-1830`, but no credit back to customer A. Detected by the
  **Reversed Transfers Without Credit-Back** check.

The third check — **Internal Transfer Suspense Non-Zero EOD** —
is the aggregate invariant: the suspense account should be zero
every EOD. If it isn't, the other two checks tell you which
shape of break caused it.

Further reading:

- [Stuck in Internal Transfer Suspense](../../../docs/walkthroughs/ar/stuck-in-internal-transfer-suspense.md)
- [Reversed Transfers Without Credit-Back](../../../docs/walkthroughs/ar/internal-reversal-uncredited.md)
- [Internal Transfer Suspense Non-Zero EOD](../../../docs/walkthroughs/ar/internal-transfer-suspense-non-zero.md)
