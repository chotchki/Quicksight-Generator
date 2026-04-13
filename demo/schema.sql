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
