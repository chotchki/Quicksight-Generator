"""Per-test failure triage manifest for the M.4.1 harness (M.4.1.f).

When a harness assertion fails (M.4.1.d / M.4.1.e), dump everything
the human-side triage needs into one file under
``tests/e2e/failures/<instance>_<test_id>_<timestamp>.txt``:

  - Test identification (test id, parameterized instance, prefix,
    timestamp)
  - The L2 instance's `seed_hash` (proves which seed was running)
  - The planted_manifest from M.4.1.b (so the human knows what
    was supposed to surface)
  - Deployed dashboard ids + embed URLs (so the human can click
    through and confirm)
  - Per-prefix matview row counts (catches "schema applied but seed
    missing" or "seed applied but matviews stale")
  - The exception's str/traceback (the actual failure)

Why a separate module: the file-format + data-collection logic is
unit-testable without spinning up a live harness. The pytest fixture
in `test_harness_end_to_end.py` is a thin wrapper that calls this
module on teardown when the request.node.rep_call indicates failure.

Pattern matches the existing browser-e2e screenshot conventions —
files land under `tests/e2e/failures/` (gitignored if a sibling
.gitignore lists it; create the dir on demand).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quicksight_gen.common.l2 import L2Instance


# Matviews + base tables to row-count for the triage manifest.
# Order matters for output readability — base tables first, then
# `current_*` matviews (proves matview refresh ran), then L1
# invariants (proves planting + matview cascade landed).
_TRIAGE_DB_OBJECTS = (
    # Base tables.
    "transactions",
    "daily_balances",
    # Current* matviews — must be fresh (count == base) for the
    # downstream invariants to read up-to-date data.
    "current_transactions",
    "current_daily_balances",
    # L1 invariant matviews — the "did anything land?" surface.
    "drift",
    "ledger_drift",
    "overdraft",
    "limit_breach",
    "stuck_pending",
    "stuck_unbundled",
    # Dashboard-shape matviews.
    "todays_exceptions",
)


def dump_failure_manifest(
    failure_dir: Path,
    *,
    test_id: str,
    instance: L2Instance,
    planted_manifest: dict[str, list[dict[str, Any]]],
    dashboard_ids: dict[str, str] | None = None,
    embed_urls: dict[str, str] | None = None,
    db_conn: Any | None = None,
    exception_text: str | None = None,
) -> Path:
    """Write a triage manifest to ``failure_dir`` and return its path.

    Filename pattern: ``<instance>_<test_id_safe>_<timestamp>.txt``
    where ``test_id_safe`` is the pytest test id with ``::`` /
    ``[`` / ``]`` replaced by ``_`` (filesystem-safe). Timestamp is
    ISO-8601 UTC with colons stripped.

    All optional inputs (``dashboard_ids``, ``embed_urls``,
    ``db_conn``, ``exception_text``) gracefully degrade — if a
    fixture failed before deploy or before DB seed, those sections
    just print "<not available>" instead of raising.

    Returns the path to the written file.
    """
    failure_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (
        datetime.now(timezone.utc).isoformat().replace(":", "")
    )
    test_id_safe = (
        test_id.replace("::", "_")
        .replace("[", "_")
        .replace("]", "")
        .replace("/", "_")
    )
    out_path = failure_dir / (
        f"{instance.instance}_{test_id_safe}_{timestamp}.txt"
    )

    sections: list[str] = []

    # 1. Header.
    sections.append(_section("Test", [
        f"test_id        : {test_id}",
        f"instance       : {instance.instance}",
        f"timestamp_utc  : {datetime.now(timezone.utc).isoformat()}",
    ]))

    # 2. Seed hash from the YAML.
    seed_hash = instance.seed_hash or "<not locked>"
    sections.append(_section("Seed Hash (YAML)", [seed_hash]))

    # 3. Planted manifest — JSON-pretty.
    sections.append(_section(
        "Planted Manifest",
        [json.dumps(_decimal_safe(planted_manifest), indent=2, default=str)],
    ))

    # 4. Dashboard ids + embed URLs.
    sections.append(_section(
        "Deployed Dashboards",
        _format_kv(dashboard_ids or {"<not available>": ""}),
    ))
    sections.append(_section(
        "Embed URLs (single-use)",
        _format_kv(embed_urls or {"<not available>": ""}),
    ))

    # 5. Matview row counts (best-effort — the conn may be closed
    # already if teardown got that far).
    sections.append(_section(
        "Matview Row Counts",
        _matview_counts(db_conn, prefix=str(instance.instance)),
    ))

    # 6. Exception text.
    sections.append(_section(
        "Exception",
        [exception_text or "<not captured>"],
    ))

    out_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return out_path


def _section(title: str, lines: list[str]) -> str:
    """Format a section block: title underlined with `=`, then body."""
    rule = "=" * max(len(title), 8)
    return f"{title}\n{rule}\n" + "\n".join(lines)


def _format_kv(d: dict[str, str]) -> list[str]:
    """Render a dict as ``key  : value`` lines, key-padded for align."""
    if not d:
        return ["<empty>"]
    width = max(len(k) for k in d)
    return [f"{k:<{width}}  : {v}" for k, v in d.items()]


def _matview_counts(db_conn: Any | None, *, prefix: str) -> list[str]:
    """Best-effort SELECT COUNT(*) per <prefix>_<obj>; missing
    objects render as ``<missing>``, query errors as ``<error: ...>``."""
    if db_conn is None:
        return ["<DB connection not available>"]
    lines: list[str] = []
    width = max(len(name) for name in _TRIAGE_DB_OBJECTS)
    for obj in _TRIAGE_DB_OBJECTS:
        full = f"{prefix}_{obj}"
        try:
            with db_conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {full}")
                row = cur.fetchone()
                count = row[0] if row else 0
            lines.append(f"{obj:<{width}}  : {count}")
        except Exception as exc:  # noqa: BLE001 — best-effort
            # Roll back the failed query before the next iteration —
            # otherwise psycopg2 leaves the txn in an aborted state
            # and every subsequent query inside the same conn errors.
            try:
                db_conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            short = type(exc).__name__
            lines.append(f"{obj:<{width}}  : <error: {short}>")
    return lines


def _decimal_safe(obj: Any) -> Any:
    """Coerce Decimal values to str for JSON serialization. Recursive."""
    from decimal import Decimal
    if isinstance(obj, dict):
        return {k: _decimal_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_safe(x) for x in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    return obj
