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

Tech debt and follow-ups identified during Phase G have moved forward — see **Phase I.4** below for the PR/AR cross-visibility audit (supersedes the earlier "PR-coexistence filters" cleanup) and **Phase J (queued)** for the remaining schema-level follow-ups.

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
- **Phase I — PR KPI semantics + AR daily statement sheet.** Two committed deliverables. Plan below.
- **Phase J (queued).** Persona dashboard layout redesigns, schema cleanup carry-over, customization handbook, persona dashboard split, fraud-team surface. Plan below.

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
- [x] H.7.3 Cross-reference pass. Commit.

---

## Phase H.8 — PR Handbook index

- [x] H.8.1 Build `docs/handbook/pr.md`:
  - Hero block
  - Preamble: SNB merchant-acquiring side; Merchant Support's reactive posture
  - "Common merchant questions" section: walkthrough cards organized by question topic
  - "Investigating exceptions" section: exception walkthrough cards
  - Footer: same Schema_v3 + Training_Story links
- [x] H.8.2 Update `mkdocs.yml` nav — add "PR Handbook" landing + nested walkthroughs.
- [x] H.8.3 `mkdocs serve` smoke.
- [x] H.8.4 Commit — `Phase H.8: PR Handbook index page`.

---

## Phase H.8.5 — Data Integration Team Handbook

Third handbook, parallel to AR + PR. Audience: SNB's **Data Integration Team** — engineers writing the ETL that populates `transactions` + `daily_balances`. The user flagged this persona repeatedly in Phase G ("data team needs to know **WHY** they should populate a column"). This phase converts `Schema_v3.md` from a contract reference into a training experience and ships an exemplary CLI helper customers can crib from.

Decisions locked (2026-04-20 conversation):
- 5 walkthroughs (full inventory below)
- Persona name in hero: **Data Integration Team** (matches AR/PR pattern)
- New CLI: `quicksight-gen demo etl-example` emits exemplary INSERT statements; walkthroughs reference its output

### H.8.5.A — Schema_v3.md WHY-expansion

Reference doc gets training warmth without becoming a tutorial. Markdown only, no code.

- [x] H.8.5.A.1 New "Getting Started for Data Teams" preamble at the top of `docs/Schema_v3.md` — frames the two-table contract from the ETL author's POV (what columns are mandatory, what's denormalized for query performance, what's metadata vs first-class).
- [x] H.8.5.A.2 Add a **Why** column (or sentence per row) to the existing column-spec tables — *"if you skip this, what dashboard breaks?"*. Examples: `parent_transfer_id` skipped → PR pipeline traversal can't link external_txn back to sale; `metadata.card_brand` skipped → Sales tab card-brand pivot empty; `origin = 'external_force_posted'` skipped → AR can't separate operator-initiated drift from fed-forced drift.
- [x] H.8.5.A.3 Cross-link forward to the H.8.5.D walkthroughs from each section (placeholder TODOs filled in once D ships).
- [x] H.8.5.A.4 `mkdocs build --strict` clean; live serve confirms the new TOC entries render.
- [x] H.8.5.A.5 Commit — `Phase H.8.5.A: expand Schema_v3 with per-key WHY narrative`.

### H.8.5.B — `quicksight-gen demo etl-example` CLI command

Exemplary ETL output customers can crib. Reads from the deployed demo Postgres (or stdin SQL dump), emits a small set of canonical INSERT statements demonstrating each metadata-key pattern. Lives next to existing `demo schema` / `demo seed` / `demo apply`.

- [x] H.8.5.B.1 Design the command surface:
  - `quicksight-gen demo etl-example --all -o demo/etl-examples.sql` — emits all examples
  - `quicksight-gen demo etl-example payment-recon` / `account-recon` — app-scoped
  - Examples are SQL fragments with `-- WHY:` comments inline
- [x] H.8.5.B.2 Inventory the canonical patterns to emit (3-5 each side):
  - PR: sale insert, settlement insert (with parent_transfer_id chain), payment insert, external_txn insert (one-to-many vs one-to-one), return insert (metadata.is_returned / return_reason)
  - AR: customer DDA transfer (internal, two-leg net-zero), force-posted ACH (origin = 'external_force_posted'), sweep (clearing_sweep type, ledger-direct posting), limit-breach setup (daily_balances.metadata limit config), GL drift recompute baseline
- [x] H.8.5.B.3 Implement: new `cli.py` subcommand + `etl_examples.py` module per app (mirrors `demo_data.py` structure). Output is plain SQL with comment headers; no DB connection required for `etl-example` (unlike `demo apply`).
- [x] H.8.5.B.4 Tests in `tests/test_demo_etl_examples.py`: every emitted INSERT parses; every example references a real column in the schema; comment headers reference real metadata keys.
- [x] H.8.5.B.5 Commit — `Phase H.8.5.B: demo etl-example CLI command`.

### H.8.5.C — Walkthrough inventory (dry pass)

Lock the 5-walkthrough list. No commit (planning step, captured in this PLAN).

- [x] H.8.5.C.1 Walkthrough list (locked):
  1. **How do I populate `transactions` from my core banking system?** — the canonical mapping walkthrough. Maps a hypothetical core-banking source schema → the two-table target. References `etl-example` output.
  2. **How do I prove my ETL is working before going live?** — validation invariants (transfer legs net-to-zero, daily_balance recompute matches stored, no orphan parent_transfer_id chains). Includes pytest-style assertion examples and a "what dashboard you should see" checklist.
  3. **How do I tag a force-posted external transfer correctly?** — the `origin` field + parent_transfer_id chain mechanics. Why force-posted matters for AR exception classification. References AR's GL-vs-Fed-Master-Drift walkthrough as the downstream consumer.
  4. **How do I add a metadata key without breaking the dashboards?** — extension contract. Schema rules (must be valid JSON, must use SQL/JSON path syntax, no JSONB types), dataset SQL pattern (`JSON_VALUE(metadata, '$.your_key')`), how to add a column to a Pivot/visual without refreshing SPICE (we're direct query).
  5. **What do I do when the demo passes but my prod data fails?** — debugging recipes. Common-pitfall checklist organized by symptom (KPI shows 0; visual shows N/A; drift KPI fires unexpectedly; date filter excludes everything).

### H.8.5.D — Write walkthroughs

- [x] H.8.5.D.1 **Batch 1 — populate + validate** (~2 files, the foundational pair):
  - `how-do-i-populate-transactions.md`
  - `how-do-i-prove-my-etl-is-working.md`
  - Commit: `Phase H.8.5.D.1: ETL populate + validate walkthroughs`.
- [x] H.8.5.D.2 **Batch 2 — extend + debug** (~3 files):
  - `how-do-i-tag-a-force-posted-transfer.md`
  - `how-do-i-add-a-metadata-key.md`
  - `what-do-i-do-when-demo-passes-but-prod-fails.md`
  - Commit: `Phase H.8.5.D.2: ETL extend + debug walkthroughs`.
- [x] H.8.5.D.3 Cross-reference pass — every walkthrough links to its 1-2 most-related siblings + the relevant Schema_v3 section + the relevant AR/PR walkthrough that consumes the populated data. Commit.

### H.8.5.E — Data Integration Handbook landing

- [x] H.8.5.E.1 Build `docs/handbook/etl.md`:
  - Hero block (third handbook palette consistent with AR/PR; persona = "Data Integration Team")
  - Preamble: SNB's Data Integration Team owns the upstream → two-table mapping; their attitude (from PLAN line 13) — "what do I have a database server that can do fancy queries for unless I use it?"
  - "The contract" section: pointer to Schema_v3.md as source of truth + summary of the two-table model
  - "The walkthroughs" cards: 5 walkthroughs grouped as Foundational (populate, validate) + Extension (tag, add-key) + Debug (demo-vs-prod)
  - "The exemplary helper" section: pointer to `quicksight-gen demo etl-example` output
  - Footer: Schema_v3 + Training_Story links (same pattern as AR/PR landings)
- [x] H.8.5.E.2 Update `mkdocs.yml` nav — third handbook parent with `Overview: handbook/etl.md` first + 5 nested walkthroughs.
- [x] H.8.5.E.3 `mkdocs build --strict` clean; live serve confirms `/handbook/etl/` 200, all 5 card links resolve.
- [x] H.8.5.E.4 Commit — `Phase H.8.5.E: Data Integration Handbook index page`.

### H.8.5.F — Cross-link cleanup

- [x] H.8.5.F.1 Update AR + PR handbook landings (`docs/handbook/ar.md`, `docs/handbook/pr.md`) — Reference footers add a third pointer to the Data Integration Handbook ("the team that populates the data behind every walkthrough on this page").
- [x] H.8.5.F.2 Update `Training_Story.md` — add a closing pointer to the Data Integration Handbook for readers who came in via the bank narrative and want the populate-the-data view.
- [x] H.8.5.F.3 Commit — `Phase H.8.5.F: cross-link Data Integration Handbook from AR/PR/story`.

---

## Phase H.9 — README integration

- [x] H.9.1 Add a "Demo Docs" section to `README.md` near the top, with one-liner pitches for AR + PR + Data Integration Handbooks and the deployed Pages URL.
- [x] H.9.2 Verify `mkdocs.yml` `site_url` is set correctly (matches GitHub Pages deployed URL).
- [x] H.9.3 Commit — `Phase H.9: link demo handbooks from README`.

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

# PLAN — Phase I

Two committed deliverables. The PR semantics test is the smaller, mechanical companion to AR's already-shipped sibling. The daily statement sheet is the larger item: a new AR analysis sheet with end-to-end test coverage and a Data Integration Handbook companion walkthrough.

## I.1 — PR KPI semantics test (`tests/e2e/test_pr_kpi_semantics.py`)

The AR sibling shipped in commit `ddb247a` (29 tests across `TestKpiScope` + `TestPlantedRowsSurface`). PR has the same risk surface — KPI counts that drift from the dataset SQL underneath them — but no test catches it. Mirror the AR pattern.

**Shape.**
- [ ] File location: `tests/e2e/test_pr_kpi_semantics.py`. Same `pg_conn` fixture pattern as AR; same `pytestmark = [pytest.mark.e2e, pytest.mark.api]`.
- [ ] **Class 1 — `TestKpiScope`.** For each PR Exceptions KPI, assert `COUNT(*)` of the dataset SQL (with any sheet-pinned filter applied) equals `COUNT(*)` of the semantic-scope SQL implied by the KPI subtitle. Checks to cover:
  - Settlement Exceptions (`qs-gen-settlement-exceptions-dataset`)
  - Payment Returns (`qs-gen-payment-returns-dataset`)
  - Sale-Settlement Mismatch (`qs-gen-sale-settlement-mismatch-dataset`)
  - Settlement-Payment Mismatch (`qs-gen-settlement-payment-mismatch-dataset`)
  - Unmatched External Txns (`qs-gen-unmatched-external-txns-dataset`)
  - Payment Reconciliation tab KPIs that have a semantic scope (e.g., late-match count, days-outstanding strata).
- [ ] **Class 2 — `TestScenarioCoverage`.** PR has no `_PLANT` constants — scenarios emerge from natural generator branching. Asserts here mirror the existing `TestScenarioCoverage` block in `tests/test_demo_data.py` (which already documents min row counts per scenario shape) but run against the deployed Postgres rather than the in-memory generator. Keeps the test file self-contained — don't share fixtures between unit and e2e layers.

**AR equivalent — close it.** The AR semantics test is shipped and stable. Strike the line item from Phase I; the file itself stays as the reference implementation.

**Layer choice.** API e2e (matches AR sibling). Skips when `cfg.demo_database_url` is unset.

## I.2 — Per-account daily statement sheet (AR)

New AR sheet for *data-feed validation / sanity check*. Purpose: when the Data Integration Team wants to prove "my feed for account X on day Y reconciles end-to-end," this sheet is the artifact they diff against. Surfaces the three pre-flight invariants from the ETL Handbook's *How do I prove my ETL is working?* walkthrough in visual form — for a single account-day slice.

### I.2.A — Sheet shape (analysis + visuals)

- [x] **New sheet:** `SHEET_DAILY_STATEMENT = "sheet-daily-statement"` in `account_recon/constants.py`. Seventh sheet on the AR analysis (Getting Started / Balances / Transfers / Transactions / Exceptions / Daily Statement).
- [x] **Parameter controls** at the top:
  - `account_id` — single-select dropdown sourced from `ar_ledger_accounts` ∪ `ar_subledger_accounts` (or the unified account dim if I.2 ships after the unified-dim refactor).
  - `balance_date` — single-date picker, default = max balance_date in `daily_balances` for the selected account.
- [x] **KPI strip** (5 KPIs in one row): Opening Balance, Total Debits, Total Credits, Closing Balance (stored), Drift (stored − recomputed). Drift KPI uses the conditional-format pattern from AR Exceptions to flash red when non-zero.
- [x] **Transactions detail table:** every leg posted to the account on `balance_date`, sorted by `posted_at`. Columns: `posted_at`, `transfer_type`, `transfer_id`, `signed_amount`, `running_balance` (window function), `memo`, `metadata` extracts (counter-account from the matching leg, source key).
- [x] **Ledger-vs-recompute pair:** two side-by-side single-cell visuals — stored EOD balance from `daily_balances`, recomputed `Σ signed_amount` from `transactions` since account inception (or since prior reset). Side-by-side keeps the drift invariant visible row-by-row.

### I.2.B — Datasets

- [x] **No new SQL shapes.** Rides entirely on existing `transactions` + `daily_balances`. Either (a) one new dataset that takes both parameters and returns one row per leg + one summary KPI row, or (b) two narrower datasets (KPI summary; transaction detail). Decide once visuals are scaffolded — split if the SQL grows past ~50 lines.
- [x] New dataset(s) follow the existing `DatasetContract` pattern in `account_recon/datasets.py`.

### I.2.C — Test data

- [x] **Inventory existing demo coverage first.** Most account-days already have planted scenarios (drift, overdraft, sweep failures). Pick 3 worked examples for the handbook companion: one clean reconciling day, one drift day, one overdraft day. Add `TestScenarioCoverage` assertions confirming each shape exists in the deployed Postgres (not just the in-memory generator) — the unit-side coverage may not be enough if the new sheet exposes a corner the existing visuals don't. → **Done in `tests/e2e/test_ar_daily_statement.py`**: clean=`gl-1010-cash-due-frb` day -1, drift=`cust-900-0001-bigfoot-brews` (+$200 from `_SUBLEDGER_DRIFT_PLANT`), overdraft=`cust-900-0002-sasquatch-sips` ($45k outbound from `_OVERDRAFT_PLANT`).
- [x] **No new generator scenarios required** unless the inventory step finds a gap. If a gap exists, plant minimally — same `random.Random(42)` determinism rules; re-lock the SHA256 hash in `tests/test_demo_data.py`. → No gap found; existing plants cover all three worked examples.

### I.2.D — Test scripts at all levels

- [x] **Unit (`tests/test_account_recon.py`).** Sheet present in analysis, parameter controls wired, KPI strip + table + side-by-side visuals exist, dataset references resolve. `tests/test_dataset_contract.py` — new dataset contract(s) match the SQL projection. Also covers the `TestDailyStatementFilters` class locking parameter-bound filter wiring + `ParameterControl` widget choice (added 2026-04-20 after the FilterControl-disabled regression).
- [x] **API e2e (`tests/e2e/test_ar_deployed_resources.py` + `test_ar_dataset_health.py`).** New dataset deployed; new sheet present in dashboard JSON; parameters declared correctly. New file or block for parameter-driven SQL — assert that running the dataset SQL with substituted parameter values returns expected row shapes (e.g., "for `gl-1850` on the latest balance_date, the leg count from the dataset matches the leg count from a direct `transactions` query with the same filters"). → **Done:** conftest `ar_dataset_ids` includes the 2 new datasets (count=23); `test_ar_dataset_health.py::EXPECTED_COLUMNS` spot-checks summary (12 cols) + transactions (13 cols); `test_ar_dashboard_structure.py` asserts 6 sheets, `Daily Statement` visual count (6), 7 parameter declarations (adds `pArDsAccountId` + `pArDsBalanceDate`), 21 filter groups (adds `fg-ar-ds-account` + `fg-ar-ds-balance-date` + 4 I.3.A KPI-scope groups), 6 visual IDs on the new sheet. Parameter-driven SQL check lives in `tests/e2e/test_ar_daily_statement.py` (same three worked examples as I.2.C, executed directly against deployed Postgres).
- [x] **Browser e2e (`tests/e2e/test_ar_sheet_visuals.py` or new `test_ar_daily_statement.py`).** Sheet renders. Default account + date populates KPIs and table. Changing the account parameter updates the visuals (poll for KPI value change). Changing the date updates the table row count. Drift KPI visible on the planted-drift account-day. → **Done (basic):** `test_ar_sheet_visuals.py` parametrized over `Daily Statement` covers visual count (6) + 6 expected titles; `test_ar_state_toggles.py` confirms `Account` + `Balance Date` parameter controls render in the sheet-controls panel. **Deferred (richer):** picking an account from the dropdown and asserting drift KPI flips to the planted +$200 — the helpers exist (`set_dropdown_value`, `wait_for_kpi_value_to_change`, `read_kpi_value`) but adds 30+ seconds of browser interaction; defer to I.2.E walkthrough screenshot capture (same flow, different verb).
- [ ] **Browser e2e — handbook-tracking sheet.** Capture screenshots for the companion walkthrough using the existing `scripts/screenshot_getting_started.py` pattern.

### I.2.E — Handbook companion walkthrough

- [x] **New file:** `docs/walkthroughs/etl/how-do-i-validate-a-single-account-day.md`. Same 7-section locked skeleton as the existing ETL walkthroughs (Story / Question / Where to look / What you'll see / What it means / Drilling in / Next step / Related walkthroughs). → **Done 2026-04-20:** all 8 sections present (the locked skeleton actually has 8 — Related walkthroughs is its own section), tagged *Engineering walkthrough — Data Integration Team. Foundational.* matching the two prior foundational ETL pages.
- [x] **Story.** Data Integration Team analyst loaded a slice; the dashboard "looks fine" but they want to verify a specific account-day reconciles. Open this sheet with their account_id + date, eyeball the KPI strip, scan the table for unexpected legs, confirm drift is zero. → **Done:** opening reframes "the whole feed *looks* fine" → treasury asks "did `gl-1850` actually reconcile yesterday?" → Daily Statement is the screen that answers it. Three worked examples pinned to `tests/e2e/test_ar_daily_statement.py` (clean=`gl-1010` yesterday; drift=`cust-900-0001-bigfoot-brews` day-5 +$200; overdraft=`cust-900-0002-sasquatch-sips` day-6 -$45k closing).
- [x] **Cross-link.** Add to: → **Done 2026-04-20**, all four landed; `mkdocs build --strict` clean.
  - `mkdocs.yml` nav under Data Integration Handbook (between *populate* and *validate*). → between `how-do-i-populate-transactions.md` and `how-do-i-prove-my-etl-is-working.md`.
  - `docs/handbook/etl.md` cards (third in Foundational group). → third card after populate + prove.
  - `docs/walkthroughs/etl/how-do-i-prove-my-etl-is-working.md` (Related walkthroughs — "single-account-day version of these invariants"). → inserted as 2nd item.
  - `docs/walkthroughs/etl/what-do-i-do-when-demo-passes-but-prod-fails.md` (Symptom 4 drilldown — "use the daily statement sheet for the offending account-day"). → appended after the drift-sign explanation in Symptom 4.
- [x] **Fix broken handbook hero logos.** `docs/handbook/{ar,pr,etl}.md` use `src="../img/snb-wordmark.svg"`, but with MkDocs Material's default `use_directory_urls`, those pages render to `site/handbook/<name>/index.html` — relative path needs to be `../../img/snb-wordmark.svg`. Live site shows broken-image icons in the hero block on all three handbook landing pages (user noticed AR/PR; ETL has the same bug since the page was cribbed from the same template). One-line fix per file. → **Done 2026-04-20:** All three patched, `mkdocs build --strict` rebuilds clean, rendered HTML now reads `src="../../img/snb-wordmark.svg"`. Note: `docs/index.md` was already correct (`src="img/snb-wordmark.svg"` from the site root). Pure HTML `<img>` tags aren't auto-rewritten by MkDocs Material like Markdown `![]()` images are; that's why dashboard screenshots inside walkthroughs (Markdown syntax) survived but the hero wordmark didn't.

### I.2.F — Sequencing

Ship the sheet itself first (I.2.A → I.2.D), commit when tests are green, then write the handbook walkthrough against the deployed sheet (I.2.E). The walkthrough screenshots need a real deployed surface; writing the doc against a sketch invites rewrites.

## I.3 — Investigate AR semantics test failures

5 failures surface in `tests/e2e/test_ar_kpi_semantics.py` against the live deployed Postgres. They split cleanly into two error classes — surfaced by writing I.1's PR sibling and re-running the AR suite as a sanity pass.

### I.3.A — Two KPI scope failures (same H.4.B bug class as ledger/sub-ledger drift)

- [x] **`test_sweep_drift_kpi_scope`** — `ar_concentration_master_sweep_drift` returns 18 rows total, only 2 have `drift <> 0`. KPI counts all 18; subtitle promises only drift days.
- [x] **`test_gl_fed_drift_kpi_scope`** — `ar_gl_vs_fed_master_drift` returns 10 rows total, only 2 have `drift <> 0`. Same shape.

Both are the H.4.B drift-counts bug class: the dataset feeds two sheets (Balances wants every day for the timeline; Exceptions wants only the drift days for the KPI), but the sheet-pinned `CategoryFilter` on `drift_status='drift'` never landed for these two CMS-specific drift checks. The fix that landed in `account_recon/filters.py` for `ledger_drift` / `subledger_drift` should be replicated for these two view names. Targeted, mechanical — same shape as the H.4.B commit. Likely 30 minutes.

### I.3.B — Three planted-row surface failures (date drift between plant + view)

- [x] **`test_sweep_target_plants_surface`** — planted entry for `gl-1850-sub-big-meadow-dairy-main` on `days_ago=3` (2026-04-17) missing from `ar_sweep_target_nonzero`. Other days for the same account surface fine.
- [x] **`test_sweep_drift_plants_surface`** — planted sweep-leg-mismatch on `days_ago=6` (2026-04-14) missing from `ar_concentration_master_sweep_drift` drift rows. Drift days observed: 2026-04-08, 2026-04-13.
- [x] **`test_gl_fed_drift_plants_surface`** — planted gl-vs-fed drift on `days_ago=4` (2026-04-16) missing from drift rows. Drift days observed: 2026-04-10, 2026-04-15.

All three follow the same shape: one specific planted day from each `_*_PLANT` constant fails to surface, while other planted days from the same constant do surface. Suggests the plants land in `transactions` but a downstream view filter excludes that specific day — most likely a date arithmetic edge case (e.g., view treats `posted_at` as a date in one timezone and the plant computes `days_ago` in another, causing one day to fall outside the view's window).

Hypotheses to check, in order:
1. **Stale seed.** Run `quicksight-gen demo apply --all -c run/config.yaml -o run/out/` and rerun the failing tests. If the seed was applied before today's date rolled forward, the missing days might just be off-by-one against the test's `date.today()` reference.
2. **View date-window filter.** Each affected view (`ar_sweep_target_nonzero`, `ar_concentration_master_sweep_drift`, `ar_gl_vs_fed_master_drift`) likely has a `WHERE balance_date >= ...` or similar. Check whether the missing days fall on a window boundary.
3. **Plant-vs-view date arithmetic skew.** Compare how `account_recon/demo_data.py` computes the planted dates (`date.today() - timedelta(days=N)`) vs. how the view computes its date column (`balance_date` cast / posted_at trunc). A timezone or weekend-skip mismatch surfaces as exactly the symptom seen.

Resolution either lands the missing filter (I.3.A pattern, narrows the dataset SQL) or lands a generator/view date-arithmetic fix (I.3.B pattern, repairs the plant-to-surface contract). Both are localized; expect a half-day of investigation + targeted fix.

### I.3.C — Sequencing

Sequence I.3 *before* I.2 — the daily statement sheet's API e2e tests will hit the same dataset views and the same date-arithmetic surface. Fixing the underlying drift before adding new tests on top of it avoids piling new failures on a leaky foundation.

### I.3.D — Resolution

Investigated 2026-04-20 — both classes resolved without any production code change.

- **I.3.B (3 planted-row failures): stale seed.** Re-ran `quicksight-gen demo apply --all -c run/config.yaml -o run/out/` (Hypothesis 1) and all 3 surface tests passed. The seed had been applied days earlier; `date.today()` had rolled forward enough that the planted-on-N-days-ago dates no longer matched what the views computed against `balance_date`. No code fix; just an operational reminder that semantics tests want a fresh seed.
- **I.3.A (2 KPI scope failures): test bug, not code bug.** The H.4.B-pattern visual-scoped pinned filters (`fg-ar-exceptions-sweep-drift-only`, `fg-ar-exceptions-gl-fed-drift-only`) already existed in `account_recon/filters.py:450-465`, scoping the KPIs to `drift_status='drift'`. The tests' `as_displayed` queries didn't model that filter — they counted every row from the view. Fix was a one-line tightening of `as_displayed` in both tests to `WHERE drift_status = 'drift'`, matching what the deployed dashboard actually shows. Test comments updated to remove the stale "as-displayed counts every row" framing.

## I.4 — PR/AR cross-visibility audit (AR = superset of PR)

**North star reset.** AR is the unified view; PR is a tight, persona-scoped subset of it. A user looking at AR should be able to find PR data if they look for it — the current `NOT LIKE 'pr-%'` and `transfer_type IN (AR-only list)` exclusions in AR dataset SQL + schema views artificially hide that data. This directly contradicts the existing queued Phase J entry ("PR-coexistence filters in AR views" — which assumed future *separation*); I.4 flips that to *inclusion* and rewrites the J entry accordingly.

This also affects I.2 design. The Daily Statement sheet is greenfield and should set the example: its two new datasets ship *without* the PR exclusions from the start, so picking a PR merchant DDA in the account dropdown surfaces that account's daily statement naturally. I.2's SQL is written to this rule; I.4 retrofits the rest of AR.

### I.4.A — Scope audit

Grep targets across `src/quicksight_gen/account_recon/datasets.py` and `demo/schema.sql`:
- `NOT LIKE 'pr-%'`
- `transfer_type IN (` — check each list for whether it's scoping to a semantic AR subset or artificially excluding PR types
- `account_type`, `control_account_id` — same classification

Classify each filter:
- **Artificial.** Filter narrows to AR-only rows to match the pre-unified persona. Remove in I.4.B.
- **Semantic.** Filter is the visual's legitimate scope (e.g., `ar_concentration_master_sweep_drift` is semantically about the Cash Concentration Master — an AR-only account; the view stays scoped). Keep.

Parallel audit on `src/quicksight_gen/payment_recon/datasets.py` — PR datasets are probably already correctly scoped (deliberate choice of sale/settlement/payment/external_txn). Confirm, don't expand.

**Generator-side observation (surfaced during I.2.C, 2026-04-20):** The ACH-only customer DDAs (`_ACH_ORIG_CUSTOMERS` — yeti-espresso et al.) carry continuously-negative balances because the seed emits ACH outflow legs on the customer DDA with no compensating inbound deposit transactions. This likely inflates the AR overdraft KPI beyond just the planted overdrafts and made these accounts unusable as the "clean reconciling day" worked example for the Daily Statement walkthrough (clean example was rerouted to `gl-1010`). Decide in I.4 whether to plant compensating deposits, narrow the overdraft KPI's scope, or just document the pattern as expected demo behavior.

- [x] **Audit complete** — every artificial-vs-semantic filter in AR + PR datasets classified; remove-list handed to I.4.B. → **Done 2026-04-20.** Findings:

  **Artificial (remove in I.4.B):**
  1. `src/quicksight_gen/account_recon/datasets.py:383` — `WHERE t.transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')` in `ar-transactions-dataset`. Hides PR transfer types from the AR Transactions tab. Removing surfaces `sale`/`settlement`/`payment`/`external_txn` rows in AR Transactions naturally.
  2. `demo/schema.sql:387` — `AND t.account_id NOT LIKE 'pr-%'` in `ar_subledger_daily_outbound_by_type` view. Pure co-residency safety net per the in-line comment ("Phase H tech debt").
  3. `demo/schema.sql:451` — `AND sub.account_id NOT LIKE 'pr-%'` in `ar_subledger_overdraft` view. Same co-residency comment. **Cross-visibility consequence:** removing this would let merchant DDA overdrafts surface in the AR Sub-Ledger Overdraft check — which is the desired behavior under the unified-AR-superset framing.

  **Semantic (keep):**
  1. `demo/schema.sql:67` — `CHECK (transfer_type IN ('sale', 'settlement', 'payment', 'external_txn', ...))` on the `transactions` table. The column-type enum contract.
  2. `demo/schema.sql:204` — `CHECK (transfer_type IN ('ach', 'wire', 'internal', 'cash'))` on `ar_ledger_transfer_limits.transfer_type`. Limits only apply to AR transfer types (a merchant settlement isn't subject to a per-DDA ACH daily limit).
  3. `demo/schema.sql:388` — `AND t.transfer_type IN ('ach', ...)` in `ar_subledger_daily_outbound_by_type`. Optimization that mirrors the downstream `ar_subledger_limit_breach` join: limits are only configured for AR transfer types (line 204 CHECK), so PR transfer types would drop in the JOIN anyway. Filter is a query-planner hint, not an artificial exclusion.

  **Rework rather than defer (handled as commit 4 below):**
  1. `demo/schema.sql:332` — `WHERE t.transfer_type IN ('ach', ...)` in `ar_transfer_net_zero` view (feeds AR Non-Zero Transfers KPI). Direct removal floods the KPI with single-leg PR `sale`/`external_txn` false positives. Solution: widen the view but exempt single-leg-expected types via a CASE-based `expected_net_zero` flag; the KPI then reads `WHERE expected_net_zero = TRUE AND net_zero_status = 'not_net_zero'`. Lands as commit 4 of I.4.B, after the simpler removals are in.

  **PR datasets (`payment_recon/datasets.py`):** zero matches for `NOT LIKE 'pr-%'` or `transfer_type IN (...)`. PR datasets scope by joining PR-specific dimension tables and traversing `parent_transfer_id`, not by transfer_type filtering. **No change needed.**

  **Greenfield Daily Statement datasets (I.2):** verified clean — `ar-daily-statement-summary-dataset` and `ar-daily-statement-transactions-dataset` carry no `pr-%` or `transfer_type` filters (lines 753, 765-767, 819-823). Already on the I.4 north star.

### I.4.B — Remove artificial exclusions

- [ ] Drop identified filters from AR datasets + schema views, one commit per coherent group (Balances, Transactions, Transfers). Four concrete commits:
  - **Commit 1 (schema views, both `pr-%` filters):** remove `account_id NOT LIKE 'pr-%'` from `ar_subledger_daily_outbound_by_type` (line 387) and `ar_subledger_overdraft` (line 451). Drop the in-line comments. Re-apply demo. SHA256 lock unaffected (views aren't generator output — confirmed 2026-04-20).
  - **Commit 1 — discovered downstream effect (2026-04-20):** Removing the overdraft filter exposes **556 PR merchant DDA overdraft rows** (6 accounts × ~92 days each) plus 2 days from `pr-external-rail`. Root cause is a generator sign-convention bug: the PR sale leg debits merchant_sub (`-sale["amount"]`) when under the "positive signed_amount = money IN" convention used by AR + the schema docs, it should credit. Net effect: merchant_dda accounts never receive positive signed_amount → structurally negative. **Decision (2026-04-20):** land Commit 1 with the noise (cross-visibility test acknowledges it as known generator behavior); the underlying sign convention fix is large enough to deserve its own phase — see **Phase I.5 — PR sign convention standardization** below. Planted AR overdraft scenarios (cust-900-0002, cust-700-0002, gl-1850-sub-cascade) verified to still surface correctly.
  - **Commit 2 (AR Transactions dataset transfer-type filter):** remove `WHERE t.transfer_type IN (...)` from `build_ar_transactions_dataset` SQL (line 383). PR transfer types now appear in the AR Transactions tab. May need a Transactions tab UI affordance (default-on Transfer Type filter chip set to AR-only? or just trust the analyst?). Decide during the commit.
  - **Commit 3 (`ar_transfer_net_zero` view: cross-app net-zero with single-leg exemption):** widen the view's source filter to all transfer types, but add an `expected_net_zero` BOOLEAN column derived from a CASE on `transfer_type` (FALSE for `sale`, `external_txn`; TRUE for everything else, since `payment` and `settlement` are multi-leg). Update `ar_transfer_summary` to carry `expected_net_zero` through. Update the AR Non-Zero Transfers KPI's pinned filter to `expected_net_zero = TRUE AND net_zero_status = 'not_net_zero'`. Verify the KPI count doesn't shift (clean PR transfers should still net to zero; planted PR mismatches surface in PR's own checks, not AR's).
  - **Commit 4 (CLAUDE.md + SPEC.md + RELEASE_NOTES.md doc updates):** strike the "AR datasets filter `WHERE transfer_type IN (...)` to exclude PR transfer types" sentence (CLAUDE.md:208), the AR co-residency safety filters bullet (SPEC.md:127), and the Phase H carry-forward note (RELEASE_NOTES.md:27). Replace with the unified-AR-superset framing.
- [ ] Each change ships with a test asserting PR rows flow through where expected (e.g., a Balances-level query returns at least one `account_type='merchant_dda'` row).
- [ ] Re-lock SHA256 if view definitions change and re-applying the demo shifts the seed hash.

### I.4.C — Update existing AR visuals for the widened data

**Deferred until after I.5 (2026-04-20).** The widening exposes ~556 PR merchant_dda overdraft rows from the I.5 sign-convention bug; once I.5 fixes the seed, that noise disappears and the per-tab UX impact may be small enough to need no chips at all. No active analyst is on the dashboard right now — re-evaluate after I.5 ships.

- [ ] Balances tab now surfaces PR merchant DDAs + the PR external-customer pool. May need a default toggle (e.g., "Show Only CMS Accounts" multi-select default) so the AR analyst's morning-check view doesn't shift under them.
- [ ] Transactions tab now surfaces `sale`, `settlement`, `payment`, `external_txn` transfer types. Transfer Type filter dropdown auto-expands.
- [ ] Transfers tab now shows PR transfers alongside AR transfers.
- [ ] Exceptions tab should be unchanged — those checks are semantically AR-only.

### I.4.D — Rewrite Phase J "PR-coexistence filters" entry

The queued J entry currently reads "Phase J deletes these — a single-feed real persona has no parallel PR ledger to filter out." That assumed future PR/AR *separation*. Rewrite to reflect the new direction: PR/AR stay unified; only artificial filters come out; AR remains the superset.

- [ ] **Rewritten** — Phase J entry reflects unified-AR-superset framing.

### I.4.E — Docs + training regression pass

- [ ] `CLAUDE.md` AR domain section gets a "AR is a superset of PR" line.
- [ ] AR Getting Started flavor text adds one sentence: PR merchant accounts appear in AR as a subset; filter by account type if you want AR-only.
- [ ] `docs/Schema_v3.md` persona-contract language stays unchanged (it's already tables-are-a-contract flavored).
- [ ] **Training/handbook regression pass.** Walk the AR + ETL training walkthroughs (`docs/walkthroughs/`) and AR Handbook index; any step that reads "all rows here are AR-only" or sets up screenshots against the narrowed dataset needs a refresh. Screenshots specifically may break (new PR rows in Balances/Transactions tables shift counts, alter sorts). Ship refreshed screenshots + copy edits alongside the audit.

### I.4.F — Sequencing

Sequence I.4 *after* I.2 Daily Statement lands. Rationale: I.2 sets the good example (greenfield datasets with no exclusions); I.4 retrofits existing AR datasets to match. Doing I.4 first would delay the higher-value I.2 work and complicate the Daily Statement's own test inventory.

Estimated 2–4 commits. If I.4.B/C grows past that (because removing exclusions uncovers visual regressions requiring redesign), promote to its own Phase J entry and leave a smaller I.4 behind.

## I.5 — PR sign convention standardization (merchant_dda balance reflects actual flow)

**North star.** PR merchant_dda accounts should follow the same sign convention as the rest of the codebase: `signed_amount > 0` = money IN to the account; `signed_amount < 0` = money OUT; `daily_balances.balance = SUM(signed_amount)` reflects what the merchant actually has on hand. Surfaced during I.4.B Commit 1 — the PR generator emits `payment` outflow legs on merchant_dda accounts but no compensating inbound, because the sale leg also debits merchant_sub (backwards from convention). This forces PR datasets to negate signed_amount in 6+ places (`-t.signed_amount AS amount`) to recover positive display values. I.5 fixes both: align the seed signs AND retire the negation pattern in PR datasets.

Why a standalone phase rather than a sub-step of I.4: the fix touches generator + datasets + tests + likely visuals; SHA256 re-lock will shift many PR e2e expectations; the diff is broad enough to deserve its own commit cadence and review surface. I.4 stays focused on filter removal; I.5 owns the sign convention.

### I.5.A — Audit current PR sign usage

- [ ] **Generator inventory.** Map every place merchant_sub or other PR sub-ledger accounts get a signed_amount written in `src/quicksight_gen/payment_recon/demo_data.py`:
  - sale leg (`_derive_pr_unified_tables` ~line 384-387): currently merchant_sub `-sale["amount"]`, customer pool `+sale["amount"]`. **Backwards.**
  - settlement leg (~line 314-345): self-cancelling pair on merchant_sub. Decide whether to keep self-cancelling or model the actual settlement → merchant payout movement.
  - payment leg (~line 280-311): merchant_sub `-payment_amount`, external rail `+payment_amount`. **Correct under target convention** (payment is money out).
  - Any other PR-side `_posting` calls touching merchant_sub or `pr-external-*`.
- [ ] **Dataset inventory.** Map every place PR datasets read signed_amount with negation in `src/quicksight_gen/payment_recon/datasets.py`. Known starting set (verify line numbers post-I.4.B): ~323, 436, 502, 553, 595, 665. For each, classify whether the negation is recovering "absolute display amount" (replace with `t.amount`) or carries semantic intent ("amount the merchant lost on this leg" — keep but rewrite intent into a column alias).
- [ ] **Test inventory.** Grep PR tests (`tests/test_demo_data.py`, `tests/test_payment_recon.py`, `tests/e2e/test_*.py` for PR) for hardcoded signed_amount expectations. Catalog every assertion that pins a specific value or sign.
- [ ] **`_ACH_ORIG_CUSTOMERS` parallel check.** The continuously-negative ACH-only customer DDAs surfaced in I.4.A have a related but distinct shape (AR-side seed, not PR). Decide whether they get folded into I.5.B or stay AR-side.
- [ ] **Document the target convention** in CLAUDE.md / SPEC.md so the rule is one place: `signed_amount > 0` = money IN; `signed_amount < 0` = money OUT; `amount` = absolute. PR merchant_dda follows this rule like every other account type.

### I.5.B — Generator-side sign correction

- [ ] **Sale leg flip.** `payment_recon/demo_data.py` ~line 384-387: merchant_sub `+sale["amount"]`, `pr-external-customer-pool` `-sale["amount"]`. Single primary edit.
- [ ] **Settlement leg revisit.** Currently self-cancelling on merchant_sub. Either keep (settlement is a logical grouping, no money actually moves) or model the merchant payout (settlement_amount credits merchant_sub, debits the bank's settlement holding account). Pick based on whether downstream visuals need the settlement-as-payout signal.
- [ ] **Payment leg verify.** Should remain unchanged; under the new convention `merchant_sub -payment_amount` (money out) is correct.
- [ ] **Determinism.** Re-lock SHA256 in `tests/test_demo_data.py::TestDeterminism::test_seed_output_hash_is_locked` (PR seed). AR seed unchanged at this stage.
- [ ] **Sign-convention contract test.** New PR test: every merchant_dda account has at least one positive-signed_amount day in the seed (sale credits the account). Pins the convention so a future regression breaks loudly.
- [ ] **Balance-coherence test.** Optional but worth adding: assert that for any merchant_dda, `daily_balances.balance` for the last seed date is within "one settlement cycle" of zero (sales come in, payments go out, residual ≈ in-flight settlement). Defines the structural expectation.

### I.5.C — Dataset cleanup (retire `-t.signed_amount` pattern)

- [ ] For each location identified in I.5.A's dataset inventory, replace `-t.signed_amount AS amount` (or `SUM(-signed_amount)`) with `t.amount` (or `SUM(amount)`) where the goal is absolute display value.
- [ ] Where a dataset reads multiple legs and needs to distinguish in-vs-out, switch to `t.signed_amount` directly under the new convention (positive = in) — usually clearer than negation.
- [ ] Update DatasetContract column types if needed (most are already DECIMAL — no change expected).
- [ ] Update `tests/test_dataset_contract.py` per-builder assertions if column expectations shift.

### I.5.D — Test re-lock and fallout

- [ ] Re-run unit + AR e2e tests after I.5.B; expect SHA256 fail on PR seed → re-lock as the intentional change.
- [ ] Re-run PR e2e tests; expect drift in:
  - PR sale visuals (totals may flip sign in unfixed display paths)
  - PR merchant balance KPIs (now non-negative)
  - PR Settlement / Payment Mismatch checks (likely unchanged — they read on transfer_id grouping, not per-leg sign)
  - Any test that hardcoded a negative signed_amount value
- [ ] Update assertions; document which were "wrong because of the bug, now correct" vs. "broke because they assumed the buggy convention." Keep a one-paragraph note in the commit body so the diff is self-documenting.

### I.5.E — Cross-visibility regression update

- [ ] `tests/e2e/test_ar_cross_visibility.py::test_merchant_dda_overdrafts_surface` currently passes because *every* merchant_dda is structurally negative (known bug). Post-I.5.B, that bug is gone — the assertion as-written would silently pass on zero merchant_dda overdrafts.
- [ ] Either: plant an explicit PR overdraft scenario in `payment_recon/demo_data.py` (one merchant whose payments exceed sales for a settlement cycle) and pin the test to that scenario, OR: drop the test assertion and replace with "no merchant_dda should be structurally negative for the entire seed window" (the inverse — locking the fix).
- [ ] Update test docstrings to remove "I.4.B Commit 1.5" references; replace with "Phase I.5 — sign convention standardization."

### I.5.F — Docs + sequencing

- [ ] CLAUDE.md domain section gets the canonical sign convention statement (one line: `signed_amount > 0` = IN, `< 0` = OUT, applies to all account types including merchant_dda).
- [ ] `docs/Schema_v3.md` per-column note for `signed_amount` already says positive=debit; reconcile language so "positive=debit" and "positive=money IN" don't read as conflicting (they're the same statement from different perspectives — bank's view vs. account's view; clarify in one place).
- [ ] PR Handbook spot-check: any walkthrough that talked about "merchant balance is structurally negative" gets updated.
- [ ] **Sequence I.5 after I.4 ships.** I.4 makes the cross-visibility lock visible (the test currently relies on the bug); I.5 fixes the bug and updates the test. Doing them out of order means re-locking SHA256 twice and writing a temporary cross-visibility assertion.
- [ ] Estimated 4–6 commits across I.5.B/C/D. Promote to its own phase if it grows further.

## I.6 — Release to PyPI + GitHub release artifacts

**North star.** `pip install quicksight-gen[demo]` works from PyPI on any tagged release. A GitHub Release page accompanies each tag with the wheel, sdist, and a pre-baked sample `out/` bundle so evaluators can inspect generated QuickSight JSON without running the generator. Tag-triggered workflow does the build, smoke-test against the wheel, publish, and release-notes draft.

**Why now.** The repo is past v3.0.0 in RELEASE_NOTES (Phase G shipped) but `pyproject.toml` still says `1.1.0`. Anyone who wants to use the tool today has to clone + `pip install -e .` — there's no `pip install`-from-PyPI path. Setting up the release pipeline now establishes the cadence; later phases can ship with a single tag push.

### I.6.A — Version source-of-truth audit + sync

- [ ] **Reconcile version.** `pyproject.toml:7` says `1.1.0`; `RELEASE_NOTES.md` headers go up through v3.0.0 / v2.0.0 / v1.5.0 (apparent multi-track numbering — schema major vs. dashboard feature). Decide on a single track going forward (recommend semver from current tip; the next tag is `v1.6.0` reflecting Phase I work, since v3.0.0 is a schema-internal version that doesn't read as semver to a PyPI consumer).
- [ ] **Pick a single source of truth.** Either (a) bump `pyproject.toml` manually per release, or (b) read version from `src/quicksight_gen/__init__.py` via `tool.setuptools.dynamic`. Option (b) lets the generator self-report (`quicksight-gen --version`) without drift. Recommend (b).
- [ ] **Document the bump-then-tag sequence** in CLAUDE.md (release section).

### I.6.B — Release-readiness audit on `pyproject.toml`

- [ ] **Classifiers.** Add `Topic`, `Intended Audience`, `Programming Language :: Python :: 3.11/3.12/3.13`, `License :: Public Domain`, `Operating System`, `Development Status`. Currently zero classifiers.
- [ ] **URLs.** Add `[project.urls]` for Homepage, Source, Issues, Changelog, Documentation (the GitHub Pages site).
- [ ] **README rendering.** Confirm `README.md` is referenced as `readme = "README.md"` in `[project]` and renders cleanly on PyPI (their renderer is stricter than GitHub's — test in I.6.C).
- [ ] **Keywords.** Add a small set: `quicksight`, `aws`, `dashboards`, `reconciliation`, `analytics`.
- [ ] **Package data.** Audit what ships in the wheel vs sdist. Confirm `tests/`, `demo/seed.sql`, `out/`, `run/` are excluded from wheel; decide whether `demo/schema.sql` ships (probably yes — it's the schema contract, useful as a reference even without `demo apply`).

### I.6.C — Local build + smoke test

- [ ] **`python -m build`.** Produces `dist/quicksight_gen-*.whl` + `*.tar.gz`. Add `build` to `[project.optional-dependencies].dev` if not already present.
- [ ] **Fresh-venv install.** `python -m venv /tmp/qs-smoke && /tmp/qs-smoke/bin/pip install dist/quicksight_gen-*.whl[demo]`. Verify `quicksight-gen --help` shows all subcommands and `quicksight-gen --version` prints the right number.
- [ ] **`generate --all` smoke.** Run against a sample config; confirm output matches a checked-in golden (or at least is non-empty + deserializable JSON). Catches missing package-data files.
- [ ] **`twine check dist/*`.** Validates the long-description renders on PyPI.

### I.6.D — PyPI account + trusted publishing setup

- [ ] **TestPyPI first.** Register `quicksight-gen` name on TestPyPI; configure a Trusted Publisher pointing at `Quicksight-Generator` repo + `release.yml` workflow + `testpypi` environment. **User action** — not a code commit.
- [ ] **PyPI.** Same pattern; second Trusted Publisher entry pointing at `pypi` environment. **User action.**
- [ ] **GitHub Environments.** Create `testpypi` + `pypi` environments under repo Settings → Environments. PyPI gets a manual approval gate for the first ~3 releases (drop later once the workflow is trusted).
- [ ] **No API tokens in repo secrets.** Trusted publishing uses OIDC; the workflow exchanges a short-lived token for an upload token at runtime.

### I.6.E — Release workflow (`.github/workflows/release.yml`)

- [ ] **Trigger.** `on: push: tags: ['v[0-9]+.[0-9]+.[0-9]+']` (excludes pre-release suffixes; add `'v[0-9]+.[0-9]+.[0-9]+-*'` later for rc / beta tags if needed).
- [ ] **Job: build.** `pypa/build` produces sdist + wheel; uploads as workflow artifact for downstream jobs.
- [ ] **Job: smoke-against-wheel.** Downloads the wheel artifact, installs it into a fresh venv, runs the unit + integration test subset that doesn't need AWS (`pytest tests/test_models.py tests/test_account_recon.py tests/test_demo_data.py tests/test_demo_sql.py tests/test_recon.py tests/test_generate.py tests/test_theme_presets.py tests/test_dataset_contract.py`). Catches missing package-data — source tests pass but wheel tests fail if a JSON template was forgotten.
- [ ] **Job: publish-testpypi.** Always on tag; uses Trusted Publisher; environment `testpypi`.
- [ ] **Job: publish-pypi.** Gated on `testpypi` job success + manual environment approval; uses Trusted Publisher; environment `pypi`.
- [ ] **Job: github-release.** Uses `softprops/action-gh-release` (or `gh release create`) — uploads sdist + wheel + `out-sample.zip` (pre-baked output for both apps); body extracted from `RELEASE_NOTES.md` for the matching tag (script-extract the section by header match).

### I.6.F — Sample output bundle

- [ ] **`scripts/bake_sample_output.py`** — runs `quicksight-gen generate --all` against a checked-in `examples/config.yaml` (no real ARNs, demo-mode wiring), zips `out/`, drops at `dist/out-sample.zip`. Workflow runs this between build and github-release.
- [ ] Decide whether `examples/config.yaml` ships in the wheel too (probably yes — gives evaluators a known-good starting point).

### I.6.G — README + badges

- [ ] Add `## Install` section to `README.md`: `pip install quicksight-gen[demo]` (or omit `[demo]` for production callers with their own datasource ARN).
- [ ] PyPI version badge alongside the existing CI + coverage badges.
- [ ] **`quicksight-gen --version` flag.** Click supports this natively; wire it once dynamic versioning lands in I.6.A.

### I.6.H — Sequencing

- [ ] **Independent of I.4 / I.5.** Release plumbing doesn't touch dataset semantics; can land in parallel. But the *first* published tag should follow a clean version — preferably after I.5 ships and the SHA256 hash re-lock is done, so the published artifact corresponds to a coherent state.
- [ ] **First release flow.** v1.6.0-test1 → TestPyPI only → manual install verify → v1.6.0 → PyPI + GitHub Release. Validates the pipeline before the real cut.
- [ ] **Estimated 6–8 commits.** Sub-phases A/B/C are doc/config commits; E is the workflow commit; F is one script + workflow wiring. D is user-only setup. G is a doc commit.

### I.6.I — Open questions

- [ ] **Pre-release channel.** Do branch builds publish to TestPyPI automatically (e.g., on push to a `release/*` branch with a `v1.6.0-rc1`-style tag), or only formal tags? Recommend formal-tags-only initially; revisit if the cadence picks up.
- [ ] **Package name on PyPI.** `quicksight-gen` is the natural name (matches `[project].name`) — verify availability on PyPI before I.6.D registration. If taken, fall back to `quicksight-generator` or namespaced (`anthropic-quicksight-gen` style) — bigger renames flow back through `[project.scripts]` and `__init__.py`.
- [ ] **License clarity.** `Unlicense` is public domain; PyPI accepts it. Confirm the `LICENSE` file at repo root matches and is included in the wheel (`tool.setuptools.license-files` defaults usually pick it up).

---

# PLAN — Phase J (queued)

Items deferred from Phase H + Phase I scope, parked here so they aren't lost. Each is independent and can phase up on its own merit. Inputs from Phase I (the daily statement sheet, in particular) may further inform priority.

## Persona-driven dashboard layout redesigns

- [ ] **AR Exceptions tab redesign.** Sheet is dense (3 rollups + 14 checks + aging bars + 2 drift timelines). Phase H walkthroughs surfaced which sections are friction-heavy; that's the input for redesign. Likely shape: per-persona view modes ("morning check" vs. "deep investigation"), or progressive disclosure of CMS-specific checks behind a category toggle.
- [ ] **PR pipeline tab structure.** Under the shared-base model (Phase G), Sales / Settlements / Payments are values of `transfer_type`, not separate entities. Current per-step tab structure is preserved from the pre-flatten era. Operator-question walkthroughs in Phase H may surface whether the per-step tab structure helps or fights merchant-support workflow. Decide redesign based on what those walkthroughs show.

## Schema cleanup carry-over from Phase G

- ~~**PR-coexistence filters in AR views**~~ — *resolved by Phase I.4.B (commits 1–4).* The original entry assumed the future was PR/AR *separation* (delete the filters, a single-feed persona has no parallel PR ledger). I.4 flipped that: AR is the superset; PR is a subset view. The artificial filters were removed in I.4.B commits 1–3; commit 4 updated CLAUDE.md / SPEC.md / RELEASE_NOTES.md to match.
- ~~**AR drift views leak benign zero-drift PR rows**~~ — *resolved by Phase I.4.B commit 1.* Both `account_id NOT LIKE 'pr-%'` filters dropped from `ar_subledger_overdraft` and `ar_subledger_daily_outbound_by_type`. Drift views now expose merchant DDA rows by intent.
- [ ] **Unified account dimension table.** AR currently keeps `ar_ledger_accounts` and `ar_subledger_accounts` as separate dimension tables. A single "all accounts" table aligns with the denormalize-don't-add-tables north star and would simplify some queries. Low priority; ship when there's a query that benefits.

## Customer-facing customization handbook

- [ ] `docs/Schema_v3.md` is the persona contract for the Data Integration Team. A longer-form customer-facing customization guide (mapping production-system tables → the two base tables, common pitfalls, performance tips, replacing dataset SQL while preserving DatasetContract) is a natural follow-up to the demo-side walkthroughs in Phase H. Deliverable shape: a "Customization Handbook" sibling to AR / PR Handbooks.

## Persona dashboard split (originally Phase E)

- [ ] Still queued. The Phase H walkthroughs and Phase I daily statement sheet (which exposes a per-account workflow that's currently buried inside the AR analysis) provide better signal on what a persona-scoped dashboard split should look like.

## New surfaces (from Training Story personas not yet served)

- [ ] **Fraud team surface.** "Search for transactions that break limits set on the accounts" — investigative, not monitoring. Different UX paradigm from PR/AR. Probably its own analysis with a search-driven entry point and ad-hoc filter chips. Needs workflow elicitation before planning visuals.
- [ ] **AML team surface.** "Detect transactions/balances outside statistical average and find patterns." Likely needs QuickSight forecasting / anomaly insights features and visual primitives we don't currently use. Needs workflow elicitation before planning visuals.
