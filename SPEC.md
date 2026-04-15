# Next Major Evolution Planning
  - Rename parent and child accounts to more standard ledger/sub-ledger
  - Ledger Accounts should also have transfers/transactions that affect the calculated balance
    - Understanding prior art around ledger/subledger roll up may help with this
  - Unify the data models, the sales->settlement->payment are still fundamentally transfers/transactions 
    
  ## Additional detail
  When I first started this project I was originally envisioning the sql queries being adapted to hit the real tables, however in further discussions keeping the tables distinct holds a lot of value. Also it will contain the performance impact of the queries.

  ## Suggestions for next major evolution

  ### On the three stated directions

  **1. Rename parent/child → ledger/sub-ledger.** Endorse strongly. "Parent/child" is a structural metaphor; the end users are accountants who think in GL vocabulary. The classical accounting pattern we're reaching for is **control account + subsidiary ledger**: the ledger account holds a summary balance in the GL; the sub-ledger holds the individual detail. Balance invariant: Σ subsidiary detail = control account balance. Adopting those names aligns the app with how the users already think, and makes the eventual multi-ledger reconciliation model legible without a glossary. Rename `child drift` → `sub-ledger drift` in the same pass so all vocabulary lands at once. (Note: `transfer_type` stays — direction B adds an orthogonal `origin` attribute rather than replacing `transfer_type`.)

  **2. Ledger accounts should post directly, not just aggregate.** Endorse strongly — required for real-system fidelity, not a nice-to-have. The current invariant (`parent balance = Σ children`) is a special case of the general GL invariant (`ledger balance = direct postings to ledger + Σ sub-ledger balances`). Ledger-level movements that don't belong to any single sub-ledger (inbound funding batches, external-rail debits that hit the ledger before the sub-ledger breakdown is known, scheduled clearing-account sweeps, fee assessments against a ledger) all need to post at the ledger level. Prior art worth studying:
  - **Control account / subsidiary ledger.** The canonical AP/AR pattern — one control row in the GL, N detail rows in the subsidiary, reconciled on a schedule. Most directly applicable here.
  - **Clearing / suspense accounts.** Zero-swept on a schedule; if not zero at the schedule point, something's stuck.
  - **Nostro/vostro mirror accounts.** Your view of a counterparty's balance vs. their view of yours; reconciled on a schedule. Maps to "external ledger balance per the counterparty" vs. "internal rollup of transfers posted to that ledger".
  - **Fund accounting** (nonprofit / gov't). Each fund is its own closed ledger with direct postings; restrictions prevent cross-fund commingling except via explicit transfers. Relevant if different ledgers have different legal/regulatory treatment.

  **3. Unify sales/settlement/payment under transfer/transaction.** Endorse — this is the biggest simplification available. Today's PR model is a specialization of the AR transfer graph: each step is a transfer from one account to another, with lifecycle states (pending / settled / paid / returned / matched) bolted on. Concretely:
  - A **sale** is a transfer from a customer sub-ledger to a merchant sub-ledger on the internal book.
  - A **settlement** is a transfer from the merchant's sub-ledger to the merchant's ledger account (scope change, not money leaving the system).
  - A **payment** is a transfer from a ledger account to an external destination, with an external-rail leg that settles asynchronously.
  - An **external system transaction** is the external-rail view of that same movement — i.e., the counterparty-side leg of a cross-system transfer. Today we model it as a separate entity; after unification it's just "the external leg of transfer X".
  - The FK chain `sale.settlement_id → settlement.payment_id → payment.external_txn_id` becomes a single `transfer.parent_transfer_id` (chain-of-custody), and the "match is valid when totals equal" check becomes "Σ of child-transfer amounts = parent-transfer amount" — a generic invariant, not a PR-specific rule.

  ### Additional directions worth bundling into the same refactor

  **A. Generalize reconciliation as "left = right on a key, with an SLA".** Every exception check in both apps reduces to: `(left_query, right_query, key, sla_days) → delta`. Today there are 4 PR checks (unsettled sales, returned payments, sale↔settlement mismatch, settlement↔payment mismatch, unmatched external txns) and 5 AR checks (parent drift, child drift, non-zero transfers, limit breach, overdraft) — nine bespoke queries with nine bespoke visuals. Replace with one `ReconciliationCheck` abstraction whose instances drive a single Exceptions visual-family (KPI + detail table + drill). Benefits: new check = one registration, not a tab redesign; cross-system checks (external statement line-item vs. internal rollup, clearing-account at schedule point vs. zero) slot in as more instances; the existing Payment Reconciliation tab becomes one instance instead of a separate tab.

  **B. Model origin and ordering as first-class, not rail.** From the recon system's perspective, the defining axis isn't "ACH vs. wire vs. card network" — it's whether a transfer was **internally originated** (normal flow, in order, full context known) or **externally force-posted** (out-of-order, arrives with partial context, may land hours or days after the real event). Keep today's `transfer_type` as an operational tag useful for limit breaches and demo filtering, but add an orthogonal `origin` attribute with two values: `internal-initiated` and `external-force-posted`. That's the axis that drives the hard reconciliation problems — out-of-order postings, retroactive corrections, transactions we don't know existed until the external ecosystem pushes them in. Limit checks still parametrize by `transfer_type`; aging, drill-down targeting, and the "what should we investigate?" language parametrize by `origin`.
  
  **C. Add a time lens — aging, not just point-in-time drift.** The real reconciliation problem is trajectory, not snapshot. A transfer that posted 10 minutes ago and hasn't matched yet is fine; same transfer 48 hours later is an exception. Add aging buckets (0-1d, 1-3d, 3-7d, >7d) to the Exceptions visuals, and show "age at which each check crosses SLA" alongside raw row counts. This also sets up the end-user mental model that the goal is **eventual consistency** — not instantaneous match, but convergence within the expected window.

  **D. Make the external-system view a peer ledger, not a lookup table.** Today "external system transactions" are shaped like a detail table we reconcile against. In the unified model, the external system is just another set of ledger accounts with its own stream of postings. An "external-rail leg of transfer X" posts to the corresponding external ledger account; the internal roll-up transaction posts to the mirror internal ledger account. Drift between them is a generic "left = right on a key" check (see A). This makes future rails (e.g., a new card network) uniform instead of bespoke.

  **E. Consolidate the codebase, keep two persona dashboards.** Post-unification, one codebase and one data model, but two dashboard surfaces — because an ops person watching merchant settlement has a different daily workflow than a treasury person watching ledger balances sweep. AR has consistently proved harder to onboard than PR (which has the longer socialization runway and a concrete chain-of-custody narrative), which makes the split natural: **PR is the on-ramp persona; AR is the power-user persona.** Both dashboards share the unified model; demo personas (Sasquatch / Farmers Valley) stay flavor-only.

  **F. Treat the per-dataset column contract as the interface between code and data.** With the explicit choice that customers will query their own tables rather than adapt demo SQL onto their schemas, the stable interface between reporting code and data is the **column list each dataset produces**, not the SQL that produces it. Today the contract is implicit — inline in each dataset builder's `columns=[...]` list. Promote it to first-class:
  - Each dataset declares its column contract once: names, types, nullability, semantic notes.
  - The dataset's SQL is one implementation of the contract against the demo schema; customers provide their own implementation against their production schema.
  - Unit tests assert the demo SQL's projected column list matches the declared contract.
  - Everything downstream (visuals, filters, drill-downs, parameter wiring) binds only to contract columns, never to SQL specifics.
  This sharpens what "customer customization" means: customers swap in their own SQL, the visual/filter/drill layer and the column contract stay identical. The customer's work is bounded by the column contract, not free-form.

  ### Cross-cutting constraints (apply to every phase)

  - **Historical reconciliation is a first-class requirement.** Past periods need to be re-reconciled, so every ledger balance and every transfer needs timestamps sufficient for as-of queries. Drift queries must parametrize on as-of date, not just `CURRENT_DATE`. Bake as-of support into Phase B's schema design — much cheaper than retrofitting. Demo seed data should span enough history (today's ~40-day window probably works) for as-of queries to have something to operate on.
  - **External system is authoritative, always.** Simplifies the reconciliation-frame language: every drift is "internal owes the fix". There's no "maybe they're wrong" branch. Exceptions UX points at internal drill-downs only; external data is a read-only ground truth.
  - **All ledgers post directly.** No "pure rollup" ledgers to special-case — every ledger has both a direct-posting stream and a sub-ledger-aggregation stream, and the drift invariant is the same for all of them. No per-ledger "direct-post allowed?" configuration to track.

  ### Suggested phasing (to bound blast radius)

  - **Phase A — Vocabulary.** Rename parent/child → ledger/sub-ledger, `child drift` → `sub-ledger drift` across code, SQL, QuickSight labels, docs. Add the `origin` attribute concept (internal-initiated vs. external-force-posted) — just as a tag on existing transfers initially, no behavior change yet. Rename dataset IDs freely; there are no saved-bookmark consumers yet. Tests should pass modulo string updates. Lowest risk, highest daily-reading clarity gain.
  - **Phase B — Unified transfer schema + column contract.** (a) Introduce `transfer` + `posting` as the common schema primitives, with an `as_of` timestamp on every balance / posting so historical recon works out-of-the-box. (b) Migrate AR's existing transfers/transactions onto the unified shape (minimal — already shaped this way). (c) Migrate PR's sales/settlements/payments/external-txns into transfer chains via `parent_transfer_id`. (d) Promote each dataset's column list to an explicit contract and refactor dataset builders to implement against it. Legacy PR detail views can be dropped rather than preserved.
  - **Phase C — Ledger-level direct postings.** Drop the "parent = Σ children" invariant; replace with `stored ledger balance = Σ direct postings on that ledger + Σ sub-ledger balances, all evaluated as-of the reporting date`. Expand `demo_data.py` so every ledger has both direct postings and child activity in its history. Update the drift exception check accordingly. Simpler than originally scoped because every ledger posts directly — no per-ledger configuration.
  - **Phase D — Unified reconciliation frame.** Re-implement each of today's 9 exception checks as instances of a `ReconciliationCheck(left, right, key, sla)` pattern. Don't pre-design the abstraction — let it emerge from the dedup. See the note in "Things worth NOT doing" below. Merge PR's "Payment Reconciliation" tab into the unified Exceptions tab. Add aging buckets (direction C) to every check here so the as-of work from Phase B gets exercised.
  - **Phase E — Persona dashboards. ** Split the single generated analysis into two persona-scoped dashboards (PR-persona on-ramp, AR-persona power-user) that share one codebase and one data model. Keep demo personas (Sasquatch / Farmers Valley) as flavor-only. 

  ### Things worth NOT doing in this refactor

  - **Don't collapse the two demo personas prematurely.** Sasquatch (merchant-facing, morning rush, punny flavor) and Farmers Valley (treasury-facing, scheduled sweep, narrative memos) are effective *because* they target different user mental models. The unified data model should still drive both, but keep them as separate personas at the dashboard/seed layer.
  - **Don't design the reconciliation DSL up front — let it emerge from dedup.** The `ReconciliationCheck` abstraction in direction A should fall out of Phase D's re-implementation of today's 9 existing checks, not precede it. Rule of three: implement each check fresh, extract the shared shape when the same pattern shows up for the third or fourth time. The abstraction is then provably fit-for-purpose because it was built from the checks, not speculation. If it can't express all 9 cleanly, it's wrong; if it can, future checks slot in essentially free.
  - **Don't lose the current PR→AR conceptual teaching boundary without replacing it.** The two apps act as a progression: PR shows a small, concrete, chain-of-custody reconciliation; AR shows the general ledger-level version. If we unify without preserving that progression, the teaching story breaks. Direction E's persona split is the intended replacement: PR-persona dashboard is the on-ramp; AR-persona dashboard is where the ledger-level abstractions live.
  - **Don't retroactively fill the deferred Phase 3/4 filter-propagation tests before the refactor.** Those tests would assert against AR filter structures that Phase A (vocabulary rename) and Phase B (unified schema) will restructure — you'd write them twice. Better: fold filter-propagation test expansion into the Phase B/D definition of done, so each new/renamed filter in the unified model gets one propagation test as it lands. Same coverage goal, one write instead of two. The existing API and structural e2e layers already catch "dashboard broken" during the refactor — filter-propagation coverage is a narrower gap that closes cleanly after the restructure.
  - **Don't touch the test suite's unit/integration/API/browser layering.** It's the main reason the refactor is tractable. Adapt tests to new vocabulary, but keep the four-layer shape (generated-JSON shape at unit, resource health at API, user-visible behavior at browser).

# Current Spec
## Goal:
	- [x] Create AWS QuickSight dashboards with tabs that help non-technical users understand financial applications. Delivered as two independent dashboards (Payment Reconciliation + Account Reconciliation) sharing one theme, account, datasource, and CLI surface.

## Users:
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

## Background:
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

## Key Domain Models:
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

## Demo Scenarios:
  - These reports are hard to understand abstractly; a narrative helps evaluators see the point. Punny, inoffensive theming is encouraged — a dry dashboard gets brighter with a smile.
  - 80/20 success/failure ratio illustrates the tool's value at catching problems.
  - Time-distributed but low-volume.

  - Payment Recon — "Sasquatch National Bank": merchant bank in the Pacific Northwest serving local coffee shops. Morning-focused sales. Optional-metadata and merchant-name variety drives the punny flavor. (Shops: Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, Wildman's Roastery.)

  - Account Recon — "Farmers Exchange Bank": a bank in a fictional valley, customers are local farmers, suppliers, and buyers. Transfer memos + transaction dates tell a story. Parents: Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, Valley Grain Co-op, Harvest Credit Exchange. (No Stardew Valley character IP — generic valley flavor only.)

## Code Base Guidance:
  - [x] Kept the existing tech selection: Python emits QuickSight JSON, boto3 applies it via `quicksight-gen deploy`. Demo datasource is Aurora PostgreSQL.
  - [x] Two dashboards produced via the existing config process.
  - [x] Code restructured — medium refactor: `common/` for shared builders (models, theme, config, deploy, cleanup, clickability, rich_text), two sibling packages `payment_recon/` and `account_recon/`.
  - [x] Layered testing — unit + integration + API e2e + browser e2e. `./run_e2e.sh` wraps the full iteration loop.
  - [x] Theming — `PRESETS` registry in `common/theme.py`; demo presets (`sasquatch-bank`, `farmers-exchange-bank`) carry `analysis_name_prefix="Demo"`.

## Output:
  - [x] QuickSight JSON, repeatedly deployable via `quicksight-gen deploy [app|--all]` (delete-then-create, async waiters, idempotent).

  - [x] Getting Started sheet on every dashboard: welcome, clickability legend, per-sheet highlights, and (when a demo preset is active) a scenario flavor block. Rich-text composition uses `common/rich_text.py`; accent color resolves from the theme at generate time.

  - [x] All generated AWS resources (themes, datasets, analyses, dashboards) tagged `ManagedBy: quicksight-gen`. Additional tags via `extra_tags` in config.yaml. The common tag is always applied.

  - [x] Published dashboards. Each analysis (Payment Recon, Account Recon) also produces a published Dashboard resource. Dashboards enable ad-hoc filtering, CSV export, and expanded sheet controls. Dashboards are accessible to every configured `principal_arns` entry.

  - [x] Visual layout sizing. KPI visuals use compact grid sizing; charts get moderate height; detail tables get the most space. White space is minimized.

  - [x] Descriptive axis labels. All bar/pie axes display human-readable labels ("Merchant", "Sales Amount ($)", "Match Status") instead of raw column names.

  - [x] Clickable cells look clickable. Conditional formatting via `common/clickability.py`: plain accent text = left-click drill; accent text on pale-tint background = right-click (`DATA_POINT_MENU`) drill. Both styles are explained on the Getting Started sheet.

  - [x] Side-by-side tables with mutual filtering. Used on the Payment Reconciliation tab for internal payments ↔ external transactions. Default reach for any future matching workflow.

  - [x] End-to-end test harness. Two-layer validation: API (boto3) verifies resource health, dashboard structure, and dataset import status; browser (Playwright WebKit, headless) loads via pre-authenticated embed URL and verifies sheet tabs, per-sheet visual counts, drill-downs, mutual-filter tables, filters, and toggles. `./run_e2e.sh` regenerates + redeploys + runs the suite.

## Decisions Captured (round 1 + 2):
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
