"""``quicksight-gen audit`` — PDF reconciliation report.

Three operations:

  apply  — emit Markdown source for the report (default), or
           ``--execute`` to write a PDF via reportlab.
  clean  — list the report file that would be removed (default), or
           ``--execute`` to delete it.
  test   — pytest the audit module + pyright.

The report is a regulator-ready PDF generated **directly from the
database**, querying the per-prefix L1 invariant matviews + base
tables. Same emit-vs-execute pattern as the other artifact groups —
no ``--execute`` means the integrator can review the rendered
Markdown / page outline before committing to a real PDF write.

Phase U.2 ships the **executive summary page** on top of the U.1
cover: per-period totals (transaction count, transfer count, dollar
volume gross/net) + L1 invariant exception counts (drift, ledger
drift, overdraft, limit breach, stuck pending, stuck unbundled,
supersession). Real numbers when ``demo_database_url`` is configured;
graceful "—" placeholders + a notice when it isn't, so the layout
stays previewable without a live DB.

Page footer carries a provenance-fingerprint placeholder (real
fingerprint lands in U.7). Per-invariant violation tables, the
per-account-day Daily Statement walk, and the sign-off block land
in U.3+.

Period default: ``yesterday + last 7 days`` (a 7-day window ending
yesterday). Override with ``--from YYYY-MM-DD`` / ``--to YYYY-MM-DD``.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import click

from quicksight_gen.cli._helpers import (
    config_option,
    execute_option,
    l2_instance_option,
    resolve_l2_for_demo,
)


@click.group()
def audit() -> None:
    """Per-instance PDF reconciliation report (cover, summary, exceptions)."""


def _period_option_from():  # type: ignore[no-untyped-def]
    return click.option(
        "--from", "period_from",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period start (YYYY-MM-DD, inclusive). Default: today − 7 days "
            "(start of the 7-day window ending yesterday)."
        ),
    )


def _period_option_to():  # type: ignore[no-untyped-def]
    return click.option(
        "--to", "period_to",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period end (YYYY-MM-DD, inclusive). Default: yesterday "
            "(today − 1)."
        ),
    )


def _resolve_period(
    period_from: datetime | None, period_to: datetime | None,
    *, today: date | None = None,
) -> tuple[date, date]:
    """Resolve the report period.

    Default: a 7-day window ending yesterday — i.e. ``[today − 7,
    today − 1]`` inclusive. Both endpoints are inclusive dates.
    Override either endpoint via ``--from`` / ``--to``.
    """
    anchor = today or date.today()
    end = period_to.date() if period_to is not None else anchor - timedelta(days=1)
    start = period_from.date() if period_from is not None else anchor - timedelta(days=7)
    if start > end:
        raise click.UsageError(
            f"--from ({start.isoformat()}) must not be after --to "
            f"({end.isoformat()})."
        )
    return start, end


def _institution_name(instance) -> str:  # type: ignore[no-untyped-def]
    """Pull the institution display name from the L2 persona block.

    Falls back to the L2 instance identifier when no persona block is
    declared — the report still renders cleanly against any L2 YAML.
    """
    persona = getattr(instance, "persona", None)
    if persona is not None and persona.institution:
        return str(persona.institution[0])
    return str(instance.instance)


def _singleton_account_ids(instance) -> set[str]:  # type: ignore[no-untyped-def]
    """IDs of L2 ``Account`` singletons (the N-N "shared" accounts).

    Used by the U.3 per-invariant tables to split rows: account_ids
    in this set get rendered as per-account aggregate summaries (a
    GL clearing or concentration account that violates daily would
    otherwise balloon the report); account_ids NOT in this set
    are template-materialized (1-1, customer-owned) and get per-row
    detail.
    """
    return {str(a.id) for a in instance.accounts}


# -- Executive summary (U.2) --------------------------------------------------


@dataclass(frozen=True)
class ExecSummary:
    """Totals rendered on the executive summary page.

    All counts are inclusive of both period endpoints. Dollar volume
    follows the dashboards' per-transfer aggregation convention
    (``MAX(ABS(amount_money))`` for gross, ``SUM(amount_money)`` for
    net) so a multi-leg transfer counts once, not once per leg.
    """
    transactions_count: int
    transfers_count: int
    dollar_volume_gross: Decimal
    dollar_volume_net: Decimal
    # Ordered (label, count) pairs — preserves render order.
    exception_counts: list[tuple[str, int]]


# (display label, matview suffix, date column for period filter — None
# means "current-state" matview: count all rows regardless of posting
# date, per the L1 dashboard's stuck_* convention).
_EXCEPTION_INVARIANTS: list[tuple[str, str, str | None]] = [
    ("Drift", "drift", "business_day_start"),
    ("Ledger drift", "ledger_drift", "business_day_start"),
    ("Overdraft", "overdraft", "business_day_start"),
    ("Limit breach", "limit_breach", "business_day"),
    ("Stuck pending", "stuck_pending", None),
    ("Stuck unbundled", "stuck_unbundled", None),
]


def _query_executive_summary(
    cfg, instance, period: tuple[date, date],  # type: ignore[no-untyped-def]
) -> ExecSummary | None:
    """Aggregate the executive-summary totals against the demo DB.

    Returns None when ``cfg.demo_database_url`` is unset — the
    renderers fall back to "—" placeholders so the layout stays
    previewable without a live connection.

    Date literals use ``DATE 'YYYY-MM-DD'`` which both Postgres and
    Oracle accept; the inclusive end is enforced via ``< end + 1
    day`` so end-of-period TIMESTAMPs are caught.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    start, end = period
    start_lit = f"DATE '{start.isoformat()}'"
    end_excl_lit = f"DATE '{(end + timedelta(days=1)).isoformat()}'"

    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()

        cur.execute(
            f"SELECT COUNT(*),"
            f" COUNT(DISTINCT transfer_id)"
            f" FROM {prefix}_transactions"
            f" WHERE status = 'Posted'"
            f"   AND posting >= {start_lit}"
            f"   AND posting < {end_excl_lit}"
        )
        leg_count, transfer_count = cur.fetchone()

        cur.execute(
            f"SELECT COALESCE(SUM(transfer_gross), 0),"
            f" COALESCE(SUM(transfer_net), 0)"
            f" FROM ("
            f"   SELECT MAX(ABS(amount_money)) AS transfer_gross,"
            f"          SUM(amount_money) AS transfer_net"
            f"   FROM {prefix}_transactions"
            f"   WHERE status = 'Posted'"
            f"     AND posting >= {start_lit}"
            f"     AND posting < {end_excl_lit}"
            f"   GROUP BY transfer_id"
            f" ) per_transfer"
        )
        gross, net = cur.fetchone()

        exception_counts: list[tuple[str, int]] = []
        for label, suffix, date_col in _EXCEPTION_INVARIANTS:
            if date_col is None:
                # Current-state matview (stuck_*): count all rows
                # regardless of posting date. Mirrors the L1 dashboard
                # which shows all currently-stuck without date filter.
                sql = f"SELECT COUNT(*) FROM {prefix}_{suffix}"
            else:
                sql = (
                    f"SELECT COUNT(*) FROM {prefix}_{suffix}"
                    f" WHERE {date_col} >= {start_lit}"
                    f"   AND {date_col} < {end_excl_lit}"
                )
            cur.execute(sql)
            (count,) = cur.fetchone()
            # Mark current-state labels with "*" so the renderer's
            # footnote attaches correctly.
            display_label = f"{label}*" if date_col is None else label
            exception_counts.append((display_label, int(count or 0)))

        # Supersession: count distinct logical transactions whose any
        # entry posts in the period AND have >1 entries (i.e. were
        # superseded). Mirrors the L1 dashboard's
        # build_supersession_transactions_dataset window-function read.
        cur.execute(
            f"SELECT COUNT(*) FROM ("
            f"   SELECT id FROM {prefix}_transactions"
            f"   WHERE posting >= {start_lit}"
            f"     AND posting < {end_excl_lit}"
            f"   GROUP BY id"
            f"   HAVING COUNT(*) > 1"
            f" ) superseded"
        )
        (superseded_count,) = cur.fetchone()
        exception_counts.append(("Supersession", int(superseded_count or 0)))

        return ExecSummary(
            transactions_count=int(leg_count or 0),
            transfers_count=int(transfer_count or 0),
            dollar_volume_gross=Decimal(gross or 0),
            dollar_volume_net=Decimal(net or 0),
            exception_counts=exception_counts,
        )
    finally:
        conn.close()


# -- Drift violations (U.3.a) -------------------------------------------------


@dataclass(frozen=True)
class DriftViolation:
    """One row of the ``<prefix>_drift`` matview, audit-shaped.

    ``business_day`` carries ``business_day_end`` from the matview —
    the day the discrepancy was observed at end-of-day. Mirrors the
    L1 dashboard's "Leaf Account Drift" table for column choice.
    """
    account_id: str
    account_name: str
    account_role: str
    account_parent_role: str
    business_day: date
    stored_balance: Decimal
    computed_balance: Decimal
    drift: Decimal


def _query_drift_violations(
    cfg, instance, period: tuple[date, date],  # type: ignore[no-untyped-def]
) -> list[DriftViolation] | None:
    """Pull drift rows whose business day falls in the period.

    Returns None when no DB is configured (renders the placeholder
    section). An empty list means the DB is healthy and zero drifts
    fired in the period — that's a good-news render, not a missing
    section.

    Sort: most-recent day first, then biggest absolute drift, then
    account_id for stable order. Auditor wants to see the freshest
    + biggest discrepancies on top.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    start, end = period
    start_lit = f"DATE '{start.isoformat()}'"
    end_excl_lit = f"DATE '{(end + timedelta(days=1)).isoformat()}'"

    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT account_id, account_name, account_role,"
            f"       account_parent_role, business_day_end,"
            f"       stored_balance, computed_balance, drift"
            f"  FROM {prefix}_drift"
            f" WHERE business_day_start >= {start_lit}"
            f"   AND business_day_start < {end_excl_lit}"
            f" ORDER BY business_day_end DESC, ABS(drift) DESC, account_id"
        )
        rows = cur.fetchall()
        return [
            DriftViolation(
                account_id=str(r[0]),
                account_name=str(r[1] or ""),
                account_role=str(r[2] or ""),
                account_parent_role=str(r[3] or ""),
                business_day=(
                    r[4].date() if hasattr(r[4], "date") else r[4]
                ),
                stored_balance=Decimal(r[5] or 0),
                computed_balance=Decimal(r[6] or 0),
                drift=Decimal(r[7] or 0),
            )
            for r in rows
        ]
    finally:
        conn.close()


# -- Overdraft violations (U.3.b) ---------------------------------------------


@dataclass(frozen=True)
class OverdraftViolation:
    """One row of the ``<prefix>_overdraft`` matview, audit-shaped.

    The matview only stores rows where stored_balance < 0, so the
    violation IS the negative balance — no computed/drift columns
    needed (the OVERDRAFT_CONTRACT comment in datasets.py says the
    same).
    """
    account_id: str
    account_name: str
    account_role: str
    account_parent_role: str  # empty string when account has no parent
    business_day: date
    stored_balance: Decimal


def _query_overdraft_violations(
    cfg, instance, period: tuple[date, date],  # type: ignore[no-untyped-def]
) -> list[OverdraftViolation] | None:
    """Pull overdraft rows whose business day falls in the period.

    Returns None when no DB is configured. Empty list = DB healthy
    with zero overdrafts (good-news render).

    Sort: most-recent day first, then biggest absolute balance
    (i.e. deepest underwater), then account_id.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    start, end = period
    start_lit = f"DATE '{start.isoformat()}'"
    end_excl_lit = f"DATE '{(end + timedelta(days=1)).isoformat()}'"

    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT account_id, account_name, account_role,"
            f"       account_parent_role, business_day_end,"
            f"       stored_balance"
            f"  FROM {prefix}_overdraft"
            f" WHERE business_day_start >= {start_lit}"
            f"   AND business_day_start < {end_excl_lit}"
            f" ORDER BY business_day_end DESC,"
            f"          ABS(stored_balance) DESC, account_id"
        )
        return [
            OverdraftViolation(
                account_id=str(r[0]),
                account_name=str(r[1] or ""),
                account_role=str(r[2] or ""),
                account_parent_role=str(r[3] or ""),
                business_day=(
                    r[4].date() if hasattr(r[4], "date") else r[4]
                ),
                stored_balance=Decimal(r[5] or 0),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


@dataclass(frozen=True)
class OverdraftChildGroupSummary:
    """Per parent-role roll-up of overdrawn child (template) accounts.

    Children share a parent role in the L2 hierarchy. Routine
    customer-account overdrafts roll up into one row per parent role
    showing distinct-children-negative + summed peak-negative — keeps
    the audit page skimmable while preserving total dollar exposure.
    A specific child's per-day detail is recoverable from the
    underlying matview if the auditor wants to drill in.
    """
    parent_role: str
    distinct_children_negative: int
    total_peak_negative: Decimal


def _split_overdraft_by_account_class(
    rows: list[OverdraftViolation],
    singleton_ids: set[str],
) -> tuple[list[OverdraftViolation], list[OverdraftChildGroupSummary]]:
    """Bucket rows into (parent per-row detail, child rolled up by parent role).

    Parents (L2 ``Account`` singletons): every occurrence emits a
    detail row — a parent itself going negative is a systemic issue
    each instance of which is independently worth surfacing.

    Children (template-materialized): grouped by ``account_parent_role``
    so each parent role gets one summary row carrying how many
    distinct children went negative in the period and the sum of
    each child's peak negative balance.
    """
    parent_rows: list[OverdraftViolation] = []
    by_parent: dict[str, dict[str, list[OverdraftViolation]]] = {}
    for r in rows:
        if r.account_id in singleton_ids:
            parent_rows.append(r)
        else:
            key = r.account_parent_role or "(no parent)"
            by_parent.setdefault(key, {}).setdefault(
                r.account_id, [],
            ).append(r)
    child_summaries = sorted(
        (
            OverdraftChildGroupSummary(
                parent_role=parent_role,
                distinct_children_negative=len(children),
                total_peak_negative=sum(
                    (
                        min(r.stored_balance for r in child_rows)
                        for child_rows in children.values()
                    ),
                    start=Decimal(0),
                ),
            )
            for parent_role, children in by_parent.items()
        ),
        # Most-negative total first (worst exposure on top).
        key=lambda s: (s.total_peak_negative, s.parent_role),
    )
    return parent_rows, child_summaries


# -- Limit breach violations (U.3.c) ------------------------------------------


@dataclass(frozen=True)
class LimitBreachViolation:
    """One row of the ``<prefix>_limit_breach`` matview, audit-shaped.

    Each row is one (account, day, transfer_type) cell where the
    cumulative outbound debit total exceeded the L2-configured cap.
    Magnitude = ``outbound_total - cap`` (always positive).
    """
    account_id: str
    account_name: str
    account_role: str
    account_parent_role: str
    business_day: date
    transfer_type: str
    outbound_total: Decimal
    cap: Decimal

    @property
    def overshoot(self) -> Decimal:
        return self.outbound_total - self.cap


def _query_limit_breach_violations(
    cfg, instance, period: tuple[date, date],  # type: ignore[no-untyped-def]
) -> list[LimitBreachViolation] | None:
    """Pull limit_breach rows whose business day falls in the period.

    Sort: most-recent day first, then biggest overshoot, then
    account_id — auditor sees the freshest + biggest cap-busts first.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    start, end = period
    start_lit = f"DATE '{start.isoformat()}'"
    end_excl_lit = f"DATE '{(end + timedelta(days=1)).isoformat()}'"

    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT account_id, account_name, account_role,"
            f"       account_parent_role, business_day,"
            f"       transfer_type, outbound_total, cap"
            f"  FROM {prefix}_limit_breach"
            f" WHERE business_day >= {start_lit}"
            f"   AND business_day < {end_excl_lit}"
            f" ORDER BY business_day DESC,"
            f"          (outbound_total - cap) DESC, account_id"
        )
        return [
            LimitBreachViolation(
                account_id=str(r[0]),
                account_name=str(r[1] or ""),
                account_role=str(r[2] or ""),
                account_parent_role=str(r[3] or ""),
                business_day=(
                    r[4].date() if hasattr(r[4], "date") else r[4]
                ),
                transfer_type=str(r[5] or ""),
                outbound_total=Decimal(r[6] or 0),
                cap=Decimal(r[7] or 0),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


@dataclass(frozen=True)
class LimitBreachChildGroupSummary:
    """Per (parent_role, transfer_type) roll-up of breaching children.

    LimitSchedule caps are keyed on (parent_role, transfer_type) per
    SPEC, so the natural child summary keys both too. Auditor sees:
    "5 customers breached the ACH outbound cap under DDAControl this
    period, total overshoot $X".
    """
    parent_role: str
    transfer_type: str
    distinct_children_breaching: int
    total_overshoot: Decimal


def _split_limit_breach_by_account_class(
    rows: list[LimitBreachViolation],
    singleton_ids: set[str],
) -> tuple[
    list[LimitBreachViolation],
    list[LimitBreachChildGroupSummary],
]:
    """Bucket rows into (parent per-row, child grouped by parent+type).

    Children grouped by (parent_role, transfer_type) since that's
    the cap dimension; total_overshoot sums each child's worst-day
    overshoot in the period.
    """
    parent_rows: list[LimitBreachViolation] = []
    by_group: dict[
        tuple[str, str], dict[str, list[LimitBreachViolation]],
    ] = {}
    for r in rows:
        if r.account_id in singleton_ids:
            parent_rows.append(r)
        else:
            key = (
                r.account_parent_role or "(no parent)",
                r.transfer_type,
            )
            by_group.setdefault(key, {}).setdefault(
                r.account_id, [],
            ).append(r)
    child_summaries = sorted(
        (
            LimitBreachChildGroupSummary(
                parent_role=key[0],
                transfer_type=key[1],
                distinct_children_breaching=len(children),
                total_overshoot=sum(
                    (
                        max(rr.overshoot for rr in child_rows)
                        for child_rows in children.values()
                    ),
                    start=Decimal(0),
                ),
            )
            for key, children in by_group.items()
        ),
        # Biggest overshoot first.
        key=lambda s: (-s.total_overshoot, s.parent_role, s.transfer_type),
    )
    return parent_rows, child_summaries


# -- Stuck pending violations (U.3.d) -----------------------------------------


@dataclass(frozen=True)
class StuckPendingViolation:
    """One row of the ``<prefix>_stuck_pending`` matview, audit-shaped.

    Each row is one transaction whose age exceeds the L2-configured
    ``max_pending_age_seconds`` cap. Magnitude = the age itself
    (seconds past posting that the transaction has been stuck in
    Pending status).
    """
    account_id: str
    account_name: str
    account_role: str
    account_parent_role: str
    transaction_id: str
    transfer_type: str
    posting: datetime
    amount_money: Decimal
    age_seconds: Decimal
    max_pending_age_seconds: int


def _query_stuck_pending_violations(
    cfg, instance,  # type: ignore[no-untyped-def]
) -> list[StuckPendingViolation] | None:
    """Pull all rows from the ``<prefix>_stuck_pending`` matview.

    No date filter: stuck_pending is a current-state matview per the
    L1 dashboard convention. Auditor sees every transaction currently
    stuck in Pending past its aging cap, regardless of when posted.
    Sort: oldest stuck first (biggest age_seconds), then account_id.
    """
    if cfg.demo_database_url is None:
        return None

    from quicksight_gen.common.db import connect_demo_db

    prefix = instance.instance
    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT account_id, account_name, account_role,"
            f"       account_parent_role, transaction_id,"
            f"       transfer_type, posting, amount_money,"
            f"       age_seconds, max_pending_age_seconds"
            f"  FROM {prefix}_stuck_pending"
            f" ORDER BY age_seconds DESC, account_id"
        )
        return [
            StuckPendingViolation(
                account_id=str(r[0]),
                account_name=str(r[1] or ""),
                account_role=str(r[2] or ""),
                account_parent_role=str(r[3] or ""),
                transaction_id=str(r[4]),
                transfer_type=str(r[5] or ""),
                posting=r[6],
                amount_money=Decimal(r[7] or 0),
                age_seconds=Decimal(r[8] or 0),
                max_pending_age_seconds=int(r[9] or 0),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


@dataclass(frozen=True)
class StuckPendingChildGroupSummary:
    """Per (parent_role, transfer_type) roll-up of stuck child txns.

    Counts both distinct affected accounts and total stuck txns:
    "5 customers under DDAControl have 12 stuck wire_concentration
    pendings totaling $X". The transaction count drives operational
    workload (12 manual interventions); the account count is the
    spread.
    """
    parent_role: str
    transfer_type: str
    distinct_children_affected: int
    stuck_transaction_count: int
    total_stuck_amount: Decimal


def _split_stuck_pending_by_account_class(
    rows: list[StuckPendingViolation],
    singleton_ids: set[str],
) -> tuple[
    list[StuckPendingViolation],
    list[StuckPendingChildGroupSummary],
]:
    """Bucket rows into (parent per-row, child grouped by parent+type)."""
    parent_rows: list[StuckPendingViolation] = []
    by_group: dict[
        tuple[str, str], list[StuckPendingViolation],
    ] = {}
    for r in rows:
        if r.account_id in singleton_ids:
            parent_rows.append(r)
        else:
            key = (
                r.account_parent_role or "(no parent)",
                r.transfer_type,
            )
            by_group.setdefault(key, []).append(r)
    child_summaries = sorted(
        (
            StuckPendingChildGroupSummary(
                parent_role=key[0],
                transfer_type=key[1],
                distinct_children_affected=len({r.account_id for r in group}),
                stuck_transaction_count=len(group),
                total_stuck_amount=sum(
                    (abs(r.amount_money) for r in group),
                    start=Decimal(0),
                ),
            )
            for key, group in by_group.items()
        ),
        # Biggest dollar pile first.
        key=lambda s: (
            -s.total_stuck_amount, s.parent_role, s.transfer_type,
        ),
    )
    return parent_rows, child_summaries


def _format_age(seconds: Decimal | int) -> str:
    """Human-readable age — days at one-decimal precision.

    Stuck-aging caps in the L2 are typically expressed in days
    (86400s, 172800s); rendering as 'N.Nd' lines up with how
    auditors talk about pending backlog.
    """
    days = float(seconds) / 86400.0
    return f"{days:.1f}d"


@audit.command("apply")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@_period_option_from()
@_period_option_to()
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default=None,
    help=(
        "Output path. Without --execute: Markdown source destination "
        "(default: stdout). With --execute: PDF destination "
        "(default: report.pdf)."
    ),
)
@execute_option()
def audit_apply(
    l2_instance_path: str | None,
    config: str,
    period_from: datetime | None,
    period_to: datetime | None,
    output: str | None,
    execute: bool,
) -> None:
    """Emit the audit report's Markdown source (or ``--execute`` to write a PDF).

    Default: print the Markdown rendering of the report (cover +
    section outline) to stdout. Pass ``-o FILE`` to write to a file.
    Useful for review before committing to a PDF.

    Pass ``--execute`` to render the report as a PDF via reportlab.
    Default destination is ``report.pdf`` in the current working
    directory; override with ``-o FILE``.

    Phase U.1 ships the cover page; body sections (executive summary,
    per-invariant tables, Daily Statement walk, sign-off block) land
    in U.2+ as the page-by-page review gates close.
    """
    _cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    start, end = _resolve_period(period_from, period_to)
    institution = _institution_name(instance)
    generated_at = datetime.now()
    exec_summary = _query_executive_summary(_cfg, instance, (start, end))
    drift_rows = _query_drift_violations(_cfg, instance, (start, end))
    overdraft_rows = _query_overdraft_violations(_cfg, instance, (start, end))
    limit_breach_rows = _query_limit_breach_violations(
        _cfg, instance, (start, end),
    )
    stuck_pending_rows = _query_stuck_pending_violations(_cfg, instance)
    singleton_ids = _singleton_account_ids(instance)

    if execute:
        out_path = Path(output) if output is not None else Path("report.pdf")
        _write_audit_pdf(
            out_path,
            institution=institution,
            period=(start, end),
            generated_at=generated_at,
            exec_summary=exec_summary,
            drift_rows=drift_rows,
            overdraft_rows=overdraft_rows,
            limit_breach_rows=limit_breach_rows,
            stuck_pending_rows=stuck_pending_rows,
            singleton_ids=singleton_ids,
        )
        click.echo(
            f"Wrote audit report to {out_path} "
            f"(institution={institution}, period={start}–{end})."
        )
        return

    markdown = _render_audit_markdown(
        institution=institution,
        period=(start, end),
        generated_at=generated_at,
        exec_summary=exec_summary,
        drift_rows=drift_rows,
        overdraft_rows=overdraft_rows,
        limit_breach_rows=limit_breach_rows,
        stuck_pending_rows=stuck_pending_rows,
        singleton_ids=singleton_ids,
    )
    if output is None:
        click.echo(markdown, nl=False)
        return
    Path(output).write_text(markdown, encoding="utf-8")
    click.echo(
        f"Wrote audit Markdown source to {output} "
        f"({len(markdown)} bytes).",
        err=True,
    )


@audit.command("clean")
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default="report.pdf",
    help="PDF path to remove (default: report.pdf).",
)
@execute_option()
def audit_clean(output: str, execute: bool) -> None:
    """Print or remove the generated report file.

    Default: print the path that would be deleted (no side effect).
    Pass ``--execute`` to actually unlink it.
    """
    target = Path(output)
    if not target.exists():
        click.echo(f"{target} doesn't exist; nothing to clean.")
        return
    if not execute:
        click.echo(f"Would delete: {target}")
        return
    target.unlink()
    click.echo(f"Removed {target}")


@audit.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k smoke').",
)
def audit_test(pytest_args: str) -> None:
    """Run the audit test suite (pytest + pyright on cli/audit.py)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/audit/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/cli/audit.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"audit test failed: {', '.join(failed)}")
    click.echo("audit test: OK")


# -- Renderers (cover page — U.2+ appends body sections) ----------------------


def _l2_fingerprint_placeholder() -> str:
    """Provenance-fingerprint placeholder.

    U.7 replaces this with ``sha256(L2_instance_fingerprint ||
    sorted_matview_row_hashes || period_anchor)`` and adds an
    ``audit verify`` subcommand. The placeholder text is distinctive
    enough that grep'ing the rendered report for it catches a "we
    shipped without wiring U.7" regression before the auditor does.
    """
    return "<pending — see Phase U.7>"


def _render_audit_markdown(
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
    exec_summary: ExecSummary | None,
    drift_rows: list[DriftViolation] | None,
    overdraft_rows: list[OverdraftViolation] | None,
    limit_breach_rows: list[LimitBreachViolation] | None,
    stuck_pending_rows: list[StuckPendingViolation] | None,
    singleton_ids: set[str],
) -> str:
    """Markdown rendering of the audit report.

    Mirrors the PDF page sequence — cover, executive summary, then
    per-invariant violation tables (U.3.a Drift, U.3.b Overdraft,
    U.3.c Limit breach, U.3.d Stuck pending; U.3.e–f land later) —
    so an integrator can review the report's content before
    committing to a real PDF write.
    """
    start, end = period
    fingerprint = _l2_fingerprint_placeholder()
    cover = (
        "# QuickSight Generator audit report\n"
        "\n"
        f"## {institution}\n"
        "\n"
        f"**Reporting period:** {start.isoformat()} – {end.isoformat()} "
        "(inclusive)\n"
        "\n"
        f"**Generated:** {generated_at.isoformat(timespec='seconds')}\n"
        "\n"
        "This report covers the L1 reconciliation invariants — drift, "
        "overdraft, limit breach, stuck pending, stuck unbundled, "
        "supersession audit — for the period above. Sourced directly "
        "from the operator's database matviews; see the provenance "
        "fingerprint at the bottom of every page for reproducibility.\n"
        "\n"
        "---\n"
        "\n"
        f"_Provenance fingerprint:_ `{fingerprint}`\n"
    )
    body = (
        _render_executive_summary_markdown(exec_summary)
        + _render_drift_markdown(drift_rows)
        + _render_overdraft_markdown(overdraft_rows, singleton_ids)
        + _render_limit_breach_markdown(limit_breach_rows, singleton_ids)
        + _render_stuck_pending_markdown(stuck_pending_rows, singleton_ids)
    )
    trailer = (
        "\n"
        "_Remaining per-invariant violation tables (stuck unbundled, "
        "supersession), the per-account-day Daily Statement walk, and "
        "the sign-off block land in Phase U.3.e+._\n"
    )
    return cover + body + trailer


def _render_executive_summary_markdown(
    summary: ExecSummary | None,
) -> str:
    """Executive summary section in Markdown form.

    Renders the same Volume + Exception-counts tables as the PDF.
    When ``summary`` is None (no DB), shows "—" cells with a notice
    so the layout stays previewable.
    """
    if summary is None:
        volume_rows = (
            "| Transactions (legs) | — |\n"
            "| Transfers (logical events) | — |\n"
            "| Dollar volume — gross | — |\n"
            "| Dollar volume — net | — |\n"
        )
        exc_labels = [
            f"{label}\\*" if date_col is None else label
            for label, _, date_col in _EXCEPTION_INVARIANTS
        ] + ["Supersession"]
        exc_rows = "".join(f"| {label} | — |\n" for label in exc_labels)
        notice = (
            "\n_Database not configured — totals shown as placeholders. "
            "Set `demo_database_url` in your config to populate._\n"
        )
    else:
        volume_rows = (
            f"| Transactions (legs) | {summary.transactions_count:,} |\n"
            f"| Transfers (logical events) | {summary.transfers_count:,} |\n"
            f"| Dollar volume — gross | "
            f"${summary.dollar_volume_gross:,.2f} |\n"
            f"| Dollar volume — net | "
            f"${summary.dollar_volume_net:,.2f} |\n"
        )
        exc_rows = "".join(
            f"| {label} | {count:,} |\n"
            for label, count in summary.exception_counts
        )
        notice = ""
    return (
        "\n"
        "---\n"
        "\n"
        "## Executive summary\n"
        f"{notice}"
        "\n"
        "### Volume\n"
        "\n"
        "| Metric | Value |\n"
        "|---|---:|\n"
        f"{volume_rows}"
        "\n"
        "### Exception counts\n"
        "\n"
        "| Invariant | Count |\n"
        "|---|---:|\n"
        f"{exc_rows}"
        "\n"
        "_\\* Current state — open as of report generation, "
        "regardless of when posted (matches the L1 dashboard "
        "convention for stuck-aging matviews)._\n"
    )


def _render_drift_markdown(
    rows: list[DriftViolation] | None,
) -> str:
    """Drift violations section in Markdown form.

    Mirrors the PDF page. None = DB not configured (placeholder
    notice only); empty list = DB healthy with zero violations
    in the period (good-news render); non-empty = full table.
    """
    header = (
        "\n"
        "---\n"
        "\n"
        "## Drift violations\n"
        "\n"
        "_Per-account-day discrepancies between stored end-of-day "
        "balance and the balance computed from posted transactions. "
        "Sourced from `<prefix>_drift` matview._\n"
    )
    if rows is None:
        return header + (
            "\n_Database not configured — table not populated. "
            "Set `demo_database_url` in your config to query._\n"
        )
    if not rows:
        return header + (
            "\n_No drift detected for the period — books reconcile._\n"
        )
    body = (
        "\n"
        "| Account ID | Account name | Role | Day | Stored | Computed | Drift |\n"
        "|---|---|---|---|---:|---:|---:|\n"
    )
    for r in rows:
        body += (
            f"| `{r.account_id}` | {r.account_name} | {r.account_role} | "
            f"{r.business_day.isoformat()} | "
            f"${r.stored_balance:,.2f} | "
            f"${r.computed_balance:,.2f} | "
            f"${r.drift:,.2f} |\n"
        )
    return header + body


def _render_overdraft_markdown(
    rows: list[OverdraftViolation] | None,
    singleton_ids: set[str],
) -> str:
    """Overdraft violations section in Markdown form.

    Splits rows into parent accounts (L2 ``Account`` singletons —
    per-row detail because a parent itself going negative is a
    systemic event) and child accounts (template-materialized —
    rolled up by parent role with distinct-children-negative +
    total-peak-negative). Same None / [] / non-empty convention as
    the Drift section.
    """
    header = (
        "\n"
        "---\n"
        "\n"
        "## Overdraft violations\n"
        "\n"
        "_Account-days where the stored end-of-day balance went "
        "negative. Sourced from `<prefix>_overdraft` matview. "
        "Parent accounts (L2 singletons — GL clearing, concentration, "
        "ZBA master) are shown per-row because a parent itself going "
        "negative is a systemic event. Child accounts (templated, "
        "e.g. customer DDAs, ZBA sub-accounts) roll up by parent "
        "role with distinct-children-negative + summed-peak-negative._\n"
    )
    if rows is None:
        return header + (
            "\n_Database not configured — table not populated. "
            "Set `demo_database_url` in your config to query._\n"
        )
    if not rows:
        return header + (
            "\n_No overdrafts detected for the period._\n"
        )

    parent_rows, child_groups = _split_overdraft_by_account_class(
        rows, singleton_ids,
    )
    out = header
    if parent_rows:
        out += (
            "\n"
            "### Parent accounts (per-row detail)\n"
            "\n"
            "| Account ID | Account name | Role | Day | Stored balance |\n"
            "|---|---|---|---|---:|\n"
        )
        for r in parent_rows:
            out += (
                f"| `{r.account_id}` | {r.account_name} | "
                f"{r.account_role} | {r.business_day.isoformat()} | "
                f"${r.stored_balance:,.2f} |\n"
            )
    else:
        out += "\n_No parent-account overdrafts in the period._\n"
    if child_groups:
        out += (
            "\n"
            "### Child accounts grouped by parent role\n"
            "\n"
            "| Parent role | Children negative | Total peak negative |\n"
            "|---|---:|---:|\n"
        )
        for s in child_groups:
            out += (
                f"| {s.parent_role} | {s.distinct_children_negative} "
                f"| ${s.total_peak_negative:,.2f} |\n"
            )
    return out


def _render_limit_breach_markdown(
    rows: list[LimitBreachViolation] | None,
    singleton_ids: set[str],
) -> str:
    """Limit breach violations section in Markdown form.

    Same parent-vs-child split as Overdraft. Children grouped by
    (parent_role, transfer_type) since the LimitSchedule cap is
    keyed on that pair.
    """
    header = (
        "\n"
        "---\n"
        "\n"
        "## Limit breach violations\n"
        "\n"
        "_Account-day-transfer_type cells where cumulative outbound "
        "exceeded the L2-configured cap. Sourced from "
        "`<prefix>_limit_breach` matview. Parent accounts shown "
        "per-row; child accounts grouped by (parent role, transfer "
        "type) — the LimitSchedule key shape._\n"
    )
    if rows is None:
        return header + (
            "\n_Database not configured — table not populated. "
            "Set `demo_database_url` in your config to query._\n"
        )
    if not rows:
        return header + (
            "\n_No limit breaches detected for the period._\n"
        )

    parent_rows, child_groups = _split_limit_breach_by_account_class(
        rows, singleton_ids,
    )
    out = header
    if parent_rows:
        out += (
            "\n"
            "### Parent accounts (per-row detail)\n"
            "\n"
            "| Account ID | Account name | Role | Day | Transfer type "
            "| Outbound | Cap | Overshoot |\n"
            "|---|---|---|---|---|---:|---:|---:|\n"
        )
        for r in parent_rows:
            out += (
                f"| `{r.account_id}` | {r.account_name} | "
                f"{r.account_role} | {r.business_day.isoformat()} | "
                f"{r.transfer_type} | ${r.outbound_total:,.2f} "
                f"| ${r.cap:,.2f} | ${r.overshoot:,.2f} |\n"
            )
    if child_groups:
        out += (
            "\n"
            "### Child accounts grouped by parent role + transfer type\n"
            "\n"
            "| Parent role | Transfer type | Children breaching "
            "| Total overshoot |\n"
            "|---|---|---:|---:|\n"
        )
        for s in child_groups:
            out += (
                f"| {s.parent_role} | {s.transfer_type} "
                f"| {s.distinct_children_breaching} "
                f"| ${s.total_overshoot:,.2f} |\n"
            )
    return out


def _render_stuck_pending_markdown(
    rows: list[StuckPendingViolation] | None,
    singleton_ids: set[str],
) -> str:
    """Stuck pending violations section in Markdown form.

    Current-state matview: NO date filter, shows every transaction
    currently stuck in Pending past its aging cap regardless of when
    posted. Same parent/child split; child summary keys on
    (parent_role, transfer_type) since the cap is per transfer type.
    """
    header = (
        "\n"
        "---\n"
        "\n"
        "## Stuck pending transactions\n"
        "\n"
        "_Transactions currently in Pending status whose age exceeds "
        "the L2-configured `max_pending_age_seconds` cap. Sourced "
        "from `<prefix>_stuck_pending` matview. **Current-state** — "
        "shown regardless of posting date (mirrors the L1 dashboard "
        "convention; the period band on the cover does not scope "
        "this section)._\n"
    )
    if rows is None:
        return header + (
            "\n_Database not configured — table not populated. "
            "Set `demo_database_url` in your config to query._\n"
        )
    if not rows:
        return header + (
            "\n_No stuck pending transactions — backlog clear._\n"
        )

    parent_rows, child_groups = _split_stuck_pending_by_account_class(
        rows, singleton_ids,
    )
    out = header
    if parent_rows:
        out += (
            "\n"
            "### Parent accounts (per-row detail)\n"
            "\n"
            "| Account ID | Account name | Transfer type | Posted "
            "| Amount | Age | Cap |\n"
            "|---|---|---|---|---:|---:|---:|\n"
        )
        for r in parent_rows:
            out += (
                f"| `{r.account_id}` | {r.account_name} | "
                f"{r.transfer_type} | "
                f"{r.posting.strftime('%Y-%m-%d %H:%M')} | "
                f"${r.amount_money:,.2f} | "
                f"{_format_age(r.age_seconds)} | "
                f"{_format_age(r.max_pending_age_seconds)} |\n"
            )
    if child_groups:
        out += (
            "\n"
            "### Child accounts grouped by parent role + transfer type\n"
            "\n"
            "| Parent role | Transfer type | Children affected "
            "| Stuck transactions | Total amount |\n"
            "|---|---|---:|---:|---:|\n"
        )
        for s in child_groups:
            out += (
                f"| {s.parent_role} | {s.transfer_type} "
                f"| {s.distinct_children_affected} "
                f"| {s.stuck_transaction_count} "
                f"| ${s.total_stuck_amount:,.2f} |\n"
            )
    return out


def _write_audit_pdf(
    path: Path,
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
    exec_summary: ExecSummary | None,
    drift_rows: list[DriftViolation] | None,
    overdraft_rows: list[OverdraftViolation] | None,
    limit_breach_rows: list[LimitBreachViolation] | None,
    stuck_pending_rows: list[StuckPendingViolation] | None,
    singleton_ids: set[str],
) -> None:
    """Render the audit report as a PDF.

    Page sequence: cover → executive summary → per-invariant tables
    (Drift, Overdraft, Limit breach, Stuck pending so far; U.3.e+
    adds the rest). Each per-invariant page paginates via LongTable.
    Every page carries a footer with the provenance fingerprint
    placeholder (real hash lands in U.7).
    """
    # Imported lazily so the audit CLI loads even when the [audit]
    # extra isn't installed — only --execute paths need reportlab.
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.85 * inch,  # extra room for the page footer
        title=f"QuickSight Generator audit report — {institution}",
    )
    styles = getSampleStyleSheet()
    institution_style = ParagraphStyle(
        "InstitutionName",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        spaceBefore=0,
        spaceAfter=12,
    )
    period_band_style = ParagraphStyle(
        "PeriodBand",
        parent=styles["BodyText"],
        fontSize=13,
        leading=18,
        spaceBefore=6,
        spaceAfter=6,
        textColor=HexColor("#1a1a1a"),
        backColor=HexColor("#eef3f7"),
        borderColor=HexColor("#c7d6e3"),
        borderWidth=0.5,
        borderPadding=10,
    )
    start, end = period
    story = [
        Paragraph(
            "QuickSight Generator audit report",
            styles["Title"],
        ),
        Spacer(1, 0.2 * inch),
        Paragraph(institution, institution_style),
        Spacer(1, 0.1 * inch),
        Paragraph(
            f"<b>Reporting period:</b> {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive)",
            period_band_style,
        ),
        Spacer(1, 0.25 * inch),
        Paragraph(
            f"<b>Generated:</b> {generated_at.isoformat(timespec='seconds')}",
            styles["BodyText"],
        ),
        Spacer(1, 0.4 * inch),
        Paragraph(
            "This report covers the L1 reconciliation invariants &mdash; "
            "drift, overdraft, limit breach, stuck pending, stuck "
            "unbundled, supersession audit &mdash; for the period above. "
            "Sourced directly from the operator's database matviews; see "
            "the provenance fingerprint at the bottom of every page for "
            "reproducibility.",
            styles["BodyText"],
        ),
    ]
    story.extend(_executive_summary_story(exec_summary, styles, period))
    story.extend(_drift_story(drift_rows, styles, period))
    story.extend(_overdraft_story(
        overdraft_rows, styles, period, singleton_ids,
    ))
    story.extend(_limit_breach_story(
        limit_breach_rows, styles, period, singleton_ids,
    ))
    story.extend(_stuck_pending_story(
        stuck_pending_rows, styles, singleton_ids,
    ))
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)


def _executive_summary_story(
    summary: ExecSummary | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.2 executive summary page.

    Caller appends to the doc story after the cover page. Renders a
    page break, heading, period context, and two tables (Volume +
    Exception counts). When summary is None, renders "—" cells and a
    notice — keeps the layout reviewable without a live DB.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        Paragraph("Executive summary", styles["Heading1"]),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive)",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if summary is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; totals shown as "
                "placeholders. Set <b>demo_database_url</b> in your "
                "config to populate.</i>",
                styles["BodyText"],
            ),
        )
        volume_data = [
            ["Metric", "Value"],
            ["Transactions (legs)", "—"],
            ["Transfers (logical events)", "—"],
            ["Dollar volume — gross", "—"],
            ["Dollar volume — net", "—"],
        ]
        exc_rows = [
            [f"{label}*" if date_col is None else label, "—"]
            for label, _, date_col in _EXCEPTION_INVARIANTS
        ]
        exc_rows.append(["Supersession", "—"])
        exception_data = [["Invariant", "Count"]] + exc_rows
    else:
        volume_data = [
            ["Metric", "Value"],
            ["Transactions (legs)", f"{summary.transactions_count:,}"],
            ["Transfers (logical events)", f"{summary.transfers_count:,}"],
            ["Dollar volume — gross", f"${summary.dollar_volume_gross:,.2f}"],
            ["Dollar volume — net", f"${summary.dollar_volume_net:,.2f}"],
        ]
        exception_data = [["Invariant", "Count"]] + [
            [label, f"{count:,}"]
            for label, count in summary.exception_counts
        ]

    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    col_widths = [3.5 * inch, 2.5 * inch]

    elements.extend([
        Spacer(1, 0.15 * inch),
        Paragraph("Volume", styles["Heading3"]),
        Spacer(1, 0.05 * inch),
        Table(volume_data, colWidths=col_widths, style=table_style),
        Spacer(1, 0.3 * inch),
        Paragraph("Exception counts", styles["Heading3"]),
        Spacer(1, 0.05 * inch),
        Table(exception_data, colWidths=col_widths, style=table_style),
        Spacer(1, 0.1 * inch),
        Paragraph(
            "<i>* Current state &mdash; open as of report generation, "
            "regardless of when posted (matches the L1 dashboard "
            "convention for stuck-aging matviews).</i>",
            styles["BodyText"],
        ),
    ])
    return elements


def _drift_story(
    rows: list[DriftViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.a Drift violations page.

    LongTable auto-paginates with the header row repeated. None = no
    DB → placeholder notice. Empty list = DB healthy with zero
    drifts in period → good-news render. Non-empty = full table.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        Paragraph("Drift violations", styles["Heading1"]),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive). "
            "Source: <b>&lt;prefix&gt;_drift</b> matview.",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Per-account-day discrepancies between stored "
            "end-of-day balance and the balance computed from "
            "posted transactions.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No drift detected for the period &mdash; "
                "books reconcile.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    cell_style = ParagraphStyle(
        "DriftCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    header = [
        "Account ID",
        "Account name",
        "Role",
        "Day",
        "Stored",
        "Computed",
        "Drift",
    ]
    data: list[list] = [header]
    for r in rows:
        data.append([
            Paragraph(r.account_id, cell_style),
            Paragraph(r.account_name, cell_style),
            Paragraph(r.account_role, cell_style),
            r.business_day.isoformat(),
            f"${r.stored_balance:,.2f}",
            f"${r.computed_balance:,.2f}",
            f"${r.drift:,.2f}",
        ])

    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        # Right-align numeric columns (Day, Stored, Computed, Drift).
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f5f8fb"),
        ]),
    ])
    col_widths = [
        1.15 * inch,  # Account ID
        1.15 * inch,  # Account name
        1.05 * inch,  # Role  (fits "CustomerDDA" / "ConcentrationMaster")
        0.8 * inch,   # Day
        0.95 * inch,  # Stored
        0.95 * inch,  # Computed
        0.9 * inch,   # Drift
    ]
    elements.append(
        LongTable(
            data, colWidths=col_widths, style=table_style, repeatRows=1,
        ),
    )
    return elements


def _overdraft_story(
    rows: list[OverdraftViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    singleton_ids: set[str],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.b Overdraft violations page.

    Renders up to TWO sub-tables:
      - Parent accounts (L2 ``Account`` singletons): per-row detail
        — each occurrence of a parent itself going negative is a
        systemic event worth surfacing individually.
      - Child accounts (template-materialized): grouped by parent
        role; one row per parent role with distinct-children-negative
        + summed-peak-negative.
    Empty sub-tables are omitted; the section header still renders.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        Paragraph("Overdraft violations", styles["Heading1"]),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive). "
            "Source: <b>&lt;prefix&gt;_overdraft</b> matview.",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Account-days where the stored end-of-day balance "
            "went negative. Parent accounts (L2 singletons &mdash; "
            "GL clearing, concentration, ZBA master) shown per-row "
            "because a parent itself going negative is systemic. "
            "Child accounts (templated, e.g. customer DDAs, ZBA "
            "sub-accounts) roll up by parent role.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No overdrafts detected for the period.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_overdraft_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "OverdraftCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f5f8fb"),
        ]),
    ])

    if parent_rows:
        elements.extend([
            Paragraph(
                "Parent accounts (per-row detail)",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Role", "Day", "Stored balance"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.account_role, cell_style),
                r.business_day.isoformat(),
                f"${r.stored_balance:,.2f}",
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.6 * inch, 1.5 * inch, 1.5 * inch,
                       0.8 * inch, 1.5 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            Paragraph(
                "Child accounts grouped by parent role",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Children negative", "Total peak negative"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                f"{s.distinct_children_negative}",
                f"${s.total_peak_negative:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[3.0 * inch, 1.6 * inch, 2.3 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _limit_breach_story(
    rows: list[LimitBreachViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    period: tuple[date, date],
    singleton_ids: set[str],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.c Limit breach violations page.

    Same parent-vs-child split as Overdraft. Children grouped by
    (parent_role, transfer_type) since the LimitSchedule cap is
    keyed on that pair. Parent table carries 8 columns (account,
    role, day, transfer_type, outbound, cap, overshoot); child
    summary 4 columns (parent_role, transfer_type, count, total
    overshoot).
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    start, end = period
    elements: list = [
        PageBreak(),
        Paragraph("Limit breach violations", styles["Heading1"]),
        Paragraph(
            f"Reporting period: {start.isoformat()} &ndash; "
            f"{end.isoformat()} (inclusive). "
            "Source: <b>&lt;prefix&gt;_limit_breach</b> matview.",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Account-day-transfer_type cells where cumulative "
            "outbound exceeded the L2-configured cap. Parent accounts "
            "shown per-row; child accounts grouped by (parent role, "
            "transfer type) &mdash; the LimitSchedule key shape.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No limit breaches detected for the period.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_limit_breach_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "LimitBreachCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f5f8fb"),
        ]),
    ])

    if parent_rows:
        elements.extend([
            Paragraph(
                "Parent accounts (per-row detail)",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Role", "Day",
             "Transfer type", "Outbound", "Cap", "Overshoot"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.account_role, cell_style),
                r.business_day.isoformat(),
                Paragraph(r.transfer_type, cell_style),
                f"${r.outbound_total:,.2f}",
                f"${r.cap:,.2f}",
                f"${r.overshoot:,.2f}",
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                # Right-align Day + Transfer type + 3 numerics.
                ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.05 * inch, 1.05 * inch, 0.85 * inch,
                       0.75 * inch, 0.95 * inch, 0.85 * inch,
                       0.7 * inch, 0.8 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            Paragraph(
                "Child accounts grouped by parent role + transfer type",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Transfer type",
             "Children breaching", "Total overshoot"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                Paragraph(s.transfer_type, cell_style),
                f"{s.distinct_children_breaching}",
                f"${s.total_overshoot:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[2.0 * inch, 2.0 * inch,
                       1.4 * inch, 1.5 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _stuck_pending_story(
    rows: list[StuckPendingViolation] | None,
    styles,  # type: ignore[no-untyped-def]
    singleton_ids: set[str],
) -> list:  # type: ignore[type-arg]
    """Platypus elements for the U.3.d Stuck pending transactions page.

    Current-state matview: NO date filter (mirrors L1 dashboard).
    Same parent/child split as Overdraft + Limit breach. Child
    summary 5 cols (parent role, transfer type, distinct children,
    stuck transaction count, total amount) — transaction count drives
    operational workload, child count drives spread.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        PageBreak,
        Paragraph,
        Spacer,
        TableStyle,
    )

    elements: list = [
        PageBreak(),
        Paragraph("Stuck pending transactions", styles["Heading1"]),
        Paragraph(
            "Source: <b>&lt;prefix&gt;_stuck_pending</b> matview.",
            styles["BodyText"],
        ),
        Paragraph(
            "<i>Transactions currently in Pending status whose age "
            "exceeds the L2-configured aging cap. <b>Current-state</b> "
            "&mdash; shown regardless of posting date; the report "
            "period band on the cover does not scope this section.</i>",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if rows is None:
        elements.append(
            Paragraph(
                "<i>Database not configured &mdash; table not "
                "populated. Set <b>demo_database_url</b> in your "
                "config to query.</i>",
                styles["BodyText"],
            ),
        )
        return elements
    if not rows:
        elements.append(
            Paragraph(
                "<i>No stuck pending transactions &mdash; backlog "
                "clear.</i>",
                styles["BodyText"],
            ),
        )
        return elements

    parent_rows, child_groups = _split_stuck_pending_by_account_class(
        rows, singleton_ids,
    )
    cell_style = ParagraphStyle(
        "StuckPendingCell",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        spaceBefore=0,
        spaceAfter=0,
    )
    base_table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d6e3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f5f8fb"),
        ]),
    ])

    if parent_rows:
        elements.extend([
            Paragraph(
                "Parent accounts (per-row detail)",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        detail_data: list[list] = [
            ["Account ID", "Account name", "Transfer type",
             "Posted", "Amount", "Age", "Cap"],
        ]
        for r in parent_rows:
            detail_data.append([
                Paragraph(r.account_id, cell_style),
                Paragraph(r.account_name, cell_style),
                Paragraph(r.transfer_type, cell_style),
                r.posting.strftime("%Y-%m-%d %H:%M"),
                f"${r.amount_money:,.2f}",
                _format_age(r.age_seconds),
                _format_age(r.max_pending_age_seconds),
            ])
        detail_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            detail_data,
            colWidths=[1.15 * inch, 1.15 * inch, 1.1 * inch,
                       1.05 * inch, 0.95 * inch,
                       0.7 * inch, 0.7 * inch],
            style=detail_style, repeatRows=1,
        ))
        elements.append(Spacer(1, 0.25 * inch))

    if child_groups:
        elements.extend([
            Paragraph(
                "Child accounts grouped by parent role + transfer type",
                styles["Heading3"],
            ),
            Spacer(1, 0.05 * inch),
        ])
        group_data: list[list] = [
            ["Parent role", "Transfer type", "Children affected",
             "Stuck transactions", "Total amount"],
        ]
        for s in child_groups:
            group_data.append([
                Paragraph(s.parent_role, cell_style),
                Paragraph(s.transfer_type, cell_style),
                f"{s.distinct_children_affected}",
                f"{s.stuck_transaction_count}",
                f"${s.total_stuck_amount:,.2f}",
            ])
        group_style = TableStyle(
            base_table_style.getCommands() + [
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ],
        )
        elements.append(LongTable(
            group_data,
            colWidths=[1.6 * inch, 1.6 * inch, 1.2 * inch,
                       1.2 * inch, 1.3 * inch],
            style=group_style, repeatRows=1,
        ))
    return elements


def _draw_footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    """Page footer drawn on every page.

    Per Phase U.6 the footer carries the report-version sentinel,
    page number, and the source-data fingerprint. U.1 wires the slot
    with a placeholder fingerprint so the layout is correct when U.7
    swaps the real hash in.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch

    canvas.saveState()
    width, _ = letter
    canvas.setFont("Helvetica", 8)
    canvas.setFillGray(0.4)
    left = 0.75 * inch
    right = width - 0.75 * inch
    baseline = 0.5 * inch
    canvas.drawString(
        left, baseline,
        f"QuickSight Generator audit report  ·  Page {doc.page}",
    )
    canvas.drawRightString(
        right, baseline,
        f"Provenance: {_l2_fingerprint_placeholder()}",
    )
    canvas.restoreState()
