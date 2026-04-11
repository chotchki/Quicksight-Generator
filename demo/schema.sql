-- QuickSight Demo Schema
-- Target: PostgreSQL 12+
--
-- Defines the tables and views that the QuickSight dataset SQL queries
-- run against.  The DROP IF EXISTS cascade at the top makes this script
-- idempotent — safe to re-run.

-- -------------------------------------------------------------------
-- Drop existing objects
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
-- Tables
-- -------------------------------------------------------------------

CREATE TABLE late_thresholds (
    transaction_type VARCHAR(50)  PRIMARY KEY,
    threshold_days   INTEGER      NOT NULL,
    description      TEXT         NOT NULL
);

CREATE TABLE merchants (
    merchant_id   VARCHAR(100) PRIMARY KEY,
    merchant_name VARCHAR(255) NOT NULL,
    merchant_type VARCHAR(50)  NOT NULL,   -- franchise | independent | cart
    location_id   VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status        VARCHAR(50)  NOT NULL DEFAULT 'active'
);

CREATE TABLE external_transactions (
    transaction_id   VARCHAR(100)   PRIMARY KEY,
    transaction_type VARCHAR(50)    NOT NULL,  -- sales | settlements | payments
    external_system  VARCHAR(100)   NOT NULL,
    external_amount  DECIMAL(12,2)  NOT NULL,
    record_count     INTEGER        NOT NULL DEFAULT 0,
    transaction_date TIMESTAMP      NOT NULL,
    status           VARCHAR(50)    NOT NULL,
    merchant_id      VARCHAR(100)   NOT NULL REFERENCES merchants(merchant_id)
);

CREATE TABLE settlements (
    settlement_id          VARCHAR(100)   PRIMARY KEY,
    merchant_id            VARCHAR(100)   NOT NULL REFERENCES merchants(merchant_id),
    settlement_type        VARCHAR(50)    NOT NULL,
    settlement_amount      DECIMAL(12,2)  NOT NULL,
    settlement_date        TIMESTAMP      NOT NULL,
    settlement_status      VARCHAR(50)    NOT NULL,
    sale_count             INTEGER        NOT NULL DEFAULT 0,
    external_transaction_id VARCHAR(100)  REFERENCES external_transactions(transaction_id)
);

CREATE TABLE sales (
    sale_id                 VARCHAR(100)   PRIMARY KEY,
    merchant_id             VARCHAR(100)   NOT NULL REFERENCES merchants(merchant_id),
    location_id             VARCHAR(100)   NOT NULL,
    amount                  DECIMAL(12,2)  NOT NULL,
    sale_timestamp          TIMESTAMP      NOT NULL,
    card_brand              VARCHAR(50),
    card_last_four          VARCHAR(4),
    reference_id            VARCHAR(100),
    metadata                TEXT,
    settlement_id           VARCHAR(100)   REFERENCES settlements(settlement_id),
    external_transaction_id VARCHAR(100)   REFERENCES external_transactions(transaction_id)
);

CREATE TABLE payments (
    payment_id              VARCHAR(100)   PRIMARY KEY,
    settlement_id           VARCHAR(100)   NOT NULL REFERENCES settlements(settlement_id),
    merchant_id             VARCHAR(100)   NOT NULL REFERENCES merchants(merchant_id),
    payment_amount          DECIMAL(12,2)  NOT NULL,
    payment_date            TIMESTAMP      NOT NULL,
    payment_status          VARCHAR(50)    NOT NULL,
    is_returned             VARCHAR(10)    NOT NULL DEFAULT 'false',
    return_reason           VARCHAR(255),
    external_transaction_id VARCHAR(100)   REFERENCES external_transactions(transaction_id)
);

-- -------------------------------------------------------------------
-- Indexes
-- -------------------------------------------------------------------

CREATE INDEX idx_sales_merchant    ON sales(merchant_id);
CREATE INDEX idx_sales_location    ON sales(location_id);
CREATE INDEX idx_sales_timestamp   ON sales(sale_timestamp);
CREATE INDEX idx_sales_settlement  ON sales(settlement_id);
CREATE INDEX idx_sales_ext_txn     ON sales(external_transaction_id);

CREATE INDEX idx_settlements_merchant ON settlements(merchant_id);
CREATE INDEX idx_settlements_ext_txn  ON settlements(external_transaction_id);

CREATE INDEX idx_payments_settlement ON payments(settlement_id);
CREATE INDEX idx_payments_merchant   ON payments(merchant_id);
CREATE INDEX idx_payments_ext_txn    ON payments(external_transaction_id);

CREATE INDEX idx_ext_txn_type     ON external_transactions(transaction_type);
CREATE INDEX idx_ext_txn_system   ON external_transactions(external_system);
CREATE INDEX idx_ext_txn_merchant ON external_transactions(merchant_id);

-- -------------------------------------------------------------------
-- Reconciliation views
--
-- These mirror the QuickSight recon dataset SQL queries and are
-- referenced by the recon-exceptions dataset.
-- -------------------------------------------------------------------

CREATE VIEW sales_recon_view AS
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    COALESCE(SUM(s.amount), 0)                        AS internal_total,
    et.external_amount - COALESCE(SUM(s.amount), 0)   AS difference,
    CASE
        WHEN et.external_amount = COALESCE(SUM(s.amount), 0)
            THEN 'matched'
        WHEN (CURRENT_DATE - et.transaction_date::date) > lt.threshold_days
            THEN 'late'
        ELSE 'not_yet_matched'
    END                                                AS match_status,
    COUNT(s.sale_id)                                   AS sale_count,
    et.merchant_id,
    et.transaction_date,
    (CURRENT_DATE - et.transaction_date::date)         AS days_outstanding,
    lt.threshold_days                                  AS late_threshold,
    lt.description                                     AS late_threshold_description
FROM external_transactions et
LEFT JOIN sales s            ON s.external_transaction_id = et.transaction_id
LEFT JOIN late_thresholds lt ON lt.transaction_type = 'sales'
WHERE et.transaction_type = 'sales'
GROUP BY et.transaction_id, et.external_system, et.external_amount,
         et.merchant_id, et.transaction_date,
         lt.threshold_days, lt.description;


CREATE VIEW settlement_recon_view AS
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    COALESCE(SUM(st.settlement_amount), 0)                        AS internal_total,
    et.external_amount - COALESCE(SUM(st.settlement_amount), 0)   AS difference,
    CASE
        WHEN et.external_amount = COALESCE(SUM(st.settlement_amount), 0)
            THEN 'matched'
        WHEN (CURRENT_DATE - et.transaction_date::date) > lt.threshold_days
            THEN 'late'
        ELSE 'not_yet_matched'
    END                                                            AS match_status,
    COUNT(st.settlement_id)                                        AS settlement_count,
    et.merchant_id,
    et.transaction_date,
    (CURRENT_DATE - et.transaction_date::date)                     AS days_outstanding,
    lt.threshold_days                                              AS late_threshold,
    lt.description                                                 AS late_threshold_description
FROM external_transactions et
LEFT JOIN settlements st     ON st.external_transaction_id = et.transaction_id
LEFT JOIN late_thresholds lt ON lt.transaction_type = 'settlements'
WHERE et.transaction_type = 'settlements'
GROUP BY et.transaction_id, et.external_system, et.external_amount,
         et.merchant_id, et.transaction_date,
         lt.threshold_days, lt.description;


CREATE VIEW payment_recon_view AS
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    COALESCE(SUM(p.payment_amount), 0)                        AS internal_total,
    et.external_amount - COALESCE(SUM(p.payment_amount), 0)   AS difference,
    CASE
        WHEN et.external_amount = COALESCE(SUM(p.payment_amount), 0)
            THEN 'matched'
        WHEN (CURRENT_DATE - et.transaction_date::date) > lt.threshold_days
            THEN 'late'
        ELSE 'not_yet_matched'
    END                                                        AS match_status,
    COUNT(p.payment_id)                                        AS payment_count,
    et.merchant_id,
    et.transaction_date,
    (CURRENT_DATE - et.transaction_date::date)                 AS days_outstanding,
    lt.threshold_days                                          AS late_threshold,
    lt.description                                             AS late_threshold_description
FROM external_transactions et
LEFT JOIN payments p         ON p.external_transaction_id = et.transaction_id
LEFT JOIN late_thresholds lt ON lt.transaction_type = 'payments'
WHERE et.transaction_type = 'payments'
GROUP BY et.transaction_id, et.external_system, et.external_amount,
         et.merchant_id, et.transaction_date,
         lt.threshold_days, lt.description;
