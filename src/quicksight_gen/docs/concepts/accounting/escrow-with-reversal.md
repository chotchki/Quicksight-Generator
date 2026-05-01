# Escrow with reversal

*Background concept — holding accounts that must net to zero, even
when a transfer fails.*

{{ diagram("conceptual", name="escrow-with-reversal") }}

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

## How L1 surfaces this

Two L1 invariants catch the two failure shapes:

- **Stuck Pending** (rail-level `max_pending_age` watch) — a transfer
  entered escrow but neither settled nor reversed in time.
- **Stuck Unbundled** (rail-level `max_unbundled_age` watch) — a
  Posted leg sits without its parent transfer's other legs landing.

Plus the universal **Drift** + **Expected EOD Balance** checks: any
escrow / suspense account with `expected_eod_balance: 0` declared in
the L2 instance will surface as a violation when EOD ≠ 0.

See [L1 Reconciliation Dashboard](../../handbook/l1.md) for the visual
surface.
