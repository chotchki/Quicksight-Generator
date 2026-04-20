<div class="snb-hero">
  <img class="snb-hero__wordmark" src="../../img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>Payment Reconciliation Handbook</h2>
  <p class="snb-hero__tagline">Merchant deposits traced end-to-end for the Payment Recon / Merchant Support team.</p>
</div>

This handbook backs the **Payment Reconciliation** dashboard — the
merchant-acquiring view of Sasquatch National Bank. Each entry
here is framed around the question an operator has when a merchant
calls, and walks them from the symptom on the dashboard to the
call-back answer for the merchant.

## The bank (merchant-acquiring side)

Sasquatch National Bank (SNB) runs a small merchant-acquiring
portfolio out of Seattle. The Merchant Support team owns
reconciliation across:

- **6 merchants** — two franchises (Bigfoot Brews, Sasquatch Sips),
  three independents (Yeti Espresso, Skookum Coffee Co., Wildman's
  Roastery), and one cart (Cryptid Coffee Cart).
- **3 external clearing systems** — BankSync, PaymentHub, and
  ClearSettle — each reports aggregated external transactions
  back to SNB for reconciliation.
- **Per-merchant settlement cadences** — franchises settle **daily**,
  independents **weekly**, the cart **monthly**. A merchant's
  cadence determines what "yesterday" means for them.

Full bank narrative (merchant roster, customer flows, the pipeline
stages): see [Account Structure](../Training_Story.md).

## The pipeline

Money flows left-to-right through four stages, and the dashboard's
pipeline tabs mirror that order:

1. **Sales** — the merchant's POS feed delivers individual sales
   (and refunds) throughout the day.
2. **Settlements** — on the merchant's cadence, a batch groups
   sales into one settlement record for remittance.
3. **Payments** — SNB emits one payment per settlement to the
   merchant's destination bank account.
4. **Payment Reconciliation** — external clearing systems
   (BankSync / PaymentHub / ClearSettle) aggregate payments into
   external transactions that SNB reconciles back to its own
   payment records.

A healthy pipeline: every sale lands in a settlement, every
settlement produces a payment, every payment reconciles to an
external transaction. When the phone rings, something in that
chain has stalled — and the operator's job is to figure out
*where*.

## The operator's posture

Unlike the AR team's morning rollup scan, Merchant Support is
**reactive**. The walkthroughs below are organized around the
question a support agent holds in their head when they pick up
the phone:

- *Where is this merchant's money?*
- *Did everyone get paid yesterday?*
- *Why doesn't this external row match anything we sent?*
- *Why is this settlement short?*

The Exceptions sheet offers the scan-for-anything-broken view
(morning rollup KPIs + aging bars per check), but most of the
traffic comes in through a phone call about one merchant. So the
walkthroughs below are split into **merchant questions** (how to
answer a call) and **exception investigations** (how to drill one
specific check's rows).

## Common merchant questions

<p class="snb-section-label">Pipeline traversal + match investigation</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/pr/wheres-my-money-for-merchant/">
    <h3>Where's My Money for [Merchant]?</h3>
    <p>Walk one merchant's money through Sales → Settlements → Payments → Payment Reconciliation to find which stage stalled.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/pr/did-all-merchants-get-paid/">
    <h3>Did All Merchants Get Paid Yesterday?</h3>
    <p>Morning-scan pattern — confirm every merchant whose batch was due has a payment in flight, and nothing's stuck overnight.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/pr/why-is-this-external-transaction-unmatched/">
    <h3>Why Is This External Transaction Unmatched?</h3>
    <p>Use the Payment Reconciliation tab's side-by-side mutual filter to see which payments compose an external row — or why nothing does.</p>
  </a>
</div>

## Investigating exceptions

<p class="snb-section-label">Per-check detail — when a specific KPI fires</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/pr/which-sales-never-made-it-to-settlement/">
    <h3>Which Sales Never Made It to Settlement?</h3>
    <p>Sales without a `settlement_id` — the batch missed them, or the merchant's schedule is broken.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/pr/why-does-this-settlement-look-short/">
    <h3>Why Does This Settlement Look Short?</h3>
    <p>The settlement record's dollar amount doesn't equal the SUM of its linked sales — late refund, POS correction, or manual override.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/pr/why-doesnt-this-payment-match-the-settlement/">
    <h3>Why Doesn't This Payment Match the Settlement?</h3>
    <p>The payment's dollar amount doesn't equal its parent settlement's amount — fee applied at payment time, manual edit, or precision drift.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/pr/how-much-did-we-return/">
    <h3>How Much Did We Return Last Week?</h3>
    <p>Returned payments by reason code — drives the weekly call-back list and catches merchants with repeat return reasons.</p>
  </a>
</div>

## Reference

- [Account Structure](../Training_Story.md) — the bank, customers,
  accounts, and money flows behind every walkthrough on this page.
- [Schema v3 — Data Feed Contract](../Schema_v3.md) — column specs,
  metadata keys, and ETL examples for the upstream feeds that populate
  the dashboards.
- [Data Integration Handbook](etl.md) — the team that populates the
  data behind every walkthrough on this page. Read it when a missing
  merchant, unmatched external txn, or broken settlement chain
  traces to the feed rather than the pipeline.
