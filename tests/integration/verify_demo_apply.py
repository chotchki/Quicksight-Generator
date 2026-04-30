"""Post-``demo apply`` verifier for the containerized CI job (P.7).

Connects to whichever dialect's local DB the CI job spun up
(``--dialect postgres`` or ``--dialect oracle``) and checks that the
expected per-prefix tables exist + the matviews carry the row counts
the spec_example seed produces (planted scenarios = 1 drift + 1
overdraft + 1 limit-breach + the standing fanout).

Exits 0 on success; exits 1 with a per-row diff on any mismatch.

Run as::

    python tests/integration/verify_demo_apply.py --dialect postgres \\
        --url "postgresql://postgres:pw@localhost:5432/postgres"

    python tests/integration/verify_demo_apply.py --dialect oracle \\
        --url "system/pw@localhost:1521/FREEPDB1"

Designed for the CI job, not as a unit test — needs a live DB and
deliberately doesn't import ``pytest``. Living under ``tests/`` keeps
it close to the rest of the verification surface even though it
doesn't get collected by ``pytest`` (no ``test_*`` prefix).
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable


# Expected row counts from emitting the spec_example seed against the
# canonical date. Deliberately lifted from the live verification we did
# in P.5.b/P.5.c (both PG + Oracle returned identical counts). Future
# scenario plant changes should re-lock these.
EXPECTED_COUNTS = {
    "spec_example_transactions": 16,
    "spec_example_daily_balances": 2,
    "spec_example_drift": 2,
    "spec_example_overdraft": 1,
    "spec_example_limit_breach": 1,
    "spec_example_todays_exceptions": 3,
    "spec_example_inv_pair_rolling_anomalies": 4,
    "spec_example_inv_money_trail_edges": 6,
}


def _connect_pg(url: str) -> tuple[object, Callable[[str], int]]:
    import psycopg2  # type: ignore[import-untyped]
    conn = psycopg2.connect(url)

    def count(table: str) -> int:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]

    return conn, count


def _connect_oracle(url: str) -> tuple[object, Callable[[str], int]]:
    import oracledb  # type: ignore[import-untyped]
    conn = oracledb.connect(url)

    def count(table: str) -> int:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]

    return conn, count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dialect", required=True, choices=["postgres", "oracle"],
    )
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    if args.dialect == "postgres":
        conn, count = _connect_pg(args.url)
    else:
        conn, count = _connect_oracle(args.url)

    failures: list[str] = []
    for table, expected in EXPECTED_COUNTS.items():
        try:
            actual = count(table)
        except Exception as e:
            failures.append(f"{table}: query failed: {e}")
            continue
        marker = "ok" if actual == expected else "FAIL"
        print(f"  [{marker}] {table:50s} {actual:4d} (expected {expected})")
        if actual != expected:
            failures.append(
                f"{table}: got {actual} rows, expected {expected}"
            )

    conn.close()
    if failures:
        print(f"\n{len(failures)} mismatch(es):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\nAll {len(EXPECTED_COUNTS)} table counts match expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
