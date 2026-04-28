"""Auto-derive a ``ScenarioPlant`` covering every L1 invariant from an L2 instance.

Companion to ``common.l2.seed`` — that module owns the typed plant
primitives + ``emit_seed`` machinery; this module knows how to walk an
arbitrary L2 instance and pick representative entities so an
integrator can run ``quicksight-gen demo seed-l2 myorg.yaml`` and get
a working seed without authoring scenarios in Python.

Heuristics (deterministic, sorted by stable keys at every choice point):

- **TemplateInstance**: materialize 2 synthetic instances under the
  first ``AccountTemplate`` (sorted by role name). Synthetic ids are
  ``cust-001`` / ``cust-002``, names ``Customer 1`` / ``Customer 2``.
  Persona-blind by construction.
- **DriftPlant**: pick the first 2-leg Rail (sorted by name) whose
  destination_role matches the template, AND has at least one
  external-scope Account whose role matches the source side. Use that
  external Account as the counter.
- **OverdraftPlant**: needs only a TemplateInstance — no rail. Plant
  on the second customer.
- **LimitBreachPlant**: first ``LimitSchedule`` (sorted by
  parent_role + transfer_type) whose transfer_type matches some
  outbound 2-leg Rail (source = template role, destination = external
  role). Plant amount = cap × 1.5 to guarantee breach.
- **StuckPendingPlant**: first Rail (sorted by name) with
  ``max_pending_age`` set.
- **StuckUnbundledPlant**: first Rail with ``max_unbundled_age`` set.
  Validator R8 guarantees such a rail is bundled by some aggregating
  rail, so the resulting Posted leg surfaces in
  ``<prefix>_stuck_unbundled``.
- **SupersessionPlant**: first single-leg Rail or any Rail with a
  customer-side leg.

Plants that can't be derived (e.g., no LimitSchedule declared, no
2-leg inbound rail) are omitted from the returned ``ScenarioPlant``.
The CLI surface logs a one-line warning per omission so the
integrator knows what's missing from their YAML for full coverage.

The auto-scenario deliberately does NOT try to produce byte-identical
output to the curated ``default_ar_scenario`` — the two are different
contracts. ``default_ar_scenario`` is the hash-locked canonical AR
fixture; this module produces a reasonable starting demo for ANY L2.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from .primitives import (
    Account,
    AccountTemplate,
    Identifier,
    L2Instance,
    LimitSchedule,
    Name,
    Rail,
    RoleExpression,
    SingleLegRail,
    TwoLegRail,
)
from .seed import (
    DriftPlant,
    LimitBreachPlant,
    OverdraftPlant,
    ScenarioPlant,
    StuckPendingPlant,
    StuckUnbundledPlant,
    SupersessionPlant,
    TemplateInstance,
    TransferTemplatePlant,
)


@dataclass(frozen=True, slots=True)
class AutoScenarioReport:
    """Describes which plants the auto-scenario emitted vs. omitted.

    The CLI prints this so the integrator knows what's missing from
    their YAML for full L1 coverage.
    """

    scenario: ScenarioPlant
    omitted: tuple[tuple[str, str], ...]   # (plant_kind, reason) pairs


def default_scenario_for(
    instance: L2Instance,
    *,
    today: date | None = None,
) -> AutoScenarioReport:
    """Walk ``instance`` and return an auto-derived ``ScenarioPlant``.

    See module docstring for per-plant heuristics. Returns the
    scenario plus a report of any plant kinds that couldn't be
    materialized from this instance (e.g., no ``LimitSchedule``
    declared → no LimitBreachPlant).
    """
    today_ref = today or datetime.now(tz=timezone.utc).date()
    omitted: list[tuple[str, str]] = []

    # -- Pick template + materialize 2 customer instances ------------
    template = _pick_template(instance)
    if template is None:
        return AutoScenarioReport(
            scenario=ScenarioPlant(template_instances=(), today=today_ref),
            omitted=(("ALL", "no AccountTemplate declared in instance"),),
        )
    cust1, cust2 = _materialize_instances(template)

    # -- Pre-compute pickable structures ----------------------------
    drift_rail = _pick_inbound_2leg_rail(instance, template.role)
    if drift_rail is None:
        omitted.append(("DriftPlant",
                        "no 2-leg Rail with destination matching template role"))
    breach_picks = _pick_breach_inputs(instance, template.role)
    if breach_picks is None:
        omitted.append(("LimitBreachPlant",
                        "no LimitSchedule whose transfer_type matches an "
                        "outbound 2-leg Rail with external counter"))
    pending_rail = _pick_first_with(
        instance.rails, key=lambda r: r.max_pending_age is not None,
    )
    if pending_rail is None:
        omitted.append(("StuckPendingPlant",
                        "no Rail declares max_pending_age"))
    unbundled_rail = _pick_first_with(
        instance.rails, key=lambda r: r.max_unbundled_age is not None,
    )
    if unbundled_rail is None:
        omitted.append(("StuckUnbundledPlant",
                        "no Rail declares max_unbundled_age"))
    super_rail = _pick_supersession_rail(instance, template.role)
    if super_rail is None:
        omitted.append(("SupersessionPlant",
                        "no single-leg Rail with leg_role matching "
                        "template role"))

    # External counter for drift + limit-breach plants. Falls back to
    # any external Account if the rail-aware lookup misses.
    drift_counter = (
        _pick_external_counter_for_rail(instance, drift_rail)
        if drift_rail is not None else None
    )

    # -- Assemble the scenario ---------------------------------------
    drift_plants: tuple[DriftPlant, ...] = ()
    if drift_rail is not None and drift_counter is not None:
        drift_plants = (
            DriftPlant(
                account_id=cust1.account_id,
                days_ago=5,
                delta_money=Decimal("75.00"),
                rail_name=drift_rail.name,
                counter_account_id=drift_counter.id,
            ),
        )
    elif drift_rail is not None and drift_counter is None:
        omitted.append(("DriftPlant",
                        f"rail {drift_rail.name!r} has no external Account "
                        f"matching its source role"))

    overdraft_plants = (
        OverdraftPlant(
            account_id=cust2.account_id,
            days_ago=6,
            money=Decimal("-1500.00"),
        ),
    )

    limit_breach_plants: tuple[LimitBreachPlant, ...] = ()
    if breach_picks is not None:
        ls, breach_rail, breach_counter = breach_picks
        # Plant amount = cap * 1.5, rounded to whole dollars, to
        # guarantee OutboundFlow > cap regardless of rounding.
        breach_amount = (ls.cap * Decimal("1.5")).quantize(Decimal("1"))
        limit_breach_plants = (
            LimitBreachPlant(
                account_id=cust1.account_id,
                days_ago=4,
                transfer_type=ls.transfer_type,
                rail_name=breach_rail.name,
                amount=breach_amount,
                counter_account_id=breach_counter.id,
            ),
        )

    stuck_pending_plants: tuple[StuckPendingPlant, ...] = ()
    if pending_rail is not None:
        stuck_pending_plants = (
            StuckPendingPlant(
                account_id=cust1.account_id,
                days_ago=2,
                transfer_type=pending_rail.transfer_type,
                rail_name=pending_rail.name,
                amount=Decimal("450.00"),
            ),
        )

    stuck_unbundled_plants: tuple[StuckUnbundledPlant, ...] = ()
    if unbundled_rail is not None:
        # max_unbundled_age caps vary widely (PT4H ↔ P31D); plant
        # comfortably past the cap by adding 7 days.
        cap_days = max(
            1,
            int((unbundled_rail.max_unbundled_age or _zero_td()).total_seconds()
                // 86400) + 7,
        )
        stuck_unbundled_plants = (
            StuckUnbundledPlant(
                account_id=cust2.account_id,
                days_ago=cap_days,
                transfer_type=unbundled_rail.transfer_type,
                rail_name=unbundled_rail.name,
                amount=Decimal("12.50"),
            ),
        )

    supersession_plants: tuple[SupersessionPlant, ...] = ()
    if super_rail is not None:
        supersession_plants = (
            SupersessionPlant(
                account_id=cust1.account_id,
                days_ago=3,
                transfer_type=super_rail.transfer_type,
                rail_name=super_rail.name,
                original_amount=Decimal("250.00"),
                corrected_amount=Decimal("275.00"),
            ),
        )

    # M.3.10g — TransferTemplate firings. For every L2-declared
    # template whose first leg_rail is a TwoLegRail with
    # expected_net=0 AND we can resolve accounts for both source +
    # destination roles, plant 2 firings (so two distinct shared
    # Transfers appear per template, exercising the transfer_key
    # Metadata-grouping).
    tt_plants_list: list[TransferTemplatePlant] = []
    for tt in sorted(
        instance.transfer_templates, key=lambda t: str(t.name)
    ):
        if not tt.leg_rails:
            omitted.append((
                f"TransferTemplatePlant[{tt.name}]",
                "template has no leg_rails declared",
            ))
            continue
        first_rail = _resolve_rail_by_name(tt.leg_rails[0], instance)
        if not isinstance(first_rail, TwoLegRail):
            omitted.append((
                f"TransferTemplatePlant[{tt.name}]",
                f"first leg_rail {tt.leg_rails[0]!r} is not a TwoLegRail "
                f"(M.3.10g first cut handles only the simple two-leg case)",
            ))
            continue
        if tt.expected_net != Decimal("0"):
            omitted.append((
                f"TransferTemplatePlant[{tt.name}]",
                f"expected_net != 0 ({tt.expected_net}); "
                f"non-zero net plants deferred",
            ))
            continue
        src_id = _pick_account_id_for_role_expr(
            first_rail.source_role, instance, template, cust1,
        )
        if src_id is None:
            omitted.append((
                f"TransferTemplatePlant[{tt.name}]",
                f"no Account or template-instance matching source_role "
                f"{first_rail.source_role!r}",
            ))
            continue
        dst_id = _pick_account_id_for_role_expr(
            first_rail.destination_role, instance, template, cust1,
        )
        if dst_id is None:
            omitted.append((
                f"TransferTemplatePlant[{tt.name}]",
                f"no Account or template-instance matching destination_role "
                f"{first_rail.destination_role!r}",
            ))
            continue
        # Pre-resolve chain children for the first firing of each
        # template (M.3.10h). Scan declared chains for entries whose
        # parent matches this template name; for each, resolve the
        # child rail + an account matching the child rail's role
        # expression. The first firing then plants matched children
        # for every declared chain edge, giving the visualization a
        # variety of (matched, orphan) parent firings to display.
        # The second firing leaves chain_children empty — that
        # parent's chain edges all surface as orphans.
        chain_children_for_firing_1 = _pick_chain_children_for_template(
            tt.name, instance, template, cust1,
        )
        for firing_seq in (1, 2):
            tt_plants_list.append(TransferTemplatePlant(
                template_name=tt.name,
                # Stagger days so the two firings spread across the
                # date window — gives the explorer something visual.
                days_ago=2 + firing_seq,
                amount=Decimal("125.00"),
                source_account_id=src_id,
                destination_account_id=dst_id,
                firing_seq=firing_seq,
                chain_children=(
                    chain_children_for_firing_1
                    if firing_seq == 1 else ()
                ),
            ))
    transfer_template_plants = tuple(tt_plants_list)
    if not instance.transfer_templates:
        omitted.append((
            "TransferTemplatePlant",
            "no TransferTemplate declared in instance",
        ))

    scenario = ScenarioPlant(
        template_instances=(cust1, cust2),
        drift_plants=drift_plants,
        overdraft_plants=overdraft_plants,
        limit_breach_plants=limit_breach_plants,
        stuck_pending_plants=stuck_pending_plants,
        stuck_unbundled_plants=stuck_unbundled_plants,
        supersession_plants=supersession_plants,
        transfer_template_plants=transfer_template_plants,
        today=today_ref,
    )
    return AutoScenarioReport(scenario=scenario, omitted=tuple(omitted))


# -- Picker helpers ----------------------------------------------------------


def _pick_template(instance: L2Instance) -> AccountTemplate | None:
    """First AccountTemplate sorted by role name; None if none declared."""
    if not instance.account_templates:
        return None
    return sorted(instance.account_templates, key=lambda t: str(t.role))[0]


def _materialize_instances(
    template: AccountTemplate,
) -> tuple[TemplateInstance, TemplateInstance]:
    """Synthesize 2 generic customer instances under the template."""
    return (
        TemplateInstance(
            template_role=template.role,
            account_id=Identifier("cust-001"),
            name=Name("Customer 1"),
        ),
        TemplateInstance(
            template_role=template.role,
            account_id=Identifier("cust-002"),
            name=Name("Customer 2"),
        ),
    )


def _pick_inbound_2leg_rail(
    instance: L2Instance, template_role: Identifier,
) -> TwoLegRail | None:
    """First TwoLegRail (sorted by name) whose destination_role includes
    the template role — i.e., money flows INTO the customer."""
    candidates = [
        r for r in instance.rails
        if isinstance(r, TwoLegRail)
        and template_role in r.destination_role
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: str(r.name))[0]


def _pick_outbound_2leg_rail(
    instance: L2Instance,
    template_role: Identifier,
    transfer_type: str,
) -> TwoLegRail | None:
    """First TwoLegRail (sorted by name) with source_role=template AND
    matching transfer_type AND a destination role that resolves to an
    external Account."""
    external_roles = {a.role for a in instance.accounts if a.scope == "external"}
    for r in sorted(instance.rails, key=lambda r: str(r.name)):
        if not isinstance(r, TwoLegRail):
            continue
        if r.transfer_type != transfer_type:
            continue
        if template_role not in r.source_role:
            continue
        if any(role in external_roles for role in r.destination_role):
            return r
    return None


def _pick_external_counter_for_rail(
    instance: L2Instance, rail: TwoLegRail,
) -> Account | None:
    """Find an external-scope Account whose role appears in the rail's
    counter side. For inbound rails, counter = source. Sorted by id."""
    candidate_roles = set(rail.source_role)
    candidates = [
        a for a in instance.accounts
        if a.scope == "external" and a.role in candidate_roles
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda a: str(a.id))[0]


def _pick_external_counter_for_outbound(
    instance: L2Instance, rail: TwoLegRail,
) -> Account | None:
    """For outbound rails, counter = destination."""
    candidate_roles = set(rail.destination_role)
    candidates = [
        a for a in instance.accounts
        if a.scope == "external" and a.role in candidate_roles
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda a: str(a.id))[0]


def _resolve_rail_by_name(
    rail_name: Identifier, instance: L2Instance,
) -> Rail | None:
    """Find the L2-declared Rail by name; None on miss. Used by the TT
    picker when validating a template's first leg_rail is a TwoLegRail.
    """
    for r in instance.rails:
        if r.name == rail_name:
            return r
    return None


def _pick_chain_children_for_template(
    template_name: Identifier,
    instance: L2Instance,
    template: AccountTemplate,
    customer_instance: TemplateInstance,
) -> tuple[tuple[Identifier, Identifier], ...]:
    """Pre-resolve chain-child (rail_name, account_id) pairs for a TT
    plant's first firing (M.3.10h).

    For each declared ChainEntry whose parent matches the template
    name, resolve the child rail (must exist in instance.rails) and
    pick an account by the child rail's role expression. Aggregating
    rails are skipped — they don't have per-Transfer parents.

    Returns the pairs in declaration order; entries that can't resolve
    to a rail or an account are silently skipped (the chain
    detection just doesn't see a matched child for them, which
    naturally surfaces as an orphan in the dashboard).
    """
    pairs: list[tuple[Identifier, Identifier]] = []
    for chain in instance.chains:
        if chain.parent != template_name:
            continue
        child_rail = _resolve_rail_by_name(chain.child, instance)
        if child_rail is None:
            continue
        # Aggregating rails sweep on cadence, not per-Transfer — they
        # MUST NOT appear as chain children per SPEC. The validator
        # enforces this at L2 load time, but a defensive skip here
        # also avoids planting a chain child that can't legitimately
        # exist in the data.
        if child_rail.aggregating:
            continue
        # Pick the role expression from the child rail's leg side
        # most likely to surface in the data. For a TwoLegRail use
        # destination_role (where money lands — the receiving party's
        # account); for a SingleLegRail use leg_role.
        if isinstance(child_rail, TwoLegRail):
            role_expr = child_rail.destination_role
        else:
            role_expr = child_rail.leg_role
        account_id = _pick_account_id_for_role_expr(
            role_expr, instance, template, customer_instance,
        )
        if account_id is None:
            # Fallback: child rail's role might be an unmaterialized
            # account-template role (e.g. MerchantDDA when only
            # CustomerDDA is materialized). The chain detection SQL
            # only checks rail_name + transfer_parent_id, not
            # account roles, so any account works for the test.
            # Land the leg on the customer instance so it's at least
            # observable in the data.
            account_id = customer_instance.account_id
        pairs.append((chain.child, account_id))
    return tuple(pairs)


def _pick_account_id_for_role_expr(
    role_expr: RoleExpression,
    instance: L2Instance,
    template: AccountTemplate,
    customer_instance: TemplateInstance,
) -> Identifier | None:
    """Pick an account_id whose role matches one of the role expression's
    members (M.3.10g TT plant picker).

    Resolution order — first match wins:

    1. If the role matches the customer template's role, use the
       materialized customer (so a CustomerDDA-side leg lands on a real
       customer instance, not a synthetic singleton).
    2. Any L2 Account whose role appears in the role expression,
       sorted by id for determinism.

    Returns ``None`` if no candidate exists. The caller treats that
    as "omit this plant".
    """
    candidate_roles = set(role_expr)
    if template.role in candidate_roles:
        return customer_instance.account_id
    candidates = [
        a for a in instance.accounts if a.role in candidate_roles
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda a: str(a.id))[0].id


def _pick_breach_inputs(
    instance: L2Instance, template_role: Identifier,
) -> tuple[LimitSchedule, TwoLegRail, Account] | None:
    """Find a (LimitSchedule, outbound Rail, external Account) triple
    suitable for a LimitBreachPlant. Sorted by LimitSchedule key."""
    for ls in sorted(
        instance.limit_schedules,
        key=lambda ls: (str(ls.parent_role), ls.transfer_type),
    ):
        rail = _pick_outbound_2leg_rail(instance, template_role, ls.transfer_type)
        if rail is None:
            continue
        counter = _pick_external_counter_for_outbound(instance, rail)
        if counter is None:
            continue
        return (ls, rail, counter)
    return None


def _pick_first_with(
    items: Iterable[Rail], *, key: Callable[[Rail], bool],
) -> Rail | None:
    """First Rail satisfying ``key(rail)``; sorted by name for determinism."""
    matching = [r for r in items if key(r)]
    if not matching:
        return None
    return sorted(matching, key=lambda r: str(r.name))[0]


def _pick_supersession_rail(
    instance: L2Instance, template_role: Identifier,
) -> Rail | None:
    """A rail whose customer-side leg is the template role.

    Single-leg rails: leg_role = template. Two-leg rails: source or
    destination = template. First by name.
    """
    for r in sorted(instance.rails, key=lambda r: str(r.name)):
        if isinstance(r, SingleLegRail) and template_role in r.leg_role:
            return r
        if isinstance(r, TwoLegRail) and (
            template_role in r.source_role
            or template_role in r.destination_role
        ):
            return r
    return None


def _zero_td():
    """Convenience for the unbundled-rail cap fallback (shouldn't fire
    in practice — the picker only returns rails with the field set)."""
    from datetime import timedelta
    return timedelta(0)
