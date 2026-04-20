"""Demo schema + helpers shipped with the wheel."""

from importlib.resources import files


def generate_schema_sql() -> str:
    """Return the PostgreSQL DDL for the demo database.

    The DDL is identical for both apps — they share the
    ``transactions`` and ``daily_balances`` base tables plus the
    AR-only dimension tables and computed views. The text is loaded
    from ``schema.sql`` packaged alongside this module so it ships
    with the wheel.
    """
    return (files(__package__) / "schema.sql").read_text(encoding="utf-8")
