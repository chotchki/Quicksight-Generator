"""ETL example generator — Payment Reconciliation.

Emits canonical INSERT statements showing how to populate
``transactions`` for the PR pipeline (sale → settlement → payment →
external_txn). Output is exemplary, not executable against the real
demo database — it uses fixed sentinel IDs so the patterns are
self-contained.

Used by ``quicksight-gen demo etl-example`` to ship a crib sheet
customers can copy from when building their own ETL.
"""

from __future__ import annotations


_HEADER = """\
-- =====================================================================
-- Payment Reconciliation — exemplary INSERT patterns
-- =====================================================================
--
-- Six canonical patterns showing how to populate `transactions` for
-- the PR pipeline: sale → settlement → payment → external_txn.
--
-- Every pattern uses fixed sentinel IDs (sale-EXAMPLE, etc.) so the
-- statements are self-contained and won't conflict with demo seed data
-- if you run them side-by-side. Strip the EXAMPLE suffix and wire the
-- column projections to your upstream feed.
--
-- See docs/Schema_v3.md for the full column contract.
-- See docs/handbook/etl.md for task-shaped walkthroughs.
--
-- =====================================================================
"""


_PATTERN_1_SALE = """\
-- ---------------------------------------------------------------------
-- Pattern 1: PR sale (`transfer_type = 'sale'`)
-- ---------------------------------------------------------------------
-- WHY: A merchant POS sale is one transaction row hitting the
--      merchant's sub-ledger DDA. The `metadata` JSON carries the
--      cross-check anchor (`merchant_account_id`) that lets the Phase
--      H sale-vs-settlement merchant cross-check verify the recipient
--      account when funds eventually settle.
-- Consumed by: Sales sheet, Where's My Money walkthrough,
--              Sale ↔ Settlement Mismatch check.

INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'sale-EXAMPLE-001',
    'sale-xfer-EXAMPLE-001',
    'sale',
    'internal_initiated',
    'pr-sub-merch-bigfoot',
    'Bigfoot Brews',
    'pr-merchant-ledger',
    'merchant_dda',
    TRUE,
    -- Sales credit the merchant's sub-ledger (negative signed_amount).
    -42.50,
    42.50,
    'success',
    TIMESTAMP '2026-04-20 09:15:00',
    DATE '2026-04-20',
    'Bigfoot Brews — Capitol Hill — POS sale',
    JSON_OBJECT(
        'source'              VALUE 'core_banking',
        'card_brand'          VALUE 'Visa',
        'card_last_four'      VALUE '4242',
        'cashier'             VALUE 'cashier-001',
        'payment_method'      VALUE 'card',
        -- WHY: Cross-check anchor — Phase H verifies this matches the
        -- recipient account_id when the funds settle.
        'merchant_account_id' VALUE 'pr-sub-merch-bigfoot',
        'merchant_name'       VALUE 'Bigfoot Brews',
        'merchant_type'       VALUE 'franchise',
        'settlement_id'       VALUE 'stl-EXAMPLE-001'
    )
);
"""


_PATTERN_2_SETTLEMENT = """\
-- ---------------------------------------------------------------------
-- Pattern 2: PR settlement (`transfer_type = 'settlement'`)
-- ---------------------------------------------------------------------
-- WHY: A settlement bundles N sales into a single batch. The
--      `parent_transfer_id` chain points from each sale to its
--      settlement; the settlement row itself is the aggregate posting
--      that moves funds from the merchant's sub-ledger to the
--      settlement holding account.
-- Consumed by: Settlements sheet, Sale ↔ Settlement Mismatch check.

-- Tag the parent_transfer_id on the source sales:
UPDATE transactions
SET parent_transfer_id = 'stl-xfer-EXAMPLE-001'
WHERE transfer_id = 'sale-xfer-EXAMPLE-001';

-- Then the settlement posting itself:
INSERT INTO transactions (
    transaction_id, transfer_id, parent_transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'stl-EXAMPLE-001',
    'stl-xfer-EXAMPLE-001',
    NULL,
    'settlement',
    'internal_initiated',
    'pr-sub-merch-bigfoot',
    'Bigfoot Brews',
    'pr-merchant-ledger',
    'merchant_dda',
    TRUE,
    42.50,
    42.50,
    'success',
    TIMESTAMP '2026-04-20 18:00:00',
    DATE '2026-04-20',
    'Daily settlement — Bigfoot Brews',
    JSON_OBJECT(
        'source'           VALUE 'core_banking',
        'settlement_type'  VALUE 'daily',
        'sale_count'       VALUE '1',
        'merchant_name'    VALUE 'Bigfoot Brews'
    )
);
"""


_PATTERN_3_PAYMENT = """\
-- ---------------------------------------------------------------------
-- Pattern 3: PR payment (`transfer_type = 'payment'`)
-- ---------------------------------------------------------------------
-- WHY: A payment remits a settlement to the merchant's external bank
--      account. Its `parent_transfer_id` points at the settlement.
--      `payment_amount` should equal the parent settlement's
--      `settlement_amount` to the cent — the Settlement ↔ Payment
--      Mismatch check fires when they diverge.
-- Consumed by: Payments sheet, Settlement ↔ Payment Mismatch check,
--              Payment Reconciliation tab.

INSERT INTO transactions (
    transaction_id, transfer_id, parent_transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
) VALUES (
    'pay-EXAMPLE-001',
    'pay-xfer-EXAMPLE-001',
    'stl-xfer-EXAMPLE-001',
    'payment',
    'internal_initiated',
    'pr-external-customer-pool',
    'External Customer Pool',
    'pr-merchant-ledger',
    'external_counter',
    FALSE,
    -42.50,
    42.50,
    'success',
    TIMESTAMP '2026-04-21 10:00:00',
    DATE '2026-04-21',
    'BankSync',
    'Remit to Bigfoot Brews',
    JSON_OBJECT(
        'source'                 VALUE 'core_banking',
        'settlement_id'          VALUE 'stl-EXAMPLE-001',
        'payment_status'         VALUE 'paid',
        'is_returned'            VALUE 'false',
        'external_transaction_id' VALUE 'ext-EXAMPLE-001'
    )
);
"""


_PATTERN_4_EXT_TXN_ONE_TO_ONE = """\
-- ---------------------------------------------------------------------
-- Pattern 4a: External transaction — one-to-one match
-- ---------------------------------------------------------------------
-- WHY: An external clearing system (BankSync, PaymentHub, ClearSettle)
--      observes one of our payments individually. Match status =
--      `matched` when external `amount` equals SUM of linked payments
--      to the cent.
-- Consumed by: Payment Reconciliation tab side-by-side tables,
--              Unmatched External Txns check.

-- Tag the parent_transfer_id on the source payment(s):
UPDATE transactions
SET parent_transfer_id = 'ext-xfer-EXAMPLE-001'
WHERE transfer_id = 'pay-xfer-EXAMPLE-001';

-- Then the external_txn observation row:
INSERT INTO transactions (
    transaction_id, transfer_id, parent_transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
) VALUES (
    'ext-EXAMPLE-001',
    'ext-xfer-EXAMPLE-001',
    NULL,
    'external_txn',
    'external_force_posted',
    'pr-external-rail-banksync',
    'BankSync external rail',
    'pr-merchant-ledger',
    'external_counter',
    FALSE,
    42.50,
    42.50,
    'success',
    TIMESTAMP '2026-04-21 14:30:00',
    DATE '2026-04-21',
    'BankSync',
    'BankSync clearing — Bigfoot Brews payout',
    JSON_OBJECT(
        'source'       VALUE 'processor_report',
        'record_count' VALUE '1'
    )
);
"""


_PATTERN_4_EXT_TXN_BATCH = """\
-- ---------------------------------------------------------------------
-- Pattern 4b: External transaction — batched (one-to-many)
-- ---------------------------------------------------------------------
-- WHY: Most clearing systems batch multiple payments into one external
--      transaction. The `parent_transfer_id` on each child payment
--      points to the parent external_txn's transfer_id; the parent's
--      `amount` is the SUM, and `metadata.record_count` is the child
--      count.
-- Consumed by: Payment Reconciliation tab, Why Is This External
--              Transaction Unmatched walkthrough.

-- For each child payment, tag the parent_transfer_id:
UPDATE transactions
SET parent_transfer_id = 'ext-xfer-EXAMPLE-002'
WHERE transfer_id IN (
    'pay-xfer-EXAMPLE-002',
    'pay-xfer-EXAMPLE-003',
    'pay-xfer-EXAMPLE-004'
);

-- Then the parent external_txn aggregate:
INSERT INTO transactions (
    transaction_id, transfer_id, parent_transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
) VALUES (
    'ext-EXAMPLE-002',
    'ext-xfer-EXAMPLE-002',
    NULL,
    'external_txn',
    'external_force_posted',
    'pr-external-rail-banksync',
    'BankSync external rail',
    'pr-merchant-ledger',
    'external_counter',
    FALSE,
    -- The amount is the SUM of the three child payments (e.g.,
    -- 42.50 + 78.25 + 19.95 = 140.70).
    140.70,
    140.70,
    'success',
    TIMESTAMP '2026-04-21 18:00:00',
    DATE '2026-04-21',
    'BankSync',
    'BankSync EOD batch — 3 merchants',
    JSON_OBJECT(
        'source'       VALUE 'processor_report',
        'record_count' VALUE '3'
    )
);
"""


_PATTERN_5_RETURN = """\
-- ---------------------------------------------------------------------
-- Pattern 5: Returned payment (`metadata.is_returned = 'true'`)
-- ---------------------------------------------------------------------
-- WHY: When a payment is returned (NSF, account_closed, disputed, etc.)
--      it stays in `transactions` but flips to `payment_status =
--      returned` with the reason in `metadata.return_reason`.
--      Returned payments do NOT post a reversal row by default — the
--      original payment row is the source of truth and downstream
--      consumers filter on `metadata.is_returned`.
-- Consumed by: How Much Did We Return walkthrough,
--              Payment Returns exception check.

INSERT INTO transactions (
    transaction_id, transfer_id, parent_transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
) VALUES (
    'pay-EXAMPLE-005',
    'pay-xfer-EXAMPLE-005',
    'stl-xfer-EXAMPLE-005',
    'payment',
    'internal_initiated',
    'pr-external-customer-pool',
    'External Customer Pool',
    'pr-merchant-ledger',
    'external_counter',
    FALSE,
    -25.00,
    25.00,
    'success',  -- WHY: status is 'success' on the original posting; the
                -- return is reflected via metadata, not status.
    TIMESTAMP '2026-04-22 11:00:00',
    DATE '2026-04-22',
    'PaymentHub',
    'Remit to Cryptid Coffee Cart — RETURNED',
    JSON_OBJECT(
        'source'         VALUE 'core_banking',
        'settlement_id'  VALUE 'stl-EXAMPLE-005',
        'payment_status' VALUE 'returned',
        'is_returned'    VALUE 'true',
        -- WHY: Drives the Payment Returns by Reason chart and the
        -- weekly call-back list.
        'return_reason'  VALUE 'account_closed'
    )
);
"""


def generate_etl_examples_sql() -> str:
    """Emit the full PR ETL examples document as a SQL string."""
    return "\n".join([
        _HEADER,
        _PATTERN_1_SALE,
        _PATTERN_2_SETTLEMENT,
        _PATTERN_3_PAYMENT,
        _PATTERN_4_EXT_TXN_ONE_TO_ONE,
        _PATTERN_4_EXT_TXN_BATCH,
        _PATTERN_5_RETURN,
    ])
