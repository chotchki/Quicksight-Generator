<div class="snb-hero">
  <img class="snb-hero__wordmark" src="../../img/snb-wordmark.svg" alt="Sasquatch National Bank">
  <h2>Investigation Handbook</h2>
  <p class="snb-hero__tagline">AML triage and provenance walks for the Compliance / Investigation team.</p>
</div>

This handbook backs the **Investigation** dashboard — the
compliance / AML view of Sasquatch National Bank. Each entry here is
framed around the investigative question an analyst opens with, and
walks them from a typed question to row-level evidence on the same
shared base ledger that PR and AR read.

## The team

Sasquatch National Bank's Investigation team sits between Treasury
(GL Recon) and the regulator. Their day is reactive — a SAR draft, a
counterparty referral, a model alert — and each case has the same
shape: pose a question about a person, a pair, or a transfer; pull
the rows that answer it; preserve the chain that ties evidence back
to the underlying postings.

Unlike PR (a four-stage pipeline) and AR (fourteen exception checks
read in a fixed morning rotation), Investigation is **question-shaped**.
Four sheets, four questions, in no particular order:

- *Recipient Fanout* — who is receiving money from too many distinct
  senders?
- *Volume Anomalies* — which sender → recipient pair just spiked
  above its rolling baseline?
- *Money Trail* — where did this transfer actually originate, and
  where does it go?
- *Account Network* — what does this account's money network look
  like, on either side?

The dashboard reads from the same `transactions` base table PR and AR
read, plus two materialized views (`inv_pair_rolling_anomalies` and
`inv_money_trail_edges`) that pre-compute the rolling-window
statistics and recursive chain walk respectively. See
[Materialized views](../Schema_v6.md#the-layered-model) for the
refresh contract — these matviews **do not auto-refresh**, so a
skipped REFRESH after ETL load means the anomaly z-scores and chain
edges lag the source data.

## The investigator's posture

The walkthroughs below are organized around the question an analyst
holds in their head when they open the dashboard:

- *Whose account looks like a collection point?* → Recipient Fanout
- *Did anything just spike this week?* → Volume Anomalies
- *Where did this specific transfer come from?* → Money Trail
- *Show me everything touching this account.* → Account Network

The four sheets are deliberately disjoint — pick the one shaped like
your question. Many cases pivot through several of them: a Recipient
Fanout hit on an account becomes a Money Trail walk on its largest
inbound transfer, then an Account Network sweep around the same
anchor to understand the full counterparty graph. Each walkthrough
flags those natural transitions at the bottom.

## The four sheets

<p class="snb-section-label">One question per sheet — pick by the shape of your question</p>

<div class="snb-card-grid">
  <a class="snb-card" href="../walkthroughs/investigation/who-is-getting-money-from-too-many-senders/">
    <h3>Who's Getting Money from Too Many Senders?</h3>
    <p>Rank recipients by their distinct sender count. Drag the threshold slider to control where "too many" starts. The fanout-cluster shape — many small inbounds → one account — is a classic structuring footprint.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/investigation/which-pair-just-spiked/">
    <h3>Which Sender → Recipient Pair Just Spiked?</h3>
    <p>Rolling 2-day SUM per (sender, recipient) pair vs. the population mean / standard deviation, exposed as a per-row z-score. σ slider sets the cutoff; the distribution chart shows the full population so the cutoff lands in context.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/investigation/where-did-this-transfer-originate/">
    <h3>Where Did This Transfer Actually Originate?</h3>
    <p>Pick a chain root from the dropdown — the Sankey renders that chain's source-to-target ribbons; the hop-by-hop table beside it lists every edge ordered by depth. Layering chains and split-deposit funnels surface here.</p>
  </a>
  <a class="snb-card" href="../walkthroughs/investigation/what-does-this-accounts-money-network-look-like/">
    <h3>What Does This Account's Money Network Look Like?</h3>
    <p>Pick an anchor account — the LEFT Sankey shows counterparties sending money INTO the anchor; the RIGHT Sankey shows the anchor sending money OUT. Right-click any table row to walk the anchor to the counterparty and re-render around the new center.</p>
  </a>
</div>

## What you'll see in the demo

The demo plants three converging scenarios on a single anchor
account, **Juniper Ridge LLC** (`cust-900-0007-juniper-ridge-llc`),
so every sheet has a non-empty answer to its question — and the
sheets connect:

- **Fanout cluster** — twelve individual depositors each ACH 2 small
  amounts to Juniper. Recipient Fanout flags Juniper at the default
  5-sender threshold; the table ranks her at the top with 12 distinct
  senders.
- **Anomaly pair** — Cascadia Trust Bank — Operations wires Juniper
  routine amounts ($300–$700) for eight days, then a single $25,000
  wire on day −10. Volume Anomalies flags that pair-window past the
  default 2σ threshold; the σ Distribution chart shows the spike
  sitting alone in the right-tail bucket.
- **Money trail** — the same Cascadia → Juniper wire that drives the
  anomaly continues as a 4-hop layering chain: Cascadia → Juniper →
  Shell A → Shell B → Shell C. Money Trail's chain-root dropdown
  surfaces the Cascadia leg; picking it renders all four hops as a
  Sankey with a slight residue per hop (layering rarely round-trips
  clean numbers).

Account Network's anchor dropdown lands on the first account
alphabetically; setting it to Juniper shows the full picture — twelve
inbound depositors on the left, three outbound shells on the right,
Juniper meeting in the middle.

## Reference

- [Account Structure](../Training_Story.md) — the bank, customers,
  accounts, and money flows behind every walkthrough on this page.
- [Schema v3 — Data Feed Contract](../Schema_v6.md) — column specs,
  metadata keys, and ETL examples for the upstream feeds. The
  [Materialized views](../Schema_v6.md#the-layered-model) section
  documents `inv_pair_rolling_anomalies` (Volume Anomalies) and
  `inv_money_trail_edges` (Money Trail / Account Network) plus the
  REFRESH cadence contract.
- [Data Integration Handbook](etl.md) — the team that populates the
  data behind every walkthrough on this page. Read it when an anomaly
  z-score, fanout count, or chain-walk result disagrees with what you
  see in the source feed.
- [GL Reconciliation Handbook](ar.md) — Treasury's view of the same
  base tables. When a Money Trail edge needs row-level posting
  evidence, AR's Transactions sheet is the next stop.
- [Payment Reconciliation Handbook](pr.md) — Merchant Support's view
  of the same base tables. When a fanout or anomaly traces back to a
  merchant settlement chain, PR's pipeline tabs are where the rest of
  the story lives.
