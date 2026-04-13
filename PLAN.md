# PLAN — Dual-dashboard restructure + Account Recon

Goal: migrate the existing Payment Recon app into a multi-app structure, then add the Account Recon app. Review gates (**STOP**) are placed wherever the spec leaves layout or flow to iteration.

Conventions:
- Branch is already isolated; no git gymnastics needed between phases.
- After each task, run the unit suite; after each phase, run the full e2e suite (unless the phase explicitly hasn't touched deploy yet).
- Each **STOP** pauses for user review + potential replanning before the next phase.
- Phase 1 is pure refactor — no user-visible behavior change on Payment Recon.
- PLAN.md checkboxes are flipped as items complete. SPEC.md checkboxes are **not** touched in flight — they are swept once in Phase 6.3.
- After each phase's commit + tag, push the branch and the tag.

## Carried-forward assumptions (from SPEC follow-ups)

- Single `late_default_days` config value used as the default for every days-outstanding slider; users override interactively.
- Optional-sales-metadata columns are declared in a Python constant adjacent to the sales SQL in `payment_recon/datasets.py` (runtime DB introspection ruled out — production `generate` has no DB creds).
- Non-demo analysis titles: "Payment Reconciliation" and "Account Reconciliation". Demo-themed variants prefix with "Demo — ".
- Shared PG schema in demo DB; tables prefixed `pr_` (Payment Recon) and `ar_` (Account Recon).
- `cleanup` gathers all stale tagged resources, prints them, and asks once (y/n) before deleting. `--yes` skips the prompt; `--dry-run` only prints.
- Getting Started sheet sheet-switch links — if QuickSight text-blocks don't support hyperlinks to sibling sheets, fall back to a small navigation-button visual per target sheet (decide during 2.6).

---

## Phase 1 — Restructure into `payment_recon/` + `common/` (no feature change)

- [x] 1.1 Create `src/quicksight_gen/common/` and migrate the shared primitives: `models.py`, `theme.py`, `config.py` (update schema for `late_default_days`), `constants.py` (non-app-specific only), `tags.py` (extracted), `deploy.py` (new — see 1.6), `cleanup.py` (new — see 1.7).
- [x] 1.2 Create `src/quicksight_gen/payment_recon/` and move the existing app modules into it: `datasets.py`, `visuals.py`, `filters.py`, `analysis.py`, `recon_visuals.py`, `recon_filters.py`, `demo_data.py`, `constants.py` (app-specific sheet IDs).
- [x] 1.3 Rename "financial" → "payment-recon" everywhere: output filenames (`payment-recon-analysis.json`, `payment-recon-dashboard.json`), resource IDs, dataset prefixes where applicable, analysis default name ("Payment Reconciliation"; demo: "Demo — Payment Reconciliation").
- [x] 1.4 Restructure the Click CLI into subcommands:
  - `quicksight-gen generate payment-recon [--theme-preset …]`
  - `quicksight-gen generate --all`
  - `quicksight-gen demo schema|seed|apply payment-recon|--all`
  - Stub `account-recon` subcommand group that raises `NotImplementedError` so test shape is stable.
- [x] 1.5 Add `quicksight-gen deploy [payment-recon|account-recon|--all] [--generate] [--yes]`: Python port of `deploy.sh`, delete-then-create semantics (no update), async waiters for analyses/dashboards. `--generate` chains `generate` first so iteration is one command.
- [x] 1.6 Add `quicksight-gen cleanup [--dry-run] [--yes]`: lists QuickSight resources in the configured account+region tagged `ManagedBy: quicksight-gen` that are NOT in the current generate output; bulk y/n confirm then deletes. Explicit command only (not chained into `deploy`).
- [x] 1.7 Delete `deploy.sh` and `run_e2e.sh`'s shell calls to it; replace with the new Python command.
- [x] 1.8 Update unit tests: fix imports, expected resource IDs, output filenames, CLI subcommand shape; keep coverage green.
- [x] 1.9 Update e2e tests: change `dashboard_id` fixture to `qs-gen-payment-recon-dashboard`; update any tests referencing old analysis name. Keep test count/behavior identical.
- [x] 1.10 Update `run_e2e.sh` to call `quicksight-gen deploy --all --generate` (or equivalent) then `pytest tests/e2e`.
- [x] 1.11 Full test pass: `pytest` green + `./run_e2e.sh` green against a freshly redeployed dashboard.
- [x] 1.11a Add support for multiple principal_arn values in config.yaml so that multiple users can view the dashboards
- [x] 1.12 Run a full destroy to clean up any renamed resources.
- [x] 1.13 Redeploy and rerun 1.11.
- [x] **STOP for review.**
- [x] 1.14 git commit, tag v0.3.1, push branch + tag

---

## Phase 2 — Payment Recon domain additions

- [x] 2.1 Refund support: add `sale_type` column to `pr_sales` (values `sale`, `refund`), allow negative `amount`. Update demo seed to include refund rows (some timestamped later than the original sale, some not). Sales Detail table displays `sale_type`. Verify settlements/payments can net negative via signed sums.
- [x] 2.2 Optional sales metadata plumbing: declare taxes / tips / discount_percentage / cashier in a Python constant (`OPTIONAL_SALE_METADATA`) adjacent to the sales SQL, each with its SQL column + data type. Surface them on Sales Detail always. Auto-generate per-sheet filter controls by type (numeric→range, string→multi-select, date/timestamp→date-range).
- [x] 2.3 Payment methods as a filter: add `payment_method` to the merchants (or sales) schema, expose as a multi-select filter on Settlements and Payments tabs. No group-by.
- [x] 2.4 Expand Exceptions & Alerts:
  - Keep the existing unsettled-sales and returned-payments tables.
  - Add a Sales → Settlement mismatch table (sales linked to a settlement where Σ(linked sales) ≠ settlement amount).
  - Add a Settlement → Payment mismatch table (settlements linked to a payment where Σ(linked settlements) ≠ payment amount).
  - Move "external transactions without a payment" from the Payment Reconciliation tab into here.
  - Layout deliberately compact — minimize whitespace; use half-width / multi-column grids.
- [x] 2.5 Days-outstanding slider: *shipped then removed in review.* The slider was added per tab per the plan, but the date-range filter already covered the same need. Replaced with **Show-Only-X SINGLE_SELECT toggles** on Sales ("Show Only Unsettled"), Settlements ("Show Only Unpaid"), and Payments ("Show Only Unmatched Externally"). No slider anywhere now.
- [x] 2.6 "Getting Started" sheet as tab index 0: one auto-derived text block per downstream sheet (sourced from each sheet's existing plain-language description). Demo mode adds a 1–2 paragraph scenario flavor block at the top. Attempt inline hyperlinks; if unsupported, add a small navigation-button visual row. *Note: rich-text formatting deferred to Phase 6 — current blocks are plain text.*
- [x] 2.7 Update unit tests: refund math, optional-metadata filter derivation, new exception tables & subtitles, toggle presence on each tab, Getting Started tab at index 0, explanation coverage still 100%.
- [x] 2.8 Update e2e tests: new dashboard structure (6 tabs now including Getting Started), visual counts, new exception tables assertable, one browser test for the state toggles (replacing the slider browser test).
- [x] **STOP for review.** Review added: right-click drill-down pattern (settlement_id on Sales, external_transaction_id on Payments), side-by-side recon tables, slider → toggle pivot, orphan external transactions in demo data.
- [ ] 2.9 git commit, tag v0.4.0, push branch + tag

---

## Phase 3 — Account Recon skeleton (all 4 tabs, rough layout)

- [ ] 3.1 Create `src/quicksight_gen/account_recon/` with `datasets.py`, `visuals.py`, `filters.py`, `analysis.py`, `demo_data.py`, `constants.py`.
- [ ] 3.2 Demo schema (shared PG schema, `ar_` prefixed):
  - `ar_parent_accounts` (id, name, is_internal)
  - `ar_accounts` (id, name, is_internal, parent_account_id)
  - `ar_daily_balances` (account_id or parent_id, date, balance) — stored daily finals for internal accounts + parents
  - `ar_transactions` (id, account_id, transfer_id, amount, posted_at, status, memo) — memo denormalized; transfers joined via `transfer_id`
  - Views: `ar_computed_parent_daily_balance` (sum of children's transactions per day), `ar_parent_balance_drift` (stored − computed), `ar_transfer_net_zero` (per-`transfer_id` sum of non-failed transactions + net-zero flag), `ar_transfer_summary` (memo picked from the earliest `transaction_id`).
- [ ] 3.3 Demo data generator for the Farmers Exchange Bank scenario — generic valley/farm/harvest naming, no trademarked game characters/places. 80/20 success/failure mix. Plant:
  - balance-drift cases (stored ≠ computed on specific days);
  - transfers whose net-of-non-failed transactions ≠ 0;
  - individual failed transactions.
- [ ] 3.4 `farmers-exchange-bank` theme preset: earth tones + valley greens + harvest gold. Applies the "Demo — " prefix to the AR analysis when selected.
- [ ] 3.5 Rough 4-tab layout (date-range filter only; no drill-downs/extra sliders yet):
  - **Balances** — parent accounts (name, stored daily balance, computed daily balance, drift) + child accounts table.
  - **Transfers** — transfer list with Σdebit, Σcredit, net, net-zero flag, memo.
  - **Transactions** — transactions table with status, amount, posted_at, transfer_id, memo; failed rows called out.
  - **Exceptions** — balance-drift table, non-net-zero transfer table, timeline visual (line/bar by day showing when mismatches occurred).
- [ ] 3.6 Getting Started sheet for AR (same pattern as PR: auto-derived instructions + demo scenario block).
- [ ] 3.7 CLI wiring: implement the `account-recon` branches on `generate`, `demo schema|seed|apply`, `deploy`; `--all` now exercises both apps.
- [ ] 3.8 Unit tests for AR: visual builders, filter groups, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet ID scoping), explanation coverage, theme preset integration, demo data determinism + row counts + scenario coverage.
- [ ] **STOP for review.** (Layout iteration expected — filters, drill-downs, and visual choices all deferred to Phase 4.)
- [ ] 3.9 git commit, tag (version TBD at phase end), push branch + tag

---

## Phase 4 — Account Recon iteration (post-review)

*Concrete task list finalized at Phase 3 review; placeholders below.*

- [ ] 4.1 Refine visual selection / per-tab layout based on review feedback.
- [ ] 4.2 Add filters: account + parent-account multi-selects, date-range (if not already), per-tab days-outstanding sliders where meaningful.
- [ ] 4.3 Cross-sheet drill-downs for drift research — Balances → Transactions filtered by account+date; Transfers → Transactions filtered by `transfer_id`.
- [ ] 4.4 API-layer e2e tests for AR: dashboard/analysis/theme/datasets exist, sheet count, per-sheet visual counts, parameters, filter groups, dataset import health.
- [ ] **STOP for review.**

---

## Phase 5 — AR browser e2e + harness updates

- [ ] 5.1 Extend `tests/e2e/conftest.py` with a second dashboard fixture (`account_recon_dashboard_id`); keep the two fixtures independent (no parametrized dual-run).
- [ ] 5.2 Browser tests for AR: dashboard loads, tab count (5: Getting Started + 4), per-sheet visual counts, drill-downs from 4.3, filter narrowing.
- [ ] 5.3 Update `run_e2e.sh` so the one-shot runner deploys both and runs the full e2e suite.
- [ ] 5.4 Namespace screenshot output per-app if it reduces noise (`tests/e2e/screenshots/payment_recon/`, `…/account_recon/`).
- [ ] **STOP for review.**

---

## Phase 6 — Docs + release

- [ ] 6.1 README.md: two-app overview, project structure, CLI reference (`generate` / `deploy` / `cleanup` / `demo` with `--all`), demo scenarios, theming presets.
- [ ] 6.2 CLAUDE.md: new module layout, `common/` API surface, deploy-in-Python note, two-app conventions.
- [ ] 6.3 SPEC.md sweep — the one-time pass for this document: check off every item delivered across Phases 1–5, prune follow-up questions that have been resolved, and reword any lines that drifted from the shipped design. Per the Conventions note above, SPEC boxes are not touched before this step.
- [ ] 6.4 RELEASE_NOTES.md entry — version TBD at release time (v0.4.0 or v1.0.0 depending on scope feel).
- [ ] 6.5 Tag and push.
