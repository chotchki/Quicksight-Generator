# Open vs. closed loop

*Background concept — the system-boundary distinction that shapes
which reconciliation problems are even possible.*

{{ diagram("conceptual", name="open-vs-closed-loop") }}

## What it is

Money movement happens in two regimes:

- **Open-loop** — at least one leg touches an external counterparty
  (the Fed, a card processor, a partner bank). The institution sees
  its internal-side leg posted right away; the counterparty side
  clears asynchronously and confirms separately.
- **Closed-loop** — both legs are entirely inside the institution's
  own ledger. The institution has full visibility from the moment
  both legs post; no external authority has to confirm.

A given account can participate in both regimes — a customer DDA
sends payments out (open-loop) and accepts internal transfers from
other DDAs (closed-loop).

## The problem it solves

Separating open-loop and closed-loop activity lets the operator
reason about **system boundaries** clearly:

- Open-loop activity eventually touches external counterparties.
  Reconciliation has to match the institution's books against
  theirs, and the lag between internal-leg and external-confirm
  is a real source of in-flight risk.
- Closed-loop activity is entirely intra-system. Reconciliation
  is easier — no external authority — but drift can still happen
  if the two legs disagree internally.

The most interesting failures sit at the boundary: when value
crosses from closed-loop to open-loop, both sides have to move in
lockstep, or the two regimes disagree.

## How L1 surfaces this

The L2 instance declares each account's `scope` (`internal` or
`external`). L1 invariants apply differently to the two:

- **Drift** + **Expected EOD Balance** apply to internal accounts
  (the institution owns the books, so the books should add up).
- **Limit Breach** applies to outbound flow toward external
  counterparties (the outbound rail is what the cap is on).
- **Stuck Pending / Unbundled Aging** are most often triggered by
  open-loop transfers waiting on a counterparty confirmation
  that never came.

See [L1 Reconciliation Dashboard](../../handbook/l1.md) for the visual
surface and the `scope` attribute on each Account in the L2 YAML
for the boundary declaration.
