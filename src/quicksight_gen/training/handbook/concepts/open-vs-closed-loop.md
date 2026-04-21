# Open vs. closed loop

*Background concept — the two worlds of value on a prepaid / stored-value card.*

## What it is

A prepaid card can carry two kinds of balance:

- **Open-loop** — spendable at any merchant on the card network
  (Visa, Mastercard, etc.). Moves through external rails; settles
  through the card processor and eventually through the banking
  system.
- **Closed-loop** — spendable only inside a specific operator's
  system (on-location terminals, in-network merchants). Moves
  entirely on the operator's own books; never touches the external
  network.

A cardholder typically has both balances on the same card, and
value can sometimes move between the two.

## The problem it solves

Separating open-loop and closed-loop activity lets the operator
reason about **system boundaries** clearly:

- Open-loop activity eventually touches external counterparties
  (processors, partner banks, the Fed). Reconciliation has to
  match our books against theirs.
- Closed-loop activity is entirely intra-system. Reconciliation
  is easier — no external authority — but drift can still happen
  if the card-side postings and the merchant-side postings don't
  agree.

The most interesting failures sit at the boundary: when value
crosses from closed-loop to open-loop, both funds pools have to
move in lockstep, or the two worlds disagree.

## In the SNB demo

The SNB demo doesn't model closed-loop cards directly — SNB
merchants' and commercial customers' DDAs are all closest to the
open-loop side (money moves externally via ACH / card networks /
wires). The analogues you can practice on:

- **External-facing postings** (card acquiring, ACH, wire) →
  open-loop analogue. Reconcile SNB's books against the Fed and
  the processor.
- **Intra-bank postings** (internal transfers, ZBA sweeps) →
  closed-loop analogue. Both legs are in SNB's own ledger; no
  external authority to check against.
- **The boundary crossings** — external force-posts and ACH sweeps
  — are the demo's most important teaching cases. The **Fed
  Activity Without Internal Post** and **GL vs. Fed Master Drift**
  checks cover these.

Further reading: [GL Reconciliation Handbook → Fed Activity Without Internal Post](../../../docs/walkthroughs/ar/fed-card-no-internal-catchup.md).
