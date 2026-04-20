# Dashboard literacy

*Shared starting point for the Accounting and Customer Service
tracks. 15 minute read.*

This page covers the mechanics of using a QuickSight dashboard
built from this tool. It's dashboard-agnostic — what's true for
the AR dashboard is true for the PR dashboard and anything else
the tool ships. Each team's track references this page, so learn
it once.

## Opening a dashboard

1. Log in to QuickSight in the environment you want — demo or
   production. Both dashboards (AR and PR) are listed on your
   home page under **Dashboards**.
2. Click the dashboard. It loads with all tabs populated.
3. The first tab is always **Getting Started** — a plain-language
   overview of what each of the other tabs shows. Read it once
   per dashboard; after that, skip to the tab you want.

## Tab navigation

Tabs sit across the top of the dashboard, left to right in the
order the data flows. Click a tab to switch.

- **AR dashboard** (5 tabs): Getting Started → Balances →
  Transfers → Transactions → Exceptions.
- **PR dashboard** (6 tabs): Getting Started → Sales →
  Settlements → Payments → Exceptions → Payment Reconciliation.

**Exceptions** is where you'll spend most of your time. The
other tabs are reference and drill targets.

## Filters

Each tab has a filter control bar at the top. Common controls:

- **Date range** — sets the time window every visual on the tab
  respects. Applies until you change it or move to a tab that
  overrides it.
- **Entity filter** — merchant (PR) or account (AR). Cascades
  across tabs when you navigate.
- **Show-Only-X toggles** — tab-specific. On AR Transactions,
  the "Show Only Failed" toggle narrows to rejected legs. On PR
  Exceptions, toggles narrow to a specific exception class.

To clear a filter, click the filter control and pick the empty
option (or, for a date range, pick the default "all time" preset).

## Clickable cells

The tool uses a visual convention so you can see what's clickable
before you click:

- **Accent-colored text** → left-click to drill. Most commonly
  a foreign-key column (`settlement_id`, `account_id`,
  `transfer_id`) — clicking navigates to the sheet that holds
  that row and filters to it.
- **Accent text on a pale tint background** → right-click to open
  a menu of drill options. Used when there are multiple drill
  targets or when the drill sets a parameter (common on the
  Payment Reconciliation tab for `external_transaction_id`).

Plain-black text isn't interactive. Hover with your cursor to
confirm — clickable cells highlight.

## Drill-downs

A drill-down is a click that navigates to another tab with
filters pre-applied. Typical drill shapes:

- **Row-to-detail** — click an ID in a summary table; drill
  switches to the detail tab filtered to that ID.
- **KPI-to-rows** — click the KPI headline; drill switches to
  the detail table for that check.
- **Bar-to-rows** — click a bar in an aging chart; drill filters
  the detail table to that bucket.

After a drill, the destination tab keeps its filter until you
navigate back and forth explicitly. **Note one known limitation:
parameter filters from right-click drills stack across tab-
switches and don't clear automatically.** If you see a tab with
unexpectedly few rows, suspect a stuck parameter; refresh the
browser tab to clear all parameters.

## Saved views

QuickSight offers per-user saved views — a bookmark of the
filters you've applied. Set up the two or three you use daily:

- On AR → Exceptions: a "morning scan" view with date range set
  to yesterday. No other filters.
- On PR → Sales: a view per merchant you handle most often.
- On AR → Transactions: a view with "Show Only Failed" toggled
  on, for triaging rejected postings.

To save a view: apply the filters you want, click the user icon
(top right), → **Save as**. Named views show up in the same menu
later.

## Exporting to Excel

Every table visual has a three-dot menu (hover, top right of the
visual) → **Export to CSV**. Useful when you want to bring a
detail table into a spreadsheet for annotation or ad-hoc pivots.
CSVs carry the columns shown, in the sort order shown.

## Keyboard & mouse quick reference

| Action | How |
|---|---|
| Navigate tabs | Click tab header |
| Left-click drill | Click accent-colored cell |
| Right-click drill menu | Right-click accent cell on tint background |
| Clear filter | Filter control → empty option (or "All") |
| Clear stuck parameters | Browser refresh on the dashboard tab |
| Export table | Visual three-dot menu → Export to CSV |
| Save a view | User icon → Save as |

## Where to go next

- [Accounting track → scenario 1](../scenarios/01-dollars-in-the-pool.md)
- [Customer Service track → scenario 3](../scenarios/03-vouchers-dont-match-sales.md)
- Upstream reference: [GL Reconciliation Handbook](../../../docs/handbook/ar.md) and [Payment Reconciliation Handbook](../../../docs/handbook/pr.md)
