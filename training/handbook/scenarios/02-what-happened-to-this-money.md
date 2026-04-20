# What happened to this transaction's money?

*Seed scenario — AR dashboard. Accounting team (also relevant to
customer service when a merchant call ties back to a specific
transaction).*

## The story

Someone — a customer, a merchant, an auditor — points at a
specific transaction and asks where the money is. They already
know the transfer was initiated (their account was debited or
they have a reference number). They're asking because it didn't
arrive at the other end, or didn't arrive in the shape they
expected.

Today this is a developer ticket: pull the postings for this
transfer, walk the chain, find where it stopped. With the AR
dashboard, the same trace is three clicks — and the exception
sheet has already pre-sorted the "stuck" and "partially-reversed"
transfers for you, so you often find the answer before you even
start typing into a filter.

Three outcomes the trace can end in:

1. **Still in flight, normal.** The transfer is a few days old
   and hasn't cleared yet, but it's within the expected window
   for its type. No action.
2. **Stuck in escrow / suspense.** Step 1 posted (money left the
   originator), Step 2 never did. The money is sitting in a
   holding account. Needs operator intervention.
3. **Reversed, but credit-back never posted.** Step 2 fired as
   a reversal, the holding account cleared, but the credit back
   to the originator never landed. The customer is missing
   money.

Outcomes 2 and 3 are the bad ones. This scenario teaches you to
distinguish them quickly.

## The question

"What happened to the money for transfer X? Is it in flight,
stuck, or lost?"

## Where to look

1. On the AR dashboard, go to **Transfers**. Filter by
   `transfer_id` if you have it, or by originator + date if you
   don't. Each transfer is one row here with a **net-zero flag**
   column.
2. If the row is present and `net_zero = TRUE`, the transfer
   completed cleanly. You're done — the money moved as expected,
   and the question is whether the recipient sees it on their
   end (usually a timing issue at the recipient's bank).
3. If `net_zero = FALSE`, the transfer didn't balance. Jump to
   **Exceptions** and look at three checks:
   - **Non-Zero Transfers** — the aggregate invariant. Every
     transfer whose successful legs don't sum to zero.
   - **Stuck in Internal Transfer Suspense** — Step 1 landed,
     Step 2 never did.
   - **Reversed Transfers Without Credit-Back** — Step 2
     fired as a reversal but the credit to the originator
     didn't land.

## What you'll see in the demo

Two distinct planted outcomes in the demo:

**Stuck-in-suspense**: the KPI shows 2 stuck transfers, \$6,155
total, originated Mar 27 and Apr 8 2026. One row is Cascade
Timber Mill → Big Meadow Dairy; the other is Pinecrest
Vineyards LLC → Harvest Moon Bakery. Both are in aging bucket 4
(8-30 days) — well past the 1-3 day "normal in-flight" window.

**Reversed-but-not-credited**: a separate planted flow with its
own KPI and detail table. Smaller dollar amounts, different
originators.

For the mechanical details:

- [Stuck in Internal Transfer Suspense (upstream)](../../../docs/walkthroughs/ar/stuck-in-internal-transfer-suspense.md)
- [Reversed Transfers Without Credit-Back (upstream)](../../../docs/walkthroughs/ar/internal-reversal-uncredited.md)

## What it means

Use this triage tree:

- **Transfer appears in Non-Zero Transfers but nowhere else.**
  The legs disagree on amount — someone posted one side wrong.
  Compare signed amounts; the gap is your mis-posting.
- **Transfer appears in Stuck in Internal Transfer Suspense.**
  Step 1 fired, Step 2 didn't. The money is in the suspense /
  escrow account. The originator is short, the recipient is
  waiting. Escalate quickly; the aging bucket tells you how
  urgent.
- **Transfer appears in Reversed Transfers Without Credit-Back.**
  The suspense account cleared — in the wrong direction. The
  money went back out of suspense as a reversal, but the
  credit-back to the originator never landed. The originator
  is missing their money *and* the suspense looks clean, which
  is the most dangerous shape because the aggregate invariants
  don't catch it.
- **Transfer is older than a few days and appears nowhere on
  Exceptions.** It completed normally; the money moved. If the
  recipient still doesn't see it, the problem is on their end.

## Drilling in

From any of the three exception-check detail tables, click the
`transfer_id` (sometimes labeled `originate_transfer_id`). The
drill switches to the **Transactions** sheet filtered to that
transfer. You'll see:

- For a stuck transfer: only Step 1 postings (the debit to
  suspense, the credit out of the originator's account). No
  Step 2.
- For a reversed-but-not-credited transfer: Step 1 plus the
  suspense-side reversal, but no corresponding credit to the
  originator's account.
- For a non-zero-amount mismatch: both sides of the transfer,
  but the signed amounts don't net to zero. The gap is visible
  in the table.

## Next step

- **Stuck in suspense** → Internal Transfer Operations. Hand
  off the `transfer_id`, the originator name, and the amount.
  They have to either fire Step 2 manually or post the
  reversal.
- **Reversed without credit-back** → Customer Operations. A
  customer is missing money that shows as successfully returned
  from suspense. They need a compensating posting.
- **Non-zero transfer (mis-posted)** → whichever team owns the
  feed that fed the bad leg. Usually a feed / ETL bug.
- **Still in flight** → no action. Tell the asker the expected
  clear date for that transfer type.

After 30 days, stuck transfers cross a regulatory threshold and
escalate to legal / compliance regardless of root cause. Bucket
5 rows on either check are never "just wait."

## Related scenarios & walkthroughs

- [Scenario 1 — Where did these few dollars in the pool come from?](01-dollars-in-the-pool.md) —
  the complementary trace for balances rather than transfers.
- [Scenario 3 — Why don't the vouchers match the sales for this set of merchants?](03-vouchers-dont-match-sales.md) —
  merchant-side pay-out mismatch; shares the "one stage of the
  chain broke" diagnostic shape.
- [Non-Zero Transfers (upstream)](../../../docs/walkthroughs/ar/non-zero-transfers.md)
- [Internal Transfer Suspense Non-Zero EOD (upstream)](../../../docs/walkthroughs/ar/internal-transfer-suspense-non-zero.md) —
  the account-level view: the same money seen as "suspense
  holding \$X overnight" rather than "this specific transfer is
  stuck."
- Background: [Escrow with reversal](../concepts/escrow-with-reversal.md), [Eventual consistency](../concepts/eventual-consistency.md).
