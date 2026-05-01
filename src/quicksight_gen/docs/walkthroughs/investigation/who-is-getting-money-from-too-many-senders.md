# Who's getting money from too many senders?

*Question-shaped walkthrough — Investigation dashboard, Recipient Fanout sheet.*

## The story

A model alert fires for an account that's been receiving small ACH
deposits from a long list of unrelated counterparties. The classic
shape of structuring: many small inbounds funnel into one collection
account so each individual deposit stays under the reporting
threshold. The investigator needs a way to ask "show me every
account whose inbound side looks like a funnel" — not just the one
the alert pointed at — and rank them so the worst offenders sit on
top.

## The question

"Whose account is receiving money from an unusual number of distinct
senders this week?"

## Where to look

Open the **Investigation** dashboard, **Recipient Fanout** sheet.

The sheet has two controls in the top-right panel:

- **Date range** — limits the analysis window via `posted_at`. Default
  is the trailing window the demo plants scenarios into; widen for
  longer-tail patterns, narrow to "this week" for a focused review.
- **Min distinct senders** — the threshold a recipient must clear to
  appear in the table. Default is 5; drag down to 2–3 to surface
  early-stage accumulation, drag up to 10+ to focus on dense clusters.

Three KPIs across the top answer "how big is the problem":

- **Qualifying Recipients** — count of recipient accounts past the
  threshold.
- **Distinct Senders** — total distinct senders feeding those
  recipients (an inflated count compared to a healthy baseline is the
  concern).
- **Total Inbound** — sum of all inbound dollars across the
  qualifying recipients.

The full-width table below ranks recipients by distinct sender count
descending. Each row carries the recipient account, its distinct
sender count for the window, and the total inbound amount. The
recipient pool is filtered to customer DDAs and merchant DDAs only
— administrative sweeps and clearing transfers don't dominate the
ranking.

## What you'll see in the demo

The demo plants a fanout cluster: twelve individual depositors, each
sending two small ACH transfers ($50–$500) to **Juniper Ridge LLC**
over the trailing four weeks. With the default threshold (5), Juniper
sits at the top of the table with **12 distinct senders** and a
total inbound around $4,000–$8,000 (rounded by the demo's RNG).

Drag the threshold slider down to 2 or 3 — additional accounts may
appear if the broader L2 instance seed has any incidental inbound
diversity (merchant DDAs typically will, since their normal sales
flow involves many distinct customer cards). Drag it up to 10+ —
Juniper stays alone, since the rest of the demo's inbound graphs are
narrower.

## What it means

Recipient Fanout is a **shape detector**, not a verdict. A high
distinct-sender count is consistent with structuring but also with
plenty of normal patterns:

- A merchant DDA legitimately collects from many distinct customers
  every day.
- A landlord's deposit account legitimately receives from many tenants
  on the first of the month.
- A church or non-profit DDA legitimately receives from many small
  donors.

The investigator's job is to **rule those out** before treating the
shape as suspicious. The ranking gives you the candidates; the
context (account type, business line, prior history) tells you which
ones to escalate.

A clean fanout finding includes: the recipient's name + account ID,
the time window, the distinct sender count, the total dollar amount,
and a one-line reason the shape is or isn't expected for that
account.

## Drilling in

The Recipient Fanout sheet is one of four question-shaped views over
the same base ledger. Once you have a candidate, the next step
depends on what you want to know:

- **"Which sender is the biggest contributor to this fanout?"** →
  Volume Anomalies sheet. Set the date range the same way; the table
  there is per-(sender, recipient, window) so you can spot the
  outsized senders within the cluster.
- **"How does this account exchange money with everyone, not just
  these senders?"** → Account Network sheet. Set the anchor to the
  flagged recipient; the inbound Sankey shows the fanout senders, and
  the outbound Sankey shows where the money goes next.
- **"Show me the actual posting rows behind one of these inbound
  transfers."** → L1 Reconciliation Dashboard, Transactions sheet,
  filtered to the recipient `account_id`.

## Next step

Pick the recipient that doesn't have an obvious benign explanation,
then walk it through Account Network + Money Trail to build the case.
A common workflow:

1. Recipient Fanout flags Juniper at 12 senders.
2. Open Account Network, set anchor to Juniper. The inbound Sankey
   shows the 12 individual depositors plus the Cascadia anomaly
   sender. The outbound Sankey shows three shell DDAs (Shell A, B, C)
   — the layering destinations.
3. Right-click the Cascadia inbound row in the touching-edges table
   below — the anchor walks to Cascadia, and the chart re-renders
   around the new center.
4. Open Money Trail to walk the chain: pick the Cascadia → Juniper
   transfer as the chain root, and watch the layering hops surface
   as a 4-hop Sankey.

That sequence — fanout detection, network sweep, trail walk — is the
default shape of a Compliance investigation, and the four sheets are
ordered to support it without having to leave the dashboard.

## Related walkthroughs

- [Which sender → recipient pair just spiked?](which-pair-just-spiked.md) —
  the next sheet over. Same base table, but ranks (sender, recipient,
  window) tuples by z-score instead of recipients by distinct sender
  count. Use it to find which sender within a fanout cluster is
  biggest.
- [What does this account's money network look like?](what-does-this-accounts-money-network-look-like.md) —
  the right step after Recipient Fanout flags an account. Anchor the
  Account Network sheet on the flagged recipient to see the full
  counterparty graph on both sides.
- [Where did this transfer actually originate?](where-did-this-transfer-originate.md) —
  the right step when one of the inbound transfers needs a
  provenance walk. Pick the transfer's chain root from the Money
  Trail dropdown.
