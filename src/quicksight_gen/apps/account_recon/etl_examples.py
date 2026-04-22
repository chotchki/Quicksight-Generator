"""ETL example generator — Account Reconciliation.

Emits canonical INSERT statements showing how to populate
``transactions`` and ``daily_balances`` for the AR / Cash Management
Suite (CMS) flows: customer DDA transfers, force-posted ACH from the
Fed, ZBA / cash-concentration sweeps, and limit configuration.

Used by ``quicksight-gen demo etl-example`` to ship a crib sheet
customers can copy from when building their own ETL.
"""

from __future__ import annotations


_HEADER = """\
-- =====================================================================
-- Account Reconciliation — exemplary INSERT patterns
-- =====================================================================
--
-- Five canonical patterns for SNB's Cash Management Suite (CMS):
--   1. Customer DDA internal transfer (two-leg net-zero)
--   2. Force-posted ACH from the Fed (origin = external_force_posted)
--   3. ZBA / cash-concentration sweep (clearing_sweep)
--   4. Limit configuration (UPDATE daily_balances metadata)
--   5. GL drift recompute (SELECT pattern, not an INSERT)
--
-- Every pattern uses fixed sentinel IDs (xfer-EXAMPLE, etc.) so the
-- statements are self-contained and won't conflict with demo seed data.
-- Strip the EXAMPLE suffix and wire the column projections to your
-- upstream feed.
--
-- See docs/Schema_v3.md for the full column contract.
-- See docs/handbook/etl.md for task-shaped walkthroughs.
--
-- =====================================================================
"""


_PATTERN_1_INTERNAL_TRANSFER = """\
-- ---------------------------------------------------------------------
-- Pattern 1: Customer DDA internal transfer (two-leg net-zero)
-- ---------------------------------------------------------------------
-- WHY: Every transfer is a SET of legs grouped by `transfer_id` that
--      MUST sum to zero (excluding `failed` rows). An on-us transfer
--      between two customer DDAs is the simplest case: one debit leg,
--      one credit leg, both with the same `transfer_id`.
-- Consumed by: Transfers sheet, AR Non-Zero Transfers exception
--              check (which flags any transfer_id whose legs DON'T net
--              to zero).

-- Leg 1: debit the source DDA.
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'txn-EXAMPLE-001A',
    'xfer-EXAMPLE-001',
    'internal',
    'internal_initiated',
    'dda-cascade-timber',
    'Cascade Timber Mill — Operating',
    'gl-2010',
    'dda',
    TRUE,
    1500.00,                                       -- positive = debit
    1500.00,
    'success',
    TIMESTAMP '2026-04-20 10:00:00',
    DATE '2026-04-20',
    'Internal transfer to Pinecrest',
    JSON_OBJECT('source' VALUE 'core_banking')
);

-- Leg 2: credit the destination DDA. Same transfer_id.
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'txn-EXAMPLE-001B',
    'xfer-EXAMPLE-001',
    'internal',
    'internal_initiated',
    'dda-pinecrest',
    'Pinecrest Vineyards — Operating',
    'gl-2010',
    'dda',
    TRUE,
    -1500.00,                                      -- negative = credit
    1500.00,
    'success',
    TIMESTAMP '2026-04-20 10:00:00',
    DATE '2026-04-20',
    'Internal transfer from Cascade Timber',
    JSON_OBJECT('source' VALUE 'core_banking')
);
-- 1500.00 + (-1500.00) = 0.00 → AR Non-Zero Transfers check stays silent.
"""


_PATTERN_2_FORCE_POSTED = """\
-- ---------------------------------------------------------------------
-- Pattern 2: Force-posted ACH from the Fed
-- ---------------------------------------------------------------------
-- WHY: When the Fed force-posts a transaction (typically an inbound
--      ACH that didn't have a matching outbound origination on our
--      side yet), we record it with `origin = 'external_force_posted'`
--      and `metadata.source = 'fed_statement'`. The AR GL vs Fed
--      Master Drift check uses these to separate operator-initiated
--      drift (a real exception) from Fed-forced drift (catch-up
--      pending).
-- Consumed by: GL vs Fed Master Drift check, Fed Activity Without
--              Internal Post check.

INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
) VALUES (
    'fed-EXAMPLE-001',
    'fed-xfer-EXAMPLE-001',
    'ach',
    'external_force_posted',                       -- WHY: drives drift split
    'gl-1010',
    'Cash & Due From FRB',
    NULL,
    'gl_control',
    TRUE,
    -2500.00,                                      -- negative = inbound credit
    2500.00,
    'success',
    TIMESTAMP '2026-04-20 13:30:00',
    DATE '2026-04-20',
    'FRB',
    'Inbound ACH — origin pending',
    JSON_OBJECT(
        'source'            VALUE 'fed_statement', -- WHY: provenance
        'statement_line_id' VALUE 'fed-stmt-2026-04-20-line-042'
    )
);
"""


_PATTERN_3_SWEEP = """\
-- ---------------------------------------------------------------------
-- Pattern 3: ZBA / cash-concentration sweep
-- ---------------------------------------------------------------------
-- WHY: Daily ZBA sweeps move all sub-ledger DDA balances into the
--      Cash Concentration Master (gl-1850). Each sweep is a single
--      transfer with N+1 legs: one debit per source DDA, one credit
--      to gl-1850 for the SUM. Modeled as `transfer_type =
--      'clearing_sweep'`.
-- Consumed by: Concentration Master Sweep Drift check, Sweep Target
--              Non-Zero EOD check.

-- Leg 1: debit a source DDA (truncated for brevity — real sweep has
--        many of these).
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'sweep-EXAMPLE-001A',
    'sweep-xfer-EXAMPLE-001',
    'clearing_sweep',
    'internal_initiated',
    'dda-cascade-timber',
    'Cascade Timber Mill — Operating',
    'gl-2010',
    'dda',
    TRUE,
    8500.00,                                       -- positive = debit (sweep out)
    8500.00,
    'success',
    TIMESTAMP '2026-04-20 17:00:00',
    DATE '2026-04-20',
    'EOD ZBA sweep to gl-1850',
    JSON_OBJECT('source' VALUE 'sweep_engine')
);

-- Leg 2: credit the Concentration Master for the SUM.
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
) VALUES (
    'sweep-EXAMPLE-001Z',
    'sweep-xfer-EXAMPLE-001',
    'clearing_sweep',
    'internal_initiated',
    'gl-1850',
    'Cash Concentration Master',
    NULL,                                          -- WHY: ledger-direct posting
    'concentration_master',
    TRUE,
    -8500.00,
    8500.00,
    'success',
    TIMESTAMP '2026-04-20 17:00:00',
    DATE '2026-04-20',
    'EOD ZBA sweep — total inbound',
    JSON_OBJECT('source' VALUE 'sweep_engine')
);
"""


_PATTERN_4_LIMITS = """\
-- ---------------------------------------------------------------------
-- Pattern 4: Per-ledger limit configuration
-- ---------------------------------------------------------------------
-- WHY: Daily outflow caps live in `daily_balances.metadata.limits` on
--      the LEDGER (top-level) row, day by day. The Sub-Ledger Limit
--      Breach check joins each transaction's daily aggregate to the
--      relevant ledger's daily_balances row and reads the cap via
--      JSON_VALUE. Without `limits` populated, the KPI shows 0 — not
--      because nothing breached, but because no limits exist to breach.
-- Consumed by: Sub-Ledger Limit Breach check.

UPDATE daily_balances
SET metadata = JSON_OBJECT(
    'source' VALUE 'core_banking',
    'limits' VALUE JSON_OBJECT(
        'ach'      VALUE 100000,                   -- $100k/day ACH outflow cap
        'wire'     VALUE 50000,                    -- $50k/day wire cap
        'internal' VALUE 25000                     -- $25k/day on-us cap
    )
)
WHERE account_id = 'gl-2010'
  AND balance_date = DATE '2026-04-20';

-- For multi-day setup, change the WHERE clause to a date range:
--   AND balance_date BETWEEN DATE '2026-04-01' AND DATE '2026-04-30'
-- Limits change rarely, so updating one day at a time on landing is
-- fine for most deployments.
"""


_PATTERN_5_DRIFT_RECOMPUTE = """\
-- ---------------------------------------------------------------------
-- Pattern 5: GL drift recompute (validation SELECT, not an INSERT)
-- ---------------------------------------------------------------------
-- WHY: The Ledger Drift check fires when `daily_balances.balance`
--      (stored) doesn't match the SUM of postings to that account
--      (recomputed) on a given date. This is the canonical pattern
--      your ETL should run as a smoke test BEFORE marking a daily
--      load complete — if drift > 0 on day-of-load, your transaction
--      feed and your balance feed disagree.
-- Consumed by: Use this to validate locally; the deployed Ledger
--              Drift check uses the same shape.

SELECT
    db.account_id,
    db.balance_date,
    db.balance                                         AS stored_balance,
    COALESCE(SUM(t.signed_amount), 0)                  AS recomputed_balance,
    db.balance - COALESCE(SUM(t.signed_amount), 0)     AS drift
FROM daily_balances db
LEFT JOIN transactions t
  ON t.account_id    = db.account_id
 AND t.balance_date <= db.balance_date
 AND t.status        = 'success'
WHERE db.balance_date = CURRENT_DATE
  AND db.control_account_id IS NULL                    -- ledger rows only
GROUP BY db.account_id, db.balance_date, db.balance
HAVING db.balance - COALESCE(SUM(t.signed_amount), 0) <> 0;

-- A row in this output means: this ledger's stored EOD balance
-- doesn't match the cumulative SUM of all postings to it. Either the
-- balance feed is wrong, or a posting is missing / extra / has the
-- wrong signed_amount sign. Investigate before going live.
"""


def generate_etl_examples_sql() -> str:
    """Emit the full AR ETL examples document as a SQL string."""
    return "\n".join([
        _HEADER,
        _PATTERN_1_INTERNAL_TRANSFER,
        _PATTERN_2_FORCE_POSTED,
        _PATTERN_3_SWEEP,
        _PATTERN_4_LIMITS,
        _PATTERN_5_DRIFT_RECOMPUTE,
    ])
