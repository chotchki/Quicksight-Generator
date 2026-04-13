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
--   Child drift  = stored child balance vs running Σ posted txns
--                  (fires when the child-balance upstream feed disagrees
--                  with the underlying transactions)
--   Parent drift = stored parent balance vs Σ children's stored balances
--                  (fires when the parent-balance upstream feed disagrees
--                  with the aggregation of its children — independent of
--                  whether the child feed and the transactions agree)
--
-- Parent- and child-level stored balances may come from different
-- upstream systems, so each drift points at a different source.
-- ===================================================================

DROP VIEW  IF EXISTS ar_transfer_summary               CASCADE;
DROP VIEW  IF EXISTS ar_transfer_net_zero              CASCADE;
DROP VIEW  IF EXISTS ar_parent_balance_drift           CASCADE;
DROP VIEW  IF EXISTS ar_account_balance_drift          CASCADE;
DROP VIEW  IF EXISTS ar_computed_parent_daily_balance  CASCADE;
DROP VIEW  IF EXISTS ar_computed_account_daily_balance CASCADE;
DROP TABLE IF EXISTS ar_transactions                   CASCADE;
DROP TABLE IF EXISTS ar_daily_balances                 CASCADE;
DROP TABLE IF EXISTS ar_parent_daily_balances          CASCADE;
DROP TABLE IF EXISTS ar_account_daily_balances         CASCADE;
DROP TABLE IF EXISTS ar_accounts                       CASCADE;
DROP TABLE IF EXISTS ar_parent_accounts                CASCADE;


CREATE TABLE ar_parent_accounts (
    parent_account_id VARCHAR(100) PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    is_internal       BOOLEAN      NOT NULL
);

CREATE TABLE ar_accounts (
    account_id        VARCHAR(100) PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    is_internal       BOOLEAN      NOT NULL,
    parent_account_id VARCHAR(100) NOT NULL REFERENCES ar_parent_accounts(parent_account_id)
);

-- Stored daily final at the parent-account level. Populated by the
-- parent-account upstream feed.
CREATE TABLE ar_parent_daily_balances (
    parent_account_id VARCHAR(100)  NOT NULL REFERENCES ar_parent_accounts(parent_account_id),
    balance_date      DATE          NOT NULL,
    balance           DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (parent_account_id, balance_date)
);

-- Stored daily final at the child-account level. Populated by the
-- child-account upstream feed — may be a different system from the
-- parent-balance feed, hence the two-level reconciliation.
CREATE TABLE ar_account_daily_balances (
    account_id   VARCHAR(100)  NOT NULL REFERENCES ar_accounts(account_id),
    balance_date DATE          NOT NULL,
    balance      DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (account_id, balance_date)
);

-- Every transfer is a group of transactions sharing a transfer_id.
-- memo is denormalized onto each row for simplicity; the summary view
-- picks a representative memo per transfer.
CREATE TABLE ar_transactions (
    transaction_id VARCHAR(100)  PRIMARY KEY,
    account_id     VARCHAR(100)  NOT NULL REFERENCES ar_accounts(account_id),
    transfer_id    VARCHAR(100)  NOT NULL,
    amount         DECIMAL(14,2) NOT NULL,
    posted_at      TIMESTAMP     NOT NULL,
    status         VARCHAR(20)   NOT NULL CHECK (status IN ('posted', 'failed', 'pending')),
    memo           VARCHAR(255)
);

CREATE INDEX idx_ar_accounts_parent               ON ar_accounts(parent_account_id);
CREATE INDEX idx_ar_txn_account                   ON ar_transactions(account_id);
CREATE INDEX idx_ar_txn_transfer                  ON ar_transactions(transfer_id);
CREATE INDEX idx_ar_txn_posted                    ON ar_transactions(posted_at);
CREATE INDEX idx_ar_txn_status                    ON ar_transactions(status);
CREATE INDEX idx_ar_parent_daily_balances_date    ON ar_parent_daily_balances(balance_date);
CREATE INDEX idx_ar_account_daily_balances_date   ON ar_account_daily_balances(balance_date);


-- Running Σ of posted transactions per child account, up to and
-- including each balance date on which a stored child balance exists.
-- Failed/pending transactions are excluded.
CREATE VIEW ar_computed_account_daily_balance AS
SELECT
    adb.account_id,
    adb.balance_date,
    COALESCE(SUM(t.amount), 0) AS computed_balance
FROM ar_account_daily_balances adb
LEFT JOIN ar_transactions t
    ON t.account_id        = adb.account_id
   AND t.status            = 'posted'
   AND t.posted_at::date  <= adb.balance_date
GROUP BY adb.account_id, adb.balance_date;


-- Child-level drift: stored − computed for each (account, date).
CREATE VIEW ar_account_balance_drift AS
SELECT
    stored.account_id,
    a.name                                    AS account_name,
    a.parent_account_id,
    pa.name                                   AS parent_name,
    CASE WHEN a.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    stored.balance_date,
    stored.balance                            AS stored_balance,
    COALESCE(computed.computed_balance, 0)    AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM ar_account_daily_balances stored
JOIN ar_accounts a        USING (account_id)
JOIN ar_parent_accounts pa USING (parent_account_id)
LEFT JOIN ar_computed_account_daily_balance computed
       ON computed.account_id   = stored.account_id
      AND computed.balance_date = stored.balance_date;


-- Σ of children's stored balances per parent per day. The parent-level
-- reconciliation invariant: stored parent balance should equal this sum.
CREATE VIEW ar_computed_parent_daily_balance AS
SELECT
    pdb.parent_account_id,
    pdb.balance_date,
    COALESCE(SUM(adb.balance), 0) AS computed_balance
FROM ar_parent_daily_balances pdb
LEFT JOIN ar_accounts a
       ON a.parent_account_id = pdb.parent_account_id
LEFT JOIN ar_account_daily_balances adb
       ON adb.account_id   = a.account_id
      AND adb.balance_date = pdb.balance_date
GROUP BY pdb.parent_account_id, pdb.balance_date;


-- Parent-level drift: stored parent balance vs Σ of children's stored
-- balances. Independent of whether the child drift view shows issues.
CREATE VIEW ar_parent_balance_drift AS
SELECT
    stored.parent_account_id,
    pa.name                                  AS parent_name,
    pa.is_internal,
    stored.balance_date,
    stored.balance                           AS stored_balance,
    COALESCE(computed.computed_balance, 0)   AS computed_balance,
    stored.balance - COALESCE(computed.computed_balance, 0) AS drift
FROM ar_parent_daily_balances stored
JOIN ar_parent_accounts pa USING (parent_account_id)
LEFT JOIN ar_computed_parent_daily_balance computed
       ON computed.parent_account_id = stored.parent_account_id
      AND computed.balance_date      = stored.balance_date;


-- Per-transfer net of non-failed transactions + net-zero flag.
-- Represents the set of transactions that should balance for each
-- transfer. A healthy transfer has net = 0. ``has_external_leg`` flags
-- transfers where at least one leg lands on an external account — the
-- external leg's effect on tracked balances is zero (we don't store
-- external balances), so a net-zero transfer can still move a tracked
-- child's running total by its full amount.
CREATE VIEW ar_transfer_net_zero AS
SELECT
    t.transfer_id,
    MIN(t.posted_at)                                              AS first_posted_at,
    SUM(CASE WHEN t.status <> 'failed' THEN t.amount ELSE 0 END)  AS net_amount,
    SUM(CASE WHEN t.amount > 0 AND t.status <> 'failed'
             THEN t.amount ELSE 0 END)                            AS total_debit,
    SUM(CASE WHEN t.amount < 0 AND t.status <> 'failed'
             THEN t.amount ELSE 0 END)                            AS total_credit,
    COUNT(*)                                                      AS leg_count,
    SUM(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END)          AS failed_leg_count,
    BOOL_OR(NOT a.is_internal)                                    AS has_external_leg,
    CASE
        WHEN SUM(CASE WHEN t.status <> 'failed' THEN t.amount ELSE 0 END) = 0
            THEN 'net_zero'
        ELSE 'not_net_zero'
    END                                                           AS net_zero_status
FROM ar_transactions t
JOIN ar_accounts a ON a.account_id = t.account_id
GROUP BY t.transfer_id;


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
    (SELECT memo FROM ar_transactions x
      WHERE x.transfer_id = tz.transfer_id
      ORDER BY x.posted_at, x.transaction_id
      LIMIT 1)                              AS memo
FROM ar_transfer_net_zero tz;
