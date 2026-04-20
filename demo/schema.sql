-- QuickSight Demo Schema
-- Target: PostgreSQL 17+ (SQL/JSON path functions; portable subset only)
--
-- Defines the tables and views that the QuickSight dataset SQL queries
-- run against.  The DROP IF EXISTS cascade at the top makes this script
-- idempotent — safe to re-run.
--
-- Both apps (Payment Recon + Account Recon) feed the shared
-- `transactions` + `daily_balances` base layer.  AR-specific dimension
-- tables (`ar_ledger_accounts`, `ar_subledger_accounts`,
-- `ar_ledger_transfer_limits`) carry the canonical account hierarchy
-- and per-type limit configuration that the views read against.

-- -------------------------------------------------------------------
-- Drop legacy objects (pre-v3.0.0 installations: unprefixed pre-v0.4
-- tables, the `pr_*` per-app tables, and the AR-only `transfer` /
-- `posting` tables that pre-dated the unified base layer).
-- -------------------------------------------------------------------

DROP VIEW  IF EXISTS payment_recon_view    CASCADE;
DROP VIEW  IF EXISTS settlement_recon_view CASCADE;
DROP VIEW  IF EXISTS sales_recon_view      CASCADE;
DROP TABLE IF EXISTS payments              CASCADE;
DROP TABLE IF EXISTS sales                 CASCADE;
DROP TABLE IF EXISTS settlements           CASCADE;
DROP TABLE IF EXISTS external_transactions CASCADE;
DROP TABLE IF EXISTS merchants             CASCADE;
DROP TABLE IF EXISTS late_thresholds       CASCADE;

DROP VIEW  IF EXISTS pr_payment_recon_view           CASCADE;
DROP VIEW  IF EXISTS pr_sale_settlement_mismatch     CASCADE;
DROP VIEW  IF EXISTS pr_settlement_payment_mismatch  CASCADE;
DROP VIEW  IF EXISTS pr_unmatched_external_txns      CASCADE;
DROP TABLE IF EXISTS pr_payments              CASCADE;
DROP TABLE IF EXISTS pr_sales                 CASCADE;
DROP TABLE IF EXISTS pr_settlements           CASCADE;
DROP TABLE IF EXISTS pr_external_transactions CASCADE;
DROP TABLE IF EXISTS pr_merchants             CASCADE;


-- ===================================================================
-- Shared base layer
--
-- Two-table feed contract for both AR and PR.  Every money-movement
-- leg lands in `transactions`; every (account, date) snapshot lands
-- in `daily_balances`.  Account name / type / control-account are
-- denormalized onto every row so common analyst queries need no joins.
--
-- The `metadata TEXT` column carries JSON; query it with SQL/JSON
-- path functions (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`).  System
-- compatibility requires PostgreSQL 17+.  Forbidden by portability
-- constraint: JSONB, `->>` / `->` / `@>` / `?` operators, GIN indexes
-- on JSON, Postgres extensions, array / range types.
--
-- See docs/Schema_v3.md for the full feed contract, canonical
-- account_type values, metadata key catalog, and ETL examples.
-- ===================================================================

DROP TABLE IF EXISTS daily_balances CASCADE;
DROP TABLE IF EXISTS transactions   CASCADE;

CREATE TABLE transactions (
    transaction_id      VARCHAR(100)   PRIMARY KEY,
    transfer_id         VARCHAR(100)   NOT NULL,
    parent_transfer_id  VARCHAR(100),
    transfer_type       VARCHAR(30)    NOT NULL
        CHECK (transfer_type IN (
            'sale', 'settlement', 'payment', 'external_txn',
            'ach', 'wire', 'internal', 'cash',
            'funding_batch', 'fee', 'clearing_sweep'
        )),
    origin              VARCHAR(30)    NOT NULL DEFAULT 'internal_initiated'
        CHECK (origin IN ('internal_initiated', 'external_force_posted')),
    account_id          VARCHAR(100)   NOT NULL,
    account_name        VARCHAR(255)   NOT NULL,
    control_account_id  VARCHAR(100),
    account_type        VARCHAR(50)    NOT NULL,
    is_internal         BOOLEAN        NOT NULL,
    signed_amount       DECIMAL(14,2)  NOT NULL,
    amount              DECIMAL(14,2)  NOT NULL,
    status              VARCHAR(20)    NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failed')),
    posted_at           TIMESTAMP      NOT NULL,
    balance_date        DATE           NOT NULL,
    external_system     VARCHAR(100),
    memo                VARCHAR(255),
    metadata            TEXT,
    CHECK (metadata IS NULL OR metadata IS JSON)
);

CREATE TABLE daily_balances (
    account_id          VARCHAR(100)   NOT NULL,
    account_name        VARCHAR(255)   NOT NULL,
    control_account_id  VARCHAR(100),
    account_type        VARCHAR(50)    NOT NULL,
    is_internal         BOOLEAN        NOT NULL,
    balance_date        DATE           NOT NULL,
    balance             DECIMAL(14,2)  NOT NULL,
    metadata            TEXT,
    PRIMARY KEY (account_id, balance_date),
    CHECK (metadata IS NULL OR metadata IS JSON)
);

-- B-tree only.  No GIN on metadata; no expression indexes on JSON-path
-- extractions.  If a metadata key needs to be indexed, lift it to a
-- first-class column instead.  The (account_id, balance_date) lookup
-- on daily_balances is served by the PK index.
CREATE INDEX idx_transactions_account_date ON transactions(account_id, posted_at);
CREATE INDEX idx_transactions_transfer     ON transactions(transfer_id);
CREATE INDEX idx_transactions_type_status  ON transactions(transfer_type, status);
CREATE INDEX idx_transactions_control      ON transactions(control_account_id);
CREATE INDEX idx_transactions_balance_date ON transactions(balance_date);
CREATE INDEX idx_transactions_parent       ON transactions(parent_transfer_id);

CREATE INDEX idx_daily_balances_date    ON daily_balances(balance_date);
CREATE INDEX idx_daily_balances_control ON daily_balances(control_account_id, balance_date);


-- ===================================================================
-- Account Reconciliation (ar_ prefix)
--
-- Double-entry bank-account model. Two independent drift checks:
--   Sub-ledger drift = stored sub-ledger balance vs running Σ posted txns
--                      (fires when the sub-ledger-balance upstream feed
--                      disagrees with the underlying transactions)
--   Ledger drift     = stored ledger balance vs Σ sub-ledgers' stored balances
--                      (fires when the ledger-balance upstream feed disagrees
--                      with the aggregation of its sub-ledgers — independent
--                      of whether the sub-ledger feed and the transactions
--                      agree)
--
-- Ledger- and sub-ledger-level stored balances may come from different
-- upstream systems, so each drift points at a different source.
-- ===================================================================

-- Drop legacy parent/child-named objects (pre-v1.2.0 installations) so
-- `demo apply` cleans up before recreating under the new vocabulary.
DROP VIEW  IF EXISTS ar_child_overdraft                CASCADE;
DROP VIEW  IF EXISTS ar_child_limit_breach             CASCADE;
DROP VIEW  IF EXISTS ar_child_daily_outbound_by_type   CASCADE;
DROP VIEW  IF EXISTS ar_parent_balance_drift           CASCADE;
DROP VIEW  IF EXISTS ar_account_balance_drift          CASCADE;
DROP VIEW  IF EXISTS ar_computed_parent_daily_balance  CASCADE;
DROP VIEW  IF EXISTS ar_computed_account_daily_balance CASCADE;
DROP TABLE IF EXISTS ar_parent_transfer_limits         CASCADE;
DROP TABLE IF EXISTS ar_parent_daily_balances          CASCADE;
DROP TABLE IF EXISTS ar_account_daily_balances         CASCADE;
DROP TABLE IF EXISTS ar_accounts                       CASCADE;
DROP TABLE IF EXISTS ar_parent_accounts                CASCADE;

-- Current-vocabulary drops
DROP VIEW  IF EXISTS ar_balance_drift_timelines_rollup   CASCADE;
DROP VIEW  IF EXISTS ar_two_sided_post_mismatch_rollup   CASCADE;
DROP VIEW  IF EXISTS ar_expected_zero_eod_rollup         CASCADE;
DROP VIEW  IF EXISTS ar_internal_reversal_uncredited     CASCADE;
DROP VIEW  IF EXISTS ar_internal_transfer_suspense_nonzero CASCADE;
DROP VIEW  IF EXISTS ar_internal_transfer_stuck          CASCADE;
DROP VIEW  IF EXISTS ar_gl_vs_fed_master_drift           CASCADE;
DROP VIEW  IF EXISTS ar_fed_card_no_internal_catchup     CASCADE;
DROP VIEW  IF EXISTS ar_ach_sweep_no_fed_confirmation    CASCADE;
DROP VIEW  IF EXISTS ar_ach_orig_settlement_nonzero      CASCADE;
DROP VIEW  IF EXISTS ar_concentration_master_sweep_drift CASCADE;
DROP VIEW  IF EXISTS ar_sweep_target_nonzero             CASCADE;
DROP VIEW  IF EXISTS ar_subledger_overdraft              CASCADE;
DROP VIEW  IF EXISTS ar_subledger_limit_breach           CASCADE;
DROP VIEW  IF EXISTS ar_subledger_daily_outbound_by_type CASCADE;
DROP VIEW  IF EXISTS ar_transfer_summary                 CASCADE;
DROP VIEW  IF EXISTS ar_transfer_net_zero                CASCADE;
DROP VIEW  IF EXISTS ar_ledger_balance_drift             CASCADE;
DROP VIEW  IF EXISTS ar_subledger_balance_drift          CASCADE;
DROP VIEW  IF EXISTS ar_computed_ledger_daily_balance    CASCADE;
DROP VIEW  IF EXISTS ar_computed_subledger_daily_balance CASCADE;
DROP TABLE IF EXISTS ar_ledger_transfer_limits           CASCADE;
DROP TABLE IF EXISTS ar_transactions                     CASCADE;
DROP TABLE IF EXISTS ar_subledger_daily_balances         CASCADE;
DROP TABLE IF EXISTS ar_ledger_daily_balances            CASCADE;
DROP TABLE IF EXISTS ar_subledger_accounts               CASCADE;
DROP TABLE IF EXISTS ar_ledger_accounts                  CASCADE;

-- Unified transfer/posting tables (Phase B)
DROP TABLE IF EXISTS posting                             CASCADE;
DROP TABLE IF EXISTS transfer                            CASCADE;


CREATE TABLE ar_ledger_accounts (
    ledger_account_id VARCHAR(100) PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    is_internal       BOOLEAN      NOT NULL
);

CREATE TABLE ar_subledger_accounts (
    subledger_account_id VARCHAR(100) PRIMARY KEY,
    name                 VARCHAR(255) NOT NULL,
    is_internal          BOOLEAN      NOT NULL,
    ledger_account_id    VARCHAR(100) NOT NULL REFERENCES ar_ledger_accounts(ledger_account_id)
);

-- Ledger-defined per-type daily transfer limits. A sub-ledger account's
-- daily outbound (debit) total for a given transfer_type may not exceed
-- its ledger's limit for that type. Absence of a row for (ledger, type)
-- means "no limit enforced for that type at this ledger".
CREATE TABLE ar_ledger_transfer_limits (
    ledger_account_id VARCHAR(100)  NOT NULL REFERENCES ar_ledger_accounts(ledger_account_id),
    transfer_type     VARCHAR(20)   NOT NULL CHECK (transfer_type IN ('ach', 'wire', 'internal', 'cash')),
    daily_limit       DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (ledger_account_id, transfer_type)
);

CREATE INDEX idx_ar_subledger_accounts_ledger ON ar_subledger_accounts(ledger_account_id);


-- Running Σ of successful postings per sub-ledger account, up to and
-- including each balance date on which a stored sub-ledger balance exists.
-- Failed postings are excluded. Phase G: reads from shared base layer.
CREATE VIEW ar_computed_subledger_daily_balance AS
SELECT
    sdb.account_id        AS subledger_account_id,
    sdb.balance_date,
    COALESCE(SUM(t.signed_amount), 0) AS computed_balance
FROM daily_balances sdb
LEFT JOIN transactions t
    ON t.account_id     = sdb.account_id
   AND t.status         = 'success'
   AND t.balance_date  <= sdb.balance_date
WHERE sdb.control_account_id IS NOT NULL
GROUP BY sdb.account_id, sdb.balance_date;


-- Sub-ledger-level drift: stored − computed for each (sub-ledger account, date).
-- Phase G: stored from daily_balances; ledger_name via self-join on the
-- corresponding ledger row (control_account_id IS NULL).
CREATE VIEW ar_subledger_balance_drift AS
SELECT
    stored.account_id                                  AS subledger_account_id,
    stored.account_name                                AS subledger_name,
    stored.control_account_id                          AS ledger_account_id,
    led.account_name                                   AS ledger_name,
    CASE WHEN stored.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    stored.balance_date,
    stored.balance                                     AS stored_balance,
    COALESCE(computed.computed_balance, 0)             AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM daily_balances stored
JOIN daily_balances led
    ON  led.account_id   = stored.control_account_id
    AND led.balance_date = stored.balance_date
LEFT JOIN ar_computed_subledger_daily_balance computed
       ON computed.subledger_account_id = stored.account_id
      AND computed.balance_date         = stored.balance_date
WHERE stored.control_account_id IS NOT NULL
  AND led.control_account_id    IS NULL;


-- Σ of sub-ledgers' stored balances + Σ direct ledger postings per
-- ledger per day. The ledger-level reconciliation invariant: stored
-- ledger balance should equal this computed balance.
-- Phase G: reads from shared base layer.
CREATE VIEW ar_computed_ledger_daily_balance AS
SELECT
    ldb.account_id AS ledger_account_id,
    ldb.balance_date,
    COALESCE(sub_totals.sub_balance, 0)
        + COALESCE(direct_totals.direct_balance, 0) AS computed_balance
FROM daily_balances ldb
LEFT JOIN (
    SELECT control_account_id AS ledger_account_id,
           balance_date,
           SUM(balance) AS sub_balance
    FROM daily_balances
    WHERE control_account_id IS NOT NULL
    GROUP BY control_account_id, balance_date
) sub_totals
    ON sub_totals.ledger_account_id = ldb.account_id
   AND sub_totals.balance_date      = ldb.balance_date
LEFT JOIN (
    SELECT account_id AS ledger_account_id,
           balance_date,
           SUM(signed_amount) AS direct_balance
    FROM transactions
    WHERE control_account_id IS NULL
      AND status = 'success'
    GROUP BY account_id, balance_date
) direct_totals
    ON direct_totals.ledger_account_id = ldb.account_id
   AND direct_totals.balance_date      = ldb.balance_date
WHERE ldb.control_account_id IS NULL;


-- Ledger-level drift: stored ledger balance vs (Σ sub-ledger stored
-- balances + Σ direct ledger postings). Independent of sub-ledger drift.
-- Phase G: stored from daily_balances ledger rows.
CREATE VIEW ar_ledger_balance_drift AS
SELECT
    stored.account_id                                AS ledger_account_id,
    stored.account_name                              AS ledger_name,
    stored.is_internal,
    stored.balance_date,
    stored.balance                                   AS stored_balance,
    COALESCE(computed.computed_balance, 0)           AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM daily_balances stored
LEFT JOIN ar_computed_ledger_daily_balance computed
       ON computed.ledger_account_id = stored.account_id
      AND computed.balance_date      = stored.balance_date
WHERE stored.control_account_id IS NULL;


-- Per-transfer net of non-failed postings + net-zero flag.
-- A healthy multi-leg transfer has net = 0. ``has_external_leg``
-- flags transfers where at least one leg lands on an external
-- sub-ledger account.
--
-- I.4.B Commit 3: widened to all transfer types under the unified-AR
-- framing. Single-leg PR transfer types (``sale``, ``external_txn``)
-- naturally have non-zero ``net_amount`` because they have no
-- counter-leg in `transactions` — that's not a reconciliation
-- exception, just the shape of the type. The downstream
-- ``ar_transfer_summary`` derives an ``expected_net_zero`` flag
-- from ``transfer_type`` so consumers (e.g., AR Non-Zero Transfers
-- KPI) can exclude single-leg-expected types from their scope.
--
-- Phase G: reads from shared `transactions`. transfer_type / origin are
-- denormalized per-row so they group cleanly without a separate join.
CREATE VIEW ar_transfer_net_zero AS
SELECT
    t.transfer_id,
    MIN(t.posted_at)                                                  AS first_posted_at,
    SUM(CASE WHEN t.status = 'success' THEN t.signed_amount ELSE 0 END) AS net_amount,
    SUM(CASE WHEN t.signed_amount > 0 AND t.status = 'success'
             THEN t.signed_amount ELSE 0 END)                         AS total_debit,
    SUM(CASE WHEN t.signed_amount < 0 AND t.status = 'success'
             THEN t.signed_amount ELSE 0 END)                         AS total_credit,
    COUNT(*)                                                          AS leg_count,
    SUM(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END)              AS failed_leg_count,
    BOOL_OR(t.control_account_id IS NOT NULL AND NOT t.is_internal)   AS has_external_leg,
    CASE
        WHEN SUM(CASE WHEN t.status = 'success' THEN t.signed_amount ELSE 0 END) = 0
            THEN 'net_zero'
        ELSE 'not_net_zero'
    END                                                               AS net_zero_status
FROM transactions t
GROUP BY t.transfer_id;


-- Per-transfer summary with representative memo (from earliest leg)
-- for display alongside net totals.
--
-- I.4.B Commit 3: derives ``expected_net_zero`` from
-- ``transfer_type``. Multi-leg transfer types (``ach``, ``wire``,
-- ``internal``, ``cash``, ``funding_batch``, ``fee``,
-- ``clearing_sweep``, ``payment``, ``settlement``) carry the
-- expectation that non-failed legs sum to zero. Single-leg types
-- (``sale``, ``external_txn``) do not — their non-zero net is
-- structural, not exceptional. Consumers of this view that flag
-- net-zero violations should filter ``expected_net_zero =
-- 'expected'`` to avoid single-leg false positives.
--
-- Phase G: memo / transfer_type / origin are denormalized in
-- `transactions` and constant per transfer_id; MIN picks the value.
CREATE VIEW ar_transfer_summary AS
SELECT
    tz.transfer_id,
    tz.first_posted_at,
    tz.net_amount,
    tz.total_debit,
    tz.total_credit,
    tz.leg_count,
    tz.failed_leg_count,
    tz.net_zero_status,
    tz.has_external_leg,
    CASE
        WHEN rep.transfer_type IN ('sale', 'external_txn')
            THEN 'not_expected'
        ELSE 'expected'
    END                                                               AS expected_net_zero,
    rep.memo,
    rep.transfer_type,
    rep.origin
FROM ar_transfer_net_zero tz
JOIN (
    SELECT transfer_id,
           MIN(transfer_type) AS transfer_type,
           MIN(origin)        AS origin,
           MIN(memo)          AS memo
    FROM transactions
    GROUP BY transfer_id
) rep ON rep.transfer_id = tz.transfer_id;


-- Per (sub-ledger account, date, transfer_type) Σ of outbound (debit)
-- amounts across non-failed transactions. Only tracked (internal)
-- sub-ledgers contribute — external sub-ledgers have no stored balance
-- to bound.
-- Phase G: reads from shared `transactions`. is_internal lives on the
-- transaction row (matches the sub-ledger's own internal flag).
CREATE VIEW ar_subledger_daily_outbound_by_type AS
SELECT
    t.account_id          AS subledger_account_id,
    t.control_account_id  AS ledger_account_id,
    t.balance_date        AS activity_date,
    t.transfer_type,
    SUM(ABS(t.signed_amount)) AS outbound_total
FROM transactions t
WHERE t.status               = 'success'
  AND t.signed_amount        < 0
  AND t.is_internal          = TRUE
  AND t.control_account_id  IS NOT NULL
  -- Mirrors the downstream `ar_subledger_limit_breach` JOIN scope:
  -- limits are only configured for AR transfer types
  -- (`ar_ledger_transfer_limits.transfer_type` CHECK above), so PR
  -- transfer types would drop in the JOIN regardless. Filter is a
  -- query-planner hint, not an artificial exclusion.
  AND t.transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')
GROUP BY t.account_id, t.control_account_id, t.balance_date, t.transfer_type;


-- Sub-ledger limit breach: daily outbound by type exceeds the ledger's
-- configured daily_limit for that type. Rows are emitted only where a
-- limit is defined.
-- Phase G (G.0.4 Locked): per-type limits live in
-- `daily_balances.metadata.limits` on the ledger row. Extracted via
-- SQL/JSON `JSON_VALUE` with a runtime-built jsonpath.
CREATE VIEW ar_subledger_limit_breach AS
SELECT
    o.subledger_account_id,
    sub.account_name                       AS subledger_name,
    o.ledger_account_id,
    led.account_name                       AS ledger_name,
    o.activity_date,
    o.transfer_type,
    o.outbound_total,
    CAST(JSON_VALUE(led.metadata,
                    ('$.limits.' || o.transfer_type)::jsonpath)
         AS DECIMAL(14,2))                 AS daily_limit,
    o.outbound_total -
        CAST(JSON_VALUE(led.metadata,
                        ('$.limits.' || o.transfer_type)::jsonpath)
             AS DECIMAL(14,2))             AS overage
FROM ar_subledger_daily_outbound_by_type o
JOIN daily_balances led
    ON  led.account_id        = o.ledger_account_id
    AND led.balance_date      = o.activity_date
   AND led.control_account_id IS NULL
JOIN daily_balances sub
    ON  sub.account_id        = o.subledger_account_id
   AND sub.balance_date       = o.activity_date
   AND sub.control_account_id IS NOT NULL
WHERE JSON_VALUE(led.metadata,
                 ('$.limits.' || o.transfer_type)::jsonpath) IS NOT NULL
  AND o.outbound_total > CAST(JSON_VALUE(led.metadata,
                                         ('$.limits.' || o.transfer_type)::jsonpath)
                              AS DECIMAL(14,2));


-- Sub-ledger overdraft: stored sub-ledger balance < 0 for a given day.
-- Phase G: reads from shared `daily_balances`; ledger_name via self-join
-- on the corresponding ledger row.
CREATE VIEW ar_subledger_overdraft AS
SELECT
    sub.account_id                       AS subledger_account_id,
    sub.account_name                     AS subledger_name,
    sub.control_account_id               AS ledger_account_id,
    led.account_name                     AS ledger_name,
    sub.balance_date,
    sub.balance                          AS stored_balance
FROM daily_balances sub
JOIN daily_balances led
    ON  led.account_id   = sub.control_account_id
   AND led.balance_date  = sub.balance_date
WHERE sub.control_account_id IS NOT NULL
  AND led.control_account_id IS NULL
  AND sub.balance < 0;


-- Sweep target non-zero EOD: ZBA operating sub-accounts (under Cash
-- Concentration Master) whose stored EOD balance is not zero. The
-- training story's invariant is that every operating sub-account sweeps
-- to zero EOD; non-zero balances mean the sweep failed or was skipped.
-- F.5.1 surfaces these.
-- Phase G: reads from shared `daily_balances`; ledger_name via self-join
-- on the corresponding ledger row.
CREATE VIEW ar_sweep_target_nonzero AS
SELECT
    sub.account_id                       AS subledger_account_id,
    sub.account_name                     AS subledger_name,
    sub.control_account_id               AS ledger_account_id,
    led.account_name                     AS ledger_name,
    sub.balance_date,
    sub.balance                          AS stored_balance
FROM daily_balances sub
JOIN daily_balances led
    ON  led.account_id   = sub.control_account_id
   AND led.balance_date  = sub.balance_date
WHERE sub.control_account_id = 'gl-1850-cash-concentration-master'
  AND led.control_account_id IS NULL
  AND sub.balance <> 0;


-- Concentration Master vs sub-account sweep drift (F.5.2).
-- Per sweep_date, sums clearing_sweep credits posted directly to the
-- Cash Concentration Master ledger and clearing_sweep debits across
-- operating sub-accounts under that same ledger. Healthy days: legs
-- balance, drift = 0. Drift rows surface days where the master leg was
-- keyed off, missing, or extra.
-- Phase G: reads from shared `transactions`. master_credits = direct
-- ledger postings (control_account_id IS NULL); subaccount_debits =
-- postings to sub-ledgers under that ledger (control_account_id =
-- 'gl-1850-cash-concentration-master').
CREATE VIEW ar_concentration_master_sweep_drift AS
WITH master_credits AS (
    SELECT
        t.balance_date                       AS sweep_date,
        SUM(t.signed_amount)                 AS master_total
    FROM transactions t
    WHERE t.transfer_type      = 'clearing_sweep'
      AND t.account_id         = 'gl-1850-cash-concentration-master'
      AND t.control_account_id IS NULL
      AND t.status             = 'success'
    GROUP BY t.balance_date
),
subaccount_debits AS (
    SELECT
        t.balance_date                       AS sweep_date,
        SUM(t.signed_amount)                 AS subaccount_total
    FROM transactions t
    WHERE t.transfer_type      = 'clearing_sweep'
      AND t.control_account_id = 'gl-1850-cash-concentration-master'
      AND t.status             = 'success'
    GROUP BY t.balance_date
)
SELECT
    COALESCE(mc.sweep_date, sd.sweep_date)         AS sweep_date,
    COALESCE(mc.master_total, 0)                   AS master_total,
    COALESCE(sd.subaccount_total, 0)               AS subaccount_total,
    COALESCE(mc.master_total, 0)
        + COALESCE(sd.subaccount_total, 0)         AS drift,
    CASE WHEN COALESCE(mc.master_total, 0)
              + COALESCE(sd.subaccount_total, 0) = 0
         THEN 'balanced'
         ELSE 'drift'
    END                                            AS drift_status
FROM master_credits mc
FULL OUTER JOIN subaccount_debits sd USING (sweep_date);


-- ACH Origination Settlement non-zero EOD (F.5.3).
-- The ACH Origination Settlement ledger (gl-1810) is a transitory clearing
-- account: per-customer ACH originations debit it during the day, and an
-- EOD sweep transfers the day's net to Cash & Due From FRB (gl-1010),
-- zeroing it out. Days the EOD sweep is skipped or fails leave the ledger
-- non-zero — surfacing here.
-- Phase G: reads from shared `daily_balances`; ledger row identified by
-- control_account_id IS NULL.
CREATE VIEW ar_ach_orig_settlement_nonzero AS
SELECT
    db.account_id                       AS ledger_account_id,
    db.account_name                     AS ledger_name,
    db.balance_date,
    db.balance                          AS stored_balance
FROM daily_balances db
WHERE db.account_id          = 'gl-1810-ach-orig-settlement'
  AND db.control_account_id IS NULL
  AND db.balance            <> 0;


-- ACH internal sweep posted but no Fed confirmation (F.5.4).
-- Each successful internal EOD sweep on gl-1810 (ACH Origination
-- Settlement) should be followed by a Fed-side confirmation child
-- transfer attesting the FRB master account moved by the same amount.
-- This view surfaces sweeps where the internal leg posted but the Fed
-- confirmation never landed — the bank thinks the cash moved, the FRB
-- has no record.
-- Phase G: reads from shared `transactions`. transfer-scoped EXISTS
-- replaces transfer-table joins. Per-leg posted_at/amount are
-- consistent across a transfer's rows, so MIN() collapses them.
CREATE VIEW ar_ach_sweep_no_fed_confirmation AS
SELECT
    t.transfer_id                       AS sweep_transfer_id,
    MIN(t.posted_at)                    AS sweep_at,
    MIN(t.amount)                       AS sweep_amount
FROM transactions t
WHERE t.transfer_type = 'clearing_sweep'
  AND EXISTS (
    SELECT 1 FROM transactions hit
    WHERE hit.transfer_id = t.transfer_id
      AND (hit.account_id         = 'gl-1810-ach-orig-settlement'
        OR hit.control_account_id = 'gl-1810-ach-orig-settlement')
  )
  AND NOT EXISTS (
    SELECT 1 FROM transactions fed
    WHERE fed.parent_transfer_id = t.transfer_id
      AND fed.transfer_type      = 'ach'
      AND fed.origin             = 'external_force_posted'
  )
GROUP BY t.transfer_id;


-- Fed activity with no matching internal post (F.5.5).
-- Card-processor settlements posted by the FRB are observed at SNB as
-- top-of-chain external_force_posted transfers (parent IS NULL) hitting
-- the payment-gateway clearing sub-ledger. Each should be followed by an
-- SNB internal catch-up child (DR gl-1815, CR merchant DDA). This view
-- surfaces Fed observations with no internal catch-up — money the Fed
-- says cleared, that SNB never recorded internally.
-- Phase G: reads from shared `transactions`; MIN() collapses leg rows.
CREATE VIEW ar_fed_card_no_internal_catchup AS
SELECT
    t.transfer_id                       AS fed_transfer_id,
    MIN(t.posted_at)                    AS fed_at,
    MIN(t.amount)                       AS fed_amount
FROM transactions t
WHERE t.transfer_type      = 'ach'
  AND t.origin             = 'external_force_posted'
  AND t.parent_transfer_id IS NULL
  AND EXISTS (
    SELECT 1 FROM transactions hit
    WHERE hit.transfer_id = t.transfer_id
      AND hit.account_id  = 'ext-payment-gateway-sub-clearing'
  )
  AND NOT EXISTS (
    SELECT 1 FROM transactions ic
    WHERE ic.parent_transfer_id = t.transfer_id
  )
GROUP BY t.transfer_id;


-- GL-vs-Fed Master drift timeline (F.5.6).
-- Per day, totals the Fed-side card processor settlement amounts and
-- the SNB internal catch-up amounts (children of those Fed transfers).
-- Healthy days: both sides equal, drift = 0. Drift > 0 means Fed
-- posted activity that SNB never recorded internally — the GL view
-- and the Fed master view diverge.
-- Phase G: reads from shared `transactions`. Per-transfer collapsing
-- via GROUP BY transfer_id is required because the new schema has one
-- row per leg; legacy `transfer.amount` was one value per transfer.
CREATE VIEW ar_gl_vs_fed_master_drift AS
WITH fed_card_observed AS (
    SELECT
        t.transfer_id,
        MIN(t.balance_date)             AS movement_date,
        MIN(t.amount)                   AS fed_amount
    FROM transactions t
    WHERE t.transfer_type      = 'ach'
      AND t.origin             = 'external_force_posted'
      AND t.parent_transfer_id IS NULL
      AND EXISTS (
        SELECT 1 FROM transactions hit
        WHERE hit.transfer_id = t.transfer_id
          AND hit.account_id  = 'ext-payment-gateway-sub-clearing'
      )
    GROUP BY t.transfer_id
),
fed_total AS (
    SELECT
        movement_date,
        SUM(fed_amount)                 AS fed_total
    FROM fed_card_observed
    GROUP BY movement_date
),
internal_per_transfer AS (
    SELECT
        ic.transfer_id,
        MIN(ic.balance_date)            AS movement_date,
        MIN(ic.amount)                  AS amount
    FROM transactions ic
    WHERE ic.parent_transfer_id IN (SELECT transfer_id FROM fed_card_observed)
    GROUP BY ic.transfer_id
),
internal_total AS (
    SELECT
        movement_date,
        SUM(amount)                     AS internal_total
    FROM internal_per_transfer
    GROUP BY movement_date
)
SELECT
    COALESCE(f.movement_date, i.movement_date) AS movement_date,
    COALESCE(f.fed_total, 0)                   AS fed_total,
    COALESCE(i.internal_total, 0)              AS internal_total,
    COALESCE(f.fed_total, 0)
        - COALESCE(i.internal_total, 0)        AS drift,
    CASE WHEN COALESCE(f.fed_total, 0)
              - COALESCE(i.internal_total, 0) = 0
         THEN 'balanced'
         ELSE 'drift'
    END                                        AS drift_status
FROM fed_total f
FULL OUTER JOIN internal_total i USING (movement_date);


-- Stuck in Internal Transfer Suspense (F.5.7).
-- Internal book-transfers between SNB customer DDAs land in two steps:
--   Step 1: DR gl-1830 (Internal Transfer Suspense), CR originator DDA
--   Step 2 (child): DR recipient DDA, CR gl-1830 -- clears the suspense
-- A "stuck" originate is a Step-1 transfer that posted with no Step-2
-- child ever appearing. The cash sits in the suspense ledger indefinitely
-- and the recipient never sees the credit.
-- Phase G: reads from shared `transactions`; MIN() collapses leg rows.
CREATE VIEW ar_internal_transfer_stuck AS
SELECT
    t.transfer_id                       AS originate_transfer_id,
    MIN(t.posted_at)                    AS originated_at,
    MIN(t.amount)                       AS originate_amount
FROM transactions t
WHERE t.transfer_type      = 'internal'
  AND t.origin             = 'internal_initiated'
  AND t.parent_transfer_id IS NULL
  AND EXISTS (
    SELECT 1 FROM transactions hit
    WHERE hit.transfer_id = t.transfer_id
      AND (hit.account_id         = 'gl-1830-internal-transfer-suspense'
        OR hit.control_account_id = 'gl-1830-internal-transfer-suspense')
  )
  AND NOT EXISTS (
    SELECT 1 FROM transactions step2
    WHERE step2.parent_transfer_id = t.transfer_id
  )
GROUP BY t.transfer_id;


-- Internal Transfer Reversal Uncredited / "double spend" (F.5.9).
-- An on-us internal transfer that was reversed, but the originator's
-- credit-back leg failed while the suspense leg succeeded. Net result:
-- originator was debited on Step 1 and never refunded, but suspense
-- nets to zero so the ledger looks healthy. The customer is short the
-- money. This is the most damaging silent failure in the cycle.
-- Phase G: reads from shared `transactions`. Inline subqueries collapse
-- per-leg rows to one row per transfer (orig + step2). Sub-ledger
-- posting is identified by control_account_id IS NOT NULL (per G.0.12).
CREATE VIEW ar_internal_reversal_uncredited AS
SELECT
    orig.transfer_id                    AS originate_transfer_id,
    orig.originated_at,
    orig.originate_amount,
    step2.transfer_id                   AS reversal_transfer_id,
    step2.reversal_at
FROM (
    SELECT
        t.transfer_id,
        MIN(t.posted_at) AS originated_at,
        MIN(t.amount)    AS originate_amount
    FROM transactions t
    WHERE t.transfer_type      = 'internal'
      AND t.origin             = 'internal_initiated'
      AND t.parent_transfer_id IS NULL
      AND EXISTS (
        SELECT 1 FROM transactions hit
        WHERE hit.transfer_id = t.transfer_id
          AND (hit.account_id         = 'gl-1830-internal-transfer-suspense'
            OR hit.control_account_id = 'gl-1830-internal-transfer-suspense')
      )
    GROUP BY t.transfer_id
) orig
JOIN (
    SELECT
        t.transfer_id,
        MIN(t.parent_transfer_id) AS parent_transfer_id,
        MIN(t.posted_at)          AS reversal_at
    FROM transactions t
    WHERE t.parent_transfer_id IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM transactions p
        WHERE p.transfer_id        = t.transfer_id
          AND p.control_account_id IS NOT NULL
          AND p.status             = 'failed'
      )
      AND EXISTS (
        SELECT 1 FROM transactions p
        WHERE p.transfer_id = t.transfer_id
          AND (p.account_id         = 'gl-1830-internal-transfer-suspense'
            OR p.control_account_id = 'gl-1830-internal-transfer-suspense')
          AND p.status      = 'success'
      )
    GROUP BY t.transfer_id
) step2 ON step2.parent_transfer_id = orig.transfer_id;


-- Internal Transfer Suspense non-zero EOD (F.5.8).
-- The Internal Transfer Suspense ledger (gl-1830) is a transitory
-- clearing account: each book-transfer between SNB customer DDAs hits
-- it on Step 1 (originator → suspense) and clears it on Step 2 (suspense
-- → recipient). Healthy day: every Step 1 has its Step 2, suspense nets
-- to zero EOD. Non-zero EOD = at least one Step-1 didn't clear that day.
-- Ledger-level analog of F.5.7's per-transfer view.
-- Phase G: reads from shared `daily_balances`; ledger row identified by
-- control_account_id IS NULL.
CREATE VIEW ar_internal_transfer_suspense_nonzero AS
SELECT
    db.account_id                       AS ledger_account_id,
    db.account_name                     AS ledger_name,
    db.balance_date,
    db.balance                          AS stored_balance
FROM daily_balances db
WHERE db.account_id          = 'gl-1830-internal-transfer-suspense'
  AND db.control_account_id IS NULL
  AND db.balance            <> 0;


-- F.5.10.a Accounts Expected Zero at EOD rollup.
-- Same SHAPE check across three control accounts: an account that should
-- be zero EOD by design, isn't. Rolls up:
--   F.5.1: Sweep target sub-accounts (under Cash Concentration Master)
--   F.5.3: ACH Origination Settlement ledger (gl-1810)
--   F.5.8: Internal Transfer Suspense ledger (gl-1830)
-- Teaches users to recognize the pattern across multiple accounts —
-- per-check tables stay below for drill-in detail.
-- Phase G: structurally unchanged — UNIONs three already-migrated
-- check views (G.7.1, G.7.3, G.7.8). Transitively reads from
-- `daily_balances`.
CREATE VIEW ar_expected_zero_eod_rollup AS
SELECT
    subledger_account_id                AS account_id,
    subledger_name                      AS account_name,
    'Sub-Ledger'                        AS account_level,
    balance_date,
    stored_balance,
    'Sweep target non-zero EOD'         AS source_check
FROM ar_sweep_target_nonzero
UNION ALL
SELECT
    ledger_account_id                   AS account_id,
    ledger_name                         AS account_name,
    'Ledger'                            AS account_level,
    balance_date,
    stored_balance,
    'ACH Origination Settlement non-zero EOD' AS source_check
FROM ar_ach_orig_settlement_nonzero
UNION ALL
SELECT
    ledger_account_id                   AS account_id,
    ledger_name                         AS account_name,
    'Ledger'                            AS account_level,
    balance_date,
    stored_balance,
    'Internal Transfer Suspense non-zero EOD' AS source_check
FROM ar_internal_transfer_suspense_nonzero;


-- Two-sided post mismatch rollup (F.5.10.b).
-- Surfaces the same SHAPE of error — one side of an expected pair
-- posted, the other side missing — across two SNB/Fed flows:
--   F.5.4: ACH internal sweep posted, no Fed confirmation
--          (we have the SNB sweep; missing the Fed leg)
--   F.5.5: Fed card observation posted, no SNB internal catch-up
--          (we have the Fed leg; missing the SNB internal post)
-- Teaches users to recognize the pattern rather than two separate
-- checks; per-check tables stay below for drill-in detail.
-- Phase G: structurally unchanged — UNIONs two already-migrated
-- check views (G.7.4, G.7.5). Transitively reads from `transactions`.
CREATE VIEW ar_two_sided_post_mismatch_rollup AS
SELECT
    sweep_transfer_id                   AS transfer_id,
    sweep_at                            AS observed_at,
    sweep_amount                        AS amount,
    'SNB internal sweep'                AS side_present,
    'Fed confirmation'                  AS side_missing,
    'ACH internal sweep without Fed confirmation' AS source_check
FROM ar_ach_sweep_no_fed_confirmation
UNION ALL
SELECT
    fed_transfer_id                     AS transfer_id,
    fed_at                              AS observed_at,
    fed_amount                          AS amount,
    'Fed card observation'              AS side_present,
    'SNB internal catch-up'             AS side_missing,
    'Fed activity without internal catch-up' AS source_check
FROM ar_fed_card_no_internal_catchup;


-- Balance drift timelines rollup (F.5.10.c).
-- Overlays per-day drift from two independent ledger-master flows on
-- one shared (date, drift $) axis so the eye can compare which feed
-- spiked on a given day:
--   F.5.2: Concentration Master sweep drift (gl-1011 vs sub-account
--          sweep totals — internal sweep leg imbalance)
--   F.5.6: GL-vs-Fed Master drift (Fed-side card observations vs SNB
--          internal catch-up totals — external/internal divergence)
-- Per-check timelines stay below for drill-in detail.
CREATE VIEW ar_balance_drift_timelines_rollup AS
SELECT
    sweep_date                          AS drift_date,
    drift,
    'Concentration Master Sweep drift'  AS source_check
FROM ar_concentration_master_sweep_drift
UNION ALL
SELECT
    movement_date                       AS drift_date,
    drift,
    'GL vs Fed Master drift'            AS source_check
FROM ar_gl_vs_fed_master_drift;
