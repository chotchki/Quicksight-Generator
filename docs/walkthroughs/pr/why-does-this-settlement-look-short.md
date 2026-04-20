# Why does this settlement look short?

*Operator-question walkthrough — Payment Reconciliation Exceptions sheet.*

## The story

A merchant calls Support: *"My settlement total for last week
doesn't match what my POS reported. I'm short ten bucks."*

The Payment Reconciliation pipeline aggregates the merchant's
sales into a settlement record — one settlement bundles N sales,
and the recorded `settlement_amount` is supposed to equal the SUM
of those linked sales. When that invariant breaks, the **Sale ↔
Settlement Mismatch** check fires. It's a pure data-integrity
guard: somewhere between the POS feed and the settlement record,
a dollar amount drifted.

The shape is small ($10 in the demo, often single-dollar in real
life) but it's exactly the kind of variance a careful merchant
notices and calls about — so even though it's a small dollar
exposure, every row deserves an answer.

## The question

"For this settlement, does the recorded settlement amount equal
the SUM of its linked sales? If not, where did the difference
come from?"

## Where to look

Open the Payment Reconciliation dashboard, **Exceptions** sheet.
The **Sale ↔ Settlement Mismatch** section sits in the per-check
area, with its KPI count, detail table, and aging bar chart.

## What you'll see in the demo

The KPI shows **3** sale↔settlement mismatches.

<details markdown><summary>Screenshot — KPI</summary>

![Sale ↔ Settlement Mismatch KPI showing the count 3](../screenshots/pr/why-does-this-settlement-look-short-01-kpi.png)

</details>

Three planted mismatches in `_inject_mismatches` — each one bumps
a real settlement's `settlement_amount` by ±$10 (with the linked
payment kept in sync, so the *payment* side reconciles fine; only
the sales-vs-settlement side breaks).

The detail table carries: `settlement_id`, `merchant_id`,
`settlement_amount`, `sales_sum`, `difference` (= settlement −
sales_sum, so ±$10 in the demo), `sale_count`, `settlement_date`,
`days_outstanding`, `aging_bucket`.

<details markdown><summary>Screenshot — detail table</summary>

![Sale ↔ Settlement Mismatch table showing 3 rows with ±10 differences](../screenshots/pr/why-does-this-settlement-look-short-02-table.png)

</details>

Because the mismatches are planted on random settlements (the
shuffle pulls 3 from the pool of paid settlements), the merchant
distribution and the aging buckets vary run-to-run, but the
**count is always 3** and the **difference is always exactly
±$10**.

The aging bar chart shows the distribution by bucket — typically
1–2 rows in bucket 4 (`8-30 days`), 1–2 in bucket 5 (`>30
days`), depending on which settlements got picked.

<details markdown><summary>Screenshot — aging chart</summary>

![Sale ↔ Settlement Mismatch by Age aging bar chart](../screenshots/pr/why-does-this-settlement-look-short-03-aging.png)

</details>

## What it means

Each row says: this settlement bundled `sale_count` sales whose
amounts SUM to `sales_sum`, but the stored `settlement_amount` is
different by `difference` dollars. The settlement record either
recorded the wrong total or one of its linked sales got a
correction after the settlement was written.

Three patterns this typically arises from in production:

- **Late refund linked back.** A refund was posted with the same
  settlement_id as an earlier sale batch but after the
  `settlement_amount` was already locked. The settlement record
  doesn't include the refund; the sales SUM does.
- **POS amount correction.** The POS feed re-issued a sale row
  with a corrected amount (typo fix, tax recalc) after the
  settlement was assembled. Sales table reflects the new amount;
  settlement_amount holds the old.
- **Manual override on settlement_amount.** Someone edited the
  settlement record directly to apply a fee, withholding, or
  manual reconciliation — without updating the underlying sale
  rows.

In the demo, all 3 are option C (manual override): the
`_inject_mismatches` helper bumps `settlement_amount` directly,
leaving the sales unchanged, to give the visual planted rows.

## Drilling in

Click `settlement_id` in any row. The drill switches to the
**Settlements** sheet filtered to that one settlement, where you
can see the recorded `settlement_amount`, `settlement_status`
(`completed` for these — they're not failed, just wrong-sized),
and the `payment_id` it generated.

To see the underlying sales, switch to the **Sales** sheet and
filter `settlement_id = <your settlement>`. Compare the SUM of
`amount` to what the Settlements row shows. The difference is
the `difference` column from the mismatch table.

For the demo plants, the SUM of sales is exactly `settlement_amount
± 10` — confirming the bump is a $10 perturbation on the
settlement side.

## Next step

Sale-settlement mismatch rows go to **Settlement Operations**:

- **Bucket 1-2 (0-3 days)** → check whether a late refund or POS
  correction landed within the bucket window. If yes, regenerate
  the settlement total. Most rows resolve here.
- **Bucket 3-4 (4-30 days)** → walk the settlement's audit log
  for a manual override. If found, confirm whether the override
  is justified (a real fee or withholding) or a data error to
  reverse.
- **Bucket 5 (>30 days)** → escalate. A month-old mismatch is
  almost certainly a manual override that wasn't documented;
  the merchant has likely already noticed and may be calling.

Customer-facing: when the merchant calls about a short
settlement, the Sale ↔ Settlement Mismatch table tells you
whether their concern is real (row exists) or whether their
arithmetic is off (no row). For real rows, the
`difference` column is the dollar amount you can reference in
the call: *"You're right — your settlement is $10 short of the
sales total. Investigating now."*

## Related walkthroughs

- [Why doesn't this payment match the settlement?](why-doesnt-this-payment-match-the-settlement.md) —
  the **next stage** of the same chain. There: the settlement
  total is right, but the payment that posted from it is the
  wrong amount. Together the two checks cover both halves of
  "the dollars don't agree across the pipeline."
- [Did all merchants get paid yesterday?](did-all-merchants-get-paid.md) —
  the morning-scan view. The Sale ↔ Settlement Mismatch KPI on
  the Exceptions tab is the same row count this walkthrough
  drills into.
- [Where's my money for [merchant]?](wheres-my-money-for-merchant.md) —
  the merchant-first deep-dive. If a merchant calls about a
  short settlement, this walkthrough is the structured trace.
- [How much did we return last week?](how-much-did-we-return.md) —
  late refunds are one cause of sale-settlement drift. If the
  merchant's mismatch lines up with a late refund row, the
  refund is the explanation.
- [Which sales never made it to settlement?](which-sales-never-made-it-to-settlement.md) —
  the inverse case: the settlement *didn't* fire at all. Together
  this check + that one cover both directions of "the settlement
  and the sales don't agree."
