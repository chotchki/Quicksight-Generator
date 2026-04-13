Goal:
	- [x] Create AWS QuickSight dashboards with tabs that help non-technical users understand financial applications. Delivered as two independent dashboards (Payment Reconciliation + Account Reconciliation) sharing one theme, account, datasource, and CLI surface.

Users:
 - Two users of this code base:
  - Developers/Product Owners seeking to customize these financial applications to work with their own existing backends
    - It is important for them to be able to customize the sql queries that feed the data sets and the columns being reported in the final views
    - It is expected they have the skills to change code but they will want to be able to edit this code in a single location for a change (meaning adhere to DRY principles)
    - These users also want to know that they didn't break anything, so a comprehensive test suite is important
    - These users want to be able to iterate quickly on changes with the non technical customers, so an ability to regenerate and redeploy is important
    - This application will need to apply themes to so it can be incorporated into the real systems. Demos should be themed differently.
  - Non technical customers of the dashboards who are expected to use these applications to accomplish their jobs
    - Their job is to find problems using these applications and then work with other teams to fix them so the reports here are clean.
    - To them these applications will be completely foreign to what they've dealt with previously
    - Plain English labels, hint test and even additional text blocks on the screens will be critical for them to adapt to the application
    - These people underderstand accounting VERY well but they are not programmers, they need to know when errors result in things they need to investigate

Background:
  - Two financial reporting applications:
    - "Payment Recon": a series of steps revolving around merchants taking in sales, this application bundles those sales to settle them and then pays those merchants at the end
    - "Account Recon": focused on bank accounts and transfers. It uses double entry accounting for all transactions and needs to maintain an accurate balance and be eventually consistent.

    - Both applications use the same SQL datasource. For production use, a pre-existing datasource ARN is provided. For demo mode, the project creates a single QuickSight data source definition from the demo database connection URL.

	- This SQL datasource is accessed using QuickSight custom-SQL datasets created by this project against the data source.
    - The project also creates example tables, data, and queries against the data.
    - The dataset queries are expected to be replaced by end users since they already have their own financial systems.

  - Focus of each app:
    - "Payment Recon":
      - Queries reporting on each step: sales → settlement → payment → matching to external systems.
      - Controls to filter and easy ways to check if a settlement didn't happen or payments were returned.
      - Ensure the payments match external systems since only payments leave the system.
      - Match statuses: matched, not-yet-matched, late. Consolidated into a single analysis as the Payment Reconciliation tab rather than a separate analysis.
    - "Account Recon" — focused on consistency and traceability:
      - Do the balances match transactions? If not, what doesn't match?
      - Do the transfers end up consistent (net-zero)? If not, what is out of sync?

Key Domain Models:
  - The domain models overlap conceptually but their focus is very different — they are kept distinct to manage complexity.
  - "Payment Recon":
    - Locations
      - Have merchants tied to them
      - Care about merchants at their location; other people care about all locations
    - Merchants
      - Make sales at a location, have a name
      - Have different types that determine settlement type
      - Have configured payment methods
    - Sales
      - Mandatory metadata: Merchant, Amount, Timestamp
      - Optional metadata (surfaced on detail, filters where useful): Taxes, Tips, Discount Percentage, Cashier
      - Sales are settled to the merchant, the settlement type depends on the merchant type
      - Refunds are rows with negative amount and a `sale_type` of refund; they net out within a settlement and may even make a settlement (and downstream payment) negative
      - Sales know the settlement they belong to if any (nullable FK)
    - Settlements
      - Bundle sales, credited to a merchant
      - Know the payment they belong to if any (nullable FK)
    - Payments
      - The only transactions that leave the system
      - Usually one settlement, but may combine settlements from different merchants
      - Land in a single external system
      - Are not instantaneous; may fail or be returned
      - Know the external system transaction they belong to if any (nullable FK)
    - External System Transactions
      - Represent one or more payments
      - External system transactions not tied to a payment are a problem
      - Available through the single datasource

    - Unique identifiers at every step. At each step, a valid match is only valid if the net effect is equal.
      - Totals on each side of the step must match after accounting for refunds/returns
      - Not subject to time delay: if a step is linked, the amount MUST match or it's a problem to be highlighted
    - Each step happens over time; "late" has a different definition depending on the step/type. The "days outstanding" filter per tab is user-adjustable with a config-driven default (`late_default_days`).

  - "Account Recon":
    - Money
      - Decimal, single currency to 2dp, no fractional reserves / conversions
    - Accounts
      - Internal or external
        - "Internal" and "external" describe reconciliation scope — whether the balance is tracked here — not system ownership. All accounts appear in the same tables; upstream data feeds populate the rows.
        - External account balances aren't this app's concern (regulator territory)
        - Internal accounts have a daily final balance
          - Stored balance is fed in from an upstream system; this app does not compute it
          - The stored balance should match the net amount of transactions done on the account in a day
          - A child account's stored balance should not go below 0 on any day — negative-balance days are flagged as overdrafts
      - Linked to a parent account, have a name
    - Parent accounts
      - Internal or external (external is out of scope)
      - Daily final balance
        - Stored balance is fed in from an upstream system; parent-level and child-level feeds may come from different upstream systems, so the two levels can disagree with each other and with the underlying transactions
        - Invariant: stored parent balance should equal the aggregation of its children's balances
      - Define per-type daily transfer limits that apply to their child accounts. A child's outbound flow of a given type on a given day that exceeds the parent's limit is flagged.
        - Limits are populated by an upstream system
        - A parent may have limits defined for only some types — undefined means "no limit enforced"
      - Have a name
    - Reconciliation scope — five independent checks performed side-by-side on the Exceptions tab:
      - Child drift: stored child balance ≠ Σ of that child's posted transactions on that day
      - Parent drift: stored parent balance ≠ Σ of its children's stored balances on that day
      - Non-zero transfers: transfers whose posted legs don't net to zero
      - Child limit breach: Σ |outbound posted amounts of type T| for a child on a day > parent's limit for type T
      - Child overdraft: stored child balance < 0 on any day
      - Each finding points at a different upstream source and is investigated independently; two drift timelines at the bottom of the Exceptions tab reveal systemic issues
    - Transfers
      - Movement of money between accounts via double-entry debits and credits
      - Cannot fail in aggregate — money is not destroyed
      - Some external, some internal
      - May have more than two transactions (e.g., if a leg fails and is retried)
      - Carry a memo (denormalized onto each transaction; the earliest transaction's memo wins for display)
    - Transactions
      - Amount, timestamp (posted), may fail individually (status column)
      - Failed transactions don't count toward transfer sum / match
      - Carry a transfer type (ACH, wire, internal, cash) for limit checking — orthogonal to direction (debit/credit)
      - If they affect an internal account, the daily balance must be updated in lockstep

Demo Scenarios:
  - These reports are hard to understand abstractly; a narrative helps evaluators see the point. Punny, inoffensive theming is encouraged — a dry dashboard gets brighter with a smile.
  - 80/20 success/failure ratio illustrates the tool's value at catching problems.
  - Time-distributed but low-volume.

  - Payment Recon — "Sasquatch National Bank": merchant bank in the Pacific Northwest serving local coffee shops. Morning-focused sales. Optional-metadata and merchant-name variety drives the punny flavor. (Shops: Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, Wildman's Roastery.)

  - Account Recon — "Farmers Exchange Bank": a bank in a fictional valley, customers are local farmers, suppliers, and buyers. Transfer memos + transaction dates tell a story. Parents: Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, Valley Grain Co-op, Harvest Credit Exchange. (No Stardew Valley character IP — generic valley flavor only.)

Code Base Guidance:
  - [x] Kept the existing tech selection: Python emits QuickSight JSON, boto3 applies it via `quicksight-gen deploy`. Demo datasource is Aurora PostgreSQL.
  - [x] Two dashboards produced via the existing config process.
  - [x] Code restructured — medium refactor: `common/` for shared builders (models, theme, config, deploy, cleanup, clickability, rich_text), two sibling packages `payment_recon/` and `account_recon/`.
  - [x] Layered testing — unit + integration + API e2e + browser e2e. `./run_e2e.sh` wraps the full iteration loop.
  - [x] Theming — `PRESETS` registry in `common/theme.py`; demo presets (`sasquatch-bank`, `farmers-exchange-bank`) carry `analysis_name_prefix="Demo"`.

Output:
  - [x] QuickSight JSON, repeatedly deployable via `quicksight-gen deploy [app|--all]` (delete-then-create, async waiters, idempotent).

  - [x] Getting Started sheet on every dashboard: welcome, clickability legend, per-sheet highlights, and (when a demo preset is active) a scenario flavor block. Rich-text composition uses `common/rich_text.py`; accent color resolves from the theme at generate time.

  - [x] All generated AWS resources (themes, datasets, analyses, dashboards) tagged `ManagedBy: quicksight-gen`. Additional tags via `extra_tags` in config.yaml. The common tag is always applied.

  - [x] Published dashboards. Each analysis (Payment Recon, Account Recon) also produces a published Dashboard resource. Dashboards enable ad-hoc filtering, CSV export, and expanded sheet controls. Dashboards are accessible to every configured `principal_arns` entry.

  - [x] Visual layout sizing. KPI visuals use compact grid sizing; charts get moderate height; detail tables get the most space. White space is minimized.

  - [x] Descriptive axis labels. All bar/pie axes display human-readable labels ("Merchant", "Sales Amount ($)", "Match Status") instead of raw column names.

  - [x] Clickable cells look clickable. Conditional formatting via `common/clickability.py`: plain accent text = left-click drill; accent text on pale-tint background = right-click (`DATA_POINT_MENU`) drill. Both styles are explained on the Getting Started sheet.

  - [x] Side-by-side tables with mutual filtering. Used on the Payment Reconciliation tab for internal payments ↔ external transactions. Default reach for any future matching workflow.

  - [x] End-to-end test harness. Two-layer validation: API (boto3) verifies resource health, dashboard structure, and dataset import status; browser (Playwright WebKit, headless) loads via pre-authenticated embed URL and verifies sheet tabs, per-sheet visual counts, drill-downs, mutual-filter tables, filters, and toggles. `./run_e2e.sh` regenerates + redeploys + runs the suite.

Decisions Captured (round 1 + 2):
  - Refactor depth: medium. Two sibling app packages sharing `common/`. Split common by concern (`common.models`, `common.theme`, `common.deploy`, etc.) where it aids testability without adding empty layers.
  - CLI shape: subcommands per app + `--all`. One shared `config.yaml`. `generate`, `deploy` (with `--generate` flag for one-shot iteration), `demo schema|seed|apply`, `cleanup`. `deploy.sh` removed.
  - Deploy strategy: delete-then-create (update API was a minefield of partially-supported fields). `deploy` polls async resources to terminal state.
  - Cleanup: separate explicit command `quicksight-gen cleanup` (`--dry-run` / `--yes`). Sweeps any resource tagged `ManagedBy: quicksight-gen` not in current output. Not run automatically before deploy.
  - Late threshold: config-default (`late_default_days`, default 30) + user-adjustable slider on every pipeline tab (Payment Recon: Sales, Settlements, Payments, Payment Reconciliation; Account Recon: Balances, Transfers, Transactions).
  - Optional metadata: introspect at query-build time where possible; fall back to co-locating the declaration with the SQL. Numbers → range filter, strings → multi-select, dates → date-range.
  - Per-step mismatches: visual + table, grouped on the Exceptions tab (both apps). Orphan external transactions live on Exceptions.
  - Getting Started copy: auto-derived from sheet descriptions initially; hand-written per-sheet highlights were added in Phase 6 rich-text work when auto-derived text read too generic.
  - Demo analysis names: "Demo — Payment Reconciliation" / "Demo — Account Reconciliation". Scenario flavor lives in the Getting Started sheet.
  - Account Recon scope: all 4 pipeline tabs (Balances, Transfers, Transactions, Exceptions) rough-laid out first, then filters/links. Grew to 5 with "Getting Started" in front.
  - Refunds: negative amount + `sale_type=refund`. No surfaced FK back to original sale.
  - Parent-drift drill-down: switch sheets with filters applied, not same-sheet.
  - Drift timeline: lives on Account Recon Exceptions.
  - Demo DB namespacing: single Postgres schema, table prefixes `pr_` / `ar_`. One QuickSight datasource.
  - Transfer memo: denormalized onto each transaction; earliest transaction's memo wins for display.
  - File rename: clean break from `financial-*` → `payment-recon-*` / `account-recon-*`. Cleanup-by-tag handles stale resources on rename.
  - E2E test expansion: unit+API+browser for both apps, at parity. Two dashboard fixtures (PR + AR), not a parametrized suite.
