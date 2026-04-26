"""LAYER 2 institutional-model primitives, typed 1:1 against ``SPEC.md``.

This module is the single source of truth for what an L2 instance contains
in memory. The YAML loader (M.1.2) deserializes into these types; the
validator (M.1.3) enforces the SPEC's load-time rules on top; the SQL
emitter (M.1.4) walks them; downstream apps (M.2-M.6) consume them.

Notation matches SPEC: every dataclass mirrors a SPEC primitive's tuple
shape exactly, with PascalCase types + snake_case field names. Frozen +
slotted to prevent surprise mutation and typo'd attribute access.

Per F2 (M.0.13 iteration gate): ``Rail`` is a discriminated union of
``TwoLegRail`` / ``SingleLegRail`` — pyright catches "leg_role on a
two-leg rail" at the construction site instead of at validation time.
The aggregating-rail flags (``aggregating`` / ``bundles_activity`` /
``cadence``) live as optional fields on either shape, since the SPEC
allows aggregating rails to be one-leg or two-leg.

Per F4: Money values are ``Decimal``; the YAML loader (M.1.2) is
responsible for the ``Decimal(str(value))`` coercion that dodges YAML
float precision.

Per F5: ``InstancePrefix`` (the ``L2Instance.instance`` field) MUST
match ``^[a-z][a-z0-9_]*$`` with max 30 characters — enforced by the
loader's identifier validator (M.1.2).

Per F1 + SPEC's load-time validation list: every Role referenced by a
Rail or AccountTemplate MUST resolve to either a declared ``Account``
or an ``AccountTemplate``. This module declares the field types; the
validator (M.1.3) walks the resolution graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, NewType, TypeAlias


# -- Value types --------------------------------------------------------------


# An identifier — used for InstancePrefix, Role names, Rail names,
# TransferTemplate names, Account IDs, MetadataKey names, etc. The runtime
# type is ``str``; ``NewType`` gives pyright the hint that mixing identifier
# kinds (e.g. passing a Role where a Rail name is expected) is suspicious
# at the type-check site.
Identifier = NewType("Identifier", str)

# A human-readable label — for Account.name. Distinct from Identifier in
# the SPEC's Notation section (Identifier is opaque + stable; Name is
# display-only and not load-bearing for any constraint).
Name = NewType("Name", str)

# Money — Decimal to 2dp in the system's single Currency. The loader
# (M.1.2) coerces YAML numerics via ``Decimal(str(value))``.
Money: TypeAlias = Decimal

# L1's Account.Scope discriminates whether reconciliation tracks the
# account's balance (Internal) or treats it as a counterparty (External).
Scope: TypeAlias = Literal["internal", "external"]

# L1's Transaction.Origin — open enum on L1, but L2 declares each Rail's
# Origin per-instance. The SPEC pins {InternalInitiated, ExternalForcePosted}
# as the v1 set; integrators may extend.
Origin: TypeAlias = str

# Every Transaction leg's direction. ``Variable`` is the closing-leg sentinel
# whose amount + direction are both determined by a containing
# TransferTemplate's ExpectedNet at posting time.
LegDirection: TypeAlias = Literal["Debit", "Credit", "Variable"]

# A Rail's TransferType extends L1's open enum (``Sale`` is the L1 default
# and need not be redeclared). Strings here are validated only against the
# rail's own declarations — there's no closed master list at L2.
TransferType: TypeAlias = str

# A SPEC-vocabulary expression for a TransferTemplate's Completion derivation.
# The validator (M.1.3) enforces this against the v1 vocabulary table:
# {business_day_end, business_day_end+Nd, month_end, metadata.<key>}.
CompletionExpression: TypeAlias = str

# A SPEC-vocabulary expression for an aggregating rail's firing cadence.
# The validator (M.1.3) enforces this against the v1 vocabulary table:
# {intraday-Nh, daily-eod, daily-bod, weekly-<weekday>, monthly-eom,
#  monthly-bom, monthly-<day>}.
CadenceExpression: TypeAlias = str

# A Rail's source/destination/leg role accepts either a single Role name
# or a union of Role names ("any of these is admissible"). Always stored
# as a tuple — single-role becomes a 1-tuple; the loader normalizes.
RoleExpression: TypeAlias = tuple[Identifier, ...]

# An item in an aggregating rail's BundlesActivity. Per SPEC: a
# TransferType matches every Transfer of that type; a RailName /
# TransferTemplateName matches Transfers produced by that specific
# rail/template. Both kinds are strings; the validator resolves which.
BundlesActivityRef: TypeAlias = Identifier


# -- Account dimension --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Account:
    """A 1-of-1 account that exists exactly once in the institution.

    Per SPEC: singletons that Rails reference by Role; the Role is
    technically optional but in practice required for any Account a Rail
    touches (per F1, enforced by the validator at load time).
    """

    id: Identifier
    scope: Scope
    name: Name | None = None
    role: Identifier | None = None
    parent_role: Identifier | None = None
    expected_eod_balance: Money | None = None


@dataclass(frozen=True, slots=True)
class AccountTemplate:
    """A class of accounts that exists in many instances at runtime.

    Per SPEC: declares the SHAPE; the specific account instance for a
    given posting is selected at posting time (typically from
    ``Transaction.Metadata``). ``parent_role`` MUST resolve to a
    singleton ``Account`` (never another ``AccountTemplate``) — enforced
    by the validator at load time per the SPEC's "singleton parent only"
    constraint.
    """

    role: Identifier
    scope: Scope
    parent_role: Identifier | None = None
    expected_eod_balance: Money | None = None


# -- Rails (discriminated union per F2) --------------------------------------


@dataclass(frozen=True, slots=True)
class TwoLegRail:
    """A Rail that produces two Transaction legs (debit + credit) per firing.

    When fired as a standalone Transfer, ``expected_net`` MUST be set
    (typically ``0``); L1 Conservation enforces ``Σ legs = expected_net``.
    When the rail is a leg-pattern of a TransferTemplate, ``expected_net``
    MUST be unset — the template owns the bundle's ExpectedNet. Per F3
    this is a cross-entity validation rule (the validator's pass 2).
    """

    name: Identifier
    transfer_type: TransferType
    origin: Origin
    metadata_keys: tuple[Identifier, ...]
    source_role: RoleExpression
    destination_role: RoleExpression
    expected_net: Money | None = None
    # Aggregating-rail flags. Per SPEC, aggregating rails MAY be two-leg.
    aggregating: bool = False
    bundles_activity: tuple[BundlesActivityRef, ...] = field(default_factory=tuple)
    cadence: CadenceExpression | None = None


@dataclass(frozen=True, slots=True)
class SingleLegRail:
    """A Rail that produces one Transaction leg per firing.

    Per SPEC: single-leg rails MUST be reconciled by EITHER a
    ``TransferTemplate`` whose ``leg_rails`` includes this rail OR an
    aggregating rail whose ``bundles_activity`` includes this rail's
    ``transfer_type``. A single-leg rail without either reconciliation
    path is a configuration error (validator catches at load).

    ``leg_direction = Variable`` means the leg's amount AND direction are
    determined at posting time by a containing TransferTemplate's
    ExpectedNet closure requirement. Each TransferTemplate MUST contain
    at most one Variable-direction leg.
    """

    name: Identifier
    transfer_type: TransferType
    origin: Origin
    metadata_keys: tuple[Identifier, ...]
    leg_role: RoleExpression
    leg_direction: LegDirection
    # Aggregating-rail flags. Per SPEC, single-leg aggregating rails are
    # permitted (e.g. a single-leg sweep that lands in an external
    # counterparty).
    aggregating: bool = False
    bundles_activity: tuple[BundlesActivityRef, ...] = field(default_factory=tuple)
    cadence: CadenceExpression | None = None


Rail: TypeAlias = TwoLegRail | SingleLegRail


# -- Transfer Templates ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransferTemplate:
    """A multi-leg shared Transfer that bundles many Rail firings.

    Per SPEC: every firing of a ``leg_rails`` rail with the same
    ``transfer_key`` Metadata values posts to the same shared Transfer.
    L1 Conservation flags the Transfer if its legs don't sum to
    ``expected_net``; L1 Timeliness flags any leg that posts after the
    derived ``Transfer.Completion``.

    A Rail listed in ``leg_rails`` MUST NOT also fire standalone
    Transfers — its firings always join the shared Transfer matching the
    ``transfer_key`` values.
    """

    name: Identifier
    transfer_type: TransferType
    expected_net: Money
    transfer_key: tuple[Identifier, ...]
    completion: CompletionExpression
    leg_rails: tuple[Identifier, ...]


# -- Chains ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChainEntry:
    """A parent → child relationship between Rails or TransferTemplates.

    Per SPEC: ``required = True`` means every parent firing SHOULD
    eventually have at least one matching child firing — a missing child
    surfaces as an orphan exception.

    When several entries share the same ``parent`` AND ``xor_group``,
    exactly one of them SHOULD fire per parent instance. Without
    ``xor_group``, multiple ``required = False`` children allow any
    combination including none.

    Aggregating rails MUST NOT appear as ``child`` (they don't have
    per-Transfer parents — they sweep on cadence). Validator enforces.
    """

    parent: Identifier
    child: Identifier
    required: bool
    xor_group: Identifier | None = None


# -- Limit Schedules ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LimitSchedule:
    """A daily cap on outbound flow per (parent role, transfer type).

    Per SPEC: time-invariant in v1. The library projects each entry into
    the relevant ``StoredBalance.Limits`` map; L1's Limit Breach
    invariant evaluates per child individually (the cap is per-child,
    not aggregated across siblings of the parent).
    """

    parent_role: Identifier
    transfer_type: TransferType
    cap: Money


# -- Top-level instance ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class L2Instance:
    """A loaded + parsed L2 institutional model.

    The ``instance`` field is the InstancePrefix per SPEC's storage
    isolation rule — propagates onto every generated DB object and
    QuickSight resource ID. Validator enforces the
    ``^[a-z][a-z0-9_]*$`` regex + 30-char cap (F5).
    """

    instance: Identifier
    accounts: tuple[Account, ...]
    account_templates: tuple[AccountTemplate, ...]
    rails: tuple[Rail, ...]
    transfer_templates: tuple[TransferTemplate, ...]
    chains: tuple[ChainEntry, ...]
    limit_schedules: tuple[LimitSchedule, ...]
