Goal: 
	- [ ] To create one or more AWS Quicksight dashboards with a series of tabs to help understand financial applications.

Users:
 - There are two users of this code base:
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
  - There are now two different financial reporting applications:
    - The first one is what has already been built "Payment Recon": a series of steps revolving around merchants taking in sales, this application bundles those sales to settle them and then pays those merchants at the end
    - The second one is about a financial application "Account Recon": that is focused on bank accounts and transfers. It uses double entry accounting for all transactions and needs to maintain an accurate balance and be eventually consistent.
  
    - Both applications use the same SQL datasource. For production use, a pre-existing datasource ARN is provided. For demo mode, the project creates a single QuickSight data source definition from the demo database connection URL.

	- This SQL datasource will be accessed using quicksight custom sql data sets that this project will need to create against the data source. 
    - It will be expected that this project creates example tables, data, queries against the data.
    - The queries used in the datasets are expected to be replaced by the end user of these applications since they will already have their own financial systems.

  - The focus of the two applications is different:
    - The first application "Payment Recon" continues to 
      - make queries to support reporting on each of the steps: sales -> settlement -> payment -> matching to external systems.
      - provide controls to filter and easy ways to check if a settlement didn’t happen or payments were returned.
      - ensure the payments match to other external systems since only payments would leave the system. 
      - There will be successful matches, not yet matched and late matching which will be exceptions. (Consolidated into a single analysis as the Payment Reconciliation tab rather than a separate analysis.)
    - The second application "Account Recon" is focused on consistency and tracibility:
        - do the balances match transactions?
          - if not what does not match?
        - do the the transfers end up consistent?
          - meaning the final effect of the transfer should be zero
          - if not what is out of sync?

Key Domain Models to Understand:
  - The domain models are not necessarily separate, however their focus is very different. It recommended at the moment to keep them distinct to manage the overall complexity.
  - The first application "Payment Recon": (What follows I believe is true in the existing implementation unless I note differently)
    - Locations
      - Have merchants that are tied to a location
      - Care only about merchants at their location but other people care about all the locations
    - Merchants
      - Make sales at a location, they do have a name (this was not called out explicitly in the earlier spec)
      - Have different types that determines settlement type
      - Have different configured payment methods
    - Sales 
      - Has mandatory metadata
        - Merchant
        - Amount
        - Timestamp
      - Optional metadata examples (This application could expose them on the sales tab/let them be filtered on but otherwise doesn't care)
        - Taxes
        - Tips
        - Discount Percentage
        - Cashier
      - Sales are settled to the merchant, the settlement type depends on the merchant type
      - sales could be refunded and should be netted out of a settlement
      - a refund should be treated like a sale type with a negative amount
      - sales/refunds know what settlement they belong to if its there, it could be null
    - Settlements
      - bundle sales
      - are credited to a merchant
      - settlements know what payment they belong to if its there, it could be null
    - Payments
      - the only transactions that leave the system
      - consist of usually a single settlement but could be multiple settlements from different merchants
      - a given payment only will land in a single external system
      - payments ARE NOT instantaneous
      - payments can fail and could be returned
      - payments will know what external system transaction they belong to if its there, it could be null
    - External System Transactions
      - represent one or more payments
      - external system transactions NOT tied to a payment are a problem
      - external system transactions are also availible through the single datasource above

	  - There are unique identifiers for locations, merchants, sales, settlements, payments and external system identifiers
		- At each step, a valid match from one to the other is only valid if the net effect is equal.
  		- This means the totals on each side of the step should equal out accounting for refunds/returns.
      - this is NOT subject to time delay, if a step is linked to the next step, the amount MUST match or its a problem to be highlighted
    - There is an underlying theme that each of these steps happen over time
      - Being late has a different definition depending on the step and even on the mentioned types above
      - Deing able to easily tell late vs didn't happen should be easily configurable
    
  - The second application "Account Recon":
    - Money
      - Decimal Amount
      - Should not be created or destroyed (This application does not handle fractional reserves)
      - Assume single currency denominated to 2 decimal places (This application does not handle fractional currency, or currency conversions)
    - Accounts
      - May be internal or external
        - External accounts its not this application's job to track their balance (That's for regulators)
        - Internal accounts have a daily final balance
          - This amount should match net amount of transactions done in a day
      - Will be linked to a parent account
      - Will have a name
    - Parent accounts
      - May be internal or external 
        - External parent accounts are not the focus of this application (That's for regulators)
      - Have a daily final balance
        - This is a saved amount and intended to be an aggregation of the children's balances
      - Will have a name
    - Transfers
      - Are the movement of money between accounts
      - Are done via double entry accounting transactions, meaning debits and credits
      - Cannot fail in aggregate, you cannot destroy money
      - Some transfers will be done externally and some are internal
      - More than two transactions may make up a transfer (for example if something fails)
      - Have a memo line to describe the why
    - Transactions
      - Have an amount in money
      - Have a timestamp when posted
      - Could fail individually
      - If it affects an internal account the daily balance MUST be updated in lockstep
        
Demo Scenarios:
  - These reporting applications can be hard to understand on their own due to the abstract nature of financial work, this section sets out a narrative to help generate example data and scenarios so that someone wanting to evaluate these applications can understand a logical theme.
  - In general chose names of things to fit the theme in a humerous / inoffensive way. 
    - Puns are highly encourgaged whenever possible with the hope being if someone looks carefully at the applications' demo output, which could be rather dry and boring brightens their day.
  - Demo scenarios needs a good mix of success and failure cases. An 80% success / 20% failure should illustrate the value of these tools to find problems. 
  - These scenarios need to happen over time but don't need huge volumes of data

  - The first application "Payment Recon"'s scenario is thus:
    - It is a tool for Sasqutch Bank who is a merchant bank in the pacific northwest to process sales from merchant customers. 
    - Its customers are primarily a series of coffee shops, their sales should reflect typical morning focused sales
    - The optional metadata on sales and/or merchant names are good place for variety
      
  - The second application "Account Recon"'s scenario is thus:
    - It is a tool for Farmers Exchange Bank which is a bank located in Stardew Valley
    - Its customer are local farmers, suppliers, and buyers for the farmer's goods
    - The memo line on transfers plus the date of the transactions should tell a story

Code Base Guideance:
  - [ ] The exisiting code base has significant value, its not recommended to change the technology selection.
    - aka Python that emits the QuickSight JSON and a Python `quicksight-gen deploy` command that applies it via boto3
    - the demo datasource is an aws aurora postgresql instance
  - [ ] The final output should be two quicksight databoards using the exisiting config process
  - [ ] The code may need to be restructured to allow for code sharing especially of interating between the quicksight api
  - [ ] A layered testing approach is still critical, the existing test scripts should be reused wherever possible
  - [ ] Theming support is still wanted
    
Output:
  - [ ] The final output should still be quicksight json and be repeatedly deployable via `quicksight-gen deploy`.

  - [ ] If the demo deployment is done, an additional sheet at the front of the dashboard should be added explaining the scenario and what the other sheets are for.
	
	- [ ] All generated AWS resources (themes, datasets, analyses) must have a common tag (`ManagedBy: quicksight-gen`) so they can be found. Additional tags can be specified via `extra_tags` in config.yaml. The common tag is always applied on top of any other tags.

	- [ ] Published dashboards. Each analysis (Payment Recon and Account Recon) also produces a published Dashboard resource. Dashboards enable ad-hoc filtering, CSV export, and expanded sheet controls. Dashboards are accessible to every configured `principal_arns` entry.

	- [ ] Visual layout sizing. KPI visuals use compact grid sizing (half-width, 6 rows) so they don't dominate the page. Charts get moderate height (12 rows), detail tables get the most space (18 rows, full-width). Try to minimize excessive white space.

	- [ ] Descriptive axis labels. All bar chart and pie chart axes display human-readable labels (e.g. "Merchant", "Sales Amount ($)", "Match Status") instead of raw column names like `transaction_id (Count)` or `external_system`.

	- [ ] Clickable cells look clickable. Any table cell that triggers a drill-down, cross-sheet navigation, or same-sheet parameter/filter action is rendered in the theme accent color via conditional formatting so users can see which cells are interactive without having to hover and discover. Two styles: plain accent text = primary left-click drill; accent text on a pale tint background = right-click (`DATA_POINT_MENU`) drill, used when a visual already has a left-click drill on a different column and a second drill target needs to live on the same table. The Getting Started sheet explains both styles; Phase 6 rich-text work must carry the same legend.

	- [ ] End-to-end test harness. Two-layer validation against a deployed dashboard: API tests (boto3) verify resource health, dashboard structure, and dataset import status; browser tests (Playwright WebKit, headless) load the dashboard via a pre-authenticated embed URL and verify sheet tabs render, per-sheet visual counts, drill-down navigation (Settlements→Sales, Payments→Settlements), Payment Reconciliation mutual table filtering, and date-range filter behavior. Single-command runner (`./run_e2e.sh`) regenerates JSON, redeploys, and runs the tests so iteration is hands-off.

Open Questions:
  - Code organization / sharing:
    - How far should the refactor go? Candidates: (a) light — keep top-level modules, extract shared helpers; (b) medium — two sibling packages `payment_recon/` and `account_recon/` alongside a `common/` for QuickSight builders, models, config, deploy; (c) heavy — a generic "dashboard" framework the two apps plug into. Preference?
      - I think the medium may be far enough. The existing python code models the quicksight api well but ends up pretty tightly coupled. The medium approach keeps some commonality which inventing a ton of extra overhead.
    - Should `models.py` (QuickSight dataclasses), theming, tagging, filter-control primitives, and the embed/runner scaffolding be factored into a single shared module both apps import from? Confirmed yes, but what's the import surface — one `common` package, or split (`common.models`, `common.theme`, `common.deploy`)?
      - It depends how cross dependent they are but if split makes them easier to test/change, I support. Modularity for the sake of modularity has a cost if you go too far, meaning if the caller ends up a bunch of extra layers its not worth it unless each layer adds value.

  - CLI & config shape:
    - Does one invocation produce both dashboards, or does each app have its own subcommand (e.g., `quicksight-gen generate payment-recon` / `account-recon` / `--all`)? Same for `demo apply`?
      - I think subcommand with an all option is wise. As we're going through fearture by feature being able to run small parts to interate quickly is important. This may result in the generate vs deploy needing to get more conjoined so we're not destroying /recreating everything just to test.
    - One `config.yaml` with both apps' settings, or one config per app? How are `principal_arn`, `datasource_arn`, `extra_tags` shared vs. per-app?
      - All shared, the final deploy is all in one place.
    - Late-threshold was a single int. Domain now says "different definition depending on the step and even on the mentioned types above". What config shape do you want — a nested map keyed by (step, type), or just per-step with a per-type override list?
      - This may be a filter on each sheet that when set shows items not progress more than for example 2 days.

  - Demo data & database:
    - Do both apps share one demo database (tables for both co-existing), or is each demo its own DB with its own `demo_database_url`? If shared, is the datasource one QuickSight data source, or one per app?
      - database and datasource are shared, tables and above probably won't make sense to for demo's sake
    - Does `quicksight-gen demo apply` now build both schemas and seed data by default, or is that gated per app?
      - I think the cli should match the decision above (separate apps with an --all). That said if the demo tables are shared, it would make sense to do it all.
    - The front "explanation" sheet: demo-only (gated on `demo apply`) or always when a scenario text is configured? Static text blocks, or any navigation affordances (links/buttons to tabs)?
      - I think the instruction text probably always makes sense, the scenario block only makes sense in demo mode. Links are fine but the flow should be helpful and conversational. The scenario block should be no more than a paragraph or two of flavor text.

  - Payment Recon additions to existing app:
    - Refunds: new column (`sale_type` + signed amount), or just negative `amount` with an implicit type? Does a refund link to the original sale, and do we surface that linkage?
      - I think a concept of a sale_type and negative amount makes sense. For this perspective, it doesn't help the end user since the important goal is that it is contained in a settlement. That said it may not come at the same time as the sale and thus settlements could be negative, that flows into payments too.
    - Optional sale metadata (taxes, tips, discount, cashier): surface on the Sales Detail table only, expose as filters, or both?
      - show on detail, give an on sheet filter for discount and cashier. This is where the optional data part needs to be plumbed through the code so that when the sql query gets reconfigured the developer can note that additional filters should show or not. I think for this optional metadata we can derive the filter type based on if its a number or string.
    - Merchant payment methods: new dimension to filter/group by on Payments / Settlements tabs, or background metadata only? 
      - filter yes, group by not as important
    - "External system transactions NOT tied to a payment are a problem" — is this a new exceptions view (dedicated visual/table), or a filter on the existing Payment Reconciliation tab?
      - I think a filter on the payment reconciliation tab
    - "At each step, a valid match… is NOT subject to time delay — the amount MUST match or it's a problem to be highlighted" — is there a new per-step "mismatch" exception visual (sales→settlement and settlement→payment), or do we rely on the existing exception tables?
      - I think a visual / table makes a lot of sense. this is where minimizing whitespace will be important so the user doesn't have to scroll forever.

  - Account Recon (new app):
    - Proposed tabs (want confirmation before building): (1) Balances — parent/child account balances with stored-vs-computed-from-transactions deltas; (2) Transfers — transfer list, completeness (net-zero check), memo search; (3) Transactions — posted transactions with failures called out; (4) Exceptions — balance mismatches + transfers whose transactions don't net to zero; (5) Payment Reconciliation-style dashboard or nothing similar? Is this breakdown on track?
      - This breakdown is tracking but I'm certain (see other answers further down), when we get to writing the plan for this we should focus on initial layout first before we spend the time on filters/links since I bet it'll need some interation
    - Transfer integrity: do we assume the source data maintains debit=credit and just report mismatches, or do we need to recompute and flag violations from transaction-level data?
      - I think the sql query should recompute and expose a mismatch column we then propogate. It will be important for troubleshooting when this occurred since its likely tied to system bugs so we'll need to figure a timeline visual too.
    - Failed individual transactions: is "failed" a status column we expect on `transactions`, or derived from absence of a matching debit/credit entry?
      - should a status column for a transaction. when that occurs that transaction no longer counts to the transfer sum / match process.
    - Daily balance for parent accounts — is it computed in SQL/view at query time, or precomputed and stored (and the dashboard only reports drift)?
      - it should be saved daily as a final balance and at query time computed to discover drift. We'll need to figure out a filter / link to a sheet flow to enable research.
    - "More than two transactions may make up a transfer (for example if something fails)" — what shape links transactions to a transfer? A `transfer_id` FK on transactions, or a separate mapping table?
      - I think a common foreign key, for example the 'transfer_id' would work. The only transfer metadata I'm thinking of is the memo line which could also be on the transaction.
    - Currency/decimal precision: store as `numeric(·,2)` in PG, fine. Anything we need to do in QuickSight beyond `$0.00` display formatting?
      - That should be fine, the locale is US_en so commas for thousands/millions too. (This is NOT asking for localization/multilanguage)

  - Theming & demo branding:
    - Do we add a `farmers-exchange-bank` / `stardew-valley` theme preset for the Account Recon demo? Rough palette guidance (earth tones, valley greens, harvest gold)? Any IP concerns with Stardew Valley naming we should avoid (character names vs. generic valley flavor)?
      - yes please, those colors work. I'd keep to generic names not explicitly in the game.
    - The existing Sasquatch preset renames the Payment Recon analysis. Does the Farmers preset similarly rename the Account Recon analysis?
      - I'd keep a rename but use a prefix of "Demo". The new instruction sheet will speak to the scenario.

  - Deploy & output:
    - Do we end up with `payment-recon-analysis.json` / `payment-recon-dashboard.json` and `account-recon-analysis.json` / `account-recon-dashboard.json` (renaming the existing `financial-*` files), or keep `financial-*` for Payment Recon and add `account-recon-*` alongside?
      - I think renaming the files makes sense.
    - Does `deploy.sh` deploy both in one pass, or do we invoke it twice with different inputs? Same `principal_arn` granted on both?
      - I'll point back to the cli advice further up but we should support individual deploys also an --all. I am open to if it would make more sense to move the deploy.sh into python so as to provide a single unified interface. 
      - Same principal_arn.

  - Tests:
    - Scope: extend the API + browser e2e harness to fully cover Account Recon too (structure, drill-downs, filters), or stand up just the API layer for Account Recon now and defer the browser layer?
      - When we talk plan, we'll want to do this in phases. I expect we'll migrate the existing app first, fix the tests, iterate on the skeleton of the new app next. E2E tests will be added for the new app once we're settled on more of its layout.
    - `tests/e2e/conftest.py` currently pins to one dashboard ID. Do we want per-app fixtures, or a parametrized suite that runs against both dashboards?
      - There will be two dashboard IDs, but I'd keep it simple and do two fixtures
    - Unit-test coverage target for Account Recon: same bar as Payment Recon (visuals, filters, cross-references, explanation coverage, demo determinism)?
      - Yes

  - Migration / backward compat:
    - Is this branch intended as a clean break (rename existing files/commands freely), or does it need to preserve the current CLI surface and output filenames for users already deploying Payment Recon?
      - Clean break, however the deploy process should have a generic function to clean up any resource with the common tag so that I don't have to clean old stuff that's not tracked after rename.

Follow-up Questions (round 2):
  - Deploy unification:
    - You're open to folding `deploy.sh` into Python for a single unified interface. Given we're already doing the rename + per-app subcommands, my recommendation is to do it now — a `quicksight-gen deploy [payment-recon|account-recon|--all]` subcommand that can also run in "generate+deploy" mode so iteration doesn't destroy/recreate unchanged resources. Delete `deploy.sh` as part of the migration. Agree, or defer to a later pass?
      - agreed
    - The existing `deploy.sh` is idempotent via delete-then-create. Do we want the Python replacement to be smarter (update-if-exists via `update-*` API calls) so iteration doesn't lose per-resource history like dashboard versions? Or stick with delete+create for simplicity?
      - keep to delete plus create, update was a trail of land mines because it seemed to be selected what was allowed to be updated

  - Cleanup-by-tag:
    - Scope: do we sweep any QuickSight resource tagged `ManagedBy: quicksight-gen` in the target account/region that is NOT part of the current generate output (i.e., stale names from prior runs)? Or only the specific resource IDs we know about?
      - any resource. That said when doing this, list what's in scope and asking for confirmation is desired
    - Safeguards: want a `--dry-run` that prints the delete list, and require `--yes` (or an interactive confirm) before actually deleting? Default behavior: interactive confirm unless `--yes`.
      - lol said the same thing jsut above
    - Should cleanup run automatically before deploy, or is it a separate explicit command (e.g., `quicksight-gen cleanup --dry-run`)?
      - separate explicit tag, regular deploy should target known resources that should be changed.

  - Late-threshold semantics:
    - "Filter on each sheet" for items not progressed for >N days. Does this replace the `late_threshold_days` config entirely (slider-only), or is the config a default value the slider loads with (and the user can override interactively)?
      - I like the default the user can override
    - Which sheets get this slider on Payment Recon: just Payment Reconciliation (current), or also Sales (sales not yet settled), Settlements (settlements not yet paid), Payments (payments not yet matched)?
      - all of them
    - Account Recon equivalents — do Balances / Transfers / Transactions also get "stuck longer than N days" sliders, or is "late" meaningful mostly for Payment Recon?
      - I think those will need sliders, depending on the accounts it gets tricky so I'm keeping it user adjustable for now

  - Optional-metadata plumbing (taxes, tips, discount, cashier):
    - Where does the "which optional columns are present + their SQL expressions" live? Options: (a) a declarative list in config.yaml per app (easiest for end-users replacing the SQL); (b) a declarative list in a Python module constant (easier for developers); (c) runtime introspection of the query result (more magic, less explicit). Prefer (a), (b), or (c)?
      - I'd prefer C if its possible. The fallback would be keep it where the SQL ends up living.
    - Filter-type derivation: number→range filter, string→multi-select filter. Date/timestamp→date-range? Anything else we need to support?
      - I think that's appropiate

  - Per-step mismatch exceptions placement:
    - "Visual / table makes a lot of sense" for sales→settlement and settlement→payment mismatches. Where does it live — (a) a new dedicated "Pipeline Mismatches" tab; (b) additions to the existing "Exceptions & Alerts" tab; (c) inline callouts on each pipeline tab? My gut: (b), so exceptions stay in one place.
      - I'm shooting for a flow of the end user should work each step because they build but it could be done with B.
    - Same question for "external transactions not tied to a payment" — you said filter on Payment Recon tab. Confirming: the filter is on Payment Reconciliation, not on Exceptions & Alerts?
      - With the prior decision I would put it all on exceptions and alerts.

  - Front sheet content:
    - Instruction text per tab (always shown) — auto-derived from each sheet's existing plain-language description, or hand-written distinct copy for the front sheet? Auto-derive keeps it DRY but may read generic; hand-written is more conversational but is another thing to keep in sync.
      - Start with auto-derive, will evaluate if hand-written makes more sense
    - Does the front sheet itself need a human-friendly name, or just "Overview" / "Getting Started"?
      - Getting Started is good

  - Demo name/theme rename format:
    - "Prefix with Demo" — concrete format proposal: "Demo — Sasquatch Bank — Payment Reconciliation" and "Demo — Farmers Exchange Bank — Account Reconciliation" (em-dash separator). OK, or different format (colon, parentheses)?
      - "Demo — Payment Reconciliation" and "Demo — Account Reconciliation", the scenario box on the "Getting Started" page will lay out the rest.

  - Account Recon initial scope:
    - For the first Account Recon pass, do we build all 4 tabs (Balances, Transfers, Transactions, Exceptions) as rough layout before iterating, or narrow to 2 (e.g., Balances + Exceptions) to get to visible output faster and then expand? You said "focus on initial layout first before filters/links" — I want to make sure we're aligned on tab count too.
      - I think we need all 4 as a rough layout first.

  - Refund → original sale linkage:
    - Does a refund row carry a `refund_of_sale_id` FK pointing at the original sale so we can show the relationship on detail, or is the link not surfaced at all (refunds are just rows with negative amounts and their own settlement linkage)?
      - For this, do rows with a negative amount and show the type of sale / refund.

  - Parent account drift drill-down:
    - The drift-research flow — concretely, do you envision clicking a parent account row on Balances to drill into a new sheet showing that account's children + transactions for the period? Or click-to-filter staying on the same sheet?
      - This is where the 4 tab mock up above matters. I think we'll switch sheets and apply filters to narrow it down.
    - The "timeline visual" for troubleshooting when mismatches occurred — lives on the Exceptions tab, or the Transfers tab, or its own sub-view?
      - Exceptions

  - Schema namespacing for demo database:
    - Two apps' tables in the same PostgreSQL schema (`public`) with namespaced table names (`pr_sales`, `ar_accounts`, etc.) to avoid collisions, or separate PG schemas (`payment_recon.*`, `account_recon.*`)? I lean namespaced table prefixes since it's less friction for the shared QuickSight datasource.
      - same schema, prefixed

  - Transfer memo storage:
    - Memo on a `transfers` table (dedicated row per transfer, joined to transactions by `transfer_id`) or denormalized onto each `transactions` row? The former is cleaner; the latter requires the SQL to pick one row's memo consistently. Preference?
      - I'd do denormalized and pick the memo on the earliest transaction id. Doesn't make sense to have another table with a foreign key for a single attribute.
