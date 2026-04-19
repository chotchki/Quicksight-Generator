# PLAN — Phase F: Cash Management Suite restructure + telling-transfer exception checks

Goal: Restructure the AR demo's ledger / sub-ledger account model from "kind of bank product → branch sub-pool" (legacy abstraction inherited from Phase A) into standard banking "GL control account → per-customer DDA / operational sub-pool", aligned with `docs/Training_Story.md`. Add four new telling-transfer scenarios (ZBA / Cash Concentration sweep, ACH origination sweep, external force-posted card settlement, on-us internal transfer with fail / reversal) and the AR exception checks each one drives.

This phase is large because it touches the demo data shape, the plant lists, every test that asserts on display names, and adds ~9 new exception checks. Plan to land ~18 commits across 7 sub-phases.

Out of scope for Phase F (deferred — own plan):
- **Schema flattening to ~2 tables (daily_balance + transaction).** Listed in `docs/context.md` as a future technical north star. Doing it concurrently with the structural data restructure would break the test suite as a safety net on two axes simultaneously. Defer to **Phase G** — Phase F must leave the test suite green so the schema migration has a stable jump-off point. Phase F's new SQL should use view abstractions where possible so Phase G can swap underlying tables without touching dataset SQL.
- PR (Payment Reconciliation) app changes. The new account model and telling transfers are AR-only. PR continues using `pr_*` legacy tables and chain-link transfer types unchanged.
- Persona dashboard split (originally Phase E in `SPEC.md`) — orthogonal to this work; remains queued.
- Customer-facing terminology guide / production-schema documentation. Phase F is internal restructure.

Conventions:
- Branch: `phase-f-cms-restructure`, cut from `main`. One sub-phase = one commit; cumulative release at the end.
- `demo apply` continues to drop-and-create. No staged migrations.
- After each sub-phase: `.venv/bin/pytest`, except where the sub-phase intentionally leaves the test suite red (called out per phase). Test suite restored to green by end of F.3.
- After F.3, F.4, and F.7: `./run_e2e.sh --parallel 4` (e2e tests). Skip e2e during F.1–F.2.
- Demo data MUST stay deterministic (`random.Random(42)`); the byte-identical-output expectation gets a one-time break at F.1, then re-locks.
- Every sheet description and every visual subtitle stays present (existing coverage tests enforce this).
- All new GL account names, exception check names, and visual subtitles use **standard CPA-readable banking terminology** (`Customer Deposits — DDA Control`, `ACH Origination Settlement`, `Cash Concentration Master`, `Internal Transfer Suspense`, `Card Acquiring Settlement`, etc.). No invented or project-specific names.

---

## Phase F.0 — Pin decisions

STOP here. Big-shape decisions cascade hard.

- [x] F.0.1 **Old account IDs (`ar-par-checking`, `ar-acc-checking-main`, ...): preserve any?** → **FULL RESET.** Semantic shift (product-category → GL-control + customer-DDA) means old IDs would mislead; byte-identical-demo-output invariant gets a one-time break here, then re-locks.
- [x] F.0.2 **New ID scheme.** → `gl-<num>-<slug>` for GL control accounts (`gl-2010-dda-control`), `cust-<num>-<slug>` for customer DDAs (`cust-900-0001-bigfoot-brews`), `gl-<num>-sub-<slug>` for operational sub-pools (`gl-1850-sub-bigmeadow-main`). Picked to make the linkage visible to learners.
- [x] F.0.3 **ZBA operating sub-accounts.** → Per-customer, 1-2 operating sub-accounts each on commercial customers (Big Meadow Dairy, Cascade Timber Mill).
- [x] F.0.4 **Planted instances per new failure scenario.** → 2-3 of each pattern. Lean count is fine; more change is coming and a couple examples illustrate the pattern.
- [x] F.0.5 **Retain existing AR exception checks?** → **YES**, all of them. The four telling-transfer scenarios are just the hardest ones; existing checks (failed-leg, off-amount, ledger drift, sub-ledger drift, limit breach, overdraft) stay valid. They get re-pointed at new account IDs in F.2.
- [x] F.0.6 **Sheet placement.** → Extend existing Exceptions tab.
- [x] F.0.7 **Consolidate where shape is similar?** → **Both, where feasible.** Per-check detail visuals stay (one teaches one error class clearly); add consolidated rollup visuals on top so users see "this is the same SHAPE of error across multiple accounts." See new F.5.10.
- [x] F.0.8 **Release version after Phase F.** → v2.0.0 (project's external semver — internal counting is at v5 but external semver is the contract).
---

## Phase F.1 — Restructure ledger + sub-ledger account tables

Replace the product-category abstraction with GL-control + customer-DDA + operational-sub-pool. Breaking change to `LEDGER_ACCOUNTS` and `SUBLEDGER_ACCOUNTS` in `account_recon/demo_data.py`. Tests intentionally red after this commit; restored by end of F.3.

- [x] F.1.1 Replace `LEDGER_ACCOUNTS`. Internal GL control accounts: Cash & Due From FRB, ACH Origination Settlement, Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense, Cash Concentration Master, Internal Suspense / Reconciliation, Customer Deposits — DDA Control. External counterparties: Federal Reserve Bank — SNB Master, Payment Gateway Processor, Coffee Shop Supply Co, Valley Grain Co-op, Harvest Credit Exchange.
- [x] F.1.2 Replace `SUBLEDGER_ACCOUNTS`. Per-customer DDAs (7) under Customer Deposits — DDA Control. Per-customer ZBA operating sub-accounts (1-2 each on commercial customers) under Cash Concentration Master. External counterparty sub-pools (preserve roughly the clearing + settlement / inbound + outbound pattern) under each external counterparty.
- [x] F.1.3 Update `_ledger_is_internal()` and `_pick_*_pair()` helpers if the contracts change. → No-op; helpers are pure list lookups, contracts unchanged. Noted: `_generate_ledger_level_transfers` funding-batch path now KeyErrors when picking an internal GL with no sub-ledgers (6 of 8) — defer to F.2.5 / F.3.
- [x] F.1.4 Skip pytest — known red. Just verify the Python parses (`python -c "import quicksight_gen.account_recon.demo_data"`) and `demo schema --all` still emits valid SQL.
- [x] F.1.5 Commit — `Phase F.1: restructure AR ledger + sub-ledger account model (tests red)`.

---

## Phase F.2 — Re-aim plant lists at new account IDs

Mechanical follow-on. All plant constants reference IDs that no longer exist. Tests still red after this commit; restored in F.3.

- [ ] F.2.1 `_LEDGER_DRIFT_PLANT` — point at new internal GL control account IDs (e.g., DDA Control, Cash Concentration Master).
- [ ] F.2.2 `_SUBLEDGER_DRIFT_PLANT` — point at new customer DDAs and ZBA sub-accounts.
- [ ] F.2.3 `_LIMIT_BREACH_PLANT` — point at new sub-ledger IDs; revisit transfer types and amounts so the breach narrative still makes sense at the customer-DDA level (e.g., "Bulk wire payout from Big Meadow Dairy DDA").
- [ ] F.2.4 `_OVERDRAFT_PLANT` — point at new customer DDA IDs.
- [ ] F.2.5 `_LEDGER_LIMITS` — re-author for the new ledger structure. Per-customer DDAs probably have their own daily ACH / wire limits; GL control accounts don't have outbound limits in the same sense.
- [ ] F.2.6 `_EXTERNAL_COUNTER_LEG_POOL` — point at new external sub-ledger IDs.
- [ ] F.2.7 Skip pytest — still known red. Verify SQL parses.
- [ ] F.2.8 Commit — `Phase F.2: re-aim plant lists at new account IDs (tests still red)`.

---

## Phase F.3 — Update existing tests

Stabilize the test suite against the new account structure. Test suite returns to green by end of this phase.

- [ ] F.3.1 `tests/test_demo_data.py` — update `LEDGER_ACCOUNTS` / `SUBLEDGER_ACCOUNTS` count assertions, display-name assertions, FK integrity tests, scenario coverage assertions.
- [ ] F.3.2 `tests/test_account_recon.py` — update visual + filter assertions referencing old ledger / sub-ledger names.
- [ ] F.3.3 `tests/test_demo_sql.py` — update structural SQL assertions.
- [ ] F.3.4 `tests/test_dataset_contract.py` — verify; minimal changes expected since no SQL changed yet.
- [ ] F.3.5 `tests/test_models.py`, `tests/test_generate.py`, `tests/test_recon.py`, `tests/test_theme_presets.py` — sweep for stray references.
- [ ] F.3.6 e2e tests deferred to F.7. Keep `QS_GEN_E2E=0` for the rest of Phase F until F.7.
- [ ] F.3.7 `.venv/bin/pytest` — full unit suite green.
- [ ] F.3.8 Commit — `Phase F.3: update unit tests for new AR account structure (tests green)`.

---

## Phase F.4 — Add new telling-transfer scenarios to demo data

Plant the four new scenarios from `docs/Training_Story.md`. Each scenario has at least one success cycle and one failure plant. Tests stay green throughout — each sub-phase adds a `TestScenarioCoverage` assertion before the planting code lands (write the assertion first; it's the fastest way to notice if a scenario silently disappears).

- [ ] F.4.1 **ZBA / Cash Concentration sweep cycle.** Daily success: each operating sub-account sweeps to Cash Concentration Master, ending zero. Failure plant (2): one day where an operating sub-account fails to sweep (ends non-zero). Add scenario coverage assertion first.
- [ ] F.4.2 **ACH origination sweep cycle.** Daily success: ACH Origination Settlement accumulates customer ACH debits, sweeps to FRB Master at EOD, ends zero. Failure plants (2): one day where the sweep posts internally but no Fed confirmation lands; one day where the sweep fails entirely (account ends non-zero).
- [ ] F.4.3 **External force-posted card settlement.** Success: Card Acquiring Settlement receives daily processor settlements that catch up internally within 1 day. Failure plant (2): Fed posted but internal catch-up never happened (mismatch surfaces).
- [ ] F.4.4 **On-Us Internal Transfer with fail / reversal.** Success: customer-to-customer internal transfer routes through Internal Transfer Suspense and settles same day. Failure plants: 2 stuck-in-suspense (no settle, no reversal after N days), 1 reversed-but-not-credited (reversal posting missing — double-spend signature).
- [ ] F.4.5 Add `TestScenarioCoverage` assertion for each pattern in `tests/test_demo_data.py` (one per failure pattern; ≥N rows of that shape — counts alone don't catch silently-missing scenarios).
- [ ] F.4.6 `.venv/bin/pytest` clean.
- [ ] F.4.7 `./run_e2e.sh --parallel 4 --skip-deploy api` — confirm dataset health holds with new scenarios. Skip browser e2e (no new visuals yet).
- [ ] F.4.8 Commit — `Phase F.4: plant four telling-transfer scenarios in AR demo data`.

---

## Phase F.5 — New AR exception checks

One commit per check. Each adds: dataset (SQL + DatasetContract), visual (KPI + table + aging bar where applicable), sheet placement (Exceptions tab — see F.0.6), and unit tests. New SQL prefers view abstractions over direct table references where possible (so Phase G schema flattening only needs to update views).

- [ ] F.5.1 **Sweep target non-zero EOD.** Operating sub-accounts that didn't sweep to zero. Visual: KPI count + detail table + aging bar. Commit — `Phase F.5.1: add Sweep target non-zero EOD check`.
- [ ] F.5.2 **Concentration master vs sub-account sweeps drift.** Sum of sweep credits to Cash Concentration Master vs sum of sweep debits from operating sub-accounts. Adds drift timeline visual. Commit.
- [ ] F.5.3 **ACH Origination Settlement non-zero EOD.** Sweep account ends day non-zero. Commit.
- [ ] F.5.4 **Internal sweep posted but no Fed confirmation.** Internal sweep transfer with no matching `external_force_posted` confirmation after N days. Aging-driven. Commit.
- [ ] F.5.5 **Fed activity with no matching internal post.** Force-posted Fed activity that internal books haven't caught up to. Commit.
- [ ] F.5.6 **GL-vs-Fed Master drift timeline.** Daily cumulative drift between SNB GL total cash and FRB Master Account balance. Timeline visual. Commit.
- [ ] F.5.7 **Stuck in Internal Transfer Suspense.** Originated transfers with no settle and no reversal after N days. Aging-driven. Commit.
- [ ] F.5.8 **Internal Transfer Suspense non-zero EOD.** Suspense account ends day non-zero. Commit.
- [ ] F.5.9 **Reversed-but-not-credited (double spend).** Original posting + reversal posting where the credit-back to originator is missing. Highest-severity check — flag visually (e.g., red KPI tile, top of Exceptions tab). Commit.
- [ ] F.5.10 **Consolidated rollup views (per F.0.7 ruling).** Per-check detail visuals from F.5.1–F.5.9 stay as-is. On top of them, add cross-check rollup visuals so users learn to recognize *shape* of error across multiple accounts:
  - **F.5.10.a "Accounts expected zero at EOD" rollup.** Single table + KPI rolling up F.5.1 (Sweep target), F.5.3 (ACH Origination Settlement), F.5.8 (Internal Transfer Suspense). Columns: account, balance, days_outstanding, aging_bucket, source_check. Ordered by aging. Teaches: same SHAPE — control account that should be zero, isn't.
  - **F.5.10.b "Two-sided post mismatch" rollup.** Single table + KPI rolling up F.5.4 (internal sweep, no Fed confirmation) + F.5.5 (Fed activity, no internal post). Columns: side_present, side_missing, amount, days_outstanding, aging_bucket, source_check. Teaches: same SHAPE — one half of a two-sided event landed, the other didn't.
  - **F.5.10.c "Balance drift timelines" rollup.** Single timeline visual overlaying F.5.2 (Concentration Master vs sub-account sweep drift) + F.5.6 (GL vs FRB Master drift). Two series, shared X axis (date), shared Y axis (drift $). Teaches: same SHAPE — two related balances diverging over time.
  - F.5.9 (reversed-but-not-credited) intentionally stays standalone — different shape (compound posting integrity), top-of-tab severity placement.
  - Place rollups at the TOP of Exceptions tab; per-check details below. Order signals "look here first for the pattern."
  - Datasets prefer view abstractions (per F.5 convention) so Phase G doesn't touch them.
  - One commit per rollup (3 commits total). Commits — `Phase F.5.10.{a,b,c}: add <name> rollup view`.
- [ ] F.5.11 After all checks + rollups land: `./run_e2e.sh --parallel 4 --skip-deploy api` — confirm new datasets health-check pass.

---

## Phase F.6 — Sync other docs

- [ ] F.6.1 `README.md` — update example output, customer names, account references.
- [ ] F.6.2 `SPEC.md` — update domain model section, account hierarchy, exception check list.
- [ ] F.6.3 `RELEASE_NOTES.md` — add v2.0.0 entry summarizing structural shift + new scenarios + new checks.
- [ ] F.6.4 `CLAUDE.md` — update domain model section to reference the CMS-based account structure.
- [ ] F.6.5 Commit — `Phase F.6: sync documentation with restructured account model`.

---

## Phase F.7 — Deploy + e2e + release

- [ ] F.7.1 `demo apply --all` — schema + new seed applied to local Postgres.
- [ ] F.7.2 `deploy --all --generate` — all resources CREATION_SUCCESSFUL.
- [ ] F.7.3 Update e2e tests (`tests/e2e/test_ar_*.py`) to reference new account names + new exception sheet sections + new visuals.
- [ ] F.7.4 `cleanup --dry-run` — no stale tagged resources.
- [ ] F.7.5 `./run_e2e.sh --parallel 4` — full green (API + browser).
- [ ] F.7.6 Tag v2.0.0, push.

---

## Decisions to make in flight

- **Old PR app references to "Big Meadow Checking" etc.** Quick check during F.3: are there any PR-side references? If so, are they intentional (cross-app demo data) or legacy strays? Clean up if strays.
- **ZBA sweep amount distribution.** Production ZBA sweeps are usually one large EOD net. For training, smaller more-frequent sweeps may make patterns more visible. Tune during F.4.1.
- **Aging bucket on suspense scenarios.** Stuck-in-suspense ages from `originated_at`. Reversed-but-not-credited ages from the reversal `posted_at`. Confirm both produce useful aging across the demo's ~40-day window.
- **Synthetic FRB Master Account in demo data.** The "FRB Master — SNB" needs a representation to support GL-vs-Fed drift checks. Probably a single ledger account with daily balance snapshots generated in parallel to internal activity. Decide structure during F.4.3 / F.5.6.
- **Dataset consolidation (F.0.7).** If Exceptions tab gets too dense, revisit consolidating shape-similar checks into parametric ones (e.g., one "GL account expected-zero EOD" dataset feeding three separate KPIs).
- **View abstractions.** Decide during F.5 whether to add SQL views that wrap `transfer` + `posting` joins, so Phase G can flatten the underlying tables without touching dataset SQL. Adds complexity now in exchange for migration ease later.

---

## Risks

- **F.1 break is large and lasts ~3 commits.** Every plant list, every test, every scenario coverage assertion references the old IDs. Test suite is intentionally red between F.1 and F.3.7. Make sure to land F.1 → F.2 → F.3 in close succession; don't leave the branch in red state across days.
- **e2e tests break for the entire Phase F until F.7.** Unit tests are fixed mid-sequence; e2e depends on deployed dashboards which only get rebuilt at F.7. Keep `QS_GEN_E2E=0` throughout; only re-enable at F.7.
- **New exception checks may surface OLD planted exceptions in unexpected ways.** Re-aimed `_LIMIT_BREACH_PLANT` (F.2.3) lands on customer DDAs that may also be in on-us-internal-transfer scenarios (F.4.4). Cross-scenario interference could surface a row in two checks. May be acceptable (real banking has multi-fault items); may need separation. Assess during F.4.5.
- **Dataset count goes from ~9 to ~18 for AR.** Each new dataset is a CREATE_DATASET call during deploy; deploy time grows. F.0.7 consolidation question is the lever to pull if this becomes a problem.
- **No FEB now → less variety in the demo.** Some existing tests may have implicitly depended on having two distinct `is_internal=True` ledger families. With everything under one bank, generator variety shrinks. Watch for tests that asserted "≥ 2 internal ledger accounts" and similar.
- **Phase G (schema flattening) is now further away.** This plan locks in the current `transfer` + `posting` + ledger + sub-ledger 4-table schema for another major release. If schema flattening turns out to be more time-sensitive than expected, the trade-off is doing it BEFORE Phase F instead — Phase F's new SQL would then be written directly against the flat schema, skipping the view-abstraction half-step. Check before committing to F.0.
