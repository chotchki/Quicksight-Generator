"""Cross-entity validation for a loaded ``L2Instance`` (M.1.3).

The loader (M.1.2) catches malformed YAML + per-entity shape errors. This
module catches everything else the SPEC requires at load time — rules
that need to look across multiple entities to decide.

Public entry point: ``validate(instance)``. Raises ``L2ValidationError``
on the first failure with a message identifying the offending field +
the rule that failed.

**Locked rule (per L.1.18 + M.1.7):** every cross-entity validator that
``validate(instance)`` runs has a dedicated rejection test in
``tests/test_l2_validate.py``. The rule numbering in this docstring
matches the test names (e.g. rule U1 → ``test_u1_duplicate_account_id_rejected``).
Adding a new validator MUST land its rejection test in the same commit
that introduces it; the audit table below extends to cover the new rule.

Rules enforced (numbered for cross-reference with the test file):
  U1. Account.id values are unique within ``accounts``.
  U2. AccountTemplate.role values are unique within ``account_templates``.
  U3. Rail.name values are unique within ``rails``.
  U4. TransferTemplate.name values are unique within ``transfer_templates``.

  R1. Every Role referenced by a Rail (source_role / destination_role /
      leg_role) resolves to some Account.role OR AccountTemplate.role.
  R2. Every Account.parent_role resolves to some Account.role OR
      AccountTemplate.role.
  R3. Every AccountTemplate.parent_role MUST resolve to a singleton
      Account.role (NOT an AccountTemplate.role) — per the SPEC's
      "Singleton parent only" rule on AccountTemplate.
  R4. Every RailName in a TransferTemplate.leg_rails exists in ``rails``.
  R5. Every Chain.parent and Chain.child resolves to a Rail name OR
      TransferTemplate name.
  R6. Every LimitSchedule.parent_role resolves to some declared Role.

  C1. Every TransferTemplate contains at most one Variable-direction leg.
  C2. Every Chain.xor_group's members share the same Chain.parent.

  S1. A two-leg Rail that is NOT a TransferTemplate leg MUST have
      ``expected_net`` set.
  S2. A two-leg Rail that IS a TransferTemplate leg MUST NOT have
      ``expected_net`` set (the template owns the bundle's ExpectedNet).
  S3. Every NON-aggregating single-leg Rail MUST be reconciled — appears
      in some TransferTemplate.leg_rails OR some aggregating Rail's
      bundles_activity (matched by Rail.name OR Rail.transfer_type).
      Aggregating single-leg rails are exempt — they ARE the
      reconciliation mechanism (per SPEC's "single-leg sweep that lands
      in an external counterparty" example).
  S4. Aggregating Rails MUST NOT appear as Chain.child.
  S5. Aggregating Rails MUST declare both ``cadence`` and
      ``bundles_activity``.
  S6. Non-aggregating Rails MUST NOT declare ``cadence`` or
      ``bundles_activity``.

  V1. Every TransferTemplate.completion matches a v1
      CompletionExpression vocabulary literal.
  V2. Every aggregating Rail's cadence matches a v1 CadenceExpression
      vocabulary literal.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from .primitives import (
    Identifier,
    L2Instance,
    Rail,
    SingleLegRail,
    TwoLegRail,
)


# -- Errors -------------------------------------------------------------------


class L2ValidationError(ValueError):
    """Raised when a loaded ``L2Instance`` fails cross-entity validation."""


# -- Vocabulary literals (per SPEC v1) ----------------------------------------


_COMPLETION_PATTERNS = (
    re.compile(r"^business_day_end$"),
    re.compile(r"^business_day_end\+(\d+)d$"),
    re.compile(r"^month_end$"),
    re.compile(r"^metadata\.[A-Za-z_][A-Za-z0-9_]*$"),
)

_WEEKDAY_NAMES = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

_CADENCE_PATTERNS = (
    re.compile(r"^intraday-(\d+)h$"),
    re.compile(r"^daily-eod$"),
    re.compile(r"^daily-bod$"),
    re.compile(r"^weekly-(mon|tue|wed|thu|fri|sat|sun)$"),
    re.compile(r"^monthly-eom$"),
    re.compile(r"^monthly-bom$"),
    re.compile(r"^monthly-(\d+)$"),
)


def _completion_is_valid(expr: str) -> bool:
    return any(p.match(expr) for p in _COMPLETION_PATTERNS)


def _cadence_is_valid(expr: str) -> bool:
    for p in _CADENCE_PATTERNS:
        m = p.match(expr)
        if not m:
            continue
        # Bounds checks: monthly-N is day-of-month 1..31.
        if expr.startswith("monthly-") and expr not in ("monthly-eom", "monthly-bom"):
            day = int(m.group(1))
            if not 1 <= day <= 31:
                return False
        return True
    return False


# -- Public API --------------------------------------------------------------


def validate(instance: L2Instance) -> None:
    """Run every cross-entity validation rule on ``instance``.

    Fail-fast: raises ``L2ValidationError`` on the first rule violation
    with a message naming the offending field + the rule.
    """
    _check_unique_account_ids(instance)
    _check_unique_account_template_roles(instance)
    _check_unique_rail_names(instance)
    _check_unique_transfer_template_names(instance)

    account_roles = {a.role for a in instance.accounts if a.role is not None}
    template_roles = {t.role for t in instance.account_templates}
    all_roles = account_roles | template_roles
    rail_names = {r.name for r in instance.rails}
    template_names = {t.name for t in instance.transfer_templates}

    _check_role_references(instance, all_roles)
    _check_account_parent_role_resolves(instance, all_roles)
    _check_account_template_parent_role_is_singleton(
        instance, account_roles, template_roles,
    )
    _check_template_leg_rails_exist(instance, rail_names)
    _check_chain_endpoints_exist(instance, rail_names, template_names)
    _check_limit_schedule_parent_role_resolves(instance, all_roles)

    _check_variable_leg_count_per_template(instance)
    _check_chain_xor_group_consistency(instance)

    _check_two_leg_expected_net_consistency(instance)
    _check_single_leg_reconciliation(instance)
    _check_chain_aggregating_not_child(instance)
    _check_aggregating_rail_required_fields(instance)
    _check_non_aggregating_rail_no_cadence_or_bundles(instance)

    _check_completion_vocabulary(instance)
    _check_cadence_vocabulary(instance)


# -- Uniqueness (U1-U4) ------------------------------------------------------


def _check_unique_account_ids(inst: L2Instance) -> None:
    """U1."""
    _reject_duplicates(
        (a.id for a in inst.accounts), label="Account.id",
    )


def _check_unique_account_template_roles(inst: L2Instance) -> None:
    """U2."""
    _reject_duplicates(
        (t.role for t in inst.account_templates), label="AccountTemplate.role",
    )


def _check_unique_rail_names(inst: L2Instance) -> None:
    """U3."""
    _reject_duplicates(
        (r.name for r in inst.rails), label="Rail.name",
    )


def _check_unique_transfer_template_names(inst: L2Instance) -> None:
    """U4."""
    _reject_duplicates(
        (t.name for t in inst.transfer_templates),
        label="TransferTemplate.name",
    )


def _reject_duplicates(values: Iterable[Identifier], *, label: str) -> None:
    counts = Counter(values)
    dupes = sorted(v for v, c in counts.items() if c > 1)
    if dupes:
        raise L2ValidationError(
            f"duplicate {label} values: {dupes!r}"
        )


# -- Reference resolution (R1-R6) --------------------------------------------


def _check_role_references(inst: L2Instance, all_roles: set[Identifier]) -> None:
    """R1: Every Role referenced by a Rail's role fields resolves to a declared Role."""
    for r in inst.rails:
        match r:
            case TwoLegRail(name=n, source_role=src, destination_role=dst):
                _check_role_set(src, all_roles, where=f"Rail {n!r}.source_role")
                _check_role_set(dst, all_roles, where=f"Rail {n!r}.destination_role")
            case SingleLegRail(name=n, leg_role=leg):
                _check_role_set(leg, all_roles, where=f"Rail {n!r}.leg_role")


def _check_role_set(
    roles: tuple[Identifier, ...], declared: set[Identifier], *, where: str,
) -> None:
    missing = [r for r in roles if r not in declared]
    if missing:
        raise L2ValidationError(
            f"{where}: roles {missing!r} are not declared on any "
            f"Account or AccountTemplate"
        )


def _check_account_parent_role_resolves(
    inst: L2Instance, all_roles: set[Identifier],
) -> None:
    """R2: every Account.parent_role resolves to some declared Role."""
    for a in inst.accounts:
        if a.parent_role is not None and a.parent_role not in all_roles:
            raise L2ValidationError(
                f"Account {a.id!r}.parent_role={a.parent_role!r}: "
                f"role is not declared on any Account or AccountTemplate"
            )


def _check_account_template_parent_role_is_singleton(
    inst: L2Instance,
    account_roles: set[Identifier],
    template_roles: set[Identifier],
) -> None:
    """R3: AccountTemplate.parent_role MUST resolve to a singleton Account.

    Per SPEC: template-under-template nesting is forbidden because the
    per-instance parent assignment becomes ambiguous (which of N
    parent-template instances does a given child-template instance roll
    up to?).
    """
    for t in inst.account_templates:
        if t.parent_role is None:
            continue
        if t.parent_role in template_roles and t.parent_role not in account_roles:
            raise L2ValidationError(
                f"AccountTemplate {t.role!r}.parent_role={t.parent_role!r}: "
                f"resolves to another AccountTemplate, but parent_role MUST "
                f"resolve to a singleton Account (template-under-template "
                f"nesting is forbidden)"
            )
        if t.parent_role not in account_roles:
            raise L2ValidationError(
                f"AccountTemplate {t.role!r}.parent_role={t.parent_role!r}: "
                f"role is not declared on any Account"
            )


def _check_template_leg_rails_exist(
    inst: L2Instance, rail_names: set[Identifier],
) -> None:
    """R4: every RailName in TransferTemplate.leg_rails exists."""
    for t in inst.transfer_templates:
        missing = [n for n in t.leg_rails if n not in rail_names]
        if missing:
            raise L2ValidationError(
                f"TransferTemplate {t.name!r}.leg_rails: rails {missing!r} "
                f"are not declared in rails"
            )


def _check_chain_endpoints_exist(
    inst: L2Instance,
    rail_names: set[Identifier],
    template_names: set[Identifier],
) -> None:
    """R5: every Chain.parent and Chain.child resolves to a Rail or Template."""
    valid = rail_names | template_names
    for i, c in enumerate(inst.chains):
        if c.parent not in valid:
            raise L2ValidationError(
                f"chains[{i}].parent={c.parent!r}: not a declared Rail "
                f"or TransferTemplate name"
            )
        if c.child not in valid:
            raise L2ValidationError(
                f"chains[{i}].child={c.child!r}: not a declared Rail "
                f"or TransferTemplate name"
            )


def _check_limit_schedule_parent_role_resolves(
    inst: L2Instance, all_roles: set[Identifier],
) -> None:
    """R6: every LimitSchedule.parent_role resolves to some declared Role."""
    for i, ls in enumerate(inst.limit_schedules):
        if ls.parent_role not in all_roles:
            raise L2ValidationError(
                f"limit_schedules[{i}].parent_role={ls.parent_role!r}: "
                f"role is not declared on any Account or AccountTemplate"
            )


# -- Cardinality (C1-C2) -----------------------------------------------------


def _check_variable_leg_count_per_template(inst: L2Instance) -> None:
    """C1: at most one LegDirection=Variable leg per TransferTemplate."""
    rails_by_name: dict[str, Rail] = {r.name: r for r in inst.rails}
    for t in inst.transfer_templates:
        variable_legs = [
            n for n in t.leg_rails
            if isinstance(rails_by_name.get(n), SingleLegRail)
            and isinstance(rails_by_name[n], SingleLegRail)
            and rails_by_name[n].leg_direction == "Variable"  # type: ignore[union-attr]
        ]
        if len(variable_legs) > 1:
            raise L2ValidationError(
                f"TransferTemplate {t.name!r}: contains {len(variable_legs)} "
                f"Variable-direction legs ({variable_legs!r}); SPEC requires "
                f"at most one (otherwise closure is under-determined)"
            )


def _check_chain_xor_group_consistency(inst: L2Instance) -> None:
    """C2: every XorGroup's members share the same Chain.parent."""
    parents_by_xor: dict[str, set[str]] = {}
    for c in inst.chains:
        if c.xor_group is None:
            continue
        parents_by_xor.setdefault(c.xor_group, set()).add(c.parent)
    for xor_group, parents in parents_by_xor.items():
        if len(parents) > 1:
            raise L2ValidationError(
                f"xor_group {xor_group!r}: members reference different "
                f"parents {sorted(parents)!r}; all members of an XOR "
                f"group MUST share the same parent"
            )


# -- State-dependent (S1-S6) -------------------------------------------------


def _check_two_leg_expected_net_consistency(inst: L2Instance) -> None:
    """S1 + S2: standalone two-leg requires expected_net; template-leg forbids it."""
    template_leg_names: set[str] = set()
    for t in inst.transfer_templates:
        template_leg_names.update(t.leg_rails)

    for r in inst.rails:
        if not isinstance(r, TwoLegRail):
            continue
        is_template_leg = r.name in template_leg_names
        if is_template_leg and r.expected_net is not None:
            raise L2ValidationError(
                f"Rail {r.name!r}: appears in a TransferTemplate's "
                f"leg_rails AND declares expected_net; the template owns "
                f"the bundle's ExpectedNet so the rail MUST NOT carry one"
            )
        if not is_template_leg and r.expected_net is None:
            raise L2ValidationError(
                f"Rail {r.name!r}: standalone two-leg rail (not in any "
                f"TransferTemplate.leg_rails) MUST declare expected_net "
                f"(typically 0)"
            )


def _check_single_leg_reconciliation(inst: L2Instance) -> None:
    """S3: every non-aggregating single-leg Rail is reconciled.

    Aggregating single-leg rails ARE the reconciliation mechanism (per
    SPEC's Aggregating Rails section: "single-leg aggregating rails are
    permitted, e.g. a single-leg sweep that lands in an external
    counterparty"). Their drift exits the system into the External
    counterparty by design — they do not themselves need to appear in
    any other rail's bundles_activity. So the S3 reconciliation check
    only applies to non-aggregating single-leg rails.

    This exemption was surfaced by the M.1.8 kitchen-sink fixture (a
    single-leg aggregating rail tripped a literal reading of the SPEC
    rule). SPEC v1's wording amended in M.1.8 to make the exemption
    explicit.
    """
    template_leg_names: set[str] = set()
    for t in inst.transfer_templates:
        template_leg_names.update(t.leg_rails)

    aggregating_bundles: set[str] = set()
    for r in inst.rails:
        if r.aggregating:
            aggregating_bundles.update(r.bundles_activity)

    for r in inst.rails:
        if not isinstance(r, SingleLegRail):
            continue
        if r.aggregating:
            # Self-reconciling per the exemption above.
            continue
        in_template = r.name in template_leg_names
        in_aggregating = (
            r.name in aggregating_bundles
            or r.transfer_type in aggregating_bundles
        )
        if not (in_template or in_aggregating):
            raise L2ValidationError(
                f"Rail {r.name!r}: single-leg rail is not reconciled "
                f"(not listed in any TransferTemplate.leg_rails AND "
                f"its name + transfer_type {r.transfer_type!r} not "
                f"matched by any aggregating Rail's bundles_activity); "
                f"the drift it introduces would persist forever"
            )


def _check_chain_aggregating_not_child(inst: L2Instance) -> None:
    """S4: aggregating Rails MUST NOT appear as Chain.child."""
    aggregating_names = {r.name for r in inst.rails if r.aggregating}
    for i, c in enumerate(inst.chains):
        if c.child in aggregating_names:
            raise L2ValidationError(
                f"chains[{i}].child={c.child!r}: aggregating Rails MUST NOT "
                f"appear as Chain.child (they sweep on cadence, not on a "
                f"per-Transfer parent trigger)"
            )


def _check_aggregating_rail_required_fields(inst: L2Instance) -> None:
    """S5: aggregating Rails MUST declare cadence + bundles_activity."""
    for r in inst.rails:
        if not r.aggregating:
            continue
        if r.cadence is None:
            raise L2ValidationError(
                f"Rail {r.name!r}: aggregating=true requires cadence to be set"
            )
        if not r.bundles_activity:
            raise L2ValidationError(
                f"Rail {r.name!r}: aggregating=true requires "
                f"bundles_activity to be a non-empty list"
            )


def _check_non_aggregating_rail_no_cadence_or_bundles(inst: L2Instance) -> None:
    """S6: non-aggregating Rails MUST NOT declare cadence or bundles_activity."""
    for r in inst.rails:
        if r.aggregating:
            continue
        if r.cadence is not None:
            raise L2ValidationError(
                f"Rail {r.name!r}: cadence is only meaningful when "
                f"aggregating=true; remove cadence or set aggregating=true"
            )
        if r.bundles_activity:
            raise L2ValidationError(
                f"Rail {r.name!r}: bundles_activity is only meaningful when "
                f"aggregating=true; remove bundles_activity or set "
                f"aggregating=true"
            )


# -- Vocabulary (V1-V2) ------------------------------------------------------


def _check_completion_vocabulary(inst: L2Instance) -> None:
    """V1: every TransferTemplate.completion matches a v1 vocabulary literal."""
    for t in inst.transfer_templates:
        if not _completion_is_valid(t.completion):
            raise L2ValidationError(
                f"TransferTemplate {t.name!r}.completion={t.completion!r}: "
                f"not a v1 CompletionExpression literal. Allowed: "
                f"business_day_end, business_day_end+Nd, month_end, "
                f"metadata.<key>"
            )


def _check_cadence_vocabulary(inst: L2Instance) -> None:
    """V2: every aggregating Rail's cadence matches a v1 vocabulary literal."""
    for r in inst.rails:
        if not r.aggregating or r.cadence is None:
            continue
        if not _cadence_is_valid(r.cadence):
            raise L2ValidationError(
                f"Rail {r.name!r}.cadence={r.cadence!r}: not a v1 "
                f"CadenceExpression literal. Allowed: intraday-Nh, "
                f"daily-eod, daily-bod, weekly-<mon..sun>, monthly-eom, "
                f"monthly-bom, monthly-<1..31>"
            )
