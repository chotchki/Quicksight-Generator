# Why don't the vouchers match the sales for this set of merchants?

*Seed scenario — PR dashboard. Customer service team.*

## The story

A group of merchants — usually connected (same region, same
merchant type, same payment cadence) — each get in touch to say
the pay-out they received doesn't match what they sold. It's
rarely a huge number; often it's \$5, \$10, a handful of dollars
per merchant. But it's consistent enough that the merchants are
comparing notes, and now you have a small coordinated complaint.

The question under the surface is: **at which stage of the pay-
out pipeline did the dollar amount change?** Three stages can
each introduce a mismatch:

1. **Sales → Settlement.** The settlement record's amount
   doesn't equal the SUM of its underlying sales (refund not
   captured, POS correction missed, manual override).
2. **Settlement → Payment.** The payment remits a different
   amount than the settlement says (fee applied at payment
   time, manual edit on the payment record, rounding drift).
3. **Payment → External system.** The external pay-out amount
   doesn't match the internal payment record.

Today, this is the kind of question that gets escalated to the
developers because it requires joining data across the pipeline
stages. With the PR dashboard, the Exceptions sheet already
isolates each mismatch shape and drills to the specific rows.

## The question

"For these merchants, why does the pay-out amount disagree with
what they sold? At which stage did the dollar amount shift?"

Note on vocabulary: in the SNB demo, the emitted-out-to-
merchant record is called a **payment** and the merchant's
destination is called an **external transaction**. If your
real-program workflow uses **voucher** for the pay-out
instruction and **external-originated ACH** for the landing
event, the mapping is direct — the pipeline shape is
identical, only the names differ. See
[vouchering](../concepts/vouchering.md) for the concept and
[translation-notes.md](../../translation-notes.md) for the
name mapping.

## Where to look

1. Open the PR dashboard, **Exceptions** sheet.
2. Set the merchant filter to the group in question (multi-
   select the merchant IDs).
3. Three mismatch KPIs sit on this sheet, top to bottom in
   pipeline order:
   - **Sale ↔ Settlement Mismatch** — settlement doesn't equal
     its sales.
   - **Settlement ↔ Payment Mismatch** — payment doesn't
     equal its settlement.
   - **Unmatched External Transactions** — external system
     has activity with no corresponding internal record.
4. Whichever KPI is non-zero for your merchant group is the
   stage that broke.

## What you'll see in the demo

Two mismatch shapes are planted:

- **Sale ↔ Settlement Mismatch** — planted with varying
  dollar deltas, spread across a handful of merchants.
- **Settlement ↔ Payment Mismatch** — exactly **3** rows,
  each with a **±\$5** difference. Deterministic but not
  hand-picked to a specific merchant (the next 3 settlements
  after the sale-settlement plants).

The detail tables both carry: `settlement_id` or `payment_id`,
`merchant_id`, the two amounts, the `difference`, and an
`aging_bucket`. Sort by `merchant_id` to cluster the affected
merchants.

For mechanical details:

- [Why does this settlement look short? (upstream)](../../../docs/walkthroughs/pr/why-does-this-settlement-look-short.md) —
  the Sale ↔ Settlement failure.
- [Why doesn't this payment match the settlement? (upstream)](../../../docs/walkthroughs/pr/why-doesnt-this-payment-match-the-settlement.md) —
  the Settlement ↔ Payment failure.

## What it means

When a group of merchants all report the same shape of mismatch:

- **Consistent \$5–\$10 per payment** (Settlement ↔ Payment)
  usually means a **fee / holdback applied at payment time** but
  not written back to the settlement record. The settlement
  looks right, the payment is short by the fee. If the merchants
  are on a common fee tier, every one of their payments will
  drift by that fee until the settlement-side write-back is
  fixed.
- **Variable dollar deltas per settlement** (Sale ↔ Settlement)
  usually means **late refund capture** — a refund was posted
  after the settlement batch ran, so the settlement amount still
  reflects gross sales. Pattern: the merchants affected are
  ones with refund activity that day.
- **Difference = exactly the transaction-fee total** (either
  check) means a **fee was billed but the underlying record
  wasn't netted**. Check the merchant fee schedule.
- **Difference is a round number** (\$10, \$25, \$100) usually
  means a **manual edit / override** on the payment or
  settlement. Check the audit log for the specific record.

## Drilling in

From the Sale ↔ Settlement Mismatch table: click `settlement_id`
to drill to the Settlements tab filtered to that settlement, then
click `settlement_id` again there to drill to the Sales tab. You
can now see the underlying sales for that settlement and compare
the SUM to the settlement amount.

From the Settlement ↔ Payment Mismatch table: click `payment_id`
to drill to Payments, then `settlement_id` to go back up to the
parent settlement. `payment_amount` on one side,
`settlement_amount` on the other — the `difference` column on
the Exceptions table already computes the gap.

## Next step

Call the merchant back with a specific dollar answer:

- "Your pay-out was short \$5 because [fee/reason], and we've
  flagged it." → routine reassurance when the difference is
  benign and expected.
- "Your settlement didn't reflect a refund we captured late —
  we'll adjust the next pay-out." → the refund-timing case.
- "We're investigating a discrepancy on this settlement and
  will follow up within [SLA]." → when the root cause isn't
  immediately obvious from the row.

Internally: Sale ↔ Settlement Mismatch rows go to whoever owns
the settlement batch; Settlement ↔ Payment Mismatch rows go to
payment operations; External mismatches go to whichever team
reconciles against the external payment system.

## Related scenarios & walkthroughs

- [Scenario 2 — What happened to this transaction's money?](02-what-happened-to-this-money.md) —
  complementary trace for a single-transaction question rather
  than a merchant-group pattern.
- [Where's my money for merchant? (upstream)](../../../docs/walkthroughs/pr/wheres-my-money-for-merchant.md) —
  when a single merchant calls about a missing pay-out (not a
  shortfall), that's the starting walkthrough.
- [Did all merchants get paid yesterday? (upstream)](../../../docs/walkthroughs/pr/did-all-merchants-get-paid.md) —
  the morning scan view; run it before the first call comes in.
- [Why is this external transaction unmatched? (upstream)](../../../docs/walkthroughs/pr/why-is-this-external-transaction-unmatched.md) —
  when the mismatch is at the external-system stage rather than
  internal pipeline stages.
- Background: [Vouchering](../concepts/vouchering.md), [Eventual consistency](../concepts/eventual-consistency.md).
