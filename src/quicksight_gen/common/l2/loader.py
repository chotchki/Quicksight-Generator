"""YAML → ``L2Instance`` loader.

Single entry point ``load_instance(path)`` reads an L2 YAML file, walks
the top-level sections (``accounts`` / ``account_templates`` / ``rails``
/ ``transfer_templates`` / ``chains`` / ``limit_schedules``), and emits
a fully-typed ``L2Instance`` per the SPEC.

What this module does:
- YAML parsing via ``yaml.safe_load`` (file/line in syntax errors comes
  from PyYAML for free).
- Required-field + type-shape checks per primitive (e.g. ``Account.id``
  is required + must be a string).
- ``Decimal(str(value))`` coercion for every Money-typed field via the
  shared ``_load_money`` helper (per F4 — dodges YAML float precision).
- ``InstancePrefix`` regex + length validation via ``_load_instance_prefix``
  (per F5 — pinned in SPEC as ``^[a-z][a-z0-9_]*$``, max 30 chars).
- Rail discrimination: presence of ``source_role`` / ``destination_role``
  → ``TwoLegRail``; presence of ``leg_role`` / ``leg_direction`` →
  ``SingleLegRail``; both or neither → error.
- ``RoleExpression`` normalization: a single string YAML value becomes
  a 1-tuple; a YAML list of strings becomes a tuple.

What this module does NOT do (deferred to M.1.3 ``validate.py``):
- Cross-entity validation (singleton-ParentRole, ≤1 Variable leg per
  template, single-leg reconciliation paths, XOR-group consistency,
  Aggregating-not-as-child, vocabulary literals for Completion/Cadence).
- Reference resolution (does this Role appear on any Account?).

Errors raise ``L2LoaderError`` with a logical path (e.g.
``accounts[2].id``) so the caller can pinpoint the bad field.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypeVar

import yaml

from .primitives import (
    Account,
    AccountTemplate,
    BundlesActivityRef,
    CadenceExpression,
    ChainEntry,
    CompletionExpression,
    Identifier,
    L2Instance,
    LegDirection,
    LimitSchedule,
    Money,
    Name,
    Origin,
    Rail,
    RoleExpression,
    Scope,
    SingleLegRail,
    TransferTemplate,
    TransferType,
    TwoLegRail,
)


# -- Errors -------------------------------------------------------------------


class L2LoaderError(ValueError):
    """Raised when an L2 YAML fails to load or fails per-entity validation."""


# -- Identifier validation (F5) ----------------------------------------------


# Per SPEC's Instance Prefix Format rule (F5 amendment):
#   MUST match ^[a-z][a-z0-9_]*$, max 30 characters.
# Lowercase-only avoids Postgres' quoted-vs-unquoted hazard;
# 30-char cap leaves room for the longest table-name suffix within
# Postgres' 63-char identifier limit.
_INSTANCE_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_INSTANCE_PREFIX_MAX = 30


def _load_instance_prefix(raw: object, *, path: str) -> Identifier:
    """Validate and return an InstancePrefix per SPEC's F5 rules."""
    if not isinstance(raw, str):
        raise L2LoaderError(
            f"{path}: expected a string instance prefix, "
            f"got {type(raw).__name__}"
        )
    if not _INSTANCE_PREFIX_RE.match(raw):
        raise L2LoaderError(
            f"{path}={raw!r}: must match {_INSTANCE_PREFIX_RE.pattern!r} "
            f"(SQL-identifier-safe; lowercase start; alphanumeric or "
            f"underscore thereafter)"
        )
    if len(raw) > _INSTANCE_PREFIX_MAX:
        raise L2LoaderError(
            f"{path}={raw!r}: max {_INSTANCE_PREFIX_MAX} characters "
            f"(got {len(raw)})"
        )
    return Identifier(raw)


def _load_identifier(raw: object, *, path: str) -> Identifier:
    """Validate and return a generic Identifier (Role / Rail / Account ID / etc.).

    Loose constraint: must be a non-empty string. Per the F5 finding,
    the strict regex applies to InstancePrefix only — other identifier
    fields use whatever conventions the SPEC's worked examples follow
    (PascalCase Roles, snake_case TransferTypes, …) and the SPEC
    doesn't pin a single regex for all of them.
    """
    if not isinstance(raw, str):
        raise L2LoaderError(
            f"{path}: expected a string identifier, got {type(raw).__name__}"
        )
    if not raw:
        raise L2LoaderError(f"{path}: identifier must be non-empty")
    return Identifier(raw)


# -- Money coercion (F4) -----------------------------------------------------


def _load_money(raw: object, *, path: str) -> Money:
    """Coerce a YAML numeric to Decimal via ``Decimal(str(raw))`` per F4.

    YAML's ``safe_load`` returns ``int``/``float`` for numerics; constructing
    ``Decimal`` from ``float`` loses precision (``Decimal(0.1) ==
    Decimal('0.10000000000000000555...')``). The fix is to round-trip
    through ``str``: ``Decimal(str(0.1))`` produces the expected
    ``Decimal('0.1')``. Also accepts string + Decimal inputs for
    integrators who prefer to author Money explicitly.
    """
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float, str)):
        try:
            return Decimal(str(raw))
        except InvalidOperation as exc:
            raise L2LoaderError(
                f"{path}={raw!r}: not a valid decimal money value"
            ) from exc
    raise L2LoaderError(
        f"{path}: expected money (number or decimal string), "
        f"got {type(raw).__name__}"
    )


# -- Generic field helpers ---------------------------------------------------


T = TypeVar("T")


def _require(raw: dict[str, Any], key: str, *, path: str) -> Any:
    """Pull a required field; raise if missing."""
    if key not in raw:
        raise L2LoaderError(f"{path}: missing required field {key!r}")
    return raw[key]


def _optional(raw: dict[str, Any], key: str, default: T) -> Any | T:
    """Pull an optional field with a default."""
    return raw.get(key, default)


def _load_string(raw: object, *, path: str) -> str:
    """Validate a non-empty string."""
    if not isinstance(raw, str):
        raise L2LoaderError(
            f"{path}: expected string, got {type(raw).__name__}"
        )
    if not raw:
        raise L2LoaderError(f"{path}: string must be non-empty")
    return raw


def _load_scope(raw: object, *, path: str) -> Scope:
    if raw not in ("internal", "external"):
        raise L2LoaderError(
            f"{path}={raw!r}: scope must be 'internal' or 'external'"
        )
    return raw  # type: ignore[return-value]


def _load_leg_direction(raw: object, *, path: str) -> LegDirection:
    if raw not in ("Debit", "Credit", "Variable"):
        raise L2LoaderError(
            f"{path}={raw!r}: leg_direction must be 'Debit', 'Credit', "
            f"or 'Variable'"
        )
    return raw  # type: ignore[return-value]


def _load_identifier_list(
    raw: object, *, path: str, allow_empty: bool = True,
) -> tuple[Identifier, ...]:
    """A YAML list of identifier strings → tuple of Identifiers."""
    if raw is None and allow_empty:
        return ()
    if not isinstance(raw, list):
        raise L2LoaderError(
            f"{path}: expected a list of identifiers, "
            f"got {type(raw).__name__}"
        )
    return tuple(
        _load_identifier(item, path=f"{path}[{i}]")
        for i, item in enumerate(raw)
    )


def _load_role_expression(raw: object, *, path: str) -> RoleExpression:
    """Single role string → 1-tuple; YAML list of role strings → tuple.

    Per the primitives module's normalization choice — RoleExpression is
    always a tuple, single-role becomes a 1-tuple. Avoids the union-vs-
    string hazard everywhere downstream.
    """
    if isinstance(raw, str):
        return (_load_identifier(raw, path=path),)
    if isinstance(raw, list):
        if not raw:
            raise L2LoaderError(
                f"{path}: role expression list must not be empty"
            )
        return tuple(
            _load_identifier(item, path=f"{path}[{i}]")
            for i, item in enumerate(raw)
        )
    raise L2LoaderError(
        f"{path}: role expression must be a string or list of strings, "
        f"got {type(raw).__name__}"
    )


# -- Per-primitive loaders ---------------------------------------------------


def _load_account(raw: object, *, path: str) -> Account:
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: account must be a mapping, got {type(raw).__name__}"
        )
    eod = raw.get("expected_eod_balance")
    return Account(
        id=_load_identifier(_require(raw, "id", path=path), path=f"{path}.id"),
        scope=_load_scope(_require(raw, "scope", path=path), path=f"{path}.scope"),
        name=Name(_load_string(raw["name"], path=f"{path}.name"))
        if "name" in raw else None,
        role=_load_identifier(raw["role"], path=f"{path}.role")
        if "role" in raw else None,
        parent_role=_load_identifier(raw["parent_role"], path=f"{path}.parent_role")
        if "parent_role" in raw else None,
        expected_eod_balance=_load_money(eod, path=f"{path}.expected_eod_balance")
        if eod is not None else None,
    )


def _load_account_template(raw: object, *, path: str) -> AccountTemplate:
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: account_template must be a mapping, "
            f"got {type(raw).__name__}"
        )
    eod = raw.get("expected_eod_balance")
    return AccountTemplate(
        role=_load_identifier(_require(raw, "role", path=path), path=f"{path}.role"),
        scope=_load_scope(_require(raw, "scope", path=path), path=f"{path}.scope"),
        parent_role=_load_identifier(raw["parent_role"], path=f"{path}.parent_role")
        if "parent_role" in raw else None,
        expected_eod_balance=_load_money(eod, path=f"{path}.expected_eod_balance")
        if eod is not None else None,
    )


def _load_rail(raw: object, *, path: str) -> Rail:
    """Discriminate two-leg vs single-leg by which keys are present."""
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: rail must be a mapping, got {type(raw).__name__}"
        )

    name = _load_identifier(_require(raw, "name", path=path), path=f"{path}.name")
    transfer_type: TransferType = _load_string(
        _require(raw, "transfer_type", path=path),
        path=f"{path}.transfer_type",
    )
    origin: Origin = _load_string(
        _require(raw, "origin", path=path), path=f"{path}.origin",
    )
    metadata_keys = _load_identifier_list(
        raw.get("metadata_keys"), path=f"{path}.metadata_keys",
    )

    # Aggregating flags can appear on either shape.
    aggregating: bool = bool(raw.get("aggregating", False))
    bundles_activity = tuple(
        BundlesActivityRef(_load_identifier(item, path=f"{path}.bundles_activity[{i}]"))
        for i, item in enumerate(raw.get("bundles_activity") or [])
    )
    cadence_raw = raw.get("cadence")
    cadence: CadenceExpression | None = (
        _load_string(cadence_raw, path=f"{path}.cadence")
        if cadence_raw is not None else None
    )

    has_two_leg_fields = "source_role" in raw or "destination_role" in raw
    has_single_leg_fields = "leg_role" in raw or "leg_direction" in raw

    if has_two_leg_fields and has_single_leg_fields:
        raise L2LoaderError(
            f"{path}: rail must declare EITHER two-leg "
            f"(source_role + destination_role) OR single-leg "
            f"(leg_role + leg_direction), not both"
        )
    if not has_two_leg_fields and not has_single_leg_fields:
        raise L2LoaderError(
            f"{path}: rail must declare EITHER two-leg "
            f"(source_role + destination_role) OR single-leg "
            f"(leg_role + leg_direction)"
        )

    if has_two_leg_fields:
        if "source_role" not in raw or "destination_role" not in raw:
            raise L2LoaderError(
                f"{path}: two-leg rail requires both source_role and "
                f"destination_role"
            )
        en = raw.get("expected_net")
        return TwoLegRail(
            name=name,
            transfer_type=transfer_type,
            origin=origin,
            metadata_keys=metadata_keys,
            source_role=_load_role_expression(
                raw["source_role"], path=f"{path}.source_role",
            ),
            destination_role=_load_role_expression(
                raw["destination_role"], path=f"{path}.destination_role",
            ),
            expected_net=_load_money(en, path=f"{path}.expected_net")
            if en is not None else None,
            aggregating=aggregating,
            bundles_activity=bundles_activity,
            cadence=cadence,
        )

    # Single-leg
    if "leg_role" not in raw or "leg_direction" not in raw:
        raise L2LoaderError(
            f"{path}: single-leg rail requires both leg_role and leg_direction"
        )
    return SingleLegRail(
        name=name,
        transfer_type=transfer_type,
        origin=origin,
        metadata_keys=metadata_keys,
        leg_role=_load_role_expression(
            raw["leg_role"], path=f"{path}.leg_role",
        ),
        leg_direction=_load_leg_direction(
            raw["leg_direction"], path=f"{path}.leg_direction",
        ),
        aggregating=aggregating,
        bundles_activity=bundles_activity,
        cadence=cadence,
    )


def _load_transfer_template(raw: object, *, path: str) -> TransferTemplate:
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: transfer_template must be a mapping, "
            f"got {type(raw).__name__}"
        )
    completion: CompletionExpression = _load_string(
        _require(raw, "completion", path=path), path=f"{path}.completion",
    )
    return TransferTemplate(
        name=_load_identifier(
            _require(raw, "name", path=path), path=f"{path}.name",
        ),
        transfer_type=_load_string(
            _require(raw, "transfer_type", path=path),
            path=f"{path}.transfer_type",
        ),
        expected_net=_load_money(
            _require(raw, "expected_net", path=path),
            path=f"{path}.expected_net",
        ),
        transfer_key=_load_identifier_list(
            _require(raw, "transfer_key", path=path),
            path=f"{path}.transfer_key",
            allow_empty=False,
        ),
        completion=completion,
        leg_rails=_load_identifier_list(
            _require(raw, "leg_rails", path=path),
            path=f"{path}.leg_rails",
            allow_empty=False,
        ),
    )


def _load_chain_entry(raw: object, *, path: str) -> ChainEntry:
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: chain entry must be a mapping, got {type(raw).__name__}"
        )
    return ChainEntry(
        parent=_load_identifier(
            _require(raw, "parent", path=path), path=f"{path}.parent",
        ),
        child=_load_identifier(
            _require(raw, "child", path=path), path=f"{path}.child",
        ),
        required=bool(_require(raw, "required", path=path)),
        xor_group=_load_identifier(raw["xor_group"], path=f"{path}.xor_group")
        if "xor_group" in raw else None,
    )


def _load_limit_schedule(raw: object, *, path: str) -> LimitSchedule:
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{path}: limit_schedule must be a mapping, "
            f"got {type(raw).__name__}"
        )
    return LimitSchedule(
        parent_role=_load_identifier(
            _require(raw, "parent_role", path=path),
            path=f"{path}.parent_role",
        ),
        transfer_type=_load_string(
            _require(raw, "transfer_type", path=path),
            path=f"{path}.transfer_type",
        ),
        cap=_load_money(_require(raw, "cap", path=path), path=f"{path}.cap"),
    )


# -- Public API --------------------------------------------------------------


def load_instance(path: Path | str) -> L2Instance:
    """Load + per-entity-validate an L2 YAML file into an ``L2Instance``.

    Cross-entity validation (M.1.3) is a separate ``validate(instance)``
    pass; ``load_instance`` only catches malformed YAML, missing required
    fields, type-shape errors, identifier-format violations, and Money
    coercion errors.
    """
    yaml_path = Path(path)
    try:
        raw_text = yaml_path.read_text()
    except OSError as exc:
        raise L2LoaderError(f"could not read {yaml_path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise L2LoaderError(
            f"YAML syntax error in {yaml_path}: {exc}"
        ) from exc

    if raw is None:
        raise L2LoaderError(f"{yaml_path}: file is empty")
    if not isinstance(raw, dict):
        raise L2LoaderError(
            f"{yaml_path}: top level must be a mapping, "
            f"got {type(raw).__name__}"
        )

    instance = _load_instance_prefix(
        _require(raw, "instance", path="instance"), path="instance",
    )

    accounts = tuple(
        _load_account(item, path=f"accounts[{i}]")
        for i, item in enumerate(raw.get("accounts") or [])
    )
    account_templates = tuple(
        _load_account_template(item, path=f"account_templates[{i}]")
        for i, item in enumerate(raw.get("account_templates") or [])
    )
    rails = tuple(
        _load_rail(item, path=f"rails[{i}]")
        for i, item in enumerate(raw.get("rails") or [])
    )
    transfer_templates = tuple(
        _load_transfer_template(item, path=f"transfer_templates[{i}]")
        for i, item in enumerate(raw.get("transfer_templates") or [])
    )
    chains = tuple(
        _load_chain_entry(item, path=f"chains[{i}]")
        for i, item in enumerate(raw.get("chains") or [])
    )
    limit_schedules = tuple(
        _load_limit_schedule(item, path=f"limit_schedules[{i}]")
        for i, item in enumerate(raw.get("limit_schedules") or [])
    )

    return L2Instance(
        instance=instance,
        accounts=accounts,
        account_templates=account_templates,
        rails=rails,
        transfer_templates=transfer_templates,
        chains=chains,
        limit_schedules=limit_schedules,
    )
