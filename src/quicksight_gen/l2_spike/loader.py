"""M.0 spike — YAML → typed L2 dataclasses + minimal validation.

The validation surface is intentionally narrow — just enough to catch
malformed YAML and the constraints the spike's downstream emitters
absolutely depend on. Full SPEC validation (singleton ParentRole,
Variable-leg counts, vocabulary literals, single-leg reconciliation, etc.)
lands in M.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeVar

import yaml


# -- Typed primitives ---------------------------------------------------------

Scope = Literal["internal", "external"]
Origin = Literal["InternalInitiated", "ExternalForcePosted"]
LegDirection = Literal["Debit", "Credit", "Variable"]


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    scope: Scope
    role: str | None = None
    name: str | None = None
    parent_role: str | None = None
    expected_eod_balance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Rail:
    name: str
    transfer_type: str
    origin: Origin
    metadata_keys: tuple[str, ...]
    # Two-leg fields
    source_role: str | None = None
    destination_role: str | None = None
    expected_net: Decimal | None = None
    # Single-leg fields — accepted by the loader but unused in M.0 (no
    # TransferTemplate / AggregatingRail to reconcile against).
    leg_role: str | None = None
    leg_direction: LegDirection | None = None


@dataclass(frozen=True, slots=True)
class L2Instance:
    instance: str
    accounts: tuple[Account, ...]
    rails: tuple[Rail, ...]


# -- Errors -------------------------------------------------------------------

class L2ValidationError(ValueError):
    """Raised when an L2 YAML fails load-time validation."""


# -- Public API ---------------------------------------------------------------

def load(path: Path | str) -> L2Instance:
    """Load and validate an L2 YAML file. Raises L2ValidationError on issues."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise L2ValidationError(
            f"L2 YAML must be a mapping at top level; got {type(raw).__name__}"
        )

    instance = _require(raw, "instance", str)
    _validate_identifier(instance, "instance")

    accounts = tuple(_load_account(a) for a in _require(raw, "accounts", list))
    rails = tuple(_load_rail(r) for r in _require(raw, "rails", list))

    inst = L2Instance(instance=instance, accounts=accounts, rails=rails)
    _validate_instance(inst)
    return inst


# -- Per-entity loaders -------------------------------------------------------

def _load_account(raw: object) -> Account:
    if not isinstance(raw, dict):
        raise L2ValidationError(f"account must be a mapping; got {type(raw).__name__}")
    eod = raw.get("expected_eod_balance")
    return Account(
        id=_require(raw, "id", str),
        scope=_require_literal(raw, "scope", ("internal", "external")),
        role=raw.get("role"),
        name=raw.get("name"),
        parent_role=raw.get("parent_role"),
        expected_eod_balance=Decimal(str(eod)) if eod is not None else None,
    )


def _load_rail(raw: object) -> Rail:
    if not isinstance(raw, dict):
        raise L2ValidationError(f"rail must be a mapping; got {type(raw).__name__}")
    expected_net = raw.get("expected_net")
    return Rail(
        name=_require(raw, "name", str),
        transfer_type=_require(raw, "transfer_type", str),
        origin=_require_literal(raw, "origin", ("InternalInitiated", "ExternalForcePosted")),
        metadata_keys=tuple(raw.get("metadata_keys", [])),
        source_role=raw.get("source_role"),
        destination_role=raw.get("destination_role"),
        expected_net=Decimal(str(expected_net)) if expected_net is not None else None,
        leg_role=raw.get("leg_role"),
        leg_direction=raw.get("leg_direction"),
    )


# -- Validation ---------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_identifier(value: str, field_name: str) -> None:
    if not _IDENTIFIER_RE.match(value):
        raise L2ValidationError(
            f"{field_name}={value!r} must match [a-z][a-z0-9_]* "
            "(SQL-identifier-safe)"
        )


def _validate_instance(inst: L2Instance) -> None:
    """Spike-level validation — narrow surface, full SPEC validation in M.1."""

    seen_ids: set[str] = set()
    for a in inst.accounts:
        if a.id in seen_ids:
            raise L2ValidationError(f"duplicate account id: {a.id!r}")
        seen_ids.add(a.id)

    declared_roles = {a.role for a in inst.accounts if a.role is not None}

    for r in inst.rails:
        is_two_leg = r.source_role is not None or r.destination_role is not None
        is_single_leg = r.leg_role is not None or r.leg_direction is not None

        if is_two_leg and is_single_leg:
            raise L2ValidationError(
                f"rail {r.name!r}: must be either two-leg or single-leg, not both"
            )
        if not is_two_leg and not is_single_leg:
            raise L2ValidationError(
                f"rail {r.name!r}: must declare either two-leg "
                "(source_role + destination_role + expected_net) or "
                "single-leg (leg_role + leg_direction)"
            )

        if is_two_leg:
            if r.source_role is None or r.destination_role is None:
                raise L2ValidationError(
                    f"rail {r.name!r}: two-leg shape requires both source_role "
                    "and destination_role"
                )
            if r.expected_net is None:
                raise L2ValidationError(
                    f"rail {r.name!r}: standalone two-leg rail requires "
                    "expected_net (typically 0). Single-leg rails and "
                    "TransferTemplate-leg variants are deferred until M.3."
                )
            for role_field, role_value in [
                ("source_role", r.source_role),
                ("destination_role", r.destination_role),
            ]:
                if role_value not in declared_roles:
                    raise L2ValidationError(
                        f"rail {r.name!r}: {role_field}={role_value!r} doesn't "
                        f"match any Account.role (declared: {sorted(declared_roles)!r})"
                    )

        if is_single_leg:
            raise L2ValidationError(
                f"rail {r.name!r}: single-leg rails are not yet supported "
                "in the M.0 spike (would require TransferTemplate or "
                "AggregatingRail to reconcile per SPEC). Deferred to M.3."
            )


# -- Type helpers -------------------------------------------------------------

T = TypeVar("T")


def _require(raw: dict[str, object], key: str, expected_type: type[T]) -> T:
    if key not in raw:
        raise L2ValidationError(f"missing required field {key!r}")
    value = raw[key]
    if not isinstance(value, expected_type):
        raise L2ValidationError(
            f"field {key!r} must be {expected_type.__name__}; "
            f"got {type(value).__name__}"
        )
    return value


def _require_literal(
    raw: dict[str, object], key: str, allowed: tuple[str, ...]
) -> str:
    value = _require(raw, key, str)
    if value not in allowed:
        raise L2ValidationError(
            f"field {key!r}={value!r} must be one of {allowed!r}"
        )
    return value
