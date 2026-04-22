# Where did this transfer actually originate?

*Question-shaped walkthrough — Investigation dashboard, Money Trail sheet.*

## The story

A receiving bank calls Compliance about a $19,000 inbound to one of
their customers. Their customer says the funds came from "an
investor", but the wire memo just reads "internal transfer". On the
SNB side, the actual originating leg sits four hops back from the
final destination — a wire from Cascadia Trust Bank that was layered
through Juniper Ridge LLC and two shell DDAs before it landed at the
counterparty bank. The investigator needs to walk the chain end-to-
end and produce the source-of-funds evidence.

## The question

"Given this transfer, where did the money actually originate, and
where else did it go?"

## Where to look

Open the **Investigation** dashboard, **Money Trail** sheet.

The sheet has three controls in the top-right panel:

- **Chain root** — dropdown of every chain root (depth-0 transfer)
  in the matview. Pick the root that anchors the chain you want to
  walk.
- **Max hops** — depth limit on the recursive walk. Default covers
  the deepest chains in the planted seed; lower it to crop very long
  chains; raise it for back-tests.
- **Min hop amount** — drops noise edges below the threshold. Default
  is $0; raise to filter out small bookkeeping legs.

Two visuals side-by-side:

- **Money Trail — Chain Sankey** (left) — renders the chain's
  source → target ribbons. The QuickSight engine self-organizes the
  layout: the root sits leftmost, the deepest descendants sit
  rightmost, ribbon thickness encodes hop amount.
- **Money Trail — Hop-by-Hop** (right) — table of every edge in the
  chain, ordered by depth ascending. Each row carries the source +
  target account names, the hop amount, the depth from root, and the
  underlying `transfer_id` so the row can be matched back to the
  postings.

The **Sankey is the headline** — it's the geometry that makes a
layering chain visually obvious. The table is for legibility (rows
the Sankey collapses or hides) and for copying transfer IDs into a
case file.

## Single-leg transfers don't draw ribbons

The matview projects one row per multi-leg edge. **Single-leg
transfers** (PR's `sale` and `external_txn` types — where the
counterparty leg lives in the external system, not in `transactions`)
appear as chain members in the table but **do not produce Sankey
ribbons** because the Sankey needs a source × target pair on each
edge. The sheet's description calls this out — if a chain mixes
multi-leg and single-leg transfers, the Sankey will look thinner
than the table.

## The math, briefly

The matview `inv_money_trail_edges` walks `parent_transfer_id` chains
via PostgreSQL's `WITH RECURSIVE`. Each transfer's parent is the
upstream transfer that funded it; chains terminate when
`parent_transfer_id IS NULL` (the chain root). The matview joins
each transfer's two legs (debit + credit) and projects one row per
multi-leg edge with the chain root, the depth from root, the source
+ target account, the hop amount, and `source_display` /
`target_display` strings (`name (id)`) so dropdowns and tables
disambiguate accounts that share names.

The matview **does not auto-refresh**. After every ETL load, the
operator runs `REFRESH MATERIALIZED VIEW inv_money_trail_edges;` —
see [Materialized views](../../Schema_v3.md#materialized-views).
QuickSight Direct Query can't run a recursive CTE inside a custom-
SQL dataset, so materialization isn't optional here.

## What you'll see in the demo

The demo plants a 4-hop layering chain rooted on a Cascadia → Juniper
wire:

| Depth | Source | Target | Amount |
|------:|--------|--------|-------:|
| 0 | Cascadia Trust Bank — Operations | Juniper Ridge LLC | $18,750.00 |
| 1 | Juniper Ridge LLC | Shell Company A | $18,500.00 |
| 2 | Shell Company A | Shell Company B | $18,250.00 |
| 3 | Shell Company B | Shell Company C | $18,000.00 |

Pick **`inv-trail-root-001`** (or whatever display string the
dropdown resolves it to — the format is `name (id)`) as the chain
root. The Sankey draws four ribbons left-to-right with steadily
shrinking width as $250 of "fees" or "residue" peels off at each
hop. The hop-by-hop table beside it lists all four edges in depth
order.

Drag the **min hop amount** slider above $18,500 — the deeper hops
disappear from the table; raise it past $19,000 and the table empties
entirely (the seed's largest hop is $18,750). This is how the K.4.9
e2e test confirms the slider actually filters.

The PR demo also seeds chains rooted on `external_txn → payment →
settlement → sale` — pick one of those from the dropdown to see a
PR-shaped chain. The single-leg `sale` and `external_txn` rows will
appear in the table but won't draw Sankey ribbons (matview projects
multi-leg edges only).

## What it means

Money Trail is a **provenance tool**. A clean chain walk gives you:

- The chain root — the originating transfer that funded everything
  downstream.
- Every intermediate hop — the layering accounts the money passed
  through.
- The terminal leaf — where the money ended up (or where the chain
  was still in flight at refresh time).
- Per-hop amounts — the residue / fee pattern that distinguishes
  legitimate fees from layering shrinkage.

A four-hop chain from an external bank to three internal shell DDAs
with $250 peeling off at each hop is consistent with layering. A
four-hop chain from a customer DDA through three internal control
accounts with no residue is consistent with a normal sweep — the
money is moving, but the geometry is benign.

A clean trail finding includes: the chain root transfer ID + posted
date, every intermediate hop's `transfer_id`, the per-hop amounts,
the terminal account, and a one-line reason the chain shape is or
isn't expected.

## Drilling in

Once you have a chain end-to-end, the next step depends on what you
want to know:

- **"Show me everything else this terminal account does."** →
  Account Network sheet. Anchor on the deepest target; the inbound
  Sankey shows the chain's last hop, and the outbound Sankey shows
  whether the money moved on again.
- **"Show me the actual posting rows for this chain."** → Account
  Reconciliation, Transactions sheet, filtered by `transfer_id` for
  each hop. The table on this sheet carries the IDs in plain text for
  copy-paste.
- **"Is the chain root part of a broader pair-spike pattern?"** →
  Volume Anomalies sheet. The chain root pair (sender → first hop)
  may also flag on z-score if the root amount is unusual for that
  pair.

## Next step

The fastest path from "I have a transfer" to "I have a complete
chain" usually goes:

1. Find the chain root. If you only have a downstream transfer ID,
   look it up in AR Transactions to read its `parent_transfer_id`,
   then walk back to the depth-0 ancestor.
2. Pick that root in the Money Trail dropdown.
3. Read the hop-by-hop table — confirm the chain depth, the per-hop
   residue pattern, and the terminal account.
4. Anchor the Account Network sheet on the terminal account to
   check whether the chain is the end of the story or just a
   way-point.

If the chain has a Cascadia-shaped root + many small downstream
splits, that's a Recipient Fanout case as well — Cascadia is the
single sender and the downstream shells become the fanout target.
The four sheets are designed to be cross-referenced.

## Related walkthroughs

- [Who's getting money from too many senders?](who-is-getting-money-from-too-many-senders.md) —
  the right entry point when the chain you're walking has a fanout
  shape at one of its hops.
- [Which sender → recipient pair just spiked?](which-pair-just-spiked.md) —
  the right entry point when you started from an alert, not a known
  transfer. The flagged pair-window's transfer ID is your chain root.
- [What does this account's money network look like?](what-does-this-accounts-money-network-look-like.md) —
  the right next step after the chain walk lands on a terminal
  account that needs a full counterparty graph review.
