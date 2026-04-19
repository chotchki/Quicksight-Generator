-- QuickSight Demo Schema
-- Target: PostgreSQL 12+
--
-- Defines the tables and views that the QuickSight dataset SQL queries
-- run against.  The DROP IF EXISTS cascade at the top makes this script
-- idempotent — safe to re-run.
--
-- Tables are prefixed `pr_` (Payment Recon) to share the `public` schema
-- with the Account Recon app's `ar_`-prefixed tables (added in Phase 3).

-- -------------------------------------------------------------------
-- Drop legacy unprefixed objects (pre-v0.4.0 installations)
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

-- -------------------------------------------------------------------
-- Drop current prefixed objects (safe to re-run)
-- -------------------------------------------------------------------

DROP VIEW  IF EXISTS pr_payment_recon_view           CASCADE;
DROP VIEW  IF EXISTS pr_sale_settlement_mismatch     CASCADE;
DROP VIEW  IF EXISTS pr_settlement_payment_mismatch  CASCADE;
DROP VIEW  IF EXISTS pr_unmatched_external_txns      CASCADE;
DROP TABLE IF EXISTS pr_payments              CASCADE;
DROP TABLE IF EXISTS pr_sales                 CASCADE;
DROP TABLE IF EXISTS pr_settlements           CASCADE;
DROP TABLE IF EXISTS pr_external_transactions CASCADE;
DROP TABLE IF EXISTS pr_merchants             CASCADE;

-- -------------------------------------------------------------------
-- Tables
-- -------------------------------------------------------------------

CREATE TABLE pr_merchants (
    merchant_id   VARCHAR(100) PRIMARY KEY,
    merchant_name VARCHAR(255) NOT NULL,
    merchant_type VARCHAR(50)  NOT NULL,   -- franchise | independent | cart
    location_id   VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status        VARCHAR(50)  NOT NULL DEFAULT 'active'
);

CREATE TABLE pr_external_transactions (
    transaction_id   VARCHAR(100)   PRIMARY KEY,
    external_system  VARCHAR(100)   NOT NULL,
    external_amount  DECIMAL(12,2)  NOT NULL,
    record_count     INTEGER        NOT NULL DEFAULT 0,
    transaction_date TIMESTAMP      NOT NULL,
    status           VARCHAR(50)    NOT NULL,
    merchant_id      VARCHAR(100)   NOT NULL REFERENCES pr_merchants(merchant_id)
);

CREATE TABLE pr_settlements (
    settlement_id          VARCHAR(100)   PRIMARY KEY,
    merchant_id            VARCHAR(100)   NOT NULL REFERENCES pr_merchants(merchant_id),
    settlement_type        VARCHAR(50)    NOT NULL,
    settlement_amount      DECIMAL(12,2)  NOT NULL,
    settlement_date        TIMESTAMP      NOT NULL,
    settlement_status      VARCHAR(50)    NOT NULL,
    sale_count             INTEGER        NOT NULL DEFAULT 0
);

CREATE TABLE pr_sales (
    sale_id                 VARCHAR(100)   PRIMARY KEY,
    merchant_id             VARCHAR(100)   NOT NULL REFERENCES pr_merchants(merchant_id),
    location_id             VARCHAR(100)   NOT NULL,
    amount                  DECIMAL(12,2)  NOT NULL,
    sale_type               VARCHAR(10)    NOT NULL DEFAULT 'sale'
        CHECK (sale_type IN ('sale', 'refund')),
    payment_method          VARCHAR(50)    NOT NULL DEFAULT 'card',
    sale_timestamp          TIMESTAMP      NOT NULL,
    card_brand              VARCHAR(50),
    card_last_four          VARCHAR(4),
    reference_id            VARCHAR(100),
    metadata                TEXT,
    settlement_id           VARCHAR(100)   REFERENCES pr_settlements(settlement_id),
    -- Optional sales metadata (SPEC 2.2).  Declared adjacent to the sales
    -- dataset SQL in code; keep this DDL in sync with OPTIONAL_SALE_METADATA.
    taxes                   DECIMAL(12,2),
    tips                    DECIMAL(12,2),
    discount_percentage     DECIMAL(5,2),
    cashier                 VARCHAR(100)
);

CREATE TABLE pr_payments (
    payment_id              VARCHAR(100)   PRIMARY KEY,
    settlement_id           VARCHAR(100)   NOT NULL REFERENCES pr_settlements(settlement_id),
    merchant_id             VARCHAR(100)   NOT NULL REFERENCES pr_merchants(merchant_id),
    payment_amount          DECIMAL(12,2)  NOT NULL,
    payment_date            TIMESTAMP      NOT NULL,
    payment_status          VARCHAR(50)    NOT NULL,
    is_returned             VARCHAR(10)    NOT NULL DEFAULT 'false',
    return_reason           VARCHAR(255),
    external_transaction_id VARCHAR(100)   REFERENCES pr_external_transactions(transaction_id),
    payment_method          VARCHAR(50)    NOT NULL DEFAULT 'card'
);

-- -------------------------------------------------------------------
-- Indexes
-- -------------------------------------------------------------------

CREATE INDEX idx_pr_sales_merchant    ON pr_sales(merchant_id);
CREATE INDEX idx_pr_sales_location    ON pr_sales(location_id);
CREATE INDEX idx_pr_sales_timestamp   ON pr_sales(sale_timestamp);
CREATE INDEX idx_pr_sales_settlement  ON pr_sales(settlement_id);

CREATE INDEX idx_pr_settlements_merchant ON pr_settlements(merchant_id);

CREATE INDEX idx_pr_payments_settlement ON pr_payments(settlement_id);
CREATE INDEX idx_pr_payments_merchant   ON pr_payments(merchant_id);
CREATE INDEX idx_pr_payments_ext_txn    ON pr_payments(external_transaction_id);

CREATE INDEX idx_pr_ext_txn_system   ON pr_external_transactions(external_system);
CREATE INDEX idx_pr_ext_txn_merchant ON pr_external_transactions(merchant_id);

-- -------------------------------------------------------------------
-- Reconciliation view
--
-- Compares internal payments against external transaction totals.
-- Referenced by the payment reconciliation dataset.
-- -------------------------------------------------------------------

CREATE VIEW pr_payment_recon_view AS
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    COALESCE(SUM(p.payment_amount), 0)                        AS internal_total,
    et.external_amount - COALESCE(SUM(p.payment_amount), 0)   AS difference,
    CASE
        WHEN et.external_amount = COALESCE(SUM(p.payment_amount), 0)
            THEN 'matched'
        WHEN (CURRENT_DATE - et.transaction_date::date) > 30
            THEN 'late'
        ELSE 'not_yet_matched'
    END                                                        AS match_status,
    COUNT(p.payment_id)                                        AS payment_count,
    et.merchant_id,
    et.transaction_date,
    (CURRENT_DATE - et.transaction_date::date)                 AS days_outstanding
FROM pr_external_transactions et
LEFT JOIN pr_payments p      ON p.external_transaction_id = et.transaction_id
GROUP BY et.transaction_id, et.external_system, et.external_amount,
         et.merchant_id, et.transaction_date;


-- -------------------------------------------------------------------
-- Exception views (SPEC 2.4)
-- -------------------------------------------------------------------

-- Settlements whose amount doesn't equal the signed sum of their sales
-- (catches refund drift, seed-injected mismatches, and manual corrections).
CREATE VIEW pr_sale_settlement_mismatch AS
SELECT
    s.settlement_id,
    s.merchant_id,
    s.settlement_amount,
    COALESCE(SUM(sl.amount), 0)                               AS sales_sum,
    s.settlement_amount - COALESCE(SUM(sl.amount), 0)         AS difference,
    s.sale_count,
    s.settlement_date,
    (CURRENT_DATE - s.settlement_date::date)                  AS days_outstanding
FROM pr_settlements s
LEFT JOIN pr_sales sl ON sl.settlement_id = s.settlement_id
GROUP BY s.settlement_id, s.merchant_id, s.settlement_amount,
         s.sale_count, s.settlement_date
HAVING s.settlement_amount <> COALESCE(SUM(sl.amount), 0);

-- Payments whose amount doesn't match their linked settlement.
CREATE VIEW pr_settlement_payment_mismatch AS
SELECT
    p.payment_id,
    p.settlement_id,
    p.merchant_id,
    p.payment_amount,
    s.settlement_amount,
    p.payment_amount - s.settlement_amount                    AS difference,
    p.payment_date,
    (CURRENT_DATE - p.payment_date::date)                     AS days_outstanding
FROM pr_payments p
JOIN pr_settlements s ON s.settlement_id = p.settlement_id
WHERE p.payment_amount <> s.settlement_amount;

-- External transactions with no internal payment linked.
CREATE VIEW pr_unmatched_external_txns AS
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    et.merchant_id,
    et.transaction_date,
    et.status,
    (CURRENT_DATE - et.transaction_date::date)                AS days_outstanding
FROM pr_external_transactions et
LEFT JOIN pr_payments p ON p.external_transaction_id = et.transaction_id
WHERE p.payment_id IS NULL;


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

-- Stored daily final at the ledger-account level. Populated by the
-- ledger-account upstream feed.
CREATE TABLE ar_ledger_daily_balances (
    ledger_account_id VARCHAR(100)  NOT NULL REFERENCES ar_ledger_accounts(ledger_account_id),
    balance_date      DATE          NOT NULL,
    balance           DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (ledger_account_id, balance_date)
);

-- Stored daily final at the sub-ledger-account level. Populated by the
-- sub-ledger-account upstream feed — may be a different system from the
-- ledger-balance feed, hence the two-level reconciliation.
CREATE TABLE ar_subledger_daily_balances (
    subledger_account_id VARCHAR(100)  NOT NULL REFERENCES ar_subledger_accounts(subledger_account_id),
    balance_date         DATE          NOT NULL,
    balance              DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (subledger_account_id, balance_date)
);

-- ar_transactions is superseded by the unified transfer + posting tables
-- (Phase B). Legacy DROP IF EXISTS retained for migration safety.

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

CREATE INDEX idx_ar_subledger_accounts_ledger      ON ar_subledger_accounts(ledger_account_id);
CREATE INDEX idx_ar_ledger_daily_balances_date     ON ar_ledger_daily_balances(balance_date);
CREATE INDEX idx_ar_subledger_daily_balances_date  ON ar_subledger_daily_balances(balance_date);


-- ===================================================================
-- Unified transfer + posting (Phase B)
--
-- Both apps share these two tables. A transfer is a logical movement
-- of money; each transfer has one or more postings (double-entry legs)
-- that must net to zero for a healthy transfer. PR's chain-of-custody
-- (sale → settlement → payment → external_txn) is modeled as a tree
-- of transfers linked by parent_transfer_id. AR's existing transfers
-- map 1:1 onto the unified transfer table.
--
-- transfer_type carries app-specific vocabulary:
--   PR: sale, settlement, payment, external_txn
--   AR: ach, wire, internal, cash
-- ===================================================================

CREATE TABLE transfer (
    transfer_id        VARCHAR(100)   PRIMARY KEY,
    parent_transfer_id VARCHAR(100)   REFERENCES transfer(transfer_id),
    transfer_type      VARCHAR(30)    NOT NULL
        CHECK (transfer_type IN (
            'sale', 'settlement', 'payment', 'external_txn',
            'ach', 'wire', 'internal', 'cash',
            'funding_batch', 'fee', 'clearing_sweep'
        )),
    origin             VARCHAR(30)    NOT NULL DEFAULT 'internal_initiated'
        CHECK (origin IN ('internal_initiated', 'external_force_posted')),
    amount             DECIMAL(14,2)  NOT NULL,
    status             VARCHAR(20)    NOT NULL DEFAULT 'posted'
        CHECK (status IN ('posted', 'pending', 'failed', 'settled',
                          'unsettled', 'returned', 'active', 'completed')),
    created_at         TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    memo               VARCHAR(255),
    external_system    VARCHAR(100)
);

CREATE TABLE posting (
    posting_id           VARCHAR(100)   PRIMARY KEY,
    transfer_id          VARCHAR(100)   NOT NULL REFERENCES transfer(transfer_id),
    ledger_account_id    VARCHAR(100)   NOT NULL REFERENCES ar_ledger_accounts(ledger_account_id),
    subledger_account_id VARCHAR(100)   REFERENCES ar_subledger_accounts(subledger_account_id),
    signed_amount        DECIMAL(14,2)  NOT NULL,
    posted_at            TIMESTAMP      NOT NULL,
    status               VARCHAR(20)    NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failed'))
);

CREATE INDEX idx_transfer_parent     ON transfer(parent_transfer_id);
CREATE INDEX idx_transfer_type       ON transfer(transfer_type);
CREATE INDEX idx_posting_transfer    ON posting(transfer_id);
CREATE INDEX idx_posting_ledger      ON posting(ledger_account_id, posted_at);
CREATE INDEX idx_posting_subledger   ON posting(subledger_account_id, posted_at);


-- Running Σ of successful postings per sub-ledger account, up to and
-- including each balance date on which a stored sub-ledger balance exists.
-- Failed postings are excluded.
CREATE VIEW ar_computed_subledger_daily_balance AS
SELECT
    sdb.subledger_account_id,
    sdb.balance_date,
    COALESCE(SUM(p.signed_amount), 0) AS computed_balance
FROM ar_subledger_daily_balances sdb
LEFT JOIN posting p
    ON p.subledger_account_id = sdb.subledger_account_id
   AND p.status               = 'success'
   AND p.posted_at::date     <= sdb.balance_date
GROUP BY sdb.subledger_account_id, sdb.balance_date;


-- Sub-ledger-level drift: stored − computed for each (sub-ledger account, date).
CREATE VIEW ar_subledger_balance_drift AS
SELECT
    stored.subledger_account_id,
    s.name                                    AS subledger_name,
    s.ledger_account_id,
    la.name                                   AS ledger_name,
    CASE WHEN s.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    stored.balance_date,
    stored.balance                            AS stored_balance,
    COALESCE(computed.computed_balance, 0)    AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM ar_subledger_daily_balances stored
JOIN ar_subledger_accounts s   USING (subledger_account_id)
JOIN ar_ledger_accounts la     USING (ledger_account_id)
LEFT JOIN ar_computed_subledger_daily_balance computed
       ON computed.subledger_account_id = stored.subledger_account_id
      AND computed.balance_date         = stored.balance_date;


-- Σ of sub-ledgers' stored balances + Σ direct ledger postings per
-- ledger per day. The ledger-level reconciliation invariant: stored
-- ledger balance should equal this computed balance.
CREATE VIEW ar_computed_ledger_daily_balance AS
SELECT
    ldb.ledger_account_id,
    ldb.balance_date,
    COALESCE(sub_totals.sub_balance, 0)
        + COALESCE(direct_totals.direct_balance, 0) AS computed_balance
FROM ar_ledger_daily_balances ldb
LEFT JOIN (
    SELECT s.ledger_account_id, sdb.balance_date,
           SUM(sdb.balance) AS sub_balance
    FROM ar_subledger_daily_balances sdb
    JOIN ar_subledger_accounts s USING (subledger_account_id)
    GROUP BY s.ledger_account_id, sdb.balance_date
) sub_totals
    ON sub_totals.ledger_account_id = ldb.ledger_account_id
   AND sub_totals.balance_date      = ldb.balance_date
LEFT JOIN (
    SELECT p.ledger_account_id, p.posted_at::date AS balance_date,
           SUM(p.signed_amount) AS direct_balance
    FROM posting p
    WHERE p.subledger_account_id IS NULL
      AND p.status = 'success'
    GROUP BY p.ledger_account_id, p.posted_at::date
) direct_totals
    ON direct_totals.ledger_account_id = ldb.ledger_account_id
   AND direct_totals.balance_date      = ldb.balance_date;


-- Ledger-level drift: stored ledger balance vs (Σ sub-ledger stored
-- balances + Σ direct ledger postings). Independent of sub-ledger drift.
CREATE VIEW ar_ledger_balance_drift AS
SELECT
    stored.ledger_account_id,
    la.name                                  AS ledger_name,
    la.is_internal,
    stored.balance_date,
    stored.balance                           AS stored_balance,
    COALESCE(computed.computed_balance, 0)   AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM ar_ledger_daily_balances stored
JOIN ar_ledger_accounts la USING (ledger_account_id)
LEFT JOIN ar_computed_ledger_daily_balance computed
       ON computed.ledger_account_id = stored.ledger_account_id
      AND computed.balance_date      = stored.balance_date;


-- Per-transfer net of non-failed postings + net-zero flag.
-- A healthy transfer has net = 0. ``has_external_leg`` flags transfers
-- where at least one leg lands on an external account.
-- Scoped to AR transfer types only.
CREATE VIEW ar_transfer_net_zero AS
SELECT
    p.transfer_id,
    MIN(p.posted_at)                                                  AS first_posted_at,
    SUM(CASE WHEN p.status = 'success' THEN p.signed_amount ELSE 0 END) AS net_amount,
    SUM(CASE WHEN p.signed_amount > 0 AND p.status = 'success'
             THEN p.signed_amount ELSE 0 END)                         AS total_debit,
    SUM(CASE WHEN p.signed_amount < 0 AND p.status = 'success'
             THEN p.signed_amount ELSE 0 END)                         AS total_credit,
    COUNT(*)                                                          AS leg_count,
    SUM(CASE WHEN p.status = 'failed' THEN 1 ELSE 0 END)              AS failed_leg_count,
    BOOL_OR(CASE WHEN s.is_internal IS NULL THEN FALSE ELSE NOT s.is_internal END)
                                                                      AS has_external_leg,
    CASE
        WHEN SUM(CASE WHEN p.status = 'success' THEN p.signed_amount ELSE 0 END) = 0
            THEN 'net_zero'
        ELSE 'not_net_zero'
    END                                                               AS net_zero_status
FROM posting p
JOIN transfer xfer ON xfer.transfer_id = p.transfer_id
LEFT JOIN ar_subledger_accounts s ON s.subledger_account_id = p.subledger_account_id
WHERE xfer.transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')
GROUP BY p.transfer_id;


-- Per-transfer summary with representative memo (from earliest leg)
-- for display alongside net totals.
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
    xfer.memo,
    xfer.transfer_type,
    xfer.origin
FROM ar_transfer_net_zero tz
JOIN transfer xfer ON xfer.transfer_id = tz.transfer_id;


-- Per (sub-ledger account, date, transfer_type) Σ of outbound (debit)
-- amounts across non-failed transactions. Only tracked (internal)
-- sub-ledgers contribute — external sub-ledgers have no stored balance
-- to bound.
CREATE VIEW ar_subledger_daily_outbound_by_type AS
SELECT
    p.subledger_account_id,
    s.ledger_account_id,
    p.posted_at::date                   AS activity_date,
    xfer.transfer_type,
    SUM(ABS(p.signed_amount))           AS outbound_total
FROM posting p
JOIN transfer xfer ON xfer.transfer_id = p.transfer_id
JOIN ar_subledger_accounts s ON s.subledger_account_id = p.subledger_account_id
WHERE p.status = 'success'
  AND p.signed_amount < 0
  AND s.is_internal = TRUE
  AND xfer.transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')
GROUP BY p.subledger_account_id, s.ledger_account_id, p.posted_at::date, xfer.transfer_type;


-- Sub-ledger limit breach: daily outbound by type exceeds the ledger's
-- configured daily_limit for that type. Rows are emitted only where a
-- limit is defined (i.e., ledger-limits join matches).
CREATE VIEW ar_subledger_limit_breach AS
SELECT
    o.subledger_account_id,
    s.name                              AS subledger_name,
    o.ledger_account_id,
    la.name                             AS ledger_name,
    o.activity_date,
    o.transfer_type,
    o.outbound_total,
    l.daily_limit,
    o.outbound_total - l.daily_limit    AS overage
FROM ar_subledger_daily_outbound_by_type o
JOIN ar_subledger_accounts s   ON s.subledger_account_id = o.subledger_account_id
JOIN ar_ledger_accounts la     ON la.ledger_account_id    = o.ledger_account_id
JOIN ar_ledger_transfer_limits l
  ON l.ledger_account_id = o.ledger_account_id
 AND l.transfer_type     = o.transfer_type
WHERE o.outbound_total > l.daily_limit;


-- Sub-ledger overdraft: stored sub-ledger balance < 0 for a given day.
CREATE VIEW ar_subledger_overdraft AS
SELECT
    sdb.subledger_account_id,
    s.name                              AS subledger_name,
    s.ledger_account_id,
    la.name                             AS ledger_name,
    sdb.balance_date,
    sdb.balance                         AS stored_balance
FROM ar_subledger_daily_balances sdb
JOIN ar_subledger_accounts s   USING (subledger_account_id)
JOIN ar_ledger_accounts la     USING (ledger_account_id)
WHERE sdb.balance < 0;


-- Sweep target non-zero EOD: ZBA operating sub-accounts (under Cash
-- Concentration Master) whose stored EOD balance is not zero. The
-- training story's invariant is that every operating sub-account sweeps
-- to zero EOD; non-zero balances mean the sweep failed or was skipped.
-- F.5.1 surfaces these.
CREATE VIEW ar_sweep_target_nonzero AS
SELECT
    sdb.subledger_account_id,
    s.name                              AS subledger_name,
    s.ledger_account_id,
    la.name                             AS ledger_name,
    sdb.balance_date,
    sdb.balance                         AS stored_balance
FROM ar_subledger_daily_balances sdb
JOIN ar_subledger_accounts s   USING (subledger_account_id)
JOIN ar_ledger_accounts la     USING (ledger_account_id)
WHERE s.ledger_account_id = 'gl-1850-cash-concentration-master'
  AND sdb.balance <> 0;


-- Concentration Master vs sub-account sweep drift (F.5.2).
-- Per sweep_date, sums clearing_sweep credits posted directly to the
-- Cash Concentration Master ledger and clearing_sweep debits across
-- operating sub-accounts under that same ledger. Healthy days: legs
-- balance, drift = 0. Drift rows surface days where the master leg was
-- keyed off, missing, or extra.
CREATE VIEW ar_concentration_master_sweep_drift AS
WITH master_credits AS (
    SELECT
        p.posted_at::date                   AS sweep_date,
        SUM(p.signed_amount)                AS master_total
    FROM posting p
    JOIN transfer t USING (transfer_id)
    WHERE t.transfer_type = 'clearing_sweep'
      AND p.ledger_account_id = 'gl-1850-cash-concentration-master'
      AND p.subledger_account_id IS NULL
      AND p.status = 'success'
    GROUP BY p.posted_at::date
),
subaccount_debits AS (
    SELECT
        p.posted_at::date                   AS sweep_date,
        SUM(p.signed_amount)                AS subaccount_total
    FROM posting p
    JOIN transfer t USING (transfer_id)
    JOIN ar_subledger_accounts s USING (subledger_account_id)
    WHERE t.transfer_type = 'clearing_sweep'
      AND s.ledger_account_id = 'gl-1850-cash-concentration-master'
      AND p.status = 'success'
    GROUP BY p.posted_at::date
)
SELECT
    COALESCE(mc.sweep_date, sd.sweep_date)         AS sweep_date,
    COALESCE(mc.master_total, 0)                   AS master_total,
    COALESCE(sd.subaccount_total, 0)               AS subaccount_total,
    COALESCE(mc.master_total, 0)
        + COALESCE(sd.subaccount_total, 0)         AS drift
FROM master_credits mc
FULL OUTER JOIN subaccount_debits sd USING (sweep_date);


-- ACH Origination Settlement non-zero EOD (F.5.3).
-- The ACH Origination Settlement ledger (gl-1810) is a transitory clearing
-- account: per-customer ACH originations debit it during the day, and an
-- EOD sweep transfers the day's net to Cash & Due From FRB (gl-1010),
-- zeroing it out. Days the EOD sweep is skipped or fails leave the ledger
-- non-zero — surfacing here.
CREATE VIEW ar_ach_orig_settlement_nonzero AS
SELECT
    ldb.ledger_account_id,
    la.name                             AS ledger_name,
    ldb.balance_date,
    ldb.balance                         AS stored_balance
FROM ar_ledger_daily_balances ldb
JOIN ar_ledger_accounts la USING (ledger_account_id)
WHERE ldb.ledger_account_id = 'gl-1810-ach-orig-settlement'
  AND ldb.balance <> 0;


-- ACH internal sweep posted but no Fed confirmation (F.5.4).
-- Each successful internal EOD sweep on gl-1810 (ACH Origination
-- Settlement) should be followed by a Fed-side confirmation child
-- transfer attesting the FRB master account moved by the same amount.
-- This view surfaces sweeps where the internal leg posted but the Fed
-- confirmation never landed — the bank thinks the cash moved, the FRB
-- has no record.
CREATE VIEW ar_ach_sweep_no_fed_confirmation AS
SELECT
    t.transfer_id                       AS sweep_transfer_id,
    t.created_at                        AS sweep_at,
    t.amount                            AS sweep_amount
FROM transfer t
WHERE t.transfer_type = 'clearing_sweep'
  AND EXISTS (
    SELECT 1 FROM posting p
    WHERE p.transfer_id = t.transfer_id
      AND p.ledger_account_id = 'gl-1810-ach-orig-settlement'
  )
  AND NOT EXISTS (
    SELECT 1 FROM transfer fed
    WHERE fed.parent_transfer_id = t.transfer_id
      AND fed.transfer_type = 'ach'
      AND fed.origin = 'external_force_posted'
  );


-- Fed activity with no matching internal post (F.5.5).
-- Card-processor settlements posted by the FRB are observed at SNB as
-- top-of-chain external_force_posted transfers (parent IS NULL) hitting
-- the payment-gateway clearing sub-ledger. Each should be followed by an
-- SNB internal catch-up child (DR gl-1815, CR merchant DDA). This view
-- surfaces Fed observations with no internal catch-up — money the Fed
-- says cleared, that SNB never recorded internally.
CREATE VIEW ar_fed_card_no_internal_catchup AS
SELECT
    t.transfer_id                       AS fed_transfer_id,
    t.created_at                        AS fed_at,
    t.amount                            AS fed_amount
FROM transfer t
WHERE t.transfer_type = 'ach'
  AND t.origin = 'external_force_posted'
  AND t.parent_transfer_id IS NULL
  AND EXISTS (
    SELECT 1 FROM posting p
    WHERE p.transfer_id = t.transfer_id
      AND p.subledger_account_id = 'ext-payment-gateway-sub-clearing'
  )
  AND NOT EXISTS (
    SELECT 1 FROM transfer ic
    WHERE ic.parent_transfer_id = t.transfer_id
  );


-- GL-vs-Fed Master drift timeline (F.5.6).
-- Per day, totals the Fed-side card processor settlement amounts and
-- the SNB internal catch-up amounts (children of those Fed transfers).
-- Healthy days: both sides equal, drift = 0. Drift > 0 means Fed
-- posted activity that SNB never recorded internally — the GL view
-- and the Fed master view diverge.
CREATE VIEW ar_gl_vs_fed_master_drift AS
WITH fed_card_observed AS (
    SELECT
        t.transfer_id,
        t.created_at::date              AS movement_date,
        t.amount                        AS fed_amount
    FROM transfer t
    WHERE t.transfer_type = 'ach'
      AND t.origin = 'external_force_posted'
      AND t.parent_transfer_id IS NULL
      AND EXISTS (
        SELECT 1 FROM posting p
        WHERE p.transfer_id = t.transfer_id
          AND p.subledger_account_id = 'ext-payment-gateway-sub-clearing'
      )
),
fed_total AS (
    SELECT
        movement_date,
        SUM(fed_amount)                 AS fed_total
    FROM fed_card_observed
    GROUP BY movement_date
),
internal_total AS (
    SELECT
        ic.created_at::date             AS movement_date,
        SUM(ic.amount)                  AS internal_total
    FROM transfer ic
    WHERE ic.parent_transfer_id IN (SELECT transfer_id FROM fed_card_observed)
    GROUP BY ic.created_at::date
)
SELECT
    COALESCE(f.movement_date, i.movement_date) AS movement_date,
    COALESCE(f.fed_total, 0)                   AS fed_total,
    COALESCE(i.internal_total, 0)              AS internal_total,
    COALESCE(f.fed_total, 0)
        - COALESCE(i.internal_total, 0)        AS drift
FROM fed_total f
FULL OUTER JOIN internal_total i USING (movement_date);


-- Stuck in Internal Transfer Suspense (F.5.7).
-- Internal book-transfers between SNB customer DDAs land in two steps:
--   Step 1: DR gl-1830 (Internal Transfer Suspense), CR originator DDA
--   Step 2 (child): DR recipient DDA, CR gl-1830 -- clears the suspense
-- A "stuck" originate is a Step-1 transfer that posted with no Step-2
-- child ever appearing. The cash sits in the suspense ledger indefinitely
-- and the recipient never sees the credit.
CREATE VIEW ar_internal_transfer_stuck AS
SELECT
    t.transfer_id                       AS originate_transfer_id,
    t.created_at                        AS originated_at,
    t.amount                            AS originate_amount
FROM transfer t
WHERE t.transfer_type = 'internal'
  AND t.origin = 'internal_initiated'
  AND t.parent_transfer_id IS NULL
  AND EXISTS (
    SELECT 1 FROM posting p
    WHERE p.transfer_id = t.transfer_id
      AND p.ledger_account_id = 'gl-1830-internal-transfer-suspense'
  )
  AND NOT EXISTS (
    SELECT 1 FROM transfer step2
    WHERE step2.parent_transfer_id = t.transfer_id
  );
