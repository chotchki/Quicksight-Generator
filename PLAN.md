# QuickSight Generator — Active Plan

**Where we are.** Phase M shipped v6.0.0 (L2 foundation + 4-app shape). Historical context for phases G–M lives in `PLAN_ARCHIVE.md`.

**Active phases below.** Phase N reshapes the two carry-over apps (Investigation, Executives) onto the L1/L2 primitives that L1 Dashboard + L2 Flow Tracing already use, and lifts theme out of code into the L2 YAML so each instance carries its own brand. Phase O renders docs + training against the L2 instance vocabulary instead of today's hand-written Sasquatch copy. Everything else collects in **Backlog**.

---

## Phase N — Port Investigation + Executives onto L1/L2; theme as L2 attribute

**Goal.** Make L2-fed apps the only model. Today Investigation + Executives still read directly from the shared base tables and carry their own per-app theme presets in `common/theme.py`. Phase N folds them into the L1/L2 stack so a single L2 YAML drives all four apps' shape, schema, and theme.

**Sequencing rationale.** Theme moves first (N.1) because it's a pure L2-side change — no app rewiring — and the reshapes that follow can pick up the new attribute. Audit happens before the reshapes (N.2) to confirm the question shape each app answers and decide keep / reshape / delete per app rather than committing in advance.

- [ ] **N.1 — Theme as an L2 YAML attribute.** Today's `PRESETS` dict in `common/theme.py` collapses to one theme per L2 instance, declared inline in the L2 YAML.
  - Add a top-level `theme:` block to `L2Instance` (primary / secondary / accent / link / etc. — match today's `ThemePreset` dataclass shape).
  - Loader parses; validator rejects malformed hex.
  - All four apps resolve theme from the L2 instance, not from `cfg.theme_preset`. Drop `--theme-preset` from the CLI.
  - `tests/l2/spec_example.yaml` + `tests/l2/sasquatch_pr.yaml` carry their own theme blocks; the existing presets become the seed values.

- [ ] **N.2 — Inv + Exec audit + reshape decision.** Read each app's surface fresh; decide per-app: **keep / reshape onto L2 / delete**. Reshape is the default expectation, but pick it deliberately.
  - What does Investigation answer that L1+L2FT don't? (Recipient Fanout, Volume Anomalies, Money Trail, Account Network — all key on `transactions` semantics.)
  - What does Executives summarize that the L1 KPI rollup doesn't? (Account Coverage, Transaction Volume, Money Moved.)
  - Capture in `docs/audits/n_2_inv_exec_audit.md`.
  - Output: per-app decision + sketch of L2 primitives consumed (or new primitives needed).

- [ ] **N.3 — Investigation reshape.** Port Investigation onto L1/L2 primitives if N.2 chose reshape. The 4 sheets all key on `transactions` semantics; map to the L2 model's per-instance prefixed schema. Investigation's matview SQL becomes per-prefix the way the L1 invariant views are.

- [ ] **N.4 — Executives reshape.** Port Executives onto L1/L2 primitives if N.2 chose reshape. The 3 operational sheets summarize over the same base; should compose from L2 instance metadata.

- [ ] **N.5 — End-of-phase iteration gate.** Cut **v6.1.0** — L2 YAML is the only configuration surface for app shape + theme. All four apps L2-fed, no per-app theme presets, no hand-rolled persona globals.

---

## Phase O — Docs + training render pipeline

**Goal.** Handbook + training pages render against the L2 instance's vocabulary instead of today's hand-written Sasquatch-flavored copy. Replaces `mapping.yaml` substitution.

- [ ] **O.1 — Docs render pipeline.**
  - Handbook prose templated against L2 persona vocabulary. mkdocs render step that takes `(L2 instance, neutral templates) → rendered handbook`.
  - The deferred L.5 "always-emitted persona leaks" cleanup happens here naturally (see `PLAN_ARCHIVE.md` for the audit findings).
  - Per F12 (`PLAN_ARCHIVE.md` M.0.10): any sub-step that invokes `ScreenshotHarness` MUST run a DB warm-up `SELECT 1` against `cfg.demo_database_url` right before fetching the embed URL — Aurora Serverless cold-start otherwise surfaces as QS's generic "We can't open that dashboard" error.
  - **Major idea**: add a sheet at the end of each dashboard and load the documentation into the dashboard itself (sibling to the existing `Info` canary sheet).
  - **L2 topology diagram render** (deferred from M.3.10d). The L2 instance is a graph; render as SVG via Graphviz `dot` (hierarchical) or `neato`/`sfdp` (force-directed) and embed in the handbook. Three plausible cuts: account-rail-account topology, chain DAG, layered combination. The `build_chains_dataset` in `apps/l2_flow_tracing/datasets.py` (CHAINS_CONTRACT) is the pre-shaped input for the chain DAG cut.

- [ ] **O.2 — Training render pipeline.**
  - Training site rendered from L2 + ScreenshotHarness regenerated per L2 instance.
  - Includes the deferred L.8 Executives handbook + walkthroughs (see `PLAN_ARCHIVE.md` Backlog).
  - Same `SELECT 1` warm-up requirement as O.1.

- [ ] **O.3 — Iteration gate.** Docs + training render against any L2 instance the integrator points at. Handbook publishing pipeline supports per-customer renders.

---

## Backlog

Single grab-bag for everything not yet in a phase. Promote to a numbered phase entry when work starts. Full historical detail in `PLAN_ARCHIVE.md`.

### Punted from Phase M ship push

- **CLI workflow polish.** Materialize the SPEC's "Workflow Ideas" — `generate config (demo|template)`, `apply schema`, `apply data`, `apply dashboards`, `generate training`. Acceptance: a fresh integrator can run end-to-end from one YAML.
- **QS-UI kitchen-sink reference tool.** Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.
- **L2FT plants-visible date-filter widening.** `assert_l2ft_plants_visible` hard-fails on sasquatch_pr because some planted firings have `days_ago` exceeding the L2FT dashboard's default date filter window. Same family as the L1 dynamic widening fix (M.4.4.12). Currently wrapped in inline xfail.
- **Drop AR-only schema.sql carry-overs.** `ar_ledger_accounts` / `ar_subledger_accounts` dimension tables stay in `schema.sql` because Investigation's demo seed registers its own sub-ledgers there for FK integrity. Phase N's Investigation reshape decides whether Inv migrates off the AR dim tables — once it does, drop the carry-overs.

### L2 model gaps

- **Validator: every Transfer MUST match a Rail.**
- **Validator: no overlap on (role, transfer_type) entries.**
- **Multiple dashboards from one L2 instance** (shared prefix + naming).
- **PR dashboard → generic L2-validation dashboard** (re-skinning of L2FT for a different validation persona).
- **Lift seed primitives into `common/l2/seed.py`** (was M.2d.5).

### Tooling / test reliability

- **Single-app deploy must not orphan shared datasource.**
- **Apply layered (query+render) pattern to all browser e2e tests** (was M.4.1.k).
- **L1 dashboard date filter doesn't surface matview rows** (root cause TBD — non-blocking workaround in place).
- **PR FilterControl dropdown e2e tests hang on dropdown open** — 5 tests in `tests/e2e/test_filters.py` time out waiting on the MUI listbox popover under `data-automation-context`. (Deleted with PR app in M.4.4 — left as reference if the dropdown helper is reused.)

### Audit / data evaluation / app info

- **Audit-readiness columns** on Daily Statement (per-row leg-match percentage, etc.) for regulator reporting. Don't use QS pixel-perfect (cost); start with PDF-print guidance in training material.
- **Postgres dataset evaluator** — given a connection, evaluate whether all exception cases are present; report stats on the CLI.
- **App Info sheet enhancements** — version of `quicksight-gen` used to generate (so version mismatches are detectable); most-recent `transactions` / `daily_balances` row date (so ETL can be troubleshooted); most-recent matview refresh timestamp.

### Tech debt

- **Encode more invariants in the type system.** K.2 did this for drill-param shape compatibility; Phase L's tree primitives close another big chunk. What remains after L is the candidate list for the next round.

### Known platform limitations — do not re-attempt without new evidence

- **QS URL-parameter control sync** — K.4.7 cross-app drills dropped. URL fragment sets the parameter store but doesn't push values into bound controls. Re-entry conditions: AWS fix, custom embedded app via `setParameters()` SDK, or a new URL form that triggers control sync. See `PLAN_ARCHIVE.md` for full re-entry details.
- **Cross-app dataset prune drops sibling app's non-default-L2 datasets.** When two L2-fed apps deploy against the same non-default L2 instance, generating one prunes the other's already-generated dataset JSONs. Workaround: skip the CLI; write JSON directly via Python. Fix candidates (option 3 recommended — per-app-prefix prune) in `PLAN_ARCHIVE.md`.
