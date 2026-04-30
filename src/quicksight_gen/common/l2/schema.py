"""Prefix-aware SQL DDL emission for an ``L2Instance`` (M.1.4 + M.1.5).

Emits one idempotent (drop-then-create) DDL script per L2 instance,
prefixed per the SPEC's storage-isolation rule (F10):

  ``<prefix>transactions``           — base table; L1 ``Transaction``
                                       denormalized with Account +
                                       Transfer fields per the
                                       Implementation Entities section.
  ``<prefix>daily_balances``         — base table; L1 ``StoredBalance``
                                       denormalized with Account fields.
  ``<prefix>current_transactions``   — view; the L1 ``CurrentTransaction``
                                       theorem materialized as max-Entry-
                                       per-ID over the base table.
  ``<prefix>current_daily_balances`` — view; the L1 ``CurrentStoredBalance``
                                       theorem materialized as max-Entry-
                                       per-(account, business_day) over
                                       the base table.

Plus B-tree indexes for the dashboard's hot-path queries on the bases.

The dashboard SQL targets the ``current_*`` views, never the bases —
that way Entry-supersession (technical-error correction per the F1
principle) is transparent to dashboard consumers.

What is NOT emitted as SQL tables (per the M.0 spike's experience):
- L2's account topology (Roles, AccountTemplates, parent_role chains) —
  the relevant fields denormalize onto the transactions / daily_balances
  rows; no separate dim table needed for v1.
- L2's Limits — projected into the ``daily_balances.limits`` Map column
  by integrator ETL; no separate limits table.
- L2's Chains, TransferTemplates — read by dashboard SQL at view-build
  time (the SQL string knows which TransferTypes can chain into which
  via L2 lookups), not materialized as tables.

The "minimum SQL surface" stance follows from the spike: M.2 (porting
AR CMS) will surface what L2 derived tables are actually needed beyond
the base layer. Add them then.
"""

from __future__ import annotations

from .primitives import L2Instance


def emit_schema(instance: L2Instance) -> str:
    """Emit the full DDL script for an L2 instance's prefixed L1 schema.

    Three layers, all per L2 instance prefix:

    1. **Base tables** — ``<prefix>_transactions`` + ``<prefix>_daily_balances``,
       v6 column shape (entry BIGSERIAL, amount_money + amount_direction,
       transfer_parent_id, rail_name, template_name, bundle_id, supersedes,
       …).
    2. **Current\\* views** — ``<prefix>_current_transactions`` +
       ``<prefix>_current_daily_balances``, materializing L1's
       max-Entry-per-logical-key theorems so dashboard SQL is transparent
       to technical-error supersession.
    3. **L1 invariant views (M.1a.7)** — ``<prefix>_drift`` /
       ``<prefix>_ledger_drift`` / ``<prefix>_overdraft`` /
       ``<prefix>_expected_eod_balance_breach`` / ``<prefix>_limit_breach``
       (plus 2 helpers: ``<prefix>_computed_subledger_balance`` +
       ``<prefix>_computed_ledger_balance``). Each materializes one of
       the SPEC's L1 SHOULD-constraints as a queryable exception
       surface; rows in these views are the constraint violations.
       Caps for ``<prefix>_limit_breach`` are embedded inline from
       ``instance.limit_schedules`` at view-emit time (CASE branches
       per declared (parent_role, transfer_type) pair) so the view DDL
       stays JSON-path-portable.

    Idempotent: every CREATE is preceded by a DROP IF EXISTS so
    re-running the same ``apply schema`` clears stale state. The
    returned string can be fed straight to ``psql`` or
    ``psycopg2.cursor.execute(sql)``.
    """
    p = instance.instance
    # L1 invariant view DROPs MUST run before base DROPs — the L1 views
    # depend on the Current* views (which depend on the base tables),
    # so dropping current_* first would error with "dependent objects
    # still exist" on a re-run. Emit L1 drops at the top of the script,
    # then the base block (which drops Current* + tables + creates
    # everything), then the L1 view CREATE statements.
    #
    # Investigation matview DROPs (N.3.b) sit alongside the L1 drops at
    # the top — they read from the base ``{p}_transactions`` table, so
    # the same dependency-ordering rule applies.
    l1_drops = _L1_INVARIANT_VIEWS_DROPS_TEMPLATE.format(p=p)
    inv_drops = _INV_MATVIEWS_DROPS_TEMPLATE.format(p=p)
    base = _SCHEMA_TEMPLATE.format(p=p)
    invariants = _emit_l1_invariant_views(instance)
    inv_views = _emit_inv_views(instance)
    return (
        l1_drops + "\n" + inv_drops + "\n" + base + "\n\n"
        + invariants + "\n\n" + inv_views
    )


def refresh_matviews_sql(instance: L2Instance) -> str:
    """Emit `REFRESH MATERIALIZED VIEW` commands in dependency order.

    M.1a.9 made every L1-pipeline view a MATERIALIZED VIEW (kills the
    correlated-subquery cost the deployed dashboard pays per visual on
    DIRECT_QUERY mode). Refresh contract for integrators: after every
    batch insert into the base tables, call this SQL to recompute
    every dependent matview. Order matters — leaves first, then
    helpers, then L1 invariants — because a downstream matview's
    REFRESH reads from upstream matview data.

    Returns one `REFRESH MATERIALIZED VIEW <name>;` per line. Caller
    splits + executes (psycopg2's cursor.execute can't run multiple
    statements separated by `;` reliably; the verify script splits on
    `;\\n` and runs each per-statement).
    """
    p = instance.instance
    names = [
        # Leaves: reads from base tables only.
        f"{p}_current_transactions",
        f"{p}_current_daily_balances",
        # Helpers: read from current_*.
        f"{p}_computed_subledger_balance",
        f"{p}_computed_ledger_balance",
        # L1 invariants: read from current_* + helpers.
        f"{p}_drift",
        f"{p}_ledger_drift",
        f"{p}_overdraft",
        f"{p}_expected_eod_balance_breach",
        f"{p}_limit_breach",
        f"{p}_stuck_pending",
        f"{p}_stuck_unbundled",
        # Dashboard-shape matviews: read from current_* +
        # L1 invariants. MUST refresh AFTER all L1 invariants are
        # fresh so todays_exceptions's UNION reads up-to-date data.
        f"{p}_daily_statement_summary",
        f"{p}_todays_exceptions",
        # Investigation matviews (N.3.b): read directly from base
        # ``{p}_transactions``, so they're independent of every L1
        # matview. Order between the two doesn't matter — they don't
        # reference each other.
        f"{p}_inv_pair_rolling_anomalies",
        f"{p}_inv_money_trail_edges",
    ]
    # REFRESH first, then ANALYZE — ANALYZE updates planner stats so
    # subsequent SELECTs use the indexes we ship on each matview
    # (without ANALYZE the planner doesn't know the post-REFRESH row
    # count + value distribution and may pick a sequential scan).
    refreshes = "\n".join(f"REFRESH MATERIALIZED VIEW {n};" for n in names)
    analyzes = "\n".join(f"ANALYZE {n};" for n in names)
    return f"{refreshes}\n{analyzes}"


def _emit_l1_invariant_views(instance: L2Instance) -> str:
    """Render the M.1a.7 L1-invariant view block for ``instance``.

    Each view drops + creates idempotently so repeated runs converge.
    Drop order is reverse of create order (no view depends on a later
    one).
    """
    p = instance.instance
    limit_cases = _render_limit_breach_cases(instance, p=p)
    pending_age_cases = _render_pending_age_cases(instance)
    unbundled_age_cases = _render_unbundled_age_cases(instance)
    return _L1_INVARIANT_VIEWS_TEMPLATE.format(
        p=p,
        limit_cases=limit_cases,
        pending_age_cases=pending_age_cases,
        unbundled_age_cases=unbundled_age_cases,
    )


def _render_limit_breach_cases(instance: L2Instance, *, p: str) -> str:
    """Build the CASE-WHEN body that the limit_breach view uses to look
    up a (parent_role, transfer_type) cap from L2's LimitSchedules.

    Inline at view-emit time (not via JSON_VALUE on daily_balances.limits)
    because dynamic-key JSON path syntax isn't portable across the SQL
    targets we support. The L2 instance's LimitSchedules are static at
    schema-emit time anyway — re-emitting the schema picks up changes.

    Returns a multi-line SQL CASE expression. References ``tx.``-prefixed
    columns since the view reads parent_role + transfer_type directly
    from the transaction row (denormalized in v6) — no JOIN to
    daily_balances needed. If the instance has no LimitSchedules,
    returns ``NULL::numeric`` (typed NULL) so the column has a concrete
    type — bare NULL infers as text in PostgreSQL and breaks the outer
    ``outbound_total > cap`` comparison with `numeric > text`.
    """
    if not instance.limit_schedules:
        return "NULL::numeric"
    branches: list[str] = []
    for ls in instance.limit_schedules:
        # Each LimitSchedule is keyed on (parent_role, transfer_type) per
        # validator U5; the cap is the threshold value.
        branches.append(
            f"WHEN tx.account_parent_role = '{ls.parent_role}' "
            f"AND tx.transfer_type = '{ls.transfer_type}' "
            f"THEN {ls.cap}"
        )
    branches_sql = "\n        ".join(branches)
    return f"CASE\n        {branches_sql}\n        ELSE NULL\n    END"


def _render_pending_age_cases(instance: L2Instance) -> str:
    """Build the CASE-WHEN body the stuck_pending view uses to look up
    a Rail's `max_pending_age` (in seconds).

    Mirror of `_render_limit_breach_cases` — inline at view-emit time
    rather than via JSON_VALUE on a per-row config column, so the SQL
    stays JSON-path-portable. Walks both TwoLegRail + SingleLegRail
    instances; each Rail with a non-None `max_pending_age` becomes one
    CASE branch keyed on `rail_name`. Rails without an aging watch get
    no branch (the outer CASE returns NULL → outer WHERE excludes them).

    Empty result if no Rail has `max_pending_age` set: returns ``NULL``
    so the view emits valid SQL but surfaces zero rows.
    """
    branches: list[str] = []
    for rail in instance.rails:
        if rail.max_pending_age is None:
            continue
        seconds = int(rail.max_pending_age.total_seconds())
        branches.append(
            f"WHEN ct.rail_name = '{rail.name}' THEN {seconds}"
        )
    if not branches:
        # Typed NULL — bare NULL infers as text and breaks the outer
        # `tx.age_seconds > tx.max_pending_age_seconds` comparison.
        return "NULL::bigint"
    branches_sql = "\n        ".join(branches)
    return f"CASE\n        {branches_sql}\n        ELSE NULL\n    END"


def _emit_inv_views(instance: L2Instance) -> str:
    """Render the N.3.b Investigation matview block for ``instance``.

    Two matviews — both per-instance prefixed:

    - ``<prefix>_inv_pair_rolling_anomalies`` — rolling 2-day SUM per
      (sender, recipient) pair + population z-score + 5-band bucket.
      Volume Anomalies sheet reads from this.
    - ``<prefix>_inv_money_trail_edges`` — ``WITH RECURSIVE`` walk over
      ``parent_transfer_id`` flattened to one row per multi-leg edge
      (with chain root + depth). Money Trail + Account Network sheets
      read from this.

    Both read only from ``<prefix>_transactions`` — no other matviews,
    no ``daily_balances``. Independent of each other; can refresh in
    any order.

    The matview bodies were lifted from ``schema.sql``'s K.4.4 / K.4.5
    definitions (N.3.a captures the originals); the only changes are
    the prefix substitutions on the matview names + the
    ``transactions`` table refs. Refresh contract is unchanged: not
    auto-refreshed, ``demo apply`` runs ``REFRESH MATERIALIZED VIEW``
    after seed inserts.
    """
    p = instance.instance
    return _INV_MATVIEWS_TEMPLATE.format(p=p)


def _render_unbundled_age_cases(instance: L2Instance) -> str:
    """Build the CASE-WHEN body the stuck_unbundled view uses to look
    up a Rail's `max_unbundled_age` (in seconds).

    Same shape as `_render_pending_age_cases`, keyed on the same
    `ct.rail_name` column. Per validator R8, `max_unbundled_age` is
    only meaningful on rails that appear in some AggregatingRail's
    `bundles_activity` — the validator catches misconfigured rails at
    L2 load time, so by the time we render here every Rail with the
    field set is bundle-eligible. Rails without `max_unbundled_age`
    get no branch (no aging watch → NULL → excluded by outer WHERE).
    """
    branches: list[str] = []
    for rail in instance.rails:
        if rail.max_unbundled_age is None:
            continue
        seconds = int(rail.max_unbundled_age.total_seconds())
        branches.append(
            f"WHEN ct.rail_name = '{rail.name}' THEN {seconds}"
        )
    if not branches:
        # Typed NULL — same reason as `_render_pending_age_cases`.
        return "NULL::bigint"
    branches_sql = "\n        ".join(branches)
    return f"CASE\n        {branches_sql}\n        ELSE NULL\n    END"


_SCHEMA_TEMPLATE = """\
-- =====================================================================
-- L2 instance: {p}
-- Generated by quicksight_gen.common.l2.schema.emit_schema
-- =====================================================================

-- Drop views first (they depend on the base tables). M.1a.9 made
-- these MATERIALIZED VIEWs.
DROP MATERIALIZED VIEW IF EXISTS {p}_current_daily_balances;
DROP MATERIALIZED VIEW IF EXISTS {p}_current_transactions;
DROP INDEX IF EXISTS idx_{p}_transactions_account_posting;
DROP INDEX IF EXISTS idx_{p}_transactions_transfer;
DROP INDEX IF EXISTS idx_{p}_transactions_type_status;
DROP INDEX IF EXISTS idx_{p}_transactions_business_day;
DROP INDEX IF EXISTS idx_{p}_transactions_parent;
DROP INDEX IF EXISTS idx_{p}_transactions_bundler_eligibility;
DROP INDEX IF EXISTS idx_{p}_daily_balances_business_day;
DROP TABLE IF EXISTS {p}_daily_balances CASCADE;
DROP TABLE IF EXISTS {p}_transactions  CASCADE;

-- ---------------------------------------------------------------------
-- L1 Transaction (denormalized with Transfer + Account fields per
-- Implementation Entities: StoredTransaction = Transaction + Transfer,
-- with Account fields also denormalized onto each leg).
--
-- entry         — BIGSERIAL append-only supersession key per L1 F's
--                 Entry primitive. Higher entry overrides lower for the
--                 same logical Transaction.id (Current* view in M.1.5).
-- amount_money  — signed Decimal per L1 Amount's "money agrees with
--                 direction" invariant. Positive ⇔ Credit; negative
--                 ⇔ Debit. The CHECK enforces sign-direction agreement.
-- transfer_parent_id — L1 Transfer.Parent recursive chain (the PR
--                 pipeline support added in Phase L's L1 spec work).
-- rail_name     — L2 Rail name that produced this leg. Required on every
--                 row so the bundler's eligibility query (M.1a / SPEC's
--                 BundleSelector RailName form) can filter without an
--                 expensive transfer→rail lookup. Denormalized at write
--                 time by integrator ETL.
-- template_name — L2 TransferTemplate name this leg belongs to (NULL for
--                 standalone-rail postings). Combined with rail_name
--                 this lets the bundler's "TransferTemplateName" and
--                 "TransferTemplateName.LegRailName" BundleSelector
--                 forms resolve to simple WHERE clauses.
-- bundle_id     — L1 Transaction.BundleId. Populated by AggregatingRail
--                 bundlers via a higher-Entry row (Supersedes =
--                 BundleAssignment); NULL on first-entry rows.
-- supersedes    — L1 Transaction.Supersedes; open enum per SPEC
--                 (no CHECK). Set on higher-Entry rows that supersede
--                 a prior row of the same id; NULL on first-entry rows.
--                 v1 categories: Inflight / BundleAssignment /
--                 TechnicalCorrection (see SPEC's "Higher-Entry rows"
--                 section for which category applies when).
-- origin        — open enum, no CHECK; integrators may extend.
-- metadata      — TEXT + IS JSON (portability constraint: no JSONB,
--                 no GIN indexes; SQL/JSON path syntax for extraction).
-- ---------------------------------------------------------------------
CREATE TABLE {p}_transactions (
    entry                BIGSERIAL      NOT NULL,
    id                   VARCHAR(100)   NOT NULL,
    account_id           VARCHAR(100)   NOT NULL,
    account_name         VARCHAR(255),
    account_role         VARCHAR(100),
    account_scope        VARCHAR(20)    NOT NULL
        CHECK (account_scope IN ('internal', 'external')),
    account_parent_role  VARCHAR(100),
    amount_money         DECIMAL(20,2)  NOT NULL,
    amount_direction     VARCHAR(20)    NOT NULL
        CHECK (amount_direction IN ('Debit', 'Credit')),
    status               VARCHAR(50)    NOT NULL,
    posting              TIMESTAMPTZ    NOT NULL,
    transfer_id          VARCHAR(100)   NOT NULL,
    transfer_type        VARCHAR(50)    NOT NULL,
    transfer_completion  TIMESTAMPTZ,
    transfer_parent_id   VARCHAR(100),
    rail_name            VARCHAR(100)   NOT NULL,
    template_name        VARCHAR(100),
    bundle_id            VARCHAR(100),
    supersedes           VARCHAR(50),
    origin               VARCHAR(50)    NOT NULL,
    metadata             TEXT,
    PRIMARY KEY (id, entry),
    -- Sign-direction agreement (L1 Amount INVARIANT):
    --   money ≥ 0 if direction = Credit; money ≤ 0 if direction = Debit.
    CHECK (
        (amount_direction = 'Credit' AND amount_money >= 0)
        OR
        (amount_direction = 'Debit'  AND amount_money <= 0)
    ),
    CHECK (metadata IS NULL OR metadata IS JSON)
);

-- ---------------------------------------------------------------------
-- L1 StoredBalance (denormalized with Account fields per Implementation
-- Entities: DailyBalance = StoredBalance + Account).
--
-- entry         — same supersession semantic as transactions.entry.
--                 Highest entry per (account_id, business_day_start)
--                 wins; older entries stay for audit.
-- expected_eod_balance — L1 ExpectedEODBalance. NULL means "no
--                 expectation" (the constraint doesn't apply).
-- limits        — JSON map of TransferType → cap, projected from L2's
--                 LimitSchedule entries by the integrator's ETL. NULL
--                 means no limit enforcement on this account-day.
-- money         — signed; CAN go negative (overdraft is observable per
--                 L1's Non-negative Stored Balance SHOULD constraint).
-- supersedes    — L1 StoredBalance.Supersedes; open enum per SPEC
--                 (no CHECK). Per the SPEC's "Higher-Entry rows"
--                 section, the only category applicable to StoredBalance
--                 is TechnicalCorrection — snapshots have no Pending
--                 lifecycle and aren't bundled. Any higher-Entry
--                 daily_balances row is by construction a correction.
-- ---------------------------------------------------------------------
CREATE TABLE {p}_daily_balances (
    entry                  BIGSERIAL      NOT NULL,
    account_id             VARCHAR(100)   NOT NULL,
    account_name           VARCHAR(255),
    account_role           VARCHAR(100),
    account_scope          VARCHAR(20)    NOT NULL
        CHECK (account_scope IN ('internal', 'external')),
    account_parent_role    VARCHAR(100),
    expected_eod_balance   DECIMAL(20,2),
    business_day_start     TIMESTAMPTZ    NOT NULL,
    business_day_end       TIMESTAMPTZ    NOT NULL,
    money                  DECIMAL(20,2)  NOT NULL,
    limits                 TEXT,
    supersedes             VARCHAR(50),
    PRIMARY KEY (account_id, business_day_start, entry),
    CHECK (business_day_end > business_day_start),
    CHECK (limits IS NULL OR limits IS JSON)
);

-- B-tree indexes for the dashboard's hot-path queries. No GIN on
-- TEXT/JSON columns per the SPEC's portability constraint.
CREATE INDEX idx_{p}_transactions_account_posting ON {p}_transactions (account_id, posting);
CREATE INDEX idx_{p}_transactions_transfer        ON {p}_transactions (transfer_id);
CREATE INDEX idx_{p}_transactions_type_status     ON {p}_transactions (transfer_type, status);
CREATE INDEX idx_{p}_transactions_parent          ON {p}_transactions (transfer_parent_id);
-- Bundler eligibility: AggregatingRails query for Posted, unbundled rows
-- by rail_name (matching their BundlesActivity selectors). Partial index
-- on `bundle_id IS NULL` keeps the index small as bundled-row count grows.
CREATE INDEX idx_{p}_transactions_bundler_eligibility
    ON {p}_transactions (rail_name, status)
    WHERE bundle_id IS NULL;
CREATE INDEX idx_{p}_daily_balances_business_day  ON {p}_daily_balances (business_day_start);

-- ---------------------------------------------------------------------
-- Current* views (M.1.5) — materialize the L1 ``CurrentTransaction`` /
-- ``CurrentStoredBalance`` theorems as max-Entry-per-logical-key over
-- the base tables. Per the SPEC's set-comprehension definitions:
--
--   CurrentTransaction := {{ tx ∈ Transaction :
--     tx.Entry = max(Transaction(ID = tx.ID).Entry) }}
--   CurrentStoredBalance := {{ sb ∈ StoredBalance :
--     sb.Entry = max(StoredBalance(Account = sb.Account,
--                                  BusinessDay = sb.BusinessDay).Entry) }}
--
-- The dashboard SQL targets these views, NOT the base tables — that way
-- Entry-supersession (technical-error correction per L1's Immutability
-- principle) is transparent to dashboard consumers. A wrong row stays
-- visible in the base table for audit; the view returns the corrected one.
-- ---------------------------------------------------------------------
-- M.1a.9 — Materialized to eliminate the per-row correlated subquery
-- that every downstream view + dataset SQL pays through. Refresh
-- contract: integrators MUST `REFRESH MATERIALIZED VIEW` after every
-- batch insert into the base tables. The library ships
-- `refresh_matviews_sql(instance)` that emits the right REFRESH order.
CREATE MATERIALIZED VIEW {p}_current_transactions AS
SELECT * FROM {p}_transactions tx
WHERE tx.entry = (
    SELECT MAX(entry) FROM {p}_transactions WHERE id = tx.id
);
-- Indexes targeting the dashboard's hot-path filters: per-account
-- date range (Daily Statement detail, Transactions sheet), per-transfer
-- (drill chain), per-status (filter dropdowns).
CREATE INDEX idx_{p}_curr_tx_account_posting
    ON {p}_current_transactions (account_id, posting);
CREATE INDEX idx_{p}_curr_tx_transfer ON {p}_current_transactions (transfer_id);
CREATE INDEX idx_{p}_curr_tx_id ON {p}_current_transactions (id);
CREATE INDEX idx_{p}_curr_tx_status ON {p}_current_transactions (status);

CREATE MATERIALIZED VIEW {p}_current_daily_balances AS
SELECT * FROM {p}_daily_balances sb
WHERE sb.entry = (
    SELECT MAX(entry)
    FROM {p}_daily_balances
    WHERE account_id = sb.account_id
      AND business_day_start = sb.business_day_start
);
-- Composite index covers (account_id, business_day_start) which every
-- downstream view JOINs / filters on. Scope index covers the WHERE
-- account_scope = 'internal' filter common in L1 invariants.
CREATE INDEX idx_{p}_curr_db_account_day
    ON {p}_current_daily_balances (account_id, business_day_start);
CREATE INDEX idx_{p}_curr_db_scope_day
    ON {p}_current_daily_balances (account_scope, business_day_start);
"""


# -- L1 invariant views (M.1a.7) ---------------------------------------------
#
# Per L2 instance, materialize the SPEC's L1 SHOULD-constraints as queryable
# exception surfaces. Each view's rows ARE the constraint violations:
# `<prefix>_drift` returns leaf-account-day cells where stored ≠ computed,
# `<prefix>_overdraft` returns rows where money < 0, etc. Dashboards
# (M.2.4 + later) just SELECT from these views — the L1 invariant SQL
# lives once per instance, not duplicated per app.
#
# All views read from the Current* views (M.1.5) so technical-error
# supersession is transparent. Drop order is reverse of create order
# (no view here depends on another in this block, but ordering is
# conservative).
_L1_INVARIANT_VIEWS_DROPS_TEMPLATE = """\
-- L1 invariant view drops (M.1a.7 + M.1a.9) — MUST run before base
-- drops because the L1 views depend on the Current* matviews (which
-- depend on the base tables). Re-emitted at the top of the script so
-- re-runs converge. M.1a.9 made these MATERIALIZED VIEWs.
--
-- Drop order: dashboard-shape matviews (todays_exceptions,
-- daily_statement_summary) drop FIRST because they read from the L1
-- invariant matviews (which read from current_* + computed_*).
--
-- Migration note: pre-M.1a.9 these were regular VIEWs; the very first
-- M.1a.9 deploy on a stale instance needs to manually
-- `DROP VIEW IF EXISTS <name>;` for each before running the script
-- (PostgreSQL refuses `DROP MATERIALIZED VIEW` on a regular VIEW).
-- Steady state (post-migration) the matview-only DROP suffices.
DROP MATERIALIZED VIEW IF EXISTS {p}_todays_exceptions;
DROP MATERIALIZED VIEW IF EXISTS {p}_daily_statement_summary;
DROP MATERIALIZED VIEW IF EXISTS {p}_stuck_unbundled;
DROP MATERIALIZED VIEW IF EXISTS {p}_stuck_pending;
DROP MATERIALIZED VIEW IF EXISTS {p}_limit_breach;
DROP MATERIALIZED VIEW IF EXISTS {p}_expected_eod_balance_breach;
DROP MATERIALIZED VIEW IF EXISTS {p}_overdraft;
DROP MATERIALIZED VIEW IF EXISTS {p}_ledger_drift;
DROP MATERIALIZED VIEW IF EXISTS {p}_drift;
DROP MATERIALIZED VIEW IF EXISTS {p}_computed_ledger_balance;
DROP MATERIALIZED VIEW IF EXISTS {p}_computed_subledger_balance;
"""


_L1_INVARIANT_VIEWS_TEMPLATE = """\
-- L1 invariant views per M.1a.7 (one set per L2 instance) ------------------
-- (DROPs moved to the top of the script so they run before the base
-- DROPs that would otherwise hit "dependent objects still exist".)

-- ---------------------------------------------------------------------
-- Helper view: ComputedBalance theorem for leaf accounts.
-- Per SPEC: ComputedBalance(account, businessDay) := Σ CurrentTransaction
-- (Account = inAccount, Status = Posted, Posting ≤ inBusinessDay.EndTime).
-- A "leaf" account is one with account_parent_role IS NOT NULL
-- (i.e., it's a child of a parent role).
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_computed_subledger_balance AS
SELECT
    sb.account_id,
    sb.business_day_start,
    sb.business_day_end,
    sb.account_parent_role,
    COALESCE((
        SELECT SUM(tx.amount_money)
        FROM {p}_current_transactions tx
        WHERE tx.account_id = sb.account_id
          AND tx.status = 'Posted'
          AND tx.posting <= sb.business_day_end
    ), 0) AS computed_balance
FROM {p}_current_daily_balances sb
WHERE sb.account_scope = 'internal'
  AND sb.account_parent_role IS NOT NULL;
-- JOIN key with current_daily_balances + drift's WHERE filter.
CREATE INDEX idx_{p}_csb_account_day
    ON {p}_computed_subledger_balance (account_id, business_day_start);

-- ---------------------------------------------------------------------
-- Helper view: ComputedBalance theorem for parent (ledger) accounts.
-- Per SPEC's LedgerDrift: stored ledger balance should equal
--   Σ child sub-ledger stored balances + Σ direct ledger postings.
-- A "parent" account is one whose role appears as account_parent_role
-- on at least one other account (resolved via subquery).
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_computed_ledger_balance AS
SELECT
    parent_db.account_id,
    parent_db.account_role,
    parent_db.business_day_start,
    parent_db.business_day_end,
    COALESCE(child_totals.child_balance, 0)
        + COALESCE(direct_totals.direct_balance, 0) AS computed_balance
FROM {p}_current_daily_balances parent_db
LEFT JOIN (
    SELECT
        child_db.account_parent_role AS parent_role,
        child_db.business_day_start,
        SUM(child_db.money) AS child_balance
    FROM {p}_current_daily_balances child_db
    WHERE child_db.account_parent_role IS NOT NULL
    GROUP BY child_db.account_parent_role, child_db.business_day_start
) child_totals
    ON child_totals.parent_role = parent_db.account_role
   AND child_totals.business_day_start = parent_db.business_day_start
LEFT JOIN (
    SELECT
        tx.account_id,
        DATE_TRUNC('day', tx.posting) AS business_day,
        SUM(tx.amount_money) AS direct_balance
    FROM {p}_current_transactions tx
    WHERE tx.status = 'Posted'
    GROUP BY tx.account_id, DATE_TRUNC('day', tx.posting)
) direct_totals
    ON direct_totals.account_id = parent_db.account_id
   AND direct_totals.business_day >= parent_db.business_day_start
   AND direct_totals.business_day < parent_db.business_day_end
WHERE parent_db.account_scope = 'internal'
  AND parent_db.account_role IS NOT NULL
  -- Only emit for accounts whose role IS a parent role to some child.
  AND EXISTS (
      SELECT 1 FROM {p}_current_daily_balances child2
      WHERE child2.account_parent_role = parent_db.account_role
  );
-- JOIN key with current_daily_balances + ledger_drift's WHERE filter.
CREATE INDEX idx_{p}_clb_account_day
    ON {p}_computed_ledger_balance (account_id, business_day_start);

-- ---------------------------------------------------------------------
-- L1 invariant: Sub-ledger drift.
-- SPEC: For every CurrentStoredBalance where Account.Scope = Internal
-- and ¬IsParent(Account), Drift(Account, BusinessDay) SHOULD equal 0.
-- Rows in this view are the violations: stored ≠ computed.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_drift AS
SELECT
    sb.account_id,
    sb.account_name,
    sb.account_role,
    sb.account_parent_role,
    sb.business_day_start,
    sb.business_day_end,
    sb.money AS stored_balance,
    cb.computed_balance,
    sb.money - cb.computed_balance AS drift
FROM {p}_current_daily_balances sb
JOIN {p}_computed_subledger_balance cb
  ON cb.account_id = sb.account_id
 AND cb.business_day_start = sb.business_day_start
WHERE sb.account_scope = 'internal'
  AND sb.account_parent_role IS NOT NULL
  AND sb.money <> cb.computed_balance;
-- Dashboard hot-path: per-sheet account dropdown + date filter, plus
-- the universal-date-range filter from M.2b.1.
CREATE INDEX idx_{p}_drift_account_day
    ON {p}_drift (account_id, business_day_start);
CREATE INDEX idx_{p}_drift_role ON {p}_drift (account_role);

-- ---------------------------------------------------------------------
-- L1 invariant: Ledger drift.
-- SPEC: For every CurrentStoredBalance where Account.Scope = Internal
-- and IsParent(Account), LedgerDrift(Account, BusinessDay) SHOULD equal 0.
-- Rows in this view are the violations.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_ledger_drift AS
SELECT
    sb.account_id,
    sb.account_name,
    sb.account_role,
    sb.business_day_start,
    sb.business_day_end,
    sb.money AS stored_balance,
    cb.computed_balance,
    sb.money - cb.computed_balance AS drift
FROM {p}_current_daily_balances sb
JOIN {p}_computed_ledger_balance cb
  ON cb.account_id = sb.account_id
 AND cb.business_day_start = sb.business_day_start
WHERE sb.money <> cb.computed_balance;
CREATE INDEX idx_{p}_ledger_drift_account_day
    ON {p}_ledger_drift (account_id, business_day_start);
CREATE INDEX idx_{p}_ledger_drift_role
    ON {p}_ledger_drift (account_role);

-- ---------------------------------------------------------------------
-- L1 invariant: Non-negative stored balance.
-- SPEC: For every CurrentStoredBalance, money SHOULD be ≥ 0.
-- Rows in this view are accounts × days where the stored balance is
-- negative (overdraft).
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_overdraft AS
SELECT
    sb.account_id,
    sb.account_name,
    sb.account_role,
    sb.account_parent_role,
    sb.business_day_start,
    sb.business_day_end,
    sb.money AS stored_balance
FROM {p}_current_daily_balances sb
WHERE sb.account_scope = 'internal'
  AND sb.money < 0;
CREATE INDEX idx_{p}_overdraft_account_day
    ON {p}_overdraft (account_id, business_day_start);
CREATE INDEX idx_{p}_overdraft_role ON {p}_overdraft (account_role);

-- ---------------------------------------------------------------------
-- L1 invariant: Expected EOD balance.
-- SPEC: For every CurrentStoredBalance where ExpectedEODBalance is
-- set, money SHOULD equal expected_eod_balance.
-- Rows are violations.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_expected_eod_balance_breach AS
SELECT
    sb.account_id,
    sb.account_name,
    sb.account_role,
    sb.business_day_start,
    sb.business_day_end,
    sb.money AS stored_balance,
    sb.expected_eod_balance,
    sb.money - sb.expected_eod_balance AS variance
FROM {p}_current_daily_balances sb
WHERE sb.expected_eod_balance IS NOT NULL
  AND sb.money <> sb.expected_eod_balance;
CREATE INDEX idx_{p}_eod_breach_account_day
    ON {p}_expected_eod_balance_breach (account_id, business_day_start);

-- ---------------------------------------------------------------------
-- L1 invariant: Limit breach.
-- SPEC: For every CurrentStoredBalance where Limits is set, for every
-- (TransferType, limit) in Limits, for every child Account whose
-- Parent = this account, OutboundFlow(child, type, businessDay)
-- SHOULD be ≤ limit.
-- Implementation: compute outbound debit totals per (account, day, type)
-- from CurrentTransaction, compare against the cap. Caps come from
-- L2's LimitSchedules — embedded inline as CASE branches at view-emit
-- time (dynamic JSON path lookup isn't portable across our SQL targets).
-- account_parent_role is denormalized on every transaction row in v6,
-- so no JOIN to daily_balances is needed (which also avoids the failure
-- mode where a breach business_day has no enclosing daily_balance row).
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_limit_breach AS
SELECT *
FROM (
    SELECT
        tx.account_id,
        tx.account_name,
        tx.account_role,
        tx.account_parent_role,
        DATE_TRUNC('day', tx.posting) AS business_day,
        tx.transfer_type,
        SUM(ABS(tx.amount_money)) AS outbound_total,
        {limit_cases} AS cap
    FROM {p}_current_transactions tx
    WHERE tx.amount_direction = 'Debit'
      AND tx.status = 'Posted'
      AND tx.account_scope = 'internal'
      AND tx.account_parent_role IS NOT NULL
    GROUP BY
        tx.account_id, tx.account_name, tx.account_role,
        tx.account_parent_role,
        DATE_TRUNC('day', tx.posting),
        tx.transfer_type
) outbound_with_cap
WHERE cap IS NOT NULL
  AND outbound_total > cap;
CREATE INDEX idx_{p}_lb_account_day
    ON {p}_limit_breach (account_id, business_day);
CREATE INDEX idx_{p}_lb_type ON {p}_limit_breach (transfer_type);

-- ---------------------------------------------------------------------
-- L1 invariant: Stuck Pending (M.2b.8).
-- SPEC-derived: every Rail with `max_pending_age` SHOULD see its legs
-- transition Pending → Posted before `posting + max_pending_age`. Rows
-- here are the violations: `status = 'Pending'` AND posting age exceeds
-- the rail's configured threshold.
--
-- Caps come from L2's per-Rail `max_pending_age`; embedded inline as
-- CASE branches at view-emit time (mirror of limit_breach's pattern,
-- so JSON-path-portable across SQL targets). Rails without a
-- `max_pending_age` get NULL and are excluded by the outer WHERE.
--
-- `max_pending_age_seconds` is the resolved cap in seconds (timedelta
-- → integer). `age_seconds` is the live age at view-refresh time —
-- recomputed each REFRESH; the matview snapshots both numbers so the
-- dashboard can sort by staleness without re-evaluating CURRENT_TIMESTAMP
-- on every visual.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_stuck_pending AS
SELECT * FROM (
    SELECT
        ct.id AS transaction_id,
        ct.account_id,
        ct.account_name,
        ct.account_role,
        ct.account_parent_role,
        ct.transfer_id,
        ct.transfer_type,
        ct.rail_name,
        ct.amount_money,
        ct.amount_direction,
        ct.posting,
        {pending_age_cases} AS max_pending_age_seconds,
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ct.posting)) AS age_seconds
    FROM {p}_current_transactions ct
    WHERE ct.status = 'Pending'
) tx
WHERE tx.max_pending_age_seconds IS NOT NULL
  AND tx.age_seconds > tx.max_pending_age_seconds;
-- Dashboard hot-path indexes — per-rail filter, per-account dropdown,
-- and the per-transfer drill (via M.2b.7 drill-target filter group).
CREATE INDEX idx_{p}_sp_rail ON {p}_stuck_pending (rail_name);
CREATE INDEX idx_{p}_sp_account ON {p}_stuck_pending (account_id);
CREATE INDEX idx_{p}_sp_transfer ON {p}_stuck_pending (transfer_id);

-- ---------------------------------------------------------------------
-- L1 invariant: Stuck Unbundled (M.2b.9).
-- SPEC-derived: every Rail with `max_unbundled_age` SHOULD see its
-- Posted legs picked up by a bundler before `posting + max_unbundled_age`.
-- Per validator R8, `max_unbundled_age` is only meaningful on rails
-- whose `transfer_type` / `rail_name` appears in some AggregatingRail's
-- `bundles_activity`. Rows here are the violations: bundle_id IS NULL
-- AND status = 'Posted' AND posting age exceeds the per-rail cap.
--
-- Caps come from L2's per-Rail `max_unbundled_age`; embedded inline as
-- CASE branches at view-emit time (mirror of stuck_pending). Same
-- live-age computation via EXTRACT(EPOCH ...) so analysts can sort by
-- staleness without re-evaluating CURRENT_TIMESTAMP.
--
-- Status filter is `'Posted'` (vs `'Pending'` for stuck_pending) since
-- AggregatingRails only bundle posted legs — a Pending leg isn't
-- "stuck unbundled," it's just "stuck pending." The two views are
-- structurally similar but cover disjoint conditions.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_stuck_unbundled AS
SELECT * FROM (
    SELECT
        ct.id AS transaction_id,
        ct.account_id,
        ct.account_name,
        ct.account_role,
        ct.account_parent_role,
        ct.transfer_id,
        ct.transfer_type,
        ct.rail_name,
        ct.amount_money,
        ct.amount_direction,
        ct.posting,
        {unbundled_age_cases} AS max_unbundled_age_seconds,
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ct.posting)) AS age_seconds
    FROM {p}_current_transactions ct
    WHERE ct.bundle_id IS NULL
      AND ct.status = 'Posted'
) tx
WHERE tx.max_unbundled_age_seconds IS NOT NULL
  AND tx.age_seconds > tx.max_unbundled_age_seconds;
-- Dashboard hot-path indexes — same shape as stuck_pending so the
-- M.2b.11 Unbundled Aging sheet's filter dropdowns hit indexed lookups.
CREATE INDEX idx_{p}_su_rail ON {p}_stuck_unbundled (rail_name);
CREATE INDEX idx_{p}_su_account ON {p}_stuck_unbundled (account_id);
CREATE INDEX idx_{p}_su_transfer ON {p}_stuck_unbundled (transfer_id);

-- ---------------------------------------------------------------------
-- Dashboard-shape matview: Daily Statement Summary.
-- M.1a.9 — moved from `apps/l1_dashboard/datasets.py` CustomSql into
-- a per-instance MATERIALIZED VIEW so QS Direct Query mode doesn't
-- re-evaluate the LAG window + GROUP BY + LEFT JOIN once per visual
-- (5 KPIs on the Daily Statement sheet = 5 re-evaluations otherwise).
-- One row per (account_id, business_day_start). Sheet-local filters
-- narrow to a single (account, day) at render time.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_daily_statement_summary AS
WITH account_days AS (
    SELECT db.account_id, db.account_name, db.account_role,
           db.account_parent_role, db.account_scope,
           db.business_day_start, db.business_day_end,
           db.money AS closing_balance_stored,
           LAG(db.money) OVER (
             PARTITION BY db.account_id
             ORDER BY db.business_day_start
           ) AS opening_balance
    FROM {p}_current_daily_balances db
),
today_flows AS (
    SELECT tx.account_id,
           DATE_TRUNC('day', tx.posting) AS business_day_start,
           SUM(CASE WHEN tx.amount_direction = 'Debit'
                    THEN tx.amount_money ELSE 0 END) AS total_debits,
           SUM(CASE WHEN tx.amount_direction = 'Credit'
                    THEN tx.amount_money ELSE 0 END) AS total_credits,
           SUM(CASE WHEN tx.amount_direction = 'Credit'
                    THEN tx.amount_money
                    ELSE -tx.amount_money END) AS net_flow,
           COUNT(*) AS leg_count
    FROM {p}_current_transactions tx
    WHERE tx.status <> 'Failed'
    GROUP BY tx.account_id, DATE_TRUNC('day', tx.posting)
)
SELECT ad.account_id, ad.account_name, ad.account_role,
       ad.account_parent_role, ad.account_scope,
       ad.business_day_start, ad.business_day_end,
       COALESCE(ad.opening_balance, 0) AS opening_balance,
       COALESCE(tf.total_debits, 0) AS total_debits,
       COALESCE(tf.total_credits, 0) AS total_credits,
       COALESCE(tf.net_flow, 0) AS net_flow,
       COALESCE(tf.leg_count, 0) AS leg_count,
       ad.closing_balance_stored,
       COALESCE(ad.opening_balance, 0)
         + COALESCE(tf.net_flow, 0) AS closing_balance_recomputed,
       ad.closing_balance_stored
         - (COALESCE(ad.opening_balance, 0)
            + COALESCE(tf.net_flow, 0)) AS drift
FROM account_days ad
LEFT JOIN today_flows tf
  ON tf.account_id = ad.account_id
  AND tf.business_day_start = ad.business_day_start;
-- Daily Statement sheet's per-(account, day) parameter filter — both
-- columns participate in the WHERE so a composite index covers the
-- KPIs + detail table at once.
CREATE INDEX idx_{p}_dss_account_day
    ON {p}_daily_statement_summary (account_id, business_day_start);

-- ---------------------------------------------------------------------
-- Dashboard-shape matview: Today's Exceptions UNION.
-- M.1a.9 — moved from `apps/l1_dashboard/datasets.py` CustomSql into
-- a per-instance MATERIALIZED VIEW so each visual on Today's
-- Exceptions queries a precomputed table instead of re-running the
-- 5-branch UNION ALL (each branch with its own MAX subquery).
-- One row per L1 invariant violation on the most recent business day.
-- `magnitude` normalized per branch so sort-by-magnitude reads
-- consistently regardless of check_type.
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW {p}_todays_exceptions AS
WITH latest_day AS (
    SELECT MAX(business_day_start) AS day
    FROM {p}_current_daily_balances
)
-- Per-day branches (drift / ledger_drift / overdraft / limit_breach /
-- expected_eod_balance_breach) — each is a per-(account, day) cell, so
-- "today's exception" filters to MAX(business_day) from current_daily_balances.
SELECT 'drift' AS check_type, account_id, account_name,
       account_role, account_parent_role,
       business_day_start AS business_day,
       NULL::TEXT AS transfer_type,
       ABS(drift) AS magnitude
FROM {p}_drift, latest_day
WHERE business_day_start = latest_day.day
UNION ALL
SELECT 'ledger_drift', account_id, account_name, account_role,
       NULL, business_day_start, NULL, ABS(drift)
FROM {p}_ledger_drift, latest_day
WHERE business_day_start = latest_day.day
UNION ALL
SELECT 'overdraft', account_id, account_name, account_role,
       account_parent_role, business_day_start, NULL,
       ABS(stored_balance)
FROM {p}_overdraft, latest_day
WHERE business_day_start = latest_day.day
UNION ALL
SELECT 'limit_breach', account_id, account_name, account_role,
       account_parent_role, business_day, transfer_type,
       (outbound_total - cap)
FROM {p}_limit_breach, latest_day
WHERE business_day = latest_day.day
UNION ALL
SELECT 'expected_eod_balance_breach', account_id, account_name,
       account_role, NULL, business_day_start, NULL, ABS(variance)
FROM {p}_expected_eod_balance_breach, latest_day
WHERE business_day_start = latest_day.day
-- Currently-open branches (M.4.4.12) — stuck_pending and stuck_unbundled
-- are matviews of legs whose age has exceeded a per-rail cap measured
-- against CURRENT_TIMESTAMP. By construction every row is "currently
-- stuck", so no per-day filter applies — include them all in the rollup.
UNION ALL
SELECT 'stuck_pending', account_id, account_name, account_role,
       account_parent_role, posting::date AS business_day,
       transfer_type, amount_money AS magnitude
FROM {p}_stuck_pending
UNION ALL
SELECT 'stuck_unbundled', account_id, account_name, account_role,
       account_parent_role, posting::date AS business_day,
       transfer_type, amount_money AS magnitude
FROM {p}_stuck_unbundled;
-- Today's Exceptions sheet has 3 dropdowns (check_type, account,
-- transfer_type); each WHERE filter benefits from its own index.
CREATE INDEX idx_{p}_te_check_type
    ON {p}_todays_exceptions (check_type);
CREATE INDEX idx_{p}_te_account ON {p}_todays_exceptions (account_id);
CREATE INDEX idx_{p}_te_type ON {p}_todays_exceptions (transfer_type);
"""


_INV_MATVIEWS_DROPS_TEMPLATE = """\
-- Investigation matview drops (N.3.b) — like the L1 invariant matview
-- drops, these MUST run before the base ``{p}_transactions`` table is
-- dropped, so we emit them at the top of the script.
DROP MATERIALIZED VIEW IF EXISTS {p}_inv_money_trail_edges;
DROP MATERIALIZED VIEW IF EXISTS {p}_inv_pair_rolling_anomalies;
"""


_INV_MATVIEWS_TEMPLATE = """\
-- =====================================================================
-- Investigation matviews per N.3.b (one set per L2 instance) -----------
-- =====================================================================
-- These are the K.4.4 + K.4.5 matviews lifted out of the legacy
-- schema.sql and prefixed for per-instance storage isolation. Read
-- only from {p}_transactions; refresh contract is unchanged
-- (``demo apply`` runs ``REFRESH MATERIALIZED VIEW`` after seed).

-- Investigation: pair-grain rolling-window anomaly matview.
-- Volume Anomalies sheet flags (sender, recipient) pairs whose 2-day
-- rolling SUM crosses the sigma-threshold parameter. Computing the
-- rolling window + population z-score on every dataset load was slow
-- enough at realistic transaction volumes to wedge QuickSight Direct
-- Query, so the work happens at refresh time instead.
--
-- Window semantics: for each (sender, recipient) day with activity,
-- the row's window covers [posted_day - 1, posted_day] (today +
-- yesterday). The 2-day length is hardcoded — a window-length
-- slider would require either multiple matviews or a generate_series
-- scan at dataset time.
--
-- Recipient filter mirrors the recipient-fanout dataset: only `dda`
-- and `merchant_dda` recipients qualify, so administrative sweeps
-- into GL control / concentration master accounts don't dominate the
-- population distribution and crowd out genuine signal.
--
-- IMPORTANT — refresh contract: this matview is NOT auto-refreshed.
-- Operators must run
--     REFRESH MATERIALIZED VIEW {p}_inv_pair_rolling_anomalies;
-- after each ETL load.
CREATE MATERIALIZED VIEW {p}_inv_pair_rolling_anomalies AS
WITH pair_legs AS (
    SELECT
        recipient.account_id          AS recipient_account_id,
        recipient.account_name        AS recipient_account_name,
        recipient.account_type        AS recipient_account_type,
        sender.account_id             AS sender_account_id,
        sender.account_name           AS sender_account_name,
        sender.account_type           AS sender_account_type,
        recipient.posted_at::date     AS posted_day,
        recipient.transfer_id,
        recipient.signed_amount       AS amount
    FROM {p}_transactions recipient
    JOIN {p}_transactions sender
      ON sender.transfer_id = recipient.transfer_id
     AND sender.signed_amount < 0
    WHERE recipient.signed_amount > 0
      AND recipient.status = 'success'
      AND sender.status = 'success'
      AND recipient.account_type IN ('dda', 'merchant_dda')
),
pair_daily AS (
    -- Collapse to one row per (pair, day) before windowing so the
    -- rolling SUM ranges over distinct days rather than individual legs.
    SELECT
        recipient_account_id,
        recipient_account_name,
        recipient_account_type,
        sender_account_id,
        sender_account_name,
        sender_account_type,
        posted_day,
        SUM(amount)                 AS day_sum,
        COUNT(DISTINCT transfer_id) AS day_transfer_count
    FROM pair_legs
    GROUP BY
        recipient_account_id, recipient_account_name, recipient_account_type,
        sender_account_id, sender_account_name, sender_account_type,
        posted_day
),
pair_windows AS (
    -- Rolling 2-day SUM per pair, anchored on each active day. RANGE
    -- INTERVAL handles sparse days correctly: a pair with activity on
    -- day N but not N-1 gets a 1-day window — semantically a single
    -- spike — rather than a phantom zero contribution.
    SELECT
        recipient_account_id,
        recipient_account_name,
        recipient_account_type,
        sender_account_id,
        sender_account_name,
        sender_account_type,
        posted_day,
        SUM(day_sum) OVER w            AS window_sum,
        SUM(day_transfer_count) OVER w AS transfer_count
    FROM pair_daily
    WINDOW w AS (
        PARTITION BY recipient_account_id, sender_account_id
        ORDER BY posted_day
        RANGE BETWEEN INTERVAL '1 day' PRECEDING AND CURRENT ROW
    )
),
population AS (
    -- Single-row scalar: mean + sample stddev across every pair-window.
    -- Sample stddev (STDDEV_SAMP) matches the analyst convention of
    -- "this window vs. the rest of the population".
    SELECT
        AVG(window_sum)::NUMERIC                       AS pop_mean,
        COALESCE(STDDEV_SAMP(window_sum), 0)::NUMERIC  AS pop_stddev
    FROM pair_windows
)
SELECT
    pw.recipient_account_id,
    pw.recipient_account_name,
    pw.recipient_account_type,
    pw.sender_account_id,
    pw.sender_account_name,
    pw.sender_account_type,
    (pw.posted_day - INTERVAL '1 day')::TIMESTAMP   AS window_start,
    pw.posted_day::TIMESTAMP                        AS window_end,
    pw.window_sum,
    pw.transfer_count,
    pop.pop_mean,
    pop.pop_stddev,
    CASE
        WHEN pop.pop_stddev = 0 THEN 0
        ELSE (pw.window_sum - pop.pop_mean) / pop.pop_stddev
    END                                             AS z_score,
    CASE
        WHEN pop.pop_stddev = 0 THEN '0-1 sigma'
        WHEN ABS((pw.window_sum - pop.pop_mean) / pop.pop_stddev) < 1 THEN '0-1 sigma'
        WHEN ABS((pw.window_sum - pop.pop_mean) / pop.pop_stddev) < 2 THEN '1-2 sigma'
        WHEN ABS((pw.window_sum - pop.pop_mean) / pop.pop_stddev) < 3 THEN '2-3 sigma'
        WHEN ABS((pw.window_sum - pop.pop_mean) / pop.pop_stddev) < 4 THEN '3-4 sigma'
        ELSE '4+ sigma'
    END                                             AS z_bucket
FROM pair_windows pw
CROSS JOIN population pop;


-- Investigation: money-trail recursive-CTE matview.
-- Money Trail sheet walks `parent_transfer_id` chains from a given
-- root, flattening each hop to a (source_account, target_account,
-- hop_amount) edge so a Sankey can render the chain. Computing the
-- recursive walk + leg pairing on every dataset query was a
-- non-starter for QuickSight Direct Query at chain depths > 2.
--
-- Two-step structure:
--   1. WITH RECURSIVE walks `parent_transfer_id` from each root
--      (transfer with NULL parent) down through descendants, tagging
--      every member with its `root_transfer_id` and `depth`.
--   2. Each chain member is then joined back to {p}_transactions and
--      split into source-leg (signed_amount < 0) x target-leg
--      (signed_amount > 0) pairs sharing the transfer_id, producing
--      one row per edge.
--
-- Multi-leg-only semantics: single-leg transfers (sale records,
-- inflow-only `external_txn` arrival rows) have no source or no
-- target leg by themselves and are dropped from the trail. They
-- still appear as chain members (counted by depth) -- they just
-- don't contribute visible edges. The chain ancestry is preserved
-- because the recursive walk operates on `transfer_id` /
-- `parent_transfer_id` directly, not on legs.
--
-- IMPORTANT — refresh contract: this matview is NOT auto-refreshed.
-- Operators must run
--     REFRESH MATERIALIZED VIEW {p}_inv_money_trail_edges;
-- after each ETL load.
CREATE MATERIALIZED VIEW {p}_inv_money_trail_edges AS
WITH RECURSIVE
distinct_transfers AS (
    -- One row per transfer_id with its parent. {p}_transactions has
    -- one row per leg, so we deduplicate before walking — the parent
    -- linkage is transfer-level, not leg-level. Note: {p}_transactions
    -- carries the parent linkage in ``transfer_parent_id`` (v6 column).
    -- The legacy global matview read ``parent_transfer_id`` from the
    -- v5 base table.
    SELECT DISTINCT transfer_id, transfer_parent_id
    FROM {p}_transactions
),
chain AS (
    -- Roots: transfers with no parent. Each root labels itself.
    SELECT
        transfer_id,
        transfer_id AS root_transfer_id,
        0           AS depth
    FROM distinct_transfers
    WHERE transfer_parent_id IS NULL

    UNION ALL

    -- Descendants inherit the root and bump depth.
    SELECT
        d.transfer_id,
        c.root_transfer_id,
        c.depth + 1
    FROM distinct_transfers d
    JOIN chain c ON d.transfer_parent_id = c.transfer_id
)
SELECT
    c.root_transfer_id,
    c.transfer_id,
    c.depth,
    src.account_id           AS source_account_id,
    src.account_name         AS source_account_name,
    src.account_type         AS source_account_type,
    tgt.account_id           AS target_account_id,
    tgt.account_name         AS target_account_name,
    tgt.account_type         AS target_account_type,
    tgt.signed_amount        AS hop_amount,
    tgt.posted_at            AS posted_at,
    tgt.transfer_type        AS transfer_type
FROM chain c
JOIN {p}_transactions tgt
  ON tgt.transfer_id = c.transfer_id
 AND tgt.signed_amount > 0
 AND tgt.status = 'success'
JOIN {p}_transactions src
  ON src.transfer_id = c.transfer_id
 AND src.signed_amount < 0
 AND src.status = 'success';
"""
