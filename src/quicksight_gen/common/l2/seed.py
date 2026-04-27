"""Demo-seed primitives for any L2 instance (M.2d.5).

Lifted from ``tests/l2/sasquatch_ar_seed.py`` so the typed plant
dataclasses + ``emit_seed`` machinery are reusable across instances:

- The Sasquatch AR fixture uses these primitives in
  ``tests/l2/sasquatch_ar_seed.py::default_ar_scenario``.
- M.3 will mirror with ``tests/l2/sasquatch_pr_seed.py::default_pr_scenario``,
  reusing every ``_emit_*_rows`` / ``_txn_row`` / ``_balance_row`` helper
  here (no per-app duplicate emit machinery).
- Integrators authoring their own L2 instance import these primitives
  directly to declare their demo scenarios in code (per M.6's CLI
  workflow).

What ``emit_seed(instance, scenarios)`` produces:
- A single deterministic SQL string ready for
  ``psycopg2.cursor.execute`` or ``psql``.
- Inserts go to ``<instance.instance>_transactions`` +
  ``<instance.instance>_daily_balances`` (the schema M.1a.7's
  ``emit_schema`` produced).
- Plant order is sorted by stable keys (account_id, days_ago,
  transfer_type) so the M.2.7 hash-lock can pin the output bytes.

What this module deliberately does NOT do:
- Reproduce a full demo's richness (background traffic, baseline-clean
  customers, multi-leg TransferTemplate cycles, AggregatingRail
  bundling). Plant the minimum that exercises every L1 invariant view;
  richer seed work belongs in app-level demo generators.
- Materialize ``AccountTemplate`` instances at runtime — the integrator
  declares concrete ``TemplateInstance`` rows on the ``ScenarioPlant``.
  At runtime, an ETL is responsible for materialization.

Public API:
- Plant dataclasses: ``TemplateInstance``, ``DriftPlant``,
  ``OverdraftPlant``, ``LimitBreachPlant``, ``StuckPendingPlant``,
  ``StuckUnbundledPlant``, ``SupersessionPlant``.
- Container: ``ScenarioPlant`` (holds template_instances + every
  plant tuple + a reference ``today`` date).
- Entry point: ``emit_seed(instance, scenarios) -> str``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .primitives import (
    Account,
    AccountTemplate,
    Identifier,
    L2Instance,
    Name,
    Rail,
    TwoLegRail,
)


# -- Public scenario dataclasses ---------------------------------------------


@dataclass(frozen=True, slots=True)
class TemplateInstance:
    """One concrete materialization of an ``AccountTemplate``.

    The L2 instance declares the SHAPE of (e.g.) `CustomerDDA`; this
    record materializes one concrete customer DDA. The integrator's ETL
    is normally responsible for materialization at runtime; for the
    demo seed we declare them inline.
    """

    template_role: Identifier   # e.g. "CustomerDDA"
    account_id: Identifier      # e.g. "cust-900-0001-bigfoot-brews"
    name: Name                  # e.g. "Bigfoot Brews — DDA"


@dataclass(frozen=True, slots=True)
class DriftPlant:
    """A planted (account, business_day) cell where stored balance disagrees
    with computed balance by ``delta_money``.

    Positive delta: stored balance is HIGHER than the sum of postings.
    Negative delta: stored balance is LOWER than the sum of postings.

    Surfaces in the L1 Drift theorem as a non-zero ``Drift`` value for
    that account-day.

    Background postings on the drift day come from ``rail_name`` (a
    declared two-leg Rail in the L2 instance); the counter-leg uses
    ``counter_account_id`` (must be a declared external Account in the
    same instance). Both are resolved from ``instance`` at emit time
    so this dataclass never needs to know about specific persona
    fixtures.
    """

    account_id: Identifier
    days_ago: int
    delta_money: Decimal
    rail_name: Identifier
    counter_account_id: Identifier


@dataclass(frozen=True, slots=True)
class OverdraftPlant:
    """A planted (account, business_day) cell where stored balance is
    negative.

    Surfaces in L1's Non-Negative Stored Balance SHOULD-constraint as
    a violation for that account-day.
    """

    account_id: Identifier
    days_ago: int
    money: Decimal              # MUST be negative


@dataclass(frozen=True, slots=True)
class LimitBreachPlant:
    """A planted (account, business_day, transfer_type) cell where the
    daily outbound flow exceeds the configured ``LimitSchedule.cap``.

    Surfaces in L1's Limit Breach SHOULD-constraint when
    ``OutboundFlow(account, transfer_type, day) > limit``.

    The breaching debit posts on the customer side; the counter-leg
    uses ``counter_account_id`` (must be a declared external Account
    in the same instance), resolved from ``instance`` at emit time so
    this dataclass never hardcodes a specific persona's counterparty.
    """

    account_id: Identifier
    days_ago: int
    transfer_type: str
    rail_name: Identifier
    amount: Decimal             # absolute value; must exceed the cap
    counter_account_id: Identifier


@dataclass(frozen=True, slots=True)
class StuckPendingPlant:
    """A planted Pending leg whose age exceeds the rail's `max_pending_age`.

    Surfaces in L1's `<prefix>_stuck_pending` view (M.2b.8) when
    `EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - posting)) >
    rail.max_pending_age_seconds`. Pick a rail with a max_pending_age
    set + a `days_ago` value comfortably past the cap.
    """

    account_id: Identifier
    days_ago: int
    transfer_type: str
    rail_name: Identifier
    amount: Decimal


@dataclass(frozen=True, slots=True)
class StuckUnbundledPlant:
    """A planted Posted leg with `bundle_id IS NULL` whose age exceeds
    the rail's `max_unbundled_age`.

    Surfaces in L1's `<prefix>_stuck_unbundled` view (M.2b.9) when the
    leg's age past `posting` exceeds the per-rail cap. Per validator
    R8, the rail MUST appear in some AggregatingRail's bundles_activity
    — the seed picks a rail that satisfies this.
    """

    account_id: Identifier
    days_ago: int
    transfer_type: str
    rail_name: Identifier
    amount: Decimal


@dataclass(frozen=True, slots=True)
class SupersessionPlant:
    """A planted logical-key (transaction.id) with multiple `entry`
    versions, simulating a TechnicalCorrection rewrite of a posted leg.

    Surfaces in M.2b.12's Supersession Audit detail tables. Emits two
    transaction rows with the same `id`: the first ("original") posts
    `original_amount`; the second ("correction") posts `corrected_amount`
    a few minutes later carrying `supersedes='TechnicalCorrection'`.
    PostgreSQL's BIGSERIAL `entry` column auto-assigns the entry
    versioning, so the second insert lands at a higher entry value.
    """

    account_id: Identifier
    days_ago: int
    transfer_type: str
    rail_name: Identifier
    original_amount: Decimal
    corrected_amount: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioPlant:
    """The full set of planted scenarios + materialized template instances.

    Defaults to today (UTC midnight) as the reference date; ``days_ago``
    on each plant subtracts from this.
    """

    template_instances: tuple[TemplateInstance, ...]
    drift_plants: tuple[DriftPlant, ...] = ()
    overdraft_plants: tuple[OverdraftPlant, ...] = ()
    limit_breach_plants: tuple[LimitBreachPlant, ...] = ()
    stuck_pending_plants: tuple[StuckPendingPlant, ...] = ()
    stuck_unbundled_plants: tuple[StuckUnbundledPlant, ...] = ()
    supersession_plants: tuple[SupersessionPlant, ...] = ()
    today: date = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).date(),
    )


# -- Public emit_seed --------------------------------------------------------


def emit_seed(instance: L2Instance, scenarios: ScenarioPlant) -> str:
    """Emit the full SQL INSERT script for the planted scenarios.

    The output is a single SQL string ready for ``psycopg2.cursor.execute``
    or feeding into ``psql``. Scenarios are emitted in deterministic
    order (sorted by account_id then days_ago) so the M.2.7 hash-lock
    can pin the output bytes.
    """
    prefix = instance.instance
    template_by_role = {t.role: t for t in instance.account_templates}
    parent_singleton_by_role = _parent_singletons(instance)

    # -- Build transaction rows --
    txn_rows: list[str] = []
    txn_counter = _Counter(start=1)

    # Each scenario plant emits its own rows; sort first for determinism.
    for p in sorted(scenarios.limit_breach_plants, key=_breach_key):
        txn_rows.extend(
            _emit_limit_breach_rows(
                p, instance, scenarios, template_by_role,
                parent_singleton_by_role, txn_counter,
            )
        )

    for p in sorted(scenarios.drift_plants, key=_drift_key):
        txn_rows.extend(
            _emit_drift_background_rows(
                p, instance, scenarios, template_by_role,
                parent_singleton_by_role, txn_counter,
            )
        )

    for p in sorted(scenarios.stuck_pending_plants, key=_stuck_pending_key):
        txn_rows.extend(
            _emit_stuck_pending_rows(
                p, scenarios, template_by_role, txn_counter,
            )
        )

    for p in sorted(scenarios.stuck_unbundled_plants, key=_stuck_unbundled_key):
        txn_rows.extend(
            _emit_stuck_unbundled_rows(
                p, scenarios, template_by_role, txn_counter,
            )
        )

    for p in sorted(scenarios.supersession_plants, key=_supersession_key):
        txn_rows.extend(
            _emit_supersession_rows(
                p, scenarios, template_by_role, txn_counter,
            )
        )

    # Overdraft scenarios don't need extra transaction rows — the
    # daily_balances row alone (negative money) drives the exception.

    # -- Build daily_balances rows --
    #
    # Each scenario plant emits its own daily_balances row at its plant
    # day. We deliberately do NOT emit a baseline daily_balance for
    # "today" — under L1 SPEC, ComputedBalance is cumulative through
    # business_day_end (sum of ALL Posted transactions, not same-day),
    # so a $0 baseline today against any account with planted
    # transactions would surface a spurious drift row. Accounts without
    # planted transactions (context-only template instances) get NO
    # daily_balance row — they're invisible to the drift / overdraft /
    # expected_eod views, which is the correct semantic.
    db_rows: list[str] = []

    for p in sorted(scenarios.drift_plants, key=_drift_key):
        db_rows.append(
            _emit_drift_balance_row(
                p, scenarios, template_by_role,
            )
        )

    for p in sorted(scenarios.overdraft_plants, key=_overdraft_key):
        db_rows.append(
            _emit_overdraft_balance_row(
                p, scenarios, template_by_role,
            )
        )

    txn_insert = (
        f"INSERT INTO {prefix}_transactions "
        "(id, account_id, account_name, account_role, account_scope, "
        "account_parent_role, amount_money, amount_direction, status, "
        "posting, transfer_id, transfer_type, transfer_completion, "
        "transfer_parent_id, rail_name, template_name, bundle_id, "
        "supersedes, origin, metadata) VALUES\n  "
        + ",\n  ".join(txn_rows)
        + ";"
    ) if txn_rows else "-- (no transactions planted)"

    db_insert = (
        f"INSERT INTO {prefix}_daily_balances "
        "(account_id, account_name, account_role, account_scope, "
        "account_parent_role, expected_eod_balance, business_day_start, "
        "business_day_end, money, limits, supersedes) VALUES\n  "
        + ",\n  ".join(db_rows)
        + ";"
    ) if db_rows else "-- (no daily_balances planted)"

    return f"""\
-- =====================================================================
-- L2 instance: {prefix} — demo seed
-- Generated by quicksight_gen.common.l2.seed.emit_seed
-- Reference date: {scenarios.today.isoformat()}
-- Plants:
--   {len(scenarios.template_instances)} template instances
--   {len(scenarios.drift_plants)} drift scenarios
--   {len(scenarios.overdraft_plants)} overdraft scenarios
--   {len(scenarios.limit_breach_plants)} limit-breach scenarios
-- =====================================================================

{txn_insert}

{db_insert}
"""


# -- Internal helpers --------------------------------------------------------


class _Counter:
    """Tiny mutable counter for deterministic ID generation."""

    def __init__(self, *, start: int = 1) -> None:
        self.value = start

    def next(self) -> int:
        v = self.value
        self.value += 1
        return v


def _drift_key(p: DriftPlant) -> tuple[str, int]:
    return (str(p.account_id), p.days_ago)


def _overdraft_key(p: OverdraftPlant) -> tuple[str, int]:
    return (str(p.account_id), p.days_ago)


def _breach_key(p: LimitBreachPlant) -> tuple[str, int, str]:
    return (str(p.account_id), p.days_ago, p.transfer_type)


def _stuck_pending_key(p: StuckPendingPlant) -> tuple[str, int, str]:
    return (str(p.account_id), p.days_ago, p.transfer_type)


def _stuck_unbundled_key(p: StuckUnbundledPlant) -> tuple[str, int, str]:
    return (str(p.account_id), p.days_ago, p.transfer_type)


def _supersession_key(p: SupersessionPlant) -> tuple[str, int, str]:
    return (str(p.account_id), p.days_ago, p.transfer_type)


def _parent_singletons(instance: L2Instance) -> dict[Identifier, Account]:
    """Build a `role -> Account` map for singleton accounts; used to
    resolve `AccountTemplate.parent_role` to a concrete parent."""
    return {
        a.role: a for a in instance.accounts if a.role is not None
    }


def _resolve_template(
    account_id: Identifier,
    scenarios: ScenarioPlant,
) -> TemplateInstance:
    """Find the materialized template instance for `account_id`."""
    for ti in scenarios.template_instances:
        if ti.account_id == account_id:
            return ti
    raise KeyError(
        f"account_id {account_id!r} not declared in scenarios.template_instances"
    )


def _resolve_account(account_id: Identifier, instance: L2Instance) -> Account:
    """Find the L2-declared Account by id; raise on miss with a clear message."""
    for a in instance.accounts:
        if a.id == account_id:
            return a
    raise KeyError(
        f"account_id {account_id!r} not declared in instance.accounts; "
        f"plant references an external counterparty that doesn't exist "
        f"in the L2 YAML"
    )


def _eod_timestamp(d: date) -> str:
    """End-of-day UTC timestamp for `d` (i.e. start of next day)."""
    next_day = d + timedelta(days=1)
    return f"{next_day.isoformat()}T00:00:00+00:00"


def _bod_timestamp(d: date) -> str:
    """Beginning-of-day UTC timestamp for `d`."""
    return f"{d.isoformat()}T00:00:00+00:00"


def _emit_limit_breach_rows(
    p: LimitBreachPlant,
    instance: L2Instance,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    parent_singleton_by_role: dict[Identifier, Account],
    counter: _Counter,
) -> list[str]:
    """Plant ONE outbound debit row exceeding the cap. The row alone is
    enough to drive `OutboundFlow > limit` for the (account, day, type)."""
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    counter_account = _resolve_account(p.counter_account_id, instance)
    counter_name = counter_account.name or Name(str(counter_account.id))
    counter_role = counter_account.role or Identifier(str(counter_account.id))
    breach_day = scenarios.today - timedelta(days=p.days_ago)
    posting_ts = (
        f"{breach_day.isoformat()}T14:00:00+00:00"  # 2pm — middle of business day
    )

    n = counter.next()
    txn_id = f"tx-breach-{n:04d}"
    transfer_id = f"tr-breach-{n:04d}"
    debit_money = -p.amount  # outbound = Debit; sign-direction agreement

    return [
        # Customer DDA debit leg (the breaching one)
        _txn_row(
            id_=txn_id,
            account_id=ti.account_id,
            account_name=ti.name,
            account_role=ti.template_role,
            account_scope=template.scope,
            account_parent_role=parent_role,
            money=debit_money,
            direction="Debit",
            posting=posting_ts,
            transfer_id=transfer_id,
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata={"customer_id": str(ti.account_id)},
        ),
        # External counter-leg (no balance tracking, but needed for Conservation)
        _txn_row(
            id_=f"{txn_id}-ext",
            account_id=counter_account.id,
            account_name=counter_name,
            account_role=counter_role,
            account_scope=counter_account.scope,
            account_parent_role=counter_account.parent_role,
            money=p.amount,  # +ve: external receives
            direction="Credit",
            posting=posting_ts,
            transfer_id=transfer_id,
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata={"customer_id": str(ti.account_id)},
        ),
    ]


def _emit_drift_background_rows(
    p: DriftPlant,
    instance: L2Instance,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    parent_singleton_by_role: dict[Identifier, Account],
    counter: _Counter,
) -> list[str]:
    """For drift planting we want SOME postings on the day so the computed
    balance is meaningful. Plant two normal credits, each $100, so the
    computed balance is $200. The drift row will then state a different
    stored balance to surface the drift.

    The rail used is whatever ``p.rail_name`` declares; its
    ``transfer_type`` and per-leg origins come from the rail's L2
    declaration. The counter-leg is the L2 Account named by
    ``p.counter_account_id``.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    rail = _resolve_rail(p.rail_name, instance)
    counter_account = _resolve_account(p.counter_account_id, instance)
    counter_name = counter_account.name or Name(str(counter_account.id))
    counter_role = counter_account.role or Identifier(str(counter_account.id))
    counter_origin = _counter_origin_for_drift(rail)
    customer_origin = _customer_origin_for_drift(rail)
    drift_day = scenarios.today - timedelta(days=p.days_ago)
    rows: list[str] = []

    for hour in (9, 14):  # two credits during the business day
        n = counter.next()
        txn_id = f"tx-drift-{n:04d}"
        transfer_id = f"tr-drift-{n:04d}"
        posting_ts = f"{drift_day.isoformat()}T{hour:02d}:00:00+00:00"
        rows.extend([
            # External debit leg
            _txn_row(
                id_=f"{txn_id}-ext",
                account_id=counter_account.id,
                account_name=counter_name,
                account_role=counter_role,
                account_scope=counter_account.scope,
                account_parent_role=counter_account.parent_role,
                money=Decimal("-100.00"),
                direction="Debit",
                posting=posting_ts,
                transfer_id=transfer_id,
                transfer_type=rail.transfer_type,
                rail_name=p.rail_name,
                origin=counter_origin,
                metadata={"customer_id": str(ti.account_id),
                          "external_reference": f"ER-{n:04d}"},
            ),
            # Customer DDA credit leg (the one we're tracking)
            _txn_row(
                id_=txn_id,
                account_id=ti.account_id,
                account_name=ti.name,
                account_role=ti.template_role,
                account_scope=template.scope,
                account_parent_role=parent_role,
                money=Decimal("100.00"),
                direction="Credit",
                posting=posting_ts,
                transfer_id=transfer_id,
                transfer_type=rail.transfer_type,
                rail_name=p.rail_name,
                origin=customer_origin,
                metadata={"customer_id": str(ti.account_id),
                          "external_reference": f"ER-{n:04d}"},
            ),
        ])
    return rows


def _resolve_rail(rail_name: Identifier, instance: L2Instance) -> Rail:
    """Find the L2-declared Rail by name; raise on miss."""
    for r in instance.rails:
        if r.name == rail_name:
            return r
    raise KeyError(
        f"rail {rail_name!r} not declared in instance.rails; "
        f"plant references a rail that doesn't exist in the L2 YAML"
    )


def _customer_origin_for_drift(rail: Rail) -> str:
    """The customer-side leg's origin on a two-leg inbound drift rail.

    Two-leg rails carry per-leg origins (source_origin / destination_origin)
    or a shared rail-level origin. For drift background, the customer
    DDA receives the credit (destination side); fall back through the
    L2 origin-resolution table.
    """
    if isinstance(rail, TwoLegRail) and rail.destination_origin is not None:
        return str(rail.destination_origin)
    if rail.origin is not None:
        return str(rail.origin)
    return "InternalInitiated"


def _counter_origin_for_drift(rail: Rail) -> str:
    """The external-side leg's origin on a two-leg inbound drift rail."""
    if isinstance(rail, TwoLegRail) and rail.source_origin is not None:
        return str(rail.source_origin)
    if rail.origin is not None:
        return str(rail.origin)
    return "ExternalForcePosted"


def _emit_drift_balance_row(
    p: DriftPlant,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
) -> str:
    """Emit one daily_balances row whose `money` differs from the sum of
    that day's planted credits ($200) by `delta_money`.

    Surfaces drift = stored - computed = $200 + delta - $200 = delta.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    drift_day = scenarios.today - timedelta(days=p.days_ago)
    computed_from_postings = Decimal("200.00")
    stored = computed_from_postings + p.delta_money
    return _balance_row(
        account_id=ti.account_id,
        account_name=ti.name,
        account_role=ti.template_role,
        account_scope=template.scope,
        account_parent_role=parent_role,
        day=drift_day,
        money=stored,
    )


def _emit_overdraft_balance_row(
    p: OverdraftPlant,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
) -> str:
    """Emit one daily_balances row with negative money — overdraft."""
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    if p.money >= 0:
        raise ValueError(
            f"OverdraftPlant.money must be negative; got {p.money!r}"
        )
    overdraft_day = scenarios.today - timedelta(days=p.days_ago)
    return _balance_row(
        account_id=ti.account_id,
        account_name=ti.name,
        account_role=ti.template_role,
        account_scope=template.scope,
        account_parent_role=parent_role,
        day=overdraft_day,
        money=p.money,
    )


def _emit_stuck_pending_rows(
    p: StuckPendingPlant,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    counter: _Counter,
) -> list[str]:
    """Plant ONE Pending leg (no external counter-leg — Pending legs
    haven't traversed the rail yet so the counter-leg doesn't exist).

    The rail's `max_pending_age` cap (inlined into the
    `<prefix>_stuck_pending` view at schema-emit time) determines
    when this surfaces; pick `days_ago` past whatever cap the chosen
    rail carries.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    plant_day = scenarios.today - timedelta(days=p.days_ago)
    posting_ts = f"{plant_day.isoformat()}T10:00:00+00:00"
    n = counter.next()
    return [
        _txn_row(
            id_=f"tx-pending-{n:04d}",
            account_id=ti.account_id,
            account_name=ti.name,
            account_role=ti.template_role,
            account_scope=template.scope,
            account_parent_role=parent_role,
            money=-p.amount,  # Debit
            direction="Debit",
            posting=posting_ts,
            transfer_id=f"tr-pending-{n:04d}",
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata={"customer_id": str(ti.account_id)},
            status="Pending",
        ),
    ]


def _emit_stuck_unbundled_rows(
    p: StuckUnbundledPlant,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    counter: _Counter,
) -> list[str]:
    """Plant ONE Posted leg with `bundle_id IS NULL` on a rail whose
    `max_unbundled_age` cap has been exceeded.

    Per validator R8, `max_unbundled_age` is only meaningful on rails
    that appear in some AggregatingRail's `bundles_activity`. Pick a
    rail name + days_ago that satisfies both conditions.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    plant_day = scenarios.today - timedelta(days=p.days_ago)
    posting_ts = f"{plant_day.isoformat()}T11:00:00+00:00"
    n = counter.next()
    return [
        _txn_row(
            id_=f"tx-unbundled-{n:04d}",
            account_id=ti.account_id,
            account_name=ti.name,
            account_role=ti.template_role,
            account_scope=template.scope,
            account_parent_role=parent_role,
            money=-p.amount,  # Debit (fee accrual)
            direction="Debit",
            posting=posting_ts,
            transfer_id=f"tr-unbundled-{n:04d}",
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata={"customer_id": str(ti.account_id)},
            # status defaults to Posted; bundle_id stays NULL — that's
            # the whole point.
        ),
    ]


def _emit_supersession_rows(
    p: SupersessionPlant,
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    counter: _Counter,
) -> list[str]:
    """Plant TWO transactions sharing one logical `id` — the original
    + a TechnicalCorrection rewrite.

    PostgreSQL's BIGSERIAL `entry` column auto-increments per insert,
    so the second row lands at a higher entry value; the M.2b.12
    Supersession Audit dataset's `COUNT(*) OVER (PARTITION BY id) > 1`
    catches the pair. No counter-leg — the corrected leg is the audit
    artifact, not a Conservation-bearing transfer.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
    plant_day = scenarios.today - timedelta(days=p.days_ago)
    n = counter.next()
    txn_id = f"tx-supersedes-{n:04d}"
    transfer_id = f"tr-supersedes-{n:04d}"
    metadata = {"customer_id": str(ti.account_id)}
    return [
        # Original posting at 09:00.
        _txn_row(
            id_=txn_id,
            account_id=ti.account_id,
            account_name=ti.name,
            account_role=ti.template_role,
            account_scope=template.scope,
            account_parent_role=parent_role,
            money=-p.original_amount,
            direction="Debit",
            posting=f"{plant_day.isoformat()}T09:00:00+00:00",
            transfer_id=transfer_id,
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata=metadata,
        ),
        # TechnicalCorrection at 09:30 — same logical id, different
        # amount, supersedes='TechnicalCorrection'.
        _txn_row(
            id_=txn_id,
            account_id=ti.account_id,
            account_name=ti.name,
            account_role=ti.template_role,
            account_scope=template.scope,
            account_parent_role=parent_role,
            money=-p.corrected_amount,
            direction="Debit",
            posting=f"{plant_day.isoformat()}T09:30:00+00:00",
            transfer_id=transfer_id,
            transfer_type=p.transfer_type,
            rail_name=p.rail_name,
            origin="InternalInitiated",
            metadata=metadata,
            supersedes="TechnicalCorrection",
        ),
    ]


def _txn_row(
    *,
    id_: str,
    account_id: Identifier,
    account_name: Name,
    account_role: Identifier,
    account_scope: str,
    account_parent_role: Identifier | None,
    money: Decimal,
    direction: str,
    posting: str,
    transfer_id: str,
    transfer_type: str,
    rail_name: Identifier,
    origin: str,
    metadata: dict[str, str],
    status: str = "Posted",
    bundle_id: str | None = None,
    supersedes: str | None = None,
) -> str:
    """Build one VALUES row for the transactions INSERT.

    `status` defaults to 'Posted' — the M.2.2 baseline scenarios all
    plant Posted legs. `bundle_id` and `supersedes` default to NULL —
    M.2b.14 plants exercise them for stuck-Unbundled / supersession
    scenarios. Static columns we don't currently exercise
    (transfer_completion, transfer_parent_id, template_name) emit
    as NULL.
    """
    parent_role_lit = (
        _sql_str(account_parent_role) if account_parent_role else "NULL"
    )
    metadata_json = (
        "{" + ", ".join(
            f'"{k}": "{v}"' for k, v in sorted(metadata.items())
        ) + "}"
    )
    bundle_lit = _sql_str(bundle_id) if bundle_id is not None else "NULL"
    supersedes_lit = _sql_str(supersedes) if supersedes is not None else "NULL"
    return (
        f"({_sql_str(id_)}, {_sql_str(account_id)}, "
        f"{_sql_str(account_name)}, {_sql_str(account_role)}, "
        f"{_sql_str(account_scope)}, {parent_role_lit}, "
        f"{money}, {_sql_str(direction)}, {_sql_str(status)}, "
        f"{_sql_str(posting)}, {_sql_str(transfer_id)}, "
        f"{_sql_str(transfer_type)}, NULL, NULL, "
        f"{_sql_str(rail_name)}, NULL, {bundle_lit}, {supersedes_lit}, "
        f"{_sql_str(origin)}, {_sql_str(metadata_json)})"
    )


def _balance_row(
    *,
    account_id: Identifier,
    account_name: Name,
    account_role: Identifier,
    account_scope: str,
    account_parent_role: Identifier | None,
    day: date,
    money: Decimal,
) -> str:
    """Build one VALUES row for the daily_balances INSERT."""
    parent_role_lit = (
        _sql_str(account_parent_role) if account_parent_role else "NULL"
    )
    return (
        f"({_sql_str(account_id)}, {_sql_str(account_name)}, "
        f"{_sql_str(account_role)}, {_sql_str(account_scope)}, "
        f"{parent_role_lit}, NULL, "
        f"{_sql_str(_bod_timestamp(day))}, "
        f"{_sql_str(_eod_timestamp(day))}, "
        f"{money}, NULL, NULL)"
    )


def _sql_str(s: object) -> str:
    """Render an arbitrary value as a SQL string literal (single-quoted,
    embedded quotes doubled). Used for every text column in the seed."""
    return "'" + str(s).replace("'", "''") + "'"
