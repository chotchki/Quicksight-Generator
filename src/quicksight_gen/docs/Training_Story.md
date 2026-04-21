# Training Scenario Account Structure

This document describes the fictional bank, customers, accounts, and money
flows that the training scenarios use. The point is to teach users to
recognize a *class* of reconciliation error using the AR app — the
specific names and topology are illustrative.

## Business Structure

Sasquatch National Bank (SNB) — a community bank serving the Pacific
Northwest.

```
Sasquatch National Bank (SNB)
 │
 ├── Merchant Customers (coffee retail)
 │    ├── Bigfoot Brews
 │    ├── Sasquatch Sips
 │    └── Yeti Espresso
 │
 └── Commercial Customers (agricultural / industrial — several acquired through FEB)
      ├── Cascade Timber Mill
      ├── Pinecrest Vineyards LLC
      ├── Big Meadow Dairy
      └── Harvest Moon Bakery

External Counterparties (not customers — SNB transacts with them but
doesn't hold their accounts)
 ├── Federal Reserve Bank — holds SNB's Master Account (cash position authority)
 ├── Payment Gateway Processor — card acquirer for SNB merchants
 ├── Coffee Shop Supply Co — receives ACH / RTP from SNB merchants
 ├── Valley Grain Co-op — agricultural settlement counterparty
 └── Harvest Credit Exchange — credit-clearing counterparty
```

## Account Structure

External authority — what SNB reconciles its books to:

```
Federal Reserve — SNB Master Account (Master Acct 21000123)
```

SNB General Ledger — ABA 999999999:

```
Asset accounts:
 ├── 1010  Cash & Due From Federal Reserve
 ├── 1810  ACH Origination Settlement       (sweep)
 ├── 1815  Card Acquiring Settlement
 ├── 1820  Wire Settlement Suspense
 ├── 1830  Internal Transfer Suspense
 ├── 1850  Cash Concentration Master        (ZBA target)
 └── 1899  Internal Suspense / Reconciliation

Liability accounts:
 └── 2010  Customer Deposits — DDA Control
      ├── 900-0001  Bigfoot Brews            — DDA
      ├── 900-0002  Sasquatch Sips           — DDA
      ├── 900-0003  Yeti Espresso            — DDA
      ├── 800-0001  Cascade Timber Mill      — DDA
      ├── 800-0002  Pinecrest Vineyards LLC  — DDA
      ├── 700-0001  Big Meadow Dairy         — DDA
      └── 700-0002  Harvest Moon Bakery      — DDA
```

The reconciliation invariant the demo teaches:

> The sum of SNB's internal GL balances must equal what the Federal
> Reserve says is in SNB's Master Account. When they don't match,
> something is in transit, posted on one side only, or stuck.

## Cash Management Suite

SNB offers commercial customers a Cash Management Suite — Zero Balance
Accounts (ZBA), ACH origination, Card Acquiring, and On-Us Internal
Transfer Service. Each product generates a different pattern of internal
book activity that the AR app teaches users to monitor.

## Telling Transfers

Four representative flows, each tied to one Cash Management Suite
product. Each is a class of reconciliation issue the AR app surfaces.

### 1. ZBA / Cash Concentration sweep

Big Meadow Dairy maintains operating sub-accounts (one per location)
that sweep to the Cash Concentration Master at EOD.

```
Sweep cycle (one set of postings per operating sub-account, daily):
  DR  1850      Cash Concentration Master              $X
  CR  700-0001  Big Meadow Dairy — Operating sub-acct  $X

External: no Fed activity (sweep is intra-bank).
```

**Reconciliation question:** did every operating sub-account sweep to
zero? Did the Cash Concentration Master receive the expected total?

**Errors this surfaces:** failed sweep (operating ends day non-zero),
partial sweep, double-posted sweep.

### 2. Daily ACH origination sweep

Throughout the day, SNB customers initiate ACH payments → debits
accumulate in 1810 ACH Origination Settlement. EOD, the net balance is
wired to the FRB Master Account, clearing the sweep account to zero.

```
Intraday accumulation (many of these):
  DR  1810      ACH Origination Settlement   $250
  CR  900-XXXX  Customer DDA                 $250
  ...

EOD sweep (one transfer):
  DR  1010      Cash & Due From FRB          $18,400  ← total day's net
  CR  1810      ACH Origination Settlement   $18,400  ← sweeps to zero

Fed-side confirmation:
  CR  FRB Master — SNB                       $18,400
  (counterparty: ACH operator)
```

**Reconciliation question:** is ACH Origination Settlement at zero EOD?
Does the swept amount match the Fed posting?

**Errors this surfaces:** failed sweep (account ends day non-zero),
partial sweep, sweep posted internally but no Fed confirmation.

### 3. External force-posted card settlement

Payment Gateway Processor settles a day's card sales into Bigfoot
Brews's DDA. The Fed posts the settlement before SNB's internal system
catches up.

```
Fed-side (happens first, externally driven):
  DR  FRB Master — Processor's Bank   $4,200
  CR  FRB Master — SNB                $4,200

SNB BOOKS — must catch up via force-posted entry:
  DR  1815      Card Acquiring Settlement   $4,200    ← origin = external_force_posted
  CR  900-0001  Bigfoot Brews — DDA         $4,200
```

**Reconciliation question:** for every Fed credit / debit, is there a
matching internal posting?

**Errors this surfaces:** unposted external activity, mis-routed force
posts, GL-vs-Fed drift over time.

### 4. On-Us Internal Transfer with fail / reversal

Big Meadow Dairy initiates a transfer to Cascade Timber Mill (both SNB
customers). The transfer routes through 1830 Internal Transfer Suspense.
It can fail (NSF, compliance hold, recipient account closed) — failures
reverse to the originator. The suspense account should net to zero EOD.

```
Step 1 — originate (move into suspense):
  DR  1830      Internal Transfer Suspense    $3,500
  CR  700-0001  Big Meadow Dairy — DDA        $3,500

Step 2a — success (settle to recipient):
  DR  800-0001  Cascade Timber Mill — DDA     $3,500
  CR  1830      Internal Transfer Suspense    $3,500

Step 2b — failure (reverse to originator):
  DR  700-0001  Big Meadow Dairy — DDA        $3,500
  CR  1830      Internal Transfer Suspense    $3,500
```

**Reconciliation question:** is Internal Transfer Suspense at zero EOD?
Are all originated transfers either settled or reversed?

**Errors this surfaces:** stuck in suspense (no settle, no reversal —
money in flight too long), settled-but-not-debited, reversed-but-not-
credited (double spend).

## Mapping to AR exception checks

Each telling transfer maps to one or more AR exception checks. Every
check surfaces as rows in the unified *Open Exceptions* table on the
**Today's Exceptions** sheet (with `days_outstanding` and
`aging_bucket` columns); the **Exceptions Trends** sheet adds an aging
matrix + per-check daily counts across all checks, plus drift
timelines for the drift checks.

| Telling transfer | New / existing AR exception check |
|---|---|
| ZBA / Cash Concentration sweep | **Sweep target non-zero EOD**; **Concentration master vs sum of sub-account sweeps** |
| Daily ACH origination sweep | **ACH Origination Settlement non-zero EOD**; **Internal sweep posted but no Fed confirmation** |
| External force-posted card settlement | **Fed activity with no matching internal post**; **GL-vs-Fed Master drift** |
| On-Us Internal Transfer with fail / reversal | **Stuck in Internal Transfer Suspense**; **Suspense non-zero EOD**; **Reversed-but-not-credited (double spend)** |

## Scenario Story

Sasquatch National Bank (SNB) is a successful community bank in the
Pacific Northwest serving coffee retailers, agricultural cooperatives,
and farms. SNB is run by an elusive founder / president, Margaret
Hollowcreek — a shrewd business person rarely seen outside the bank's
modest headquarters.

In September 2025, riding the region's endless appetite for coffee and
a healthy capital position, SNB acquired the struggling Farmers
Exchange Bank (FEB) just before harvest season. Integration was
completed quickly: legacy FEB customers (Cascade Timber Mill, Pinecrest
Vineyards LLC, Big Meadow Dairy, Harvest Moon Bakery) became SNB
customers, and FEB's chart of accounts was merged into SNB's general
ledger.

Important payment flows for the customers:

- **Merchants** (coffee retail) accept the vast majority of their
  customer payments via credit / debit cards. SNB partners with the
  Payment Gateway Processor to enable card acceptance. Card sales are
  settled to the merchants' DDAs every business day via the Card
  Acquiring Settlement account.
- **Commercial customers** pay their suppliers primarily via ACH or
  Real-Time Payments. All ACH originations route through the ACH
  Origination Settlement account, which net-settles to the FRB Master
  Account at EOD.

The training scenarios play out from September 2025 through December
2025.

What follows are the details of people in the different departments at
SNB.
  - SNB's General Ledger Reconciliation / Accounting Operations team
    - opens the AR dashboard each morning, scans **Today's Exceptions** for the day's totals, glances **Exceptions Trends** for the shape of any breaks, drills into anything aging past their threshold
    - a key data sanity check artifact for them is checking an externally generated bank statement against this system's data import
  - SNB's Merchant Support Team
    - opens a dashboard and looks to see all the merchants sales had settled/been paid
  - SNB's Data Integration Team
    - creates ETL jobs to populate the data to support this tool. The simpler and fewer the tables are, the easier it is for them to do their job. Their attitude is, what do I have a database server that can do fancy queries for unless I use it?
  - SNB's Fraud Team
    - uses the recon tool to search for transactions that break limits set on the accounts
  - SNB's Investigation/AML Team
    - uses the recon tool to detect if transactions/balances are outside of the statistical average and attempts to find patterns
    - They are looking for a dashboard that shows: for transfers between different subledger accounts, are there transfers inside a couple day sliding window that sum to amounts that 2 std deviations higher than other transfers?
  - SNB's Executive Management
    - Looking for transaction statistics and trends.
    - For all the data in the system, how much money is moving over time?
    - How many accounts do we have open?
    - How many accounts have activity?
    - Any other useful stats

## Where to go from here

- [GL Reconciliation Handbook](handbook/ar.md) — the AR dashboard's
  walkthroughs, organized by exception class. Where the Accounting
  Operations team works.
- [Payment Reconciliation Handbook](handbook/pr.md) — the PR
  dashboard's walkthroughs, organized by operator question. Where
  the Merchant Support team works.
- [Data Integration Handbook](handbook/etl.md) — the feed-side
  walkthroughs: mapping an upstream system into `transactions` and
  `daily_balances`, validating the load, extending the metadata
  contract. Where the Data Integration Team works.
