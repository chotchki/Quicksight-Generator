"""SQL dialect helpers — Phase P.2.

Public surface:

- ``Dialect`` enum (``POSTGRES``, ``ORACLE``).
- Per-construct helpers that emit dialect-appropriate SQL fragments.

Phase P.2 ships every helper with a Postgres branch only; the Oracle
branch raises ``NotImplementedError`` until Phase P.3 fills it in.
"""

from __future__ import annotations

from .dialect import (
    Dialect,
    analyze_table,
    boolean_type,
    cast,
    create_matview,
    date_minus_days,
    date_trunc_day,
    decimal_type,
    drop_index_if_exists,
    drop_matview_if_exists,
    drop_table_if_exists,
    drop_view_if_exists,
    epoch_seconds_between,
    interval_days,
    json_check,
    refresh_matview,
    serial_type,
    text_type,
    timestamp_tz_type,
    to_date,
    typed_null,
    varchar_type,
    with_recursive,
)

__all__ = [
    "Dialect",
    "analyze_table",
    "boolean_type",
    "cast",
    "create_matview",
    "date_minus_days",
    "date_trunc_day",
    "decimal_type",
    "drop_index_if_exists",
    "drop_matview_if_exists",
    "drop_table_if_exists",
    "drop_view_if_exists",
    "epoch_seconds_between",
    "interval_days",
    "json_check",
    "refresh_matview",
    "serial_type",
    "text_type",
    "timestamp_tz_type",
    "to_date",
    "typed_null",
    "varchar_type",
    "with_recursive",
]
