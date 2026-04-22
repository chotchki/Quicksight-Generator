"""Demo data generator for the Investigation app.

K.4.2 ships an empty stub: writes no rows into the shared `transactions`
+ `daily_balances` base tables. K.4.6 plants the scenario data exercising
each sheet (fanout cluster, 2σ-anomalous window pair, 4-hop transfer
chain).

Investigation reads from the same base tables as PR/AR — there is no
investigation-specific schema. Per-app demo data is additive.
"""

from __future__ import annotations

from datetime import date


def generate_demo_sql(anchor_date: date | None = None) -> str:
    """Return SQL for investigation-specific seed data.

    Empty for the K.4.2 skeleton. K.4.6 plants the scenarios that drive
    the K.4.3 / K.4.4 / K.4.5 sheets.
    """
    return "-- Investigation: no demo data yet (K.4.6 plants scenarios)\n"
