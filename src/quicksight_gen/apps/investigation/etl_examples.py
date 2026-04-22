"""ETL examples for the Investigation app.

K.4.2 ships none — investigation has no app-specific metadata keys
beyond what PR/AR already document. K.4.4 may add an example for the
σ-threshold parameterization if the matview lands.
"""

from __future__ import annotations


def generate_etl_examples_sql() -> str:
    """Return canonical INSERT/UPSERT patterns for ETL authors.

    Empty for the K.4.2 skeleton. Investigation reads the same
    `transactions` + `daily_balances` shape as PR/AR; the existing
    examples in `apps/payment_recon/etl_examples.py` and
    `apps/account_recon/etl_examples.py` cover all needed patterns.
    """
    return "-- Investigation: no app-specific ETL patterns (K.4.2 skeleton)\n"
