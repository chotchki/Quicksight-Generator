"""Canonical PostgreSQL DDL for the QuickSight base layer.

The schema is the *interface contract* that production ETL writes to:
two base tables (``transactions`` + ``daily_balances``) shared between
both apps, plus the AR-only dimension tables and computed views. The
demo seed in ``payment_recon.demo_data`` and ``account_recon.demo_data``
loads against this same DDL — there is no separate "demo schema". The
SQL is also exposed via the ``quicksight-gen demo schema`` CLI command.
"""

from importlib.resources import files


def generate_schema_sql() -> str:
    """Return the PostgreSQL DDL for the base layer."""
    return (files(__package__) / "schema.sql").read_text(encoding="utf-8")
