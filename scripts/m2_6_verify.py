"""M.2.6 — deploy v6 schema + plant seed + verify L1 invariant views.

End-to-end verification that the M.1a.7 + M.2.1 + M.2.2 stack works
against real Aurora. Reads ``run/config.yaml``, warms the cluster
(per F12 Aurora cold-start lesson), applies the v6 schema (drop +
create), plants the M.2.2 default scenario, queries each L1 invariant
view, and asserts each planted scenario surfaces a row.

Usage:

    .venv/bin/python scripts/m2_6_verify.py
    .venv/bin/python scripts/m2_6_verify.py --config path/to/config.yaml
    .venv/bin/python scripts/m2_6_verify.py --skip-warmup
    .venv/bin/python scripts/m2_6_verify.py --schema-only
    .venv/bin/python scripts/m2_6_verify.py --no-deploy   # skip schema+seed

Exit codes:
- 0 — all assertions passed
- 1 — at least one scenario didn't surface (or any other failure)
- 2 — config / connection error before assertions could run

The thin shell wrapper ``m2_6_verify.sh`` at repo root mirrors the
``run_e2e.sh`` ergonomics (env-var defaults, --skip-* flags).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Make sure tests/ is on sys.path so we can import the seed generator
# (it lives there per M.2.2 — production module location decided at
# M.2.10's iteration gate).
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))


def _connect(database_url: str, *, timeout_s: int = 60):
    """Open a psycopg2 connection with a generous cold-start timeout."""
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError:
        print(
            "FATAL: psycopg2 not installed. "
            "Install with `.venv/bin/pip install 'quicksight-gen[demo]'`.",
            file=sys.stderr,
        )
        sys.exit(2)
    return psycopg2.connect(database_url, connect_timeout=timeout_s)


def _warm_aurora(conn) -> None:
    """First SELECT after cold-start can take 20-30s. Pay it once
    upfront with a trivial query so subsequent statements run hot."""
    print("→ Warming Aurora (SELECT 1)...", end=" ", flush=True)
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchall()
    print(f"OK ({time.time() - t0:.1f}s)")


def _apply_schema(conn, instance) -> None:
    """Apply the v6 schema (drop + create base tables + Current* +
    L1 invariant views). Idempotent."""
    from quicksight_gen.common.l2 import emit_schema
    sql = emit_schema(instance)
    print(f"→ Applying schema ({len(sql):,} chars)...", end=" ", flush=True)
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"OK ({time.time() - t0:.1f}s)")


def _apply_seed(conn, instance, today_ref) -> None:
    """Apply the M.2.2 default scenario seed."""
    from quicksight_gen.common.l2.seed import emit_seed
    from tests.l2.sasquatch_ar_seed import default_ar_scenario
    sql = emit_seed(instance, default_ar_scenario(today=today_ref))
    print(
        f"→ Planting seed (today={today_ref.isoformat()}, "
        f"{len(sql):,} chars)...",
        end=" ", flush=True,
    )
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"OK ({time.time() - t0:.1f}s)")


def _refresh_matviews(conn, instance) -> None:
    """M.1a.9 — REFRESH every matview in dependency order.

    Required after every base-table batch insert; without it the L1
    invariant views (matviews) return stale data. PostgreSQL refuses
    to refresh a downstream matview before its upstream is fresh, so
    `refresh_matviews_sql` emits the right order.
    """
    from quicksight_gen.common.l2 import refresh_matviews_sql

    statements = [
        s.strip() for s in refresh_matviews_sql(instance).split(";")
        if s.strip()
    ]
    print(f"→ Refreshing {len(statements)} matviews...", end=" ", flush=True)
    t0 = time.time()
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()
    print(f"OK ({time.time() - t0:.1f}s)")


def _query_view(conn, sql: str) -> list[tuple[Any, ...]]:
    """Run a verification SELECT; return rows."""
    with conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def _verify_drift(conn, prefix: str) -> bool:
    """The drift plant is on cust-900-0001-bigfoot-brews; the view should
    surface that row with drift = +$75."""
    print("→ Verifying drift scenario (bigfoot-brews +$75)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT account_id, drift
        FROM {prefix}_drift
        WHERE account_id = 'cust-900-0001-bigfoot-brews'
    """)
    if not rows:
        print("FAIL — no row in <prefix>_drift for bigfoot-brews")
        return False
    if len(rows) > 1:
        print(f"FAIL — expected 1 row, got {len(rows)}: {rows!r}")
        return False
    drift = rows[0][1]
    if drift != 75:
        print(f"FAIL — expected drift=75, got {drift!r}")
        return False
    print(f"OK (drift={drift})")
    return True


def _verify_overdraft(conn, prefix: str) -> bool:
    """Sasquatch-sips overdraft plant: stored balance = -$1500."""
    print("→ Verifying overdraft scenario (sasquatch-sips -$1500)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT account_id, stored_balance
        FROM {prefix}_overdraft
        WHERE account_id = 'cust-900-0002-sasquatch-sips'
    """)
    if not rows:
        print("FAIL — no row in <prefix>_overdraft for sasquatch-sips")
        return False
    balance = rows[0][1]
    if balance >= 0:
        print(f"FAIL — expected negative balance, got {balance!r}")
        return False
    print(f"OK (stored_balance={balance})")
    return True


def _verify_limit_breach(conn, prefix: str) -> bool:
    """Big-meadow-dairy limit breach: $22k wire vs $15k cap."""
    print("→ Verifying limit-breach scenario (big-meadow-dairy wire $22k > $15k)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT account_id, transfer_type, outbound_total, cap
        FROM {prefix}_limit_breach
        WHERE account_id = 'cust-700-0001-big-meadow-dairy'
    """)
    if not rows:
        print("FAIL — no row in <prefix>_limit_breach for big-meadow-dairy")
        return False
    _, ttype, outbound, cap = rows[0]
    if ttype != "wire":
        print(f"FAIL — expected transfer_type='wire', got {ttype!r}")
        return False
    if outbound <= cap:
        print(f"FAIL — expected outbound > cap, got {outbound} <= {cap}")
        return False
    print(f"OK (outbound={outbound} > cap={cap})")
    return True


def _verify_stuck_pending(conn, prefix: str) -> bool:
    """Bigfoot-brews stuck Pending: ACH leg 2 days old vs PT24H cap."""
    print("→ Verifying stuck-pending scenario (bigfoot-brews ACH > 24h)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT account_id, rail_name, max_pending_age_seconds, age_seconds
        FROM {prefix}_stuck_pending
        WHERE account_id = 'cust-900-0001-bigfoot-brews'
    """)
    if not rows:
        print("FAIL — no row in <prefix>_stuck_pending for bigfoot-brews")
        return False
    _, rail, cap_s, age_s = rows[0]
    if age_s <= cap_s:
        print(f"FAIL — expected age > cap, got age={age_s}s <= cap={cap_s}s")
        return False
    print(f"OK (rail={rail} age={age_s:.0f}s > cap={cap_s}s)")
    return True


def _verify_stuck_unbundled(conn, prefix: str) -> bool:
    """Sasquatch-sips stuck Unbundled: fee accrual 35 days old vs P31D cap."""
    print("→ Verifying stuck-unbundled scenario (sasquatch-sips fee > 31d)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT account_id, rail_name, max_unbundled_age_seconds, age_seconds
        FROM {prefix}_stuck_unbundled
        WHERE account_id = 'cust-900-0002-sasquatch-sips'
    """)
    if not rows:
        print("FAIL — no row in <prefix>_stuck_unbundled for sasquatch-sips")
        return False
    _, rail, cap_s, age_s = rows[0]
    if age_s <= cap_s:
        print(f"FAIL — expected age > cap, got age={age_s}s <= cap={cap_s}s")
        return False
    print(f"OK (rail={rail} age={age_s:.0f}s > cap={cap_s}s)")
    return True


def _verify_supersession(conn, prefix: str) -> bool:
    """Bigfoot-brews TechnicalCorrection: 2 entries on the same logical id."""
    print("→ Verifying supersession scenario (TechnicalCorrection)...", end=" ", flush=True)
    rows = _query_view(conn, f"""
        SELECT id, COUNT(*) AS entry_count
        FROM {prefix}_transactions
        WHERE id LIKE 'tx-supersedes-%'
        GROUP BY id
        HAVING COUNT(*) > 1
    """)
    if not rows:
        print("FAIL — no logical key with multiple entries planted")
        return False
    txn_id, count = rows[0]
    print(f"OK ({txn_id} has {count} entries)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="M.2.6 verification: deploy v6 schema + verify L1 views",
    )
    parser.add_argument(
        "--config", type=Path,
        default=_REPO_ROOT / "run" / "config.yaml",
        help="path to config YAML (default: run/config.yaml)",
    )
    parser.add_argument(
        "--skip-warmup", action="store_true",
        help="skip the Aurora cold-start warmup query",
    )
    parser.add_argument(
        "--schema-only", action="store_true",
        help="apply schema; skip seed + verification",
    )
    parser.add_argument(
        "--no-deploy", action="store_true",
        help="skip schema + seed; just run verification queries",
    )
    args = parser.parse_args()

    # Late imports so --help works even if the venv isn't fully set up.
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.common.config import load_config

    cfg = load_config(str(args.config))
    if not cfg.demo_database_url:
        print(
            f"FATAL: {args.config} has no demo_database_url — set one or "
            f"add a different config.",
            file=sys.stderr,
        )
        return 2

    where = cfg.demo_database_url.split("@")[-1]
    print(f"Connecting to {where}")
    conn = _connect(cfg.demo_database_url)
    try:
        instance = default_l2_instance()
        prefix = instance.instance
        print(f"L2 instance: {prefix} ({len(instance.accounts)} accounts, "
              f"{len(instance.rails)} rails, {len(instance.limit_schedules)} limits)")

        if not args.skip_warmup:
            _warm_aurora(conn)

        today_ref = datetime.now(tz=timezone.utc).date()

        if not args.no_deploy:
            _apply_schema(conn, instance)
            if args.schema_only:
                print()
                print("Schema-only run complete. Skipping seed + verification.")
                return 0
            _apply_seed(conn, instance, today_ref)
            _refresh_matviews(conn, instance)

        print()
        print("=== Verification ===")
        results = [
            _verify_drift(conn, prefix),
            _verify_overdraft(conn, prefix),
            _verify_limit_breach(conn, prefix),
            _verify_stuck_pending(conn, prefix),
            _verify_stuck_unbundled(conn, prefix),
            _verify_supersession(conn, prefix),
        ]
        print()
        passed = sum(results)
        total = len(results)
        if passed == total:
            print(f"PASS — {passed}/{total} scenarios surfaced as expected.")
            return 0
        print(f"FAIL — {passed}/{total} scenarios surfaced.")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
