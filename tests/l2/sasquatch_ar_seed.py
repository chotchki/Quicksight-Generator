"""Demo seed generator for the Sasquatch AR L2 instance (M.2.2).

Produces deterministic SQL INSERTs against the v6 ``<prefix>_transactions``
+ ``<prefix>_daily_balances`` tables — i.e., what M.1.4's ``emit_schema``
emits — given a loaded ``L2Instance`` + a ``ScenarioPlant`` describing
which exception scenarios to surface.

Lives under ``tests/l2/`` because M.2.2's bar is "the schema accepts
L2-shaped data and exception queries surface the right rows" — the
generator is test infrastructure, not yet production. M.2.3+ wires the
AR app to consume the L2 instance; once that lands, the generator
moves under ``apps/account_recon/`` (or its successor under M.2a's
"L1 dashboard" reframing) and replaces today's ``demo_data.py``.

What this generator does:
- Materialize AccountTemplate instances (creates concrete customer
  DDAs / ZBA sub-accounts under their parent singletons).
- Plant 1 drift scenario, 1 overdraft scenario, 1 limit-breach scenario
  by default — enough to verify each L1 exception query surfaces a
  known row. Caller can plant additional scenarios via the
  ``ScenarioPlant`` dataclass.
- Emit deterministic SQL — reproducibility is load-bearing for the
  M.2.7 hash-lock. The generator avoids ``random``; every value is
  derived from explicit inputs.

What this generator does NOT do (intentionally):
- Reproduce today's full ``demo_data.py`` richness (~1800 lines, 80+
  background transactions, 5 baseline-clean customers, etc.). That's
  M.2.4 / M.2a / M.5 work; here we plant the minimum that exercises
  every exception query.
- Handle multi-leg TransferTemplate cycles, AggregatingRail bundling,
  or chain-required-true validation at the SQL level. Those primitives
  exist in the L2 instance but planting their runtime behavior is
  M.2a / M.3+ work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from quicksight_gen.common.l2 import (
    Account,
    AccountTemplate,
    Identifier,
    L2Instance,
    Name,
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
    """

    account_id: Identifier
    days_ago: int
    delta_money: Decimal


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
    """

    account_id: Identifier
    days_ago: int
    transfer_type: str
    rail_name: Identifier
    amount: Decimal             # absolute value; must exceed the cap


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
                p, scenarios, template_by_role,
                parent_singleton_by_role, txn_counter,
            )
        )

    for p in sorted(scenarios.drift_plants, key=_drift_key):
        txn_rows.extend(
            _emit_drift_background_rows(
                p, scenarios, template_by_role,
                parent_singleton_by_role, txn_counter,
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
-- Generated by tests.l2.sasquatch_ar_seed.emit_seed
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


def _eod_timestamp(d: date) -> str:
    """End-of-day UTC timestamp for `d` (i.e. start of next day)."""
    next_day = d + timedelta(days=1)
    return f"{next_day.isoformat()}T00:00:00+00:00"


def _bod_timestamp(d: date) -> str:
    """Beginning-of-day UTC timestamp for `d`."""
    return f"{d.isoformat()}T00:00:00+00:00"


def _emit_limit_breach_rows(
    p: LimitBreachPlant,
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
            account_id=Identifier("ext-frb-snb-master"),
            account_name=Name("Federal Reserve Bank — SNB Master"),
            account_role=Identifier("ExternalCounterparty"),
            account_scope="external",
            account_parent_role=None,
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
    scenarios: ScenarioPlant,
    template_by_role: dict[Identifier, AccountTemplate],
    parent_singleton_by_role: dict[Identifier, Account],
    counter: _Counter,
) -> list[str]:
    """For drift planting we want SOME postings on the day so the computed
    balance is meaningful. Plant two normal credits (inbound ACH), each $100,
    so the computed balance is $200. The drift row will then state a
    different stored balance to surface the drift.
    """
    ti = _resolve_template(p.account_id, scenarios)
    template = template_by_role[ti.template_role]
    parent_role = template.parent_role
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
                account_id=Identifier("ext-frb-snb-master"),
                account_name=Name("Federal Reserve Bank — SNB Master"),
                account_role=Identifier("ExternalCounterparty"),
                account_scope="external",
                account_parent_role=None,
                money=Decimal("-100.00"),
                direction="Debit",
                posting=posting_ts,
                transfer_id=transfer_id,
                transfer_type="ach",
                rail_name=Identifier("CustomerInboundACH"),
                origin="ExternalForcePosted",
                metadata={"external_reference": f"ER-{n:04d}",
                          "customer_id": str(ti.account_id)},
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
                transfer_type="ach",
                rail_name=Identifier("CustomerInboundACH"),
                origin="InternalInitiated",
                metadata={"external_reference": f"ER-{n:04d}",
                          "customer_id": str(ti.account_id)},
            ),
        ])
    return rows


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
) -> str:
    """Build one VALUES row for the transactions INSERT.

    Static columns we don't currently exercise (transfer_completion,
    transfer_parent_id, template_name, bundle_id, supersedes) emit as
    NULL — they're real columns the schema requires but the M.2.2
    scenario set doesn't plant rows that need them.
    """
    parent_role_lit = (
        _sql_str(account_parent_role) if account_parent_role else "NULL"
    )
    metadata_json = (
        "{" + ", ".join(
            f'"{k}": "{v}"' for k, v in sorted(metadata.items())
        ) + "}"
    )
    return (
        f"({_sql_str(id_)}, {_sql_str(account_id)}, "
        f"{_sql_str(account_name)}, {_sql_str(account_role)}, "
        f"{_sql_str(account_scope)}, {parent_role_lit}, "
        f"{money}, {_sql_str(direction)}, 'Posted', "
        f"{_sql_str(posting)}, {_sql_str(transfer_id)}, "
        f"{_sql_str(transfer_type)}, NULL, NULL, "
        f"{_sql_str(rail_name)}, NULL, NULL, NULL, "
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


# -- A canonical default scenario --------------------------------------------


def default_ar_scenario(today: date | None = None) -> ScenarioPlant:
    """The default M.2.2 scenario: one materialized DDA per planted
    exception, exactly enough to verify each L1 exception query surfaces
    a known row.

    Customer IDs reuse today's `apps/account_recon/demo_data.py` slugs
    (`cust-900-0001-bigfoot-brews` etc.) so cross-checking against the
    existing AR demo's row counts stays straightforward.
    """
    today_ref = today or datetime.now(tz=timezone.utc).date()
    instances = (
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-900-0001-bigfoot-brews"),
            name=Name("Bigfoot Brews — DDA"),
        ),
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-900-0002-sasquatch-sips"),
            name=Name("Sasquatch Sips — DDA"),
        ),
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-700-0001-big-meadow-dairy"),
            name=Name("Big Meadow Dairy — DDA"),
        ),
    )
    return ScenarioPlant(
        template_instances=instances,
        drift_plants=(
            DriftPlant(
                account_id=Identifier("cust-900-0001-bigfoot-brews"),
                days_ago=5,
                delta_money=Decimal("75.00"),  # +$75: stored is $75 too high
            ),
        ),
        overdraft_plants=(
            OverdraftPlant(
                account_id=Identifier("cust-900-0002-sasquatch-sips"),
                days_ago=6,
                money=Decimal("-1500.00"),  # $1.5k overdrawn
            ),
        ),
        limit_breach_plants=(
            LimitBreachPlant(
                account_id=Identifier("cust-700-0001-big-meadow-dairy"),
                days_ago=8,
                transfer_type="wire",
                rail_name=Identifier("CustomerOutboundWire"),
                amount=Decimal("22000.00"),  # > $15k wire cap
            ),
        ),
        today=today_ref,
    )
