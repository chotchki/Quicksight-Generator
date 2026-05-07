"""Y.1.o — Probe QS dataset-parameter substitution behavior at runtime.

Three QS bug classes in a row (X.1.b sample-values 404, K.4.7 URL-as-state,
Y.1.k cascade) only manifest in deployed state where pg_stat_statements
with QS provenance comments is the only visibility into what SQL QS
actually issued. Manual screenshot debugging burned hours; this script
turns the diagnostic into something repeatable.

Two capabilities:

1. ``inspect`` — pull the deployed dataset's CustomSQL via
   ``describe_data_set`` and print it alongside its DatasetParameters.
   Confirms what shape made it past the boto3 emit (placeholder syntax,
   parameter ValueType, default values).

2. ``snapshot`` / ``diff`` — capture pg_stat_statements rows filtered to
   queries carrying a specific QS provenance comment substring (e.g.
   ``l2ft-sheet-rails`` or a visualId). Two snapshots taken around a
   controlled user action let the diff show calls-delta + rows-returned
   per query — answering "did QS re-fire" and "did the WHERE narrow the
   row set".

Usage::

    # Inspect deployed L2FT postings dataset (post-deploy SQL + params)
    .venv/bin/python scripts/qs_substitution_probe.py inspect \\
        -c run/config.postgres.yaml \\
        --dataset qs-gen-postgres-sasquatch_pr-l2ft-postings-dataset

    # Snapshot before user action (saves to /tmp/qs-probe-baseline.json)
    .venv/bin/python scripts/qs_substitution_probe.py snapshot \\
        -c run/config.postgres.yaml \\
        --filter l2ft-sheet-rails \\
        --label baseline

    # ... user does action in browser ...

    # Snapshot after, then diff
    .venv/bin/python scripts/qs_substitution_probe.py snapshot \\
        -c run/config.postgres.yaml \\
        --filter l2ft-sheet-rails \\
        --label post-action

    .venv/bin/python scripts/qs_substitution_probe.py diff \\
        baseline post-action

Filtering: pg_stat_statements deduplicates on the normalized query
shape, so two different bind values look identical at the rows level.
The diff shows calls-delta + rows-delta which tells the meaningful
story even with normalization.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quicksight_gen.common.config import load_config  # noqa: E402
from quicksight_gen.common.db import connect_demo_db  # noqa: E402
from quicksight_gen.common.sql import Dialect  # noqa: E402

_SNAPSHOT_DIR = Path("/tmp/qs-probe")


@dataclass
class QueryStat:
    queryid: int
    calls: int
    total_ms: float
    mean_ms: float
    rows: int
    query_text: str


def _snapshot_pg(
    conn: Any, filter_substring: str, top: int = 200,
) -> list[QueryStat]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT queryid, calls,
                   ROUND(total_exec_time::numeric, 1)::float AS total_ms,
                   ROUND(mean_exec_time::numeric, 2)::float  AS mean_ms,
                   rows,
                   LEFT(REGEXP_REPLACE(query, '\\s+', ' ', 'g'), 1200) AS qtext
            FROM pg_stat_statements
            WHERE query ILIKE %s
            ORDER BY total_exec_time DESC
            LIMIT %s
            """,
            (f"%{filter_substring}%", top),
        )
        out: list[QueryStat] = []
        for queryid, calls, total_ms, mean_ms, n_rows, qtext in cur.fetchall():
            out.append(QueryStat(
                queryid=int(queryid),
                calls=int(calls),
                total_ms=float(total_ms),
                mean_ms=float(mean_ms),
                rows=int(n_rows),
                query_text=qtext or "",
            ))
        return out
    finally:
        cur.close()


def _print_analysis_params(client: Any, account_id: str, analysis_id: str) -> None:
    resp = client.describe_analysis_definition(
        AwsAccountId=account_id, AnalysisId=analysis_id,
    )
    defn = resp["Definition"]
    decls = defn.get("ParameterDeclarations", [])
    print(f"=== Analysis: {analysis_id}")
    print(f"    {len(decls)} parameter declaration(s)")
    print()
    for d in decls:
        for kind, body in d.items():
            name = body.get("Name", "?")
            value_type = body.get("ParameterValueType", "?")
            default = body.get("DefaultValues", {})
            mapped = body.get("MappedDataSetParameters") or []
            print(f"  {name} ({kind}) ValueType={value_type}")
            print(f"    default: {default}")
            for m in mapped:
                print(
                    f"    mapped → DataSetIdentifier="
                    f"{m.get('DataSetIdentifier')!r} "
                    f"DataSetParameterName={m.get('DataSetParameterName')!r}"
                )


def cmd_inspect(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    client = boto3.client("quicksight", region_name=cfg.aws_region)
    if args.analysis:
        _print_analysis_params(client, cfg.aws_account_id, args.analysis)
        return 0
    resp = client.describe_data_set(
        AwsAccountId=cfg.aws_account_id, DataSetId=args.dataset,
    )
    ds = resp["DataSet"]
    print(f"=== Dataset: {ds['DataSetId']}")
    print(f"    Name: {ds.get('Name', '?')}")
    print(f"    LastUpdated: {ds.get('LastUpdatedTime', '?')}")
    print()

    physical_table_map = ds.get("PhysicalTableMap", {})
    for pt_id, pt in physical_table_map.items():
        custom_sql = pt.get("CustomSql", {})
        sql_text = custom_sql.get("SqlQuery", "")
        if sql_text:
            print(f"--- CustomSQL ({pt_id}) ---")
            print(sql_text)
            print()

    params = ds.get("DatasetParameters", [])
    if params:
        print("--- DatasetParameters ---")
        for p in params:
            for kind, body in p.items():
                print(
                    f"    {body.get('Name')}: kind={kind} "
                    f"ValueType={body.get('ValueType')} "
                    f"DefaultValues={body.get('DefaultValues')}"
                )
        print()
    else:
        print("    (no DataSetParameters declared)")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if cfg.dialect is not Dialect.POSTGRES:
        print(
            f"[snapshot] only postgres supported (got {cfg.dialect}); "
            "Oracle would need v$sqlstats path",
            file=sys.stderr,
        )
        return 1
    conn = connect_demo_db(cfg)
    try:
        rows = _snapshot_pg(conn, args.filter, top=args.top)
    finally:
        conn.close()
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SNAPSHOT_DIR / f"{args.label}.json"
    path.write_text(json.dumps([asdict(r) for r in rows], indent=2))
    print(f"=== Snapshot: {len(rows)} rows → {path}")
    for r in rows[:10]:
        snippet = r.query_text[:140].replace("\n", " ")
        print(
            f"    queryid={r.queryid} calls={r.calls} rows={r.rows} "
            f"mean={r.mean_ms}ms  {snippet}…"
        )
    if len(rows) > 10:
        print(f"    … ({len(rows) - 10} more in {path})")
    return 0


def _load_snapshot(label: str) -> list[QueryStat]:
    path = _SNAPSHOT_DIR / f"{label}.json"
    raw = json.loads(path.read_text())
    return [QueryStat(**r) for r in raw]


def cmd_diff(args: argparse.Namespace) -> int:
    before = {r.queryid: r for r in _load_snapshot(args.before)}
    after = {r.queryid: r for r in _load_snapshot(args.after)}

    new_ids = sorted(after.keys() - before.keys())
    bumped_ids = sorted(
        qid for qid in after.keys() & before.keys()
        if after[qid].calls > before[qid].calls
    )
    quiet_ids = sorted(after.keys() & before.keys()) if args.show_quiet else []

    print(f"=== Diff: {args.before} → {args.after}")
    print(
        f"    {len(new_ids)} NEW query plan(s), "
        f"{len(bumped_ids)} bumped, "
        f"{len(after.keys() & before.keys()) - len(bumped_ids)} unchanged"
    )
    print()

    for label, ids, get_delta in (
        ("NEW", new_ids, lambda qid: (after[qid].calls, after[qid].rows)),
        (
            "BUMPED",
            bumped_ids,
            lambda qid: (
                after[qid].calls - before[qid].calls,
                after[qid].rows - before[qid].rows,
            ),
        ),
    ):
        if not ids:
            continue
        print(f"--- {label} ---")
        for qid in ids:
            row = after[qid]
            d_calls, d_rows = get_delta(qid)
            snippet = row.query_text[:200].replace("\n", " ")
            print(
                f"  queryid={qid} Δcalls={d_calls} Δrows={d_rows} "
                f"mean={row.mean_ms}ms"
            )
            print(f"    {snippet}…")
            print()

    if quiet_ids:
        print(f"--- UNCHANGED ({len(quiet_ids)}) ---")
        for qid in quiet_ids:
            row = after[qid]
            print(f"  queryid={qid} calls={row.calls} rows={row.rows}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ins = sub.add_parser(
        "inspect", help="Describe deployed dataset (CustomSQL + params).",
    )
    p_ins.add_argument("-c", "--config", required=True, type=Path)
    p_ins.add_argument("--dataset", help="DataSetId to inspect.")
    p_ins.add_argument(
        "--analysis",
        help="AnalysisId to inspect (parameter declarations + mappings).",
    )
    p_ins.set_defaults(func=cmd_inspect)

    p_snap = sub.add_parser(
        "snapshot", help="Snapshot pg_stat_statements rows by filter.",
    )
    p_snap.add_argument("-c", "--config", required=True, type=Path)
    p_snap.add_argument(
        "--filter",
        required=True,
        help="ILIKE substring match against query text (e.g. sheetId).",
    )
    p_snap.add_argument(
        "--label", required=True, help="Snapshot label (becomes filename).",
    )
    p_snap.add_argument("--top", type=int, default=200)
    p_snap.set_defaults(func=cmd_snapshot)

    p_diff = sub.add_parser(
        "diff", help="Diff two snapshots — calls + rows delta per query.",
    )
    p_diff.add_argument("before")
    p_diff.add_argument("after")
    p_diff.add_argument(
        "--show-quiet",
        action="store_true",
        help="Also list queries that didn't change (default: hidden).",
    )
    p_diff.set_defaults(func=cmd_diff)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
