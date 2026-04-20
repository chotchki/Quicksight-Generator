# PLAN — Phase G: schema flatten + PR/AR data merger

Two co-equal goals:

1. **Schema flatten.** Collapse the 12-table demo schema down to **two base tables** — `transactions` (one row per money-movement leg) and `daily_balances` (one row per account per day) — so the new "Data Integration Team" persona in `docs/Training_Story.md` has the simplest possible feed contract to populate from upstream systems.
2. **PR/AR data unification.** Both apps' demo data lands in the SAME `transactions` table (PR-specific metadata in JSONB) and the SAME `daily_balances` table. Today PR reads from `pr_*` legacy tables and AR reads from `transfer`+`posting`+`ar_*`; after Phase G, both share one base layer. This completes the cutover deferred since Phase B and retires the entire `pr_*` table family.
  - Comment: I like the thought of using a metadata column on transactions to move things are not technically needed for the recon but could be useful for different personas.

Computed views stay (they're the "fancy queries the database does" the persona explicitly endorses); only the BASE tables flatten and unify. After Phase G, `SPEC.md` gets a fresh rewrite (separate work, not in this plan).

The new persona is the load-bearing motivation:

> SNB's Data Integration Team — creates ETL jobs to populate the data to support this tool. The simpler and fewer the tables are, the easier it is for them to do their job. Their attitude is, what do I have a database server that can do fancy queries for unless I use it?

This dovetails with the existing design memory `project_design_north_stars.md` (CPA-readable + minimum table count, denormalize, don't add tables lightly).

Out of scope for Phase G (own future work):
- **`SPEC.md` rewrite.** Phase G changes the schema; the SPEC's ground truth shifts hard. Better to do the SPEC rewrite as a single coherent edit *after* G lands, not interleaved with the migration.
- **Persona dashboard split** (originally Phase E in `SPEC.md`) — orthogonal; remains queued.
- **PR app exception/visual changes.** Phase G migrates PR's *data layer* but leaves the PR sheet structure and visual catalog unchanged. Any new PR-side checks would be a follow-up phase.
- **Production SQL example library.** Phase G ships ETL example queries for the new persona, but a full customer-facing customization guide is later.
  - Comment: Sounds good, I consider this ripe for the training path so the user can know WHY they should populate a column. External systems will be messy so understanding the nuance is key. The tables are going to end up as an API contract.

Conventions:
- Branch: `phase-g-schema-flatten`, cut from `main` after v2.0.0 is tagged.
- One sub-phase = one commit. Cumulative release at the end (v3.0.0).
- **Strangler migration** — add new tables alongside old, dual-write demo data, migrate dataset SQL one at a time, drop old tables only when nothing reads them. Test suite stays GREEN after every commit (no intentional-red windows like Phase F had).
  - Comment: It is probably worth preplanning re-evaluation gates after each major step. I would not be surprised if things we encountered unexpectedly.
- `DatasetContract` is the safety net: every dataset declares column-name + type list, and unit tests assert that the SQL projection matches. As long as a rewritten dataset emits the same contract, downstream visuals can't break — so SQL can be rewritten freely against the new tables.
- `demo apply` continues to drop-and-create. No staged migrations.
- After each sub-phase: `.venv/bin/pytest`. After every dataset-migration sub-phase: `./run_e2e.sh --skip-deploy api` against the previous deploy is sufficient (browser e2e only at G.14).
- Demo data MUST stay deterministic (`random.Random(42)`). The dual-write window will break byte-identical-output; re-locks at G.11 when single-write returns.
- **No new account names, no new exception checks.** Phase G is a pure data-layer migration; the visible dashboards must look identical before and after. Any visible diff is a regression.
  - Comment: After major steps, I think a full deploy to quicksight, e2e test is important to really validate the step didn't break anything.
- **Computed views STAY.** Drift, rollups, transfer-net-zero — all the value-add SQL the database performs continues to live in views. Only the bases flatten.
- **PR and AR are no longer schema-isolated.** Both apps' transactions go into the same `transactions` table; both apps' account snapshots go into the same `daily_balances` table. The `pr_*` table family is fully retired by G.10. AR datasets and PR datasets read from the same base layer — the only thing distinguishing them is which `transfer_type` / `account_type` rows they filter on (and, for PR, what they pull out of the metadata column).
- **Database portability constraint — system compatibility requires Postgres 17+.** The demo runs PostgreSQL but every SQL feature must stay portable across the dialect that consumes this app. **Use** `TEXT` columns for JSON storage (with `IS JSON` constraint where the dialect supports it), and **only** the SQL/JSON path functions `JSON_VALUE` / `JSON_QUERY` / `JSON_EXISTS` for extraction. **Forbidden:** `JSONB`, `JSON` types, `->>` / `->` / `@>` / `?` operators, GIN indexes on JSON, Postgres extensions (`pg_trgm`, `uuid-ossp`, etc.), array/range column types. PG 17+ provides the portable `JSON_VALUE` syntax that older Postgres lacks.
- **Re-evaluation gates.** After each major chunk (G.3, G.5, G.8, G.9), STOP for a full deploy + browser e2e gate (its own `G.X.gate` sub-phase). Don't push forward if a gate finds anything unexpected — re-plan first.

---

## Phase G.0 — Pin decisions

STOP here. Several decisions cascade hard across 30+ commits.

- [ ] G.0.1 **Account metadata: denormalized columns vs. sidecar reference table?**
  - Option A — Pure 2-table: `account_id`, `account_name`, `parent_account_id`, `parent_account_name`, `is_internal`, `account_type` columns on BOTH `transactions` and `daily_balances`. Truly two tables; ETL writes everything from upstream.
  - Option B — 2 + tiny `accounts` reference: keep account display metadata in a 3rd reference table (rarely changes); `transactions` and `daily_balances` carry only `account_id`. Cleaner normalization, ~3 tables.
  - **Recommendation:** A. The persona explicitly values "fewer tables"; daily_balances row-per-day-per-account already serves as the implicit account list (every account has a snapshot, even at zero); display-name drift is acceptable (history reflects the name as-of-then).
  - Answer: Agreed with A, makes it much easier to react and account for changes.
- [ ] G.0.2 **Ledger / sub-ledger distinction in the flat model.** Today they're separate tables. Flat options:
  - Option A — Single `account_id` namespace; `parent_account_id` (nullable) marks ledger relationships. A ledger has `parent_account_id IS NULL`; sub-ledgers have it set. Direct ledger postings = `transactions.account_id = <ledger>` and that ledger has `parent_account_id IS NULL`.
  - Option B — `account_level` enum column (`ledger` / `subledger`) plus `ledger_id` column on subledgers.
  - **Recommendation:** A. Self-referential FK is the standard accounting hierarchy pattern; one column does both jobs.
  - Answer:Agree with A but would like to know if the column naming matches the accounting terminology standardization? If so I support.
  - **Locked:** column name is `control_account_id` (the standard accounting term — the GL summary account that aggregates a subsidiary ledger). Phase G.1 doc + Phase G.12 training material both explain that "control account" = "parent in the FK sense" so a Data Integration Team reader without accounting background can map it.
- [ ] G.0.3 **PR-specific metadata: column type and extraction syntax?** PR carries `card_brand`, `cashier`, `merchant_type`, `settlement_type`, `payment_method`, optional `taxes/tips/discount` per sale. Options:
  - Option A — `metadata TEXT` column on `transactions` (with `IS JSON` constraint), queried via SQL/JSON path functions (`JSON_VALUE(metadata, '$.card_brand')`). Portable per the database-portability convention; persona-aligned (database does fancy extraction queries).
  - Option B — Single sidecar table `transaction_metadata(transaction_id PK, ...)`. SQL stays familiar JOIN. Adds one table.
  - Option C — Drop PR-specific metadata entirely, fold into `memo` text. Loses filterability.
  - **Recommendation:** A (TEXT + SQL/JSON path).
  - Answer: I like option A, but use a text column.
  - **Locked:** `metadata TEXT` column with `IS JSON` constraint where supported. All extraction goes through `JSON_VALUE` / `JSON_QUERY` / `JSON_EXISTS`. NO Postgres-only operators (`->>`, `@>`) anywhere in dataset SQL or views. The `metadata` text column is the universal "extras" container — used by PR (card_brand, etc.), by AR (limits on ledger rows in `daily_balances`, source provenance on transactions), and by future Phase H consumers.
- [ ] G.0.4 **Per-ledger transfer limits: separate table vs. inline on accounts row?**
  - Limits today: `ar_ledger_transfer_limits` (~5 rows total). They're tiny and rarely change. Options:
    - Keep tiny `account_limits` reference table (3rd or 4th table, depending on G.0.1).
    - Pack into JSONB on the ledger account row in `daily_balances` (one row per ledger per day already exists).
    - Drop limits entirely — they're a Phase A artifact and the only check that uses them (Sub-Ledger Limit Breach) could be parameter-driven instead.
  - **Recommendation (revised after G.0.3):** collapse `account_limits` into `daily_balances.metadata` on the LEDGER row of each day (e.g., `{"limits": {"ach": 100000, "wire": 50000, "internal": 25000}}`). Limits CAN shift daily; daily storage is the natural place. Eliminates the third table — schema lands at TRULY 2 base tables. Limit-breach check joins each transaction's daily aggregate to the relevant ledger's daily_balances row and reads the limit via `JSON_VALUE(db.metadata, '$.limits.' || t.transfer_type)`.
  - Answer: Limits can shift daily so I think keeping in a json metadata column makes sense (storing as text). I added more training personas that the question reminded me of.
  - **Locked:** collapse — limits live in `daily_balances.metadata` text column on ledger-account rows. **Net schema: 2 base tables (`transactions` + `daily_balances`).** No `account_limits` reference table.
- [ ] G.0.5 **Should `daily_balances` carry `computed_balance` too, or compute it in a view?**
  - Today: `ar_*_daily_balances` stores only the upstream-fed `balance`; computed balances are SQL views over `posting`.
  - Phase G option: keep `daily_balances` as upstream-fed only (computed stays in views). The drift checks then compare stored vs. view-computed.
  - **Recommendation:** stored only. Don't bake computation into the table. Persona's "database does the fancy queries" applies — the drift VIEW is exactly that.
  - Answer: agreed, calculate in views
- [ ] G.0.6 **Compatibility view layer: build it or skip it?**
  - Option A — Build `transfer`, `posting`, `ar_ledger_accounts`, `ar_subledger_accounts`, `ar_ledger_daily_balances`, `ar_subledger_daily_balances` as VIEWS over the new tables. Dataset SQL stays untouched during migration; we just swap underlying tables.
  - Option B — Skip the view layer; rewrite dataset SQL directly against new tables, dataset by dataset.
  - **Recommendation:** B. Phase F's experience: views-over-views gets confusing fast, and DatasetContract makes per-dataset rewrites safe. Per-dataset commits are also more reviewable than one giant "swap the world" commit. View layer would only make sense if we had to ship the migration in pieces over weeks.
  - Answer: agreed, clean break
- [ ] G.0.7 **PR `pr_*` legacy tables: drop in Phase G or defer?**
  - Phase B left `pr_merchants`, `pr_sales`, `pr_settlements`, `pr_payments`, `pr_external_transactions` as the source-of-truth for PR datasets, with PR demo *also* dual-writing to `transfer`+`posting`. With Phase G's new `transactions` table, PR datasets can finally read from there.
  - **Recommendation:** drop in Phase G. This is one of the two co-equal goals — the merger only completes when the `pr_*` tables are gone and PR datasets read from the same `transactions` / `daily_balances` AR datasets read from. Phase B's deferred cutover gets done as part of the larger migration. After G.10, there is one base layer for both apps.
  - Answer: Agreed drop
- [ ] G.0.8 **`merchants` / `external_systems` reference data: where does it live?**
  - Today PR has `pr_merchants` (display name + type + location) and `pr_external_transactions` carries `external_system` as a string column.
  - Options: (a) merchants become accounts (DDA-equivalent) so they appear in `accounts` reference (or denormalized columns); (b) merchants live in a dedicated `pr_merchants` reference table; (c) merchant attributes (name, type) denormalize onto `transactions` rows with merchant involvement.
  - **Recommendation:** (a). Each merchant already has a corresponding sub-ledger account (`pr-sub-{merchant}` from Phase B); promote that to be the canonical merchant identity. Drop `pr_merchants`. Loss: location_id (which has no current visual / filter consumer). Win: one less table.
  - Answer: Merchants are just accounts. Sales (aka transactions) should have merchant metadata. This can be used as another check if a settlement miss directed funds 
  - **Locked:** merchants are accounts (drop `pr_merchants`). Sale transactions carry merchant metadata in the `metadata` text column — `merchant_account_id`, `merchant_name`, `merchant_type` — recorded in Phase G even though the consuming check is Phase H. The "settlement-misdirected-funds" check (compare sale's recorded merchant against settlement's recipient account) is **Phase H scope**, not Phase G. Phase G only records the data; Phase H builds the view + dashboard.
- [ ] G.0.9 **External counterparties (`Federal Reserve Bank — SNB Master`, processors) in the flat model.** They're already accounts in the AR ledger (`is_internal=FALSE`). No change — they fit the unified model naturally.
- [ ] G.0.10 **Naming.** `transactions` (plural) vs `transaction` (singular)? `daily_balances` vs `daily_balance` vs just `balances`? Existing tables are mixed (`transfer` singular, `posting` singular, `ar_*_daily_balances` plural). The new persona reads ETL SQL — pick the form that reads best in `INSERT INTO transactions ...` / `SELECT * FROM daily_balances WHERE ...`. **Recommendation:** plural for both (`transactions`, `daily_balances`). The legacy singulars (`transfer`, `posting`) are already inconsistent; pick one rule going forward.
  - Answer: I'm good with plural.
- [ ] G.0.11 **Release version after Phase G.** v3.0.0 — schema base tables change is breaking for any external consumer of `demo/schema.sql`. (Customer production schemas aren't affected; they bring their own SQL. But the demo schema is the contract for `demo apply`.)
  - Answer: v3.0.0 will be well earned here.
- [ ] G.0.12 **`account_type` enum: separate role from level?** Today `account_type` mixes role (`dda`) and structural level (`ledger`/`subledger`). In the flat model, options:
  - Option A — `account_type` = product/role only (`dda`, `gl_control`, `merchant_dda`, `external_counterparty`, `concentration_master`, `funds_pool`); structural level comes from `parent_account_id IS NULL` (a top-level account is implicitly a ledger control account).
  - Option B — keep level baked into `account_type` (`ledger_dda`, `subledger_dda`, etc.) — easier to filter; loses single-source-of-truth for hierarchy.
  - **Recommendation:** A. Phase G is the cleanup window; structural level should derive from `parent_account_id`, not be denormalized into the type column.
  - **Locked:** A. The Phase G.1 doc enumerates the canonical `account_type` values.
- [ ] G.0.13 **Phase H accommodation: which metadata keys to record now even though no Phase G check consumes them?** Phase H scope (per `docs/Training_Story.md` new personas) includes a sales-vs-settlement merchant cross-check, an external bank-statement comparison, fraud limit-search views, and AML statistical-anomaly views. Phase G ships zero new dashboards / checks but should record the metadata Phase H consumers will need:
  - **Sales transactions:** `metadata.merchant_account_id`, `metadata.merchant_name`, `metadata.merchant_type` (per G.0.8 Locked).
  - **External-statement-derived rows (Phase H ingest):** land as `transactions` rows with `is_internal=FALSE` account, `metadata.source = 'fed_statement'`, `metadata.statement_line_id` for traceability. No new table.
  - **Ledger limits:** `daily_balances.metadata.limits.{transfer_type}` on ledger rows (per G.0.4 Locked).
  - **Source provenance** on every row: `metadata.source` text key (`'core_banking'`, `'fed_statement'`, `'manual_force_post'`, `'sweep_engine'`, etc.) so the AML / Fraud teams can filter on origin.
  - **Recommendation:** record all of the above in Phase G demo-data generation; document each key in `docs/Schema_v3.md` with WHY (training material angle the user flagged: data team needs to know WHY they should populate a column).
  - **Locked:** agreed.

---

## Phase G.1 — Write target schema as a doc

Before any code change, write down what we're building so the persona contract is reviewable.

- [ ] G.1.1 New file `docs/Schema_v3.md`. Sections:
  - **The two base tables:** `transactions`, `daily_balances`. Full column definitions, types (PG 17+ portable types only), nullability, what populates each column, what consumes it. Explicit "system compatibility requires Postgres 17+" note at the top.
  - **Account hierarchy modeling** (per G.0.2): `control_account_id` self-FK semantics; explain that "control account" = the parent / GL summary account, for readers without an accounting background.
  - **`account_type` canonical values** (per G.0.12): full enumeration with one-line definitions.
  - **The `metadata` text column contract** (per G.0.3): TEXT + `IS JSON` constraint; SQL/JSON path extraction syntax; canonical key list per row context (sales rows vs. ledger daily_balances rows vs. external-ingest rows); examples; **WHY each key matters** (data team angle — they need to know why to populate it). Per G.0.13: keys reserved for Phase H consumers are documented with a "Phase H consumer" tag.
  - **Computed views catalog:** every existing view restated against the new tables (drift checks, rollups, transfer summary, etc.). Persona reads these as templates.
  - **ETL examples** for the new persona: 5-10 example queries shaped like "to populate `transactions` from your core banking system, run a query shaped like ..." Realistic enough to be cargo-cult-able. Each example explains the WHY of the columns it touches.
  - **Forbidden SQL patterns:** explicit list of Postgres-only features that must not appear (no `JSONB`, no `->>`, no GIN indexes on JSON, no extensions, no array types).
- [ ] G.1.2 Commit — `Phase G.1: document target two-table schema and ETL examples`.

---

## Phase G.2 — Add new base tables alongside old

Schema-only commit. Demo data not yet writing to them; nothing reads from them.

- [ ] G.2.1 Add `transactions` and `daily_balances` to `demo/schema.sql` (TWO base tables only — `account_limits` collapsed into `daily_balances.metadata` per G.0.4). Both tables include a `metadata TEXT` column with `IS JSON` CHECK constraint. Position above the old AR tables so DROP order is clean.
- [ ] G.2.2 Add indexes the new tables need: B-tree on `transactions(account_id, posted_at)`, `transactions(transfer_id)`, `transactions(transfer_type, status)`, `transactions(control_account_id)`, `daily_balances(account_id, balance_date)`, `daily_balances(control_account_id, balance_date)`. **No** GIN indexes on `metadata`; **no** expression indexes on JSON-path extractions (per portability constraint).
- [ ] G.2.3 Update `tests/test_demo_sql.py` to assert presence of new tables alongside existing assertions for old.
- [ ] G.2.4 `.venv/bin/pytest` — green.
- [ ] G.2.5 Commit — `Phase G.2: add transactions + daily_balances tables to demo schema`.

---

## Phase G.3 — Demo data dual-write into shared base tables

Demo generators populate BOTH old and new tables. The new tables are SHARED — AR and PR demo data write into the SAME `transactions` and `daily_balances` rows. Datasets still read from old. Test suite stays green.

- [ ] G.3.1 `account_recon/demo_data.py` — emit `INSERT INTO transactions` for every posting + `INSERT INTO daily_balances` for every ledger and sub-ledger daily snapshot. Account hierarchy denormalization happens here (parent_account_id, account names, etc.). AR rows tagged with AR-flavored `transfer_type` values (`ach`, `wire`, `internal`, `cash`, `funding_batch`, `fee`, `clearing_sweep`).
- [ ] G.3.2 `payment_recon/demo_data.py` — emit `INSERT INTO transactions` into the **same** `transactions` table that AR writes to (not a parallel one) for every posting. PR already dual-writes to `transfer`+`posting` from Phase B; extend the same write to the new unified flat table. PR rows carry PR-flavored `transfer_type` values (`sale`, `settlement`, `payment`, `external_txn`) and PR-side metadata (card_brand, settlement_type, etc.) in the JSONB column per G.0.3. Per-merchant `INSERT INTO daily_balances` snapshots also land in the same shared `daily_balances` table.
- [ ] G.3.3 New scenario-coverage tests in `tests/test_demo_data.py`: assert that every posting in `transfer`+`posting` (across both apps) has a corresponding row in the shared `transactions` table, and that every (account, date) in old daily_balance tables has a matching row in shared `daily_balances`. Catches dual-write drift early. Also assert the table contains BOTH AR-flavored and PR-flavored rows after a full `--all` demo apply (i.e., the merger actually merged).
- [ ] G.3.4 Ledger daily-limits packed into `daily_balances.metadata` on ledger rows (per G.0.4): each ledger account's daily_balances row carries `{"limits": {...}}` derived from current `_LEDGER_LIMITS` constant. Phase H may make these vary day-to-day; Phase G ships static limits per ledger via the metadata column.
- [ ] G.3.5 Phase H prep: source provenance (`metadata.source`) and merchant metadata (`metadata.merchant_*` on sales) populated per G.0.13. Coverage tests assert presence on representative rows.
- [ ] G.3.6 `.venv/bin/pytest` — green.
- [ ] G.3.7 `demo apply --all` locally — verify both old and new tables populate. Spot-check row counts and a few hand-written reconciliation queries against the new tables (using SQL/JSON path syntax — verify no Postgres-only operators sneak in).
- [ ] G.3.8 Commit — `Phase G.3: dual-write demo data to new transactions + daily_balances tables`.

---

## Phase G.3.gate — Re-evaluation gate (no commit)

After dual-write goes in but BEFORE any dataset migrates, full deploy + browser e2e — confirms dual-write didn't subtly perturb the existing tables.

- [ ] G.3.gate.1 `quicksight-gen demo apply --all -c run/config.yaml -o run/out/`
- [ ] G.3.gate.2 `quicksight-gen deploy --all --generate -c run/config.yaml -o run/out/` — all CREATION_SUCCESSFUL.
- [ ] G.3.gate.3 `./run_e2e.sh --skip-deploy --parallel 4` — full green (API + browser).
- [ ] G.3.gate.4 Spot-check the rendered AR + PR dashboards in browser; nothing should look different.
- [ ] G.3.gate.5 STOP. If anything is unexpected, re-plan before proceeding to G.4.

---

## Phase G.4 — Migrate AR balances + accounts datasets

Five datasets that surface raw account / balance data. Lowest risk because the SQL is mostly SELECT. Each commit migrates one dataset; DatasetContract assertion catches column drift.

- [ ] G.4.1 `ar-ledger-accounts-dataset` — was over `ar_ledger_accounts`. Now: `SELECT DISTINCT ledger fields FROM daily_balances WHERE parent_account_id IS NULL` (or read from `account_limits` / from a dedicated computed view). Commit.
- [ ] G.4.2 `ar-subledger-accounts-dataset` — analogous. Commit.
- [ ] G.4.3 `ar-ledger-balance-drift-dataset` — view rewrites from `ar_ledger_balance_drift`. The drift VIEW logic stays; only its underlying tables change. Commit.
- [ ] G.4.4 `ar-subledger-balance-drift-dataset` — analogous. Commit.
- [ ] G.4.5 `ar-balance-drift-timelines-rollup-dataset` — already a rollup; underlying view definitions update. Commit.

After each: `.venv/bin/pytest` (DatasetContract guard) + `./run_e2e.sh --skip-deploy api` against the prior deploy still passes.

---

## Phase G.5 — Migrate AR transfer / transaction datasets

- [ ] G.5.1 `ar-transactions-dataset`. Commit.
- [ ] G.5.2 `ar-transfer-summary-dataset`. The `ar_transfer_summary` view rewrites against `transactions` (group by `transfer_id`). Commit.
- [ ] G.5.3 `ar-non-zero-transfers-dataset` — view rewrites; same group-by-transfer pattern. Commit.

---

## Phase G.5.gate — Re-evaluation gate (no commit)

After AR transfer/transaction datasets migrate. Catches dual-write SQL drift before it propagates to the harder rewrites in G.6/G.7.

- [ ] G.5.gate.1 `demo apply --all` + `deploy --all --generate` — CREATION_SUCCESSFUL.
- [ ] G.5.gate.2 `./run_e2e.sh --skip-deploy --parallel 4` — full green.
- [ ] G.5.gate.3 STOP if anything unexpected. Re-plan before G.6.

---

## Phase G.6 — Migrate AR baseline exception checks

- [ ] G.6.1 `ar-limit-breach-dataset` — view rewrites against `transactions` + `daily_balances` (limit lives in `daily_balances.metadata` on the ledger row per G.0.4; extract via `JSON_VALUE(db.metadata, '$.limits.' || t.transfer_type)`). Commit.
- [ ] G.6.2 `ar-overdraft-dataset` — view rewrites against `daily_balances` (sub-ledger snapshots). Commit.

---

## Phase G.7 — Migrate AR CMS-specific exception checks

Nine datasets from Phase F. Each is a view over today's `transfer`+`posting`+`ar_*_daily_balances`; each gets rewritten over `transactions`+`daily_balances`. Group into commits by dataset; resist the urge to bundle.

- [ ] G.7.1 `ar-sweep-target-nonzero-dataset`. Commit.
- [ ] G.7.2 `ar-concentration-master-sweep-drift-dataset`. Commit.
- [ ] G.7.3 `ar-ach-orig-settlement-nonzero-dataset`. Commit.
- [ ] G.7.4 `ar-ach-sweep-no-fed-confirmation-dataset`. Commit.
- [ ] G.7.5 `ar-fed-card-no-internal-catchup-dataset`. Commit.
- [ ] G.7.6 `ar-gl-vs-fed-master-drift-dataset`. Commit.
- [ ] G.7.7 `ar-internal-transfer-stuck-dataset`. Commit.
- [ ] G.7.8 `ar-internal-transfer-suspense-nonzero-dataset`. Commit.
- [ ] G.7.9 `ar-internal-reversal-uncredited-dataset`. Commit.

---

## Phase G.8 — Migrate AR cross-check rollups

Two of three rollups didn't already cover in G.4.5.

- [ ] G.8.1 `ar-expected-zero-eod-rollup-dataset`. Commit.
- [ ] G.8.2 `ar-two-sided-post-mismatch-rollup-dataset`. Commit.

After G.8: AR side reads zero columns from old `transfer` / `posting` / `ar_*` tables. Sanity-check via grep on `account_recon/datasets.py`.

---

## Phase G.8.gate — Re-evaluation gate (no commit)

AR side fully migrated; PR side still on old tables. This is the largest gate — half the migration is done.

- [ ] G.8.gate.1 `demo apply --all` + `deploy --all --generate` — CREATION_SUCCESSFUL.
- [ ] G.8.gate.2 `./run_e2e.sh --skip-deploy --parallel 4` — full green.
- [ ] G.8.gate.3 Manual browser walk-through of all AR sheets — Balances, Transfers, Transactions, Exceptions (all 47 visuals). Compare against the v2.0.0 deploy by eye if possible.
- [ ] G.8.gate.4 STOP if anything unexpected. PR migration in G.9 is the long tail; entering it with anything unresolved on the AR side compounds risk.

---

## Phase G.9 — Migrate PR datasets to read from the shared base layer

Hardest because of metadata extraction (G.0.3). 11 datasets. The view layer (`pr_payment_recon_view`, `pr_sale_settlement_mismatch`, `pr_settlement_payment_mismatch`, `pr_unmatched_external_txns`) gets rewritten too.

This is the half of the merger that lights up: AR datasets after G.4–G.8 read from `transactions` / `daily_balances`; PR datasets after G.9 read from the **same** `transactions` / `daily_balances`. After G.9, both apps share one base layer. The `pr_*` tables become dead weight ready to drop in G.10.

- [ ] G.9.1 `merchants-dataset` — `SELECT DISTINCT merchant_account_id, merchant_name, merchant_type FROM transactions WHERE metadata ? 'merchant_type'` (or analogous against `daily_balances` for the canonical account list). Commit.
- [ ] G.9.2 `sales-dataset`. Metadata extraction (`metadata->>'card_brand'`, etc.). Commit.
- [ ] G.9.3 `settlements-dataset`. Commit.
- [ ] G.9.4 `payments-dataset`. Commit.
- [ ] G.9.5 `external-transactions-dataset`. Commit.
- [ ] G.9.6 `payment-recon-dataset` — the big reconciliation view rewrites entirely against `transactions`. Commit.
- [ ] G.9.7 `settlement-exceptions-dataset`. Commit.
- [ ] G.9.8 `payment-returns-dataset`. Commit.
- [ ] G.9.9 `sale-settlement-mismatch-dataset`. Commit.
- [ ] G.9.10 `settlement-payment-mismatch-dataset`. Commit.
- [ ] G.9.11 `unmatched-external-txns-dataset`. Commit.

After G.9: PR side reads zero columns from old `pr_*` tables.

---

## Phase G.9.gate — Re-evaluation gate (no commit)

Both AR and PR fully migrated. Last gate before legacy-table drop in G.10. Highest value gate: this is the moment the merger is real.

- [ ] G.9.gate.1 `demo apply --all` + `deploy --all --generate` — CREATION_SUCCESSFUL.
- [ ] G.9.gate.2 `./run_e2e.sh --skip-deploy --parallel 4` — full green.
- [ ] G.9.gate.3 Manual browser walk: AR + PR sheets, including the Payment Reconciliation mutual-filter table.
- [ ] G.9.gate.4 Confirm via grep: zero references to `pr_*`, `transfer`, `posting`, `ar_ledger_accounts`, `ar_subledger_accounts`, `ar_ledger_daily_balances`, `ar_subledger_daily_balances`, `ar_ledger_transfer_limits` in `src/`, `tests/` (excluding `demo/schema.sql` DROPs and the dual-write code that G.10 removes).
- [ ] G.9.gate.5 STOP if anything unexpected. Dropping tables in G.10 is irreversible from this branch's perspective.

---

## Phase G.10 — Drop legacy tables

Sanity check via grep first that no dataset SQL or demo data write touches the old tables, then drop.

- [ ] G.10.1 `grep -E "ar_ledger_accounts|ar_subledger_accounts|ar_ledger_daily_balances|ar_subledger_daily_balances|ar_ledger_transfer_limits|^CREATE.*transfer\b|^CREATE.*posting\b|pr_merchants|pr_sales|pr_settlements|pr_payments|pr_external_transactions"` across `src/`, `tests/`, `demo/` — only the DROP statements at the top of `schema.sql` should match.
- [ ] G.10.2 Update `demo/schema.sql`: remove `CREATE TABLE` for `ar_ledger_accounts`, `ar_subledger_accounts`, `ar_ledger_daily_balances`, `ar_subledger_daily_balances`, `ar_ledger_transfer_limits`, `transfer`, `posting`, all `pr_*` tables. Keep DROP statements at the top (clean re-apply after upgrade). Remove their indexes.
- [ ] G.10.3 Update demo data generators to single-write only to `transactions` / `daily_balances`. Remove dual-write paths.
- [ ] G.10.4 Update `tests/test_demo_sql.py` — old-table assertions become "not present"; new-table assertions become primary.
- [ ] G.10.5 `.venv/bin/pytest` — green.
- [ ] G.10.6 `demo apply --all` — verify clean apply on a fresh database.
- [ ] G.10.7 Commit — `Phase G.10: drop legacy AR + PR base tables; PR/AR fully merged into shared transactions + daily_balances`.

---

## Phase G.11 — Re-lock deterministic-output invariants

Single-write reshapes the seed-write order; deterministic-output tests may need fresh expected values.

- [ ] G.11.1 Re-run `tests/test_demo_data.py` determinism assertions; if expected values shifted (likely — write order changed), regenerate and commit the new fixtures.
- [ ] G.11.2 Verify `random.Random(42)` output is still byte-identical run-to-run on the new path.
- [ ] G.11.3 Commit — `Phase G.11: re-lock deterministic demo data fixtures after schema flatten`.

---

## Phase G.12 — Update CLAUDE.md, README.md, RELEASE_NOTES.md

- [ ] G.12.1 `CLAUDE.md` — domain model section: replace 4-table-per-app description with 2-table description. Update generated output block (no impact — datasets unchanged). Update the "Architecture Decisions" line about `transfer`+`posting` schema.
- [ ] G.12.2 `README.md` — project structure block (`demo/schema.sql` description), `Customising → Change the SQL` section (point at the new tables).
- [ ] G.12.3 `RELEASE_NOTES.md` — add v3.0.0 entry: "schema flatten + PR/AR data merger — 12 tables → **2 base tables** (`transactions` + `daily_balances`); ledger limits collapsed into `daily_balances.metadata`. PR and AR demo data now share the same tables; the `pr_*` legacy table family is fully retired. JSON metadata uses portable `TEXT` + SQL/JSON path syntax (system compatibility requires Postgres 17+). Computed views and dataset contracts unchanged. Dashboards visually identical to v2.x. New `docs/Schema_v3.md` documents the feed contract for the Data Integration Team persona."
- [ ] G.12.4 Defer `SPEC.md` — per goal note, that gets a separate pass after Phase G.
- [ ] G.12.5 Commit — `Phase G.12: sync docs to the two-table schema and add v3.0.0 release notes`.

---

## Phase G.13 — Verify ETL example queries

The persona tests Phase G's success: can a Data Integration Team member ETL upstream data into these two tables and have the dashboards work?

- [ ] G.13.1 Working through `docs/Schema_v3.md` example queries by hand against the demo Postgres — every query should run, every result should match what the dashboard shows.
- [ ] G.13.2 Add a few of those queries as `tests/test_etl_examples.py` so the doc doesn't drift silently.
- [ ] G.13.3 Commit — `Phase G.13: lock ETL example queries with regression test`.

---

## Phase G.14 — Deploy + e2e + release

- [ ] G.14.1 `demo apply --all` — schema + new seed applied to local Postgres.
- [ ] G.14.2 `deploy --all --generate` — all resources CREATION_SUCCESSFUL. Same dashboards, same visuals — only the underlying datasets' SQL changed.
- [ ] G.14.3 `cleanup --dry-run` — no stale tagged resources.
- [ ] G.14.4 `./run_e2e.sh --parallel 4` — full green (API + browser). Browser e2e is the canary that the visible dashboard didn't regress.
- [ ] G.14.5 Tag v3.0.0, push.

---

## Decisions to make in flight

- **SQL/JSON path ergonomics.** First few PR dataset rewrites in G.9 will reveal whether `JSON_VALUE(metadata, '$.card_brand')` is acceptable or unbearable in dataset SQL. If unbearable, fall back to a `transaction_metadata` sidecar table (option B from G.0.3) — three-table outcome still a 75% win. Decide by G.9.3.
- **Dropping merchants → accounts (G.0.8).** First PR dataset rewrite touching merchants (G.9.1) is the test. If `daily_balances WHERE account_type='merchant_dda'` reads naturally, ship; if it requires gymnastics, restore a small `pr_merchants` reference table.
- **External counterparty representation.** FRB Master Account, processors — they need `daily_balances` rows for the GL-vs-Fed drift check to compute against something. Decide structure during G.3.2 (probably daily snapshots fed in deterministically alongside internal activity).
- **`computed_balance` view name collisions.** Old views `ar_computed_ledger_daily_balance` / `ar_computed_subledger_daily_balance` either get renamed (collapse into one `computed_daily_balance`) or stay paired. Probably collapse — they're shape-identical now that ledger and sub-ledger live in one table.
- **`postings_per_transfer` indexed lookup.** Many drift / rollup queries group by `transfer_id`; the new flat table needs an index. Validate during G.6 / G.7 that pagination on the demo size (~3000 rows) doesn't degrade.
- **PR `is_returned`, `return_reason`, `payment_status`.** PR has several enum-like columns the dashboards filter on. JSONB or first-class columns? For columns with consumers in dataset SQL, first-class is faster and clearer. Probably first-class for any column that appears in a `WHERE` or `GROUP BY` of a current dataset.

---

## Phase G carry-over

Tech debt and follow-ups identified during Phase G have moved to **Phase I (queued)** below — see "Schema cleanup carry-over from Phase G" for PR-coexistence filters in AR views and drift-view PR-row leakage.

---

## Risks

- **PR dataset rewrites are the long tail (G.9 — 11 commits).** PR has more domain-specific metadata than AR and the chain-of-custody view (`pr_payment_recon_view`) is the most complex SQL in the codebase. Expect this phase to take longer per commit than AR migrations. Don't bundle.
- **DatasetContract is the safety net — abuse it.** Every dataset migration is a SQL rewrite; the test that asserts "SQL projection matches contract" is the difference between safe and terrifying. If a contract assertion fails, STOP — don't loosen the contract; the new SQL is wrong.
- **Browser e2e doesn't run until G.14.** Dataset SQL changes go through API e2e (dataset health checks) but visual rendering only validates at the very end. If a dataset's SQL is subtly wrong (e.g., NULL handling differs, ordering changes), it might pass DatasetContract + API health and still render badly. Mitigation: spot-check a couple of dashboards in the browser mid-phase (after G.5 and G.8) using `--skip-deploy browser` against the prior deploy. Won't catch new-SQL regressions but catches dual-write bugs.
- **Dual-write window inflates demo apply time.** Every posting writes twice during G.3 → G.10. Probably acceptable for the demo's ~few-thousand row scale; if `demo apply` slows past ~30s, batch the new-table inserts.
- **Determinism re-lock at G.11 is tedious but mechanical.** Don't fight it; just regenerate.
- **G.10 grep is the load-bearing safety check.** Drop too early and live datasets break in production. The grep has to be thorough — include both source and test files, both SQL and Python identifiers.
- **Postgres 17+ required for `demo apply`.** Pre-17 Postgres lacks SQL/JSON path syntax (`JSON_VALUE`, etc.). The portability convention forbids the Postgres-only fallbacks (`->>`, etc.). Mitigation: doc loudly in `docs/Schema_v3.md`, `README.md`, and CI; `demo apply` should fail-fast with a helpful error if it detects PG < 17.
- **JSON metadata extraction is unfamiliar to anyone used to plain columns.** Dataset SQL becomes `JSON_VALUE(metadata, '$.card_brand')` everywhere PR-specific or limit data is read. First few rewrites in G.6 / G.9 will be slow as the muscle memory builds. Mitigation: write a small SQL helper view per metadata-rich entity (e.g., `pr_sales_metadata` view that exposes `card_brand`, `cashier`, etc. as columns over the underlying transactions row) IF the dataset SQL becomes painful — but resist building it preemptively.
- **Sidecar fallback if SQL/JSON proves unbearable.** Three-table outcome (`transactions` + `daily_balances` + `transaction_metadata` sidecar) is still a 75% reduction from today's 12. Don't let the ideal-2 outcome become an enemy of shipping. Decide by G.9.3 per the in-flight decisions list.
- **SPEC.md gets messier mid-phase, not cleaner.** Phase G doesn't touch SPEC.md (per Out of Scope) but the SPEC's account-model description gets staler with every commit. Live with it; the rewrite is the next phase.

---

## After Phase G

- **SPEC.md rewrite** — DONE in commit `20def68` (v3.0.0 + 1).
- **Phase H — walkthrough handbook.** Demo-side training docs that double as a dashboard usability audit. Plan below.
- **Phase I (queued).** Customer ETL guide, persona dashboard split, layout redesigns, schema cleanup. Plan below.

---

# PLAN — Phase H: walkthrough handbook

Goal: ship a Sasquatch-themed handbook on the existing GitHub Pages site that walks operators through every exception class on the demo dashboards. Two purposes:

1. **Training material** the user can socialize with real teams (GL Reconciliation for AR; Merchant Support for PR).
2. **Dashboard usability audit** — any walkthrough that's awkward to write step-by-step is design feedback for Phase I redesigns.

Three deliverables:

1. **AR walkthroughs** — 17 markdown files (3 rollups + 14 per-check), one per visual section on the AR Exceptions sheet. (2 sample walkthroughs already drafted in `docs/AR_Walkthroughs.md`; H.1 splits them into per-file structure.)
2. **PR walkthroughs** — ~7 markdown files organized by *operator question* rather than check name (Merchant Support is reactive, not monitoring).
3. **Sasquatch-themed handbook pages** — AR Handbook + PR Handbook index pages with full custom CSS, hero imagery, and palette derived from the existing theme presets.

Plus a **screenshot spike** — leverage the e2e Playwright harness to generate focused screenshots that toggle inline in each walkthrough step.

Conventions (Phase H specific):

- Branch: `phase-h-handbook`, cut from `main` at v3.0.1.
- Walkthrough commits batched by group (rollups / baseline / CMS for AR; pipeline / exceptions for PR) to keep PR diffs reviewable.
- Demo numbers in walkthroughs come from `*/demo_data.py` constants — verifiable byte-for-byte against the deployed dashboard.
- Walkthrough skeleton (locked from H.0): Story → Question → Where to look → What you'll see in the demo → What it means → Drilling in → Next step + cross-references.
- Each walkthrough cross-references related walkthroughs at the bottom (e.g., Stuck in Suspense ↔ Suspense Non-Zero ↔ Reversal Uncredited).
- MkDocs Material stays — extend with custom CSS + hero, don't replace.
- No new tests required for docs-only changes; `mkdocs serve` smoke after each batch is the validation.
- Release: v3.1.0 (additive — new docs, no schema or behavior change).

---

## Phase H.0 — Pin decisions

- [ ] H.0.1 **Walkthrough doc location.** `docs/walkthroughs/ar/` + `docs/walkthroughs/pr/`. Recommend: locked.
- [ ] H.0.2 **File naming convention.** Kebab-case slugs from check name (e.g., `stuck-in-internal-transfer-suspense.md`); nav order comes from `mkdocs.yml`, not filenames.
- [ ] H.0.3 **Skeleton lock.** 7-section template (Story / Question / Where to look / What you'll see in the demo / What it means / Drilling in / Next step) confirmed from sample iteration. Locked.
- [ ] H.0.4 **Index page count.** Separate AR Handbook + PR Handbook (different personas → different mental models). Locked.
- [ ] H.0.5 **Sasquatch theming source.** Pull palette from `common/theme.py` `sasquatch-bank` + `sasquatch-bank-ar` presets (single source of truth — same colors the rendered dashboards use).
- [x] H.0.6 **Hero imagery concept.** Locked on (b) — Sasquatch wordmark + clean palette only. Wordmark is SVG (text + footprint), no imagery commission. Escalate to (a) only if (b) lands flat after live review.
- [ ] H.0.7 **Screenshot spike scope (per H.2).** Per-step screenshots embedded in walkthroughs as collapsed `<details>` blocks (scannable for repeat readers, one-click reveal for first-timers).
- [ ] H.0.8 **PR walkthrough operator-question list.** Drafted in H.6.2; review and lock there.
- [ ] H.0.9 **Release version.** v3.1.0 — additive, no breaking changes.
- [ ] H.0.10 **GitHub Pages deploy.** Existing CI workflow already builds Pages; verify no permission additions needed for hero images / custom CSS.

---

## Phase H.1 — Restructure docs and migrate existing samples

- [ ] H.1.1 Create `docs/walkthroughs/ar/` and `docs/walkthroughs/pr/`.
- [ ] H.1.2 Move existing rollup sample to `docs/walkthroughs/ar/expected-zero-eod-rollup.md` (extracted from `docs/AR_Walkthroughs.md`).
- [ ] H.1.3 Move existing per-check sample to `docs/walkthroughs/ar/stuck-in-internal-transfer-suspense.md`.
- [ ] H.1.4 Delete `docs/AR_Walkthroughs.md` (content fully migrated to per-file structure).
- [ ] H.1.5 Update `mkdocs.yml` nav placeholder (final nav lands in H.5).
- [ ] H.1.6 Commit — `Phase H.1: restructure walkthroughs into per-file layout`.

---

## Phase H.2 — Screenshot spike

Spike question: can we leverage the e2e Playwright fixtures to generate focused, cropped screenshots of individual visuals that walkthroughs can reference inline?

- [x] H.2.1 Inventory existing helpers: `tests/e2e/browser_helpers.py` provides `webkit_page`, `generate_dashboard_embed_url`, `wait_for_dashboard_loaded`, `wait_for_visual_titles_present`, `click_sheet_tab`, plus the marker-attribute pattern in `click_first_row_of_visual`. Tall-viewport trick from `test_ar_sheet_visuals.TALL_VIEWPORT` (1600x12000) defeats QuickSight's below-the-fold virtualization.
- [x] H.2.2 Built `scripts/generate_walkthrough_screenshots.py`. Three iterations to land:
  - Playwright `locator.has_text` doesn't match QuickSight title labels reliably — use `page.evaluate` with exact `innerText.trim()` match instead.
  - QuickSight virtualizes below-the-fold visuals; "scroll-then-back-to-top" unloads them again. Solution: tall viewport so everything stays hydrated.
  - `page.screenshot(clip=...)` fails on 12000-tall viewport ("clipped area outside resulting image"). Solution: marker-attribute the target element + Playwright `locator.screenshot()` for per-element capture.
- [x] H.2.3 Three shots produced for Stuck in Suspense walkthrough (KPI / table / aging chart). All readable, tightly cropped, ~20-50KB each.
- [x] H.2.4 Walkthrough updated with `<details>`-toggled screenshots. Each section reads cleanly text-first, screenshots reveal on click. MkDocs Material `<details>` works out of the box.
- [x] H.2.5 **GO**. Spike succeeded. Commit script + 3 screenshots + updated walkthrough.
- [x] H.2.6 Freshness policy: screenshots are committed under `docs/walkthroughs/screenshots/`, regenerated on demand via `python scripts/generate_walkthrough_screenshots.py`. Not a CI step. Each walkthrough author runs the script after editing the SHOTS list, eyeballs the output, commits.

**Lesson learned in H.2.4**: writing the existing walkthroughs without screenshots produced a hallucinated table layout (originator/recipient name columns that don't actually exist in the visual). Each H.4 / H.7 walkthrough must be verified against the rendered visual — either by capturing screenshots first and writing prose to match, or by reading the visual's `Values=[...]` block in `*/visuals.py`. Add a "verify column list against visual definition" step to the standard walkthrough authoring checklist.

---

## Phase H.3 — Sasquatch-themed MkDocs site

- [x] H.3.1 AR-dominant palette — `sasquatch-bank-ar` tokens mirrored as CSS custom props in `docs/stylesheets/sasquatch.css`. PR palette tokens reserved for per-page accents in H.7.
- [x] H.3.2 Custom CSS at `docs/stylesheets/sasquatch.css` (palette overrides + hero block + walkthrough card grid). Wired via `mkdocs.yml` `extra_css`. Material `palette: { primary: custom, accent: custom }` so overrides take effect.
- [x] H.3.3 Hero imagery — option (b) wordmark only (no commissioned art). `docs/img/snb-wordmark.svg` (~820 B), `docs/img/favicon.svg` (~400 B), `docs/img/snb-mark.svg` (~400 B). Negligible Pages payload.
- [x] H.3.4 Sasquatch wordmark + favicon in `docs/img/`. Wired via `theme.logo: img/snb-mark.svg` and `theme.favicon: img/favicon.svg`.
- [x] H.3.5 Skipped — CSS-only hero block on `index.md` works without `home.html` override. Revisit only if landing pages need structural change.
- [x] H.3.6 `mkdocs build --strict` clean; live serve confirms hero, logo, favicon, and CSS all 200; `index.html` carries the hero block with wordmark.
- [x] H.3.7 Commit — `Phase H.3: Sasquatch-themed MkDocs site (palette + hero + custom CSS)`.

---

## Phase H.4 — AR walkthroughs

15 walkthroughs to produce (the 2 samples are done). Each follows the locked skeleton from H.0.3. Each carries demo-anchored numbers from `account_recon/demo_data.py`. If H.2 went green, each carries inline screenshots toggled via `<details>`.

- [x] H.4.1 **Batch A — rollups** (2 files):
  - `two-sided-post-mismatch-rollup.md`
  - `balance-drift-timelines-rollup.md`
  - Commit: `Phase H.4.A: AR rollup walkthroughs`.
- [x] H.4.2 **Batch B — baseline checks** (5 files):
  - `sub-ledger-drift.md`
  - `ledger-drift.md`
  - `non-zero-transfers.md`
  - `sub-ledger-limit-breach.md`
  - `sub-ledger-overdraft.md`
  - Commit: `Phase H.4.B: AR baseline check walkthroughs`.
- [x] H.4.3 **Batch C — CMS-specific** (8 files; Stuck in Suspense is already done):
  - `sweep-target-non-zero.md`
  - `concentration-master-sweep-drift.md`
  - `ach-origination-non-zero.md`
  - `ach-sweep-no-fed-confirmation.md`
  - `fed-card-no-internal-catchup.md`
  - `gl-vs-fed-master-drift.md`
  - `internal-transfer-suspense-non-zero.md`
  - `internal-reversal-uncredited.md`
  - Commit: `Phase H.4.C: AR CMS-specific check walkthroughs`.
- [x] H.4.4 Cross-reference pass: each walkthrough's "Related" footer links neighbor walkthroughs. Replaced 7 `(forthcoming)` placeholders with real links across 4 files; added the missing Related section on `expected-zero-eod-rollup.md`; added the Two-Sided Post Mismatch Rollup link to both per-check ACH/Fed walkthroughs. Commit: `Phase H.4: cross-reference AR walkthroughs`.

---

## Phase H.5 — AR Handbook index

- [x] H.5.1 Built `docs/handbook/ar.md` with the H.3 hero block, "The bank" preamble (cribbed from `Training_Story.md`), "The morning routine" section, three rollup cards under "Morning checks", and 14 per-check cards split into Baseline (5) and CMS-specific (9) groups. Footer references `Training_Story.md` + `Schema_v3.md`.
- [x] H.5.2 mkdocs.yml nav — collapsed walkthroughs under a single "AR Handbook" parent with `Overview: handbook/ar.md` first; also added `Schema_v3.md` to nav (clears the prior "exists in docs but not in nav" build info).
- [x] H.5.3 mkdocs build --strict clean; live serve confirms `/handbook/ar/` 200, all 17 card links resolve to walkthrough pages 200, footer `[Account Structure]` / `[Schema v3]` links rewritten to directory URLs and 200.
- [x] H.5.4 Commit — `Phase H.5: AR Handbook index page`.

---

## Phase H.6 — PR walkthrough inventory + organization

- [x] H.6.1 Inventory PR exception cases from `payment_recon/demo_data.py` and `payment_recon/datasets.py`:
  - 5 PR exception checks: settlement exceptions, payment returns, sale↔settlement mismatch, settlement↔payment mismatch, unmatched external txns
  - Payment Reconciliation matching workflow (the side-by-side mutual filter)
  - Pipeline traversal scenarios (Sales → Settlements → Payments → External Txns)
  - Plant data: 10 unsettled sales (Yeti + Cryptid), 5 returns (2 Sasquatch / 1 Yeti / 2 Cryptid), 2 failed settlements (stl-0001/0002), 3 sale↔settlement mismatches (±$10), 3 settlement↔payment mismatches (±$5), ~13 orphan ext txns (8 recent / 5 older), 4 unmatched payments. Every 6th batched ext_txn drifts $5–$40.
- [x] H.6.2 Translate inventory into operator-question format. Draft list (lock in this step):
  - "Where's my money for [merchant X]?" — pipeline traversal
  - "Did all merchants get paid yesterday?" — KPI scan
  - "Why is this external transaction unmatched?" — Payment Recon tab
  - "Why does this settlement look short?" — sale↔settlement mismatch
  - "Why is there a payment but no settlement?" — settlement↔payment mismatch
  - "How much did we return last week?" — payment returns
  - "Which sales never made it to settlement?" — settlement exceptions
- [x] H.6.3 Confirm scope: ~7 walkthroughs. Lock list.
- [x] H.6.4 No commit (planning step, captured in this PLAN.md).

---

## Phase H.7 — PR walkthroughs

Same skeleton as AR, framed around the operator question rather than the check name. The "Story" section is the merchant's frustration; the "Next step" is the resolution back to the merchant.

- [x] H.7.1 **Batch A — pipeline + matching** (~3 files):
  - `wheres-my-money-for-merchant.md`
  - `did-all-merchants-get-paid.md`
  - `why-is-this-external-transaction-unmatched.md`
  - Commit: `Phase H.7.A: PR pipeline + matching walkthroughs`.
- [x] H.7.2 **Batch B — exceptions** (~4 files):
  - `why-does-this-settlement-look-short.md`
  - `why-doesnt-this-payment-match-the-settlement.md` *(renamed from `why-is-there-a-payment-but-no-settlement.md` — original title implied orphan-payment shape, but the underlying check is settlement↔payment **amount mismatch**, not missing-settlement)*
  - `how-much-did-we-return.md`
  - `which-sales-never-made-it-to-settlement.md`
  - Commit: `Phase H.7.B: PR exception walkthroughs`.
- [ ] H.7.3 Cross-reference pass. Commit.

---

## Phase H.8 — PR Handbook index

- [ ] H.8.1 Build `docs/handbook/pr.md`:
  - Hero block
  - Preamble: SNB merchant-acquiring side; Merchant Support's reactive posture
  - "Common merchant questions" section: walkthrough cards organized by question topic
  - "Investigating exceptions" section: exception walkthrough cards
  - Footer: same Schema_v3 + Training_Story links
- [ ] H.8.2 Update `mkdocs.yml` nav — add "PR Handbook" landing + nested walkthroughs.
- [ ] H.8.3 `mkdocs serve` smoke.
- [ ] H.8.4 Commit — `Phase H.8: PR Handbook index page`.

---

## Phase H.9 — README integration

- [ ] H.9.1 Add a "Demo Docs" section to `README.md` near the top, with one-liner pitches for AR + PR Handbooks and the deployed Pages URL.
- [ ] H.9.2 Verify `mkdocs.yml` `site_url` is set correctly (matches GitHub Pages deployed URL).
- [ ] H.9.3 Commit — `Phase H.9: link demo handbooks from README`.

---

## Phase H.10 — Deploy + ship

- [ ] H.10.1 Push branch; verify GitHub Actions builds Pages successfully.
- [ ] H.10.2 Browse the deployed site — every walkthrough loads, every link resolves, hero renders, screenshots load (if H.2 went green).
- [ ] H.10.3 Spot-check one walkthrough end-to-end against the deployed AWS dashboard — every dollar amount + row count matches.
- [ ] H.10.4 Tag v3.1.0, push tag.
- [ ] H.10.5 Open PR `phase-h-handbook` → `main`; merge.

---

## Decisions to make in flight

- **Hero imagery realism vs abstraction.** The hero is brand-defining. If wordmark-only feels flat in mkdocs serve preview, escalate to PNW silhouette + Sasquatch icon before committing.
- **Combined SNB palette vs separate AR / PR palettes.** The two existing themes (`sasquatch-bank` for PR, `sasquatch-bank-ar` for AR) intentionally differ to keep the dashboards visually distinct. If the docs site uses both palettes (one per handbook), it's visually busy; if it uses one shared SNB palette, the dashboards-vs-docs visual link weakens. Recommend: shared SNB-neutral palette with section-accent shifts (AR pages tinted toward AR theme accent, PR pages toward PR accent).
- **PR walkthroughs may not parallelize cleanly.** "By operator question" framing means some walkthroughs traverse the dashboard differently from others (some walk forward through tabs, some open at Payment Recon and stay there). Skeleton may need flexing per walkthrough rather than rigid templating. Acceptable — don't over-template.
- **Screenshot freshness policy.** If H.2 ships screenshots, every dashboard change risks stale screenshots. Lean toward "illustrative" disclaimer + on-demand regeneration script rather than per-deploy CI regeneration.

---

## Risks

- **Spike risk on screenshots (H.2).** E2E Playwright fixtures are designed for assertion-driven tests, not screenshot generation. The screenshot path may need new helpers for visual cropping, hover state, focus state. Time-box H.2 to one day; if it doesn't land cleanly, ship walkthroughs text-only and revisit later.
- **MkDocs custom CSS tax.** Material's customization surface is broad but every override is a maintenance liability when Material upgrades. Keep the custom CSS minimal — palette + hero + maybe a card grid. Resist deeper structural overrides.
- **Demo numbers drift if seed changes.** Walkthroughs cite specific dollar amounts and row counts from `demo_data.py`. If anyone tweaks the seed, walkthroughs go stale silently. Mitigation: document this risk in `CLAUDE.md` so future generator changes prompt walkthrough re-verification. (A CI test that grep-extracts dollar amounts and asserts they match the seed is brittle; skip.)
- **Cross-reference link rot.** 17 + 7 = 24 walkthroughs cross-referencing each other can break silently when files rename. Mitigation: MkDocs `markdown_extensions: pymdownx.snippets` + relative links so a broken link fails the build. Also: settle the slug names early (H.1, H.4.1) so renames are rare.
- **Sample walkthrough numbers may be wrong.** The Stuck in Suspense walkthrough cites `$6,155.00 total` and specific 11-day / 23-day stuck transfers. Verify against actual seed during H.1.3 — if wrong, fix and treat as case study for the demo-numbers-drift risk above.

---

# PLAN — Phase I (queued)

Items deferred from Phase H scope, parked here so they aren't lost. Each is independent and can phase up on its own merit. Inputs from Phase H walkthroughs (which surface dashboard friction concretely) will inform priority and shape.

## Persona-driven dashboard layout redesigns

- **AR Exceptions tab redesign.** Sheet is dense (3 rollups + 14 checks + aging bars + 2 drift timelines). Phase H walkthroughs will surface which sections are friction-heavy; that's the input for redesign. Likely shape: per-persona view modes ("morning check" vs. "deep investigation"), or progressive disclosure of CMS-specific checks behind a category toggle.
- **PR pipeline tab structure.** Under the shared-base model (Phase G), Sales / Settlements / Payments are values of `transfer_type`, not separate entities. Current per-step tab structure is preserved from the pre-flatten era. Operator-question walkthroughs in Phase H may surface whether the per-step tab structure helps or fights merchant-support workflow. Decide redesign based on what those walkthroughs show.

## E2E visual-semantics coverage

Surfaced during Phase H.4.B: the Ledger Drift and Sub-Ledger Drift KPIs on the AR Exceptions sheet were counting *every* `(account, date)` row from the drift datasets, not just the rows where `drift_status = 'drift'`. The bug went unnoticed because:

- The drift datasets are shared with the Balances sheet (where unfiltered counts make sense).
- API e2e tests assert dataset *health* (rows return, no SPICE errors) but not row *content* — they don't check that the visible KPI count corresponds to anything meaningful from the planted demo scenarios.
- Browser e2e tests assert visual *presence* (titles render, tables have rows) but not visual *semantics* — they don't assert that the rendered KPI value matches the count of planted exception rows.

The fix landed via two sheet-scoped pinned `CategoryFilter`s on `drift_status='drift'` (see `account_recon/filters.py` and the H.4.B commit). The deeper Phase I work is the test gap:

- **Per-check KPI assertion.** For each AR Exceptions KPI (5 baseline + 9 CMS-specific + 3 rollups), assert the rendered count equals the row count of the underlying dataset filtered to its expected scope (`drift_status='drift'`, `non_failed_imbalance > 0`, etc.). Catch dataset-vs-visual filter drift the moment it ships.
- **Per-check planted-row sanity.** For checks driven by `_*_PLANT` constants in `account_recon/demo_data.py`, assert the dataset returns the planted rows (and only the planted rows where the check is "1 plant = 1 row"; for sticky-drift / sticky-overdraft checks, assert at least the planted rows are present plus a documented multiplier for day-roll-forward).
- **Layer choice.** API e2e is the right home — it's faster than browser, runs deterministically off the deployed datasets, and is where dataset health already lives. Browser e2e remains the rendering canary, not the semantics canary.

Inputs: incident debugging notes are in the H.4.B commit; the filter that was missing is the test contract.

## Schema cleanup carry-over from Phase G

- **PR-coexistence filters in AR views.** `ar_subledger_overdraft` and `ar_subledger_daily_outbound_by_type` carry an `account_id NOT LIKE 'pr-%'` filter. Necessary today because PR + AR co-reside in the same `daily_balances` / `transactions` tables and the entity-scoped views (drift, overdraft) would otherwise surface PR rows in AR exceptions (G.6 leak: 556 spurious overdraft rows). Phase I deletes these — a single-feed real persona has no parallel PR ledger to filter out. Grep target: `pr-%` in `demo/schema.sql`. The right replacement is the `account_type` discriminator from G.0.12 (`gl_control`, `dda`, …), scoped to whatever account_types the AR persona owns.
- **AR drift views leak benign zero-drift PR rows** (744 sub-ledger, 93 ledger). Filtered out of Exceptions tab by `drift > 0`; pollutes Balances tab counts. Same Phase I fix as above resolves it.
- **Unified account dimension table.** AR currently keeps `ar_ledger_accounts` and `ar_subledger_accounts` as separate dimension tables. A single "all accounts" table aligns with the denormalize-don't-add-tables north star and would simplify some queries. Low priority; ship when there's a query that benefits.

## Customer-facing customization handbook

- `docs/Schema_v3.md` is the persona contract for the Data Integration Team. A longer-form customer-facing customization guide (mapping production-system tables → the two base tables, common pitfalls, performance tips, replacing dataset SQL while preserving DatasetContract) is a natural follow-up to the demo-side walkthroughs in Phase H. Deliverable shape: a "Customization Handbook" sibling to AR / PR Handbooks.

## Persona dashboard split (originally Phase E)

- Still queued. The Phase H walkthroughs (and any layout redesigns from the items above) provide better signal on what a persona-scoped dashboard split should look like.

## New Phase I-shaped surfaces (from Training Story personas not yet served)

- **Fraud team surface.** "Search for transactions that break limits set on the accounts" — investigative, not monitoring. Different UX paradigm from PR/AR. Probably its own analysis with a search-driven entry point and ad-hoc filter chips. Needs workflow elicitation before planning visuals.
- **AML team surface.** "Detect transactions/balances outside statistical average and find patterns." Likely needs QuickSight forecasting / anomaly insights features and visual primitives we don't currently use. Needs workflow elicitation before planning visuals.
