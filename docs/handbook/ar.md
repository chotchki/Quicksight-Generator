<div class="snb-hero">
  <img class="snb-hero__wordmark" src="../../img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>GL Reconciliation Handbook</h2>
  <p class="snb-hero__tagline">Morning checks and triage walkthroughs for the Treasury / GL Recon team.</p>
</div>

This handbook backs the **Account Reconciliation** dashboard — the
treasury / GL view of Sasquatch National Bank. Each entry here teaches
one *class* of reconciliation error so analysts learn to recognize the
shape, not memorize an account list.

## The bank

Sasquatch National Bank (SNB) is a Pacific-Northwest community bank.
After absorbing Farmers Exchange Bank's commercial book, the GL Recon
team owns reconciliation across:

- **8 internal GL control accounts** — Cash & Due From FRB, ACH
  Origination Settlement (`gl-1810`), Card Acquiring Settlement, Wire
  Settlement Suspense, Internal Transfer Suspense (`gl-1830`), Cash
  Concentration Master (`gl-1850`), Internal Suspense / Reconciliation,
  and Customer Deposits — DDA Control.
- **7 customer DDAs** — three coffee retailers (Bigfoot Brews, Sasquatch
  Sips, Yeti Espresso) plus four commercial customers (Cascade Timber
  Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery).
- **External counterparties** SNB transacts with — most notably the
  Federal Reserve Bank, which holds SNB's master account.

Full bank narrative (account topology, customer flows, the four
telling-transfer cycles): see [Account Structure](../Training_Story.md).

## The morning routine

Open the AR dashboard and switch to the **Exceptions** sheet. Three
rollups sit at the top of the page in order — Balance Drift Timelines,
Two-Sided Post Mismatch, Expected-Zero EOD. Read them first; they
answer "did *anything* break overnight?" Each rollup is a different
*shape* of break, so a clean morning means all three KPIs are zero or
all three timelines are flat.

If a rollup fires, scroll down to the per-check sections that own the
rows. Each per-check has its own KPI / detail table / aging bar
chart, and each is a walkthrough below.

## Morning checks — the three rollups

<p class="snb-section-label">Read these first, every morning</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/ar/balance-drift-timelines-rollup/">
    <h3>Balance Drift Timelines</h3>
    <p>Across the last several weeks, did any day's reconciliation invariant drift away from zero — and which one?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/two-sided-post-mismatch-rollup/">
    <h3>Two-Sided Post Mismatch</h3>
    <p>Are there any expected SNB/Fed post pairs where one side landed but the other didn't?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/expected-zero-eod-rollup/">
    <h3>Expected-Zero EOD</h3>
    <p>Of the accounts that should have ended yesterday at zero, are any carrying a balance?</p>
  </a>
</div>

## When this fires, what to do — per-check walkthroughs

<p class="snb-section-label">Baseline checks — invariants on every account / transfer</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/ar/sub-ledger-drift/">
    <h3>Sub-Ledger Drift</h3>
    <p>Are any sub-ledger accounts carrying a stored balance that doesn't match their posting history?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/ledger-drift/">
    <h3>Ledger Drift</h3>
    <p>Are any GL control accounts carrying a stored balance that doesn't match the sum of their sub-ledgers (plus direct postings)?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/non-zero-transfers/">
    <h3>Non-Zero Transfers</h3>
    <p>Are there any transfers where the non-failed legs don't add up to zero?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/sub-ledger-limit-breach/">
    <h3>Sub-Ledger Limit Breach</h3>
    <p>Did any customer DDA push more than its allowed daily total out yesterday — by ACH, wire, or cash?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/sub-ledger-overdraft/">
    <h3>Sub-Ledger Overdraft</h3>
    <p>Did any sub-ledger account end the day with a negative stored balance — and for how long?</p>
  </a>
</div>

<p class="snb-section-label">CMS-specific checks — the four telling-transfer cycles</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/ar/sweep-target-non-zero/">
    <h3>Sweep Target Non-Zero EOD</h3>
    <p>Did any operating sub-account under Cash Concentration Master end the day with a non-zero balance — and for how long?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/concentration-master-sweep-drift/">
    <h3>Concentration Master Sweep Drift</h3>
    <p>On the days a CMS sweep posted, did the master credits and operating sub-account debits actually balance?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/ach-origination-non-zero/">
    <h3>ACH Origination Non-Zero EOD</h3>
    <p>Did the ACH Origination Settlement ledger end yesterday at zero — i.e., did the EOD sweep to FRB actually fire?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/ach-sweep-no-fed-confirmation/">
    <h3>ACH Sweep Without Fed Confirmation</h3>
    <p>For every internal EOD sweep that posted on gl-1810, did the Fed-side confirmation actually land?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/fed-card-no-internal-catchup/">
    <h3>Fed Activity Without Internal Post</h3>
    <p>For every Fed-observed card settlement, did SNB's internal catch-up entry actually post?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/gl-vs-fed-master-drift/">
    <h3>GL vs Fed Master Drift</h3>
    <p>Across days the Fed observed card settlement activity, do SNB's internal posts net to the same total — how persistent and how large is the drift?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/stuck-in-internal-transfer-suspense/">
    <h3>Stuck in Internal Transfer Suspense</h3>
    <p>Are there any on-us transfers where Step 1 posted but Step 2 never did?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/internal-transfer-suspense-non-zero/">
    <h3>Internal Transfer Suspense Non-Zero EOD</h3>
    <p>Did the Internal Transfer Suspense ledger end yesterday at zero — i.e., did every Step 1 have a Step 2 clearing it?</p>
  </a>
  <a class="snb-card" href="../walkthroughs/ar/internal-reversal-uncredited/">
    <h3>Reversed Transfers Without Credit-Back</h3>
    <p>For every reversed on-us transfer, did the originator's credit-back leg actually post — or did the suspense clear without refunding the customer?</p>
  </a>
</div>

## Reference

- [Account Structure](../Training_Story.md) — the bank, customers,
  accounts, and money flows behind every walkthrough on this page.
- [Schema v3 — Data Feed Contract](../Schema_v3.md) — column specs,
  metadata keys, and ETL examples for the upstream feeds that populate
  the dashboards.
- [Data Integration Handbook](etl.md) — the team that populates the
  data behind every walkthrough on this page. Read it when a drift
  or missing-row exception traces to the feed rather than the ledger.
