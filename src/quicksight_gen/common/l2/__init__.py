"""LAYER 2 institutional model — typed primitives + loader + validator.

This package is the production library code that supersedes the M.0 spike
(``quicksight_gen.l2_spike``). Per the M.0.13 iteration gate, M.1 lifts
the spike's working glue here piece by piece:

  M.1.1  primitives.py — typed dataclasses for every L2 SPEC primitive.
  M.1.2  loader.py     — YAML → primitives, with friendly error messages.
  M.1.3  validate.py   — load-time SPEC validation rules + rejection tests.
  M.1.4  emit.py       — prefix-aware SQL emission for L1 + L2 tables.
  M.1.5  current.py    — Current* SQL views for Transaction + StoredBalance.
  M.1.10 (separate)    — promote ScreenshotHarness from tests/e2e/.

External callers import from this package's public surface, not from any
internal submodule.
"""

from .derived import PARENT_TRANSFER_ID, posted_requirements_for
from .loader import L2LoaderError, load_instance
from .schema import emit_schema, refresh_matviews_sql
from .theme import ThemePreset
from .validate import L2ValidationError, validate
from .primitives import (
    Account,
    AccountTemplate,
    BundlesActivityRef,
    CadenceExpression,
    ChainEntry,
    CompletionExpression,
    Duration,
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
    SupersedeReason,
    TransferTemplate,
    TransferType,
    TwoLegRail,
)

__all__ = [
    "Account",
    "AccountTemplate",
    "BundlesActivityRef",
    "CadenceExpression",
    "ChainEntry",
    "CompletionExpression",
    "Duration",
    "Identifier",
    "L2Instance",
    "L2LoaderError",
    "L2ValidationError",
    "LegDirection",
    "LimitSchedule",
    "Money",
    "Name",
    "Origin",
    "PARENT_TRANSFER_ID",
    "Rail",
    "RoleExpression",
    "Scope",
    "SingleLegRail",
    "SupersedeReason",
    "ThemePreset",
    "TransferTemplate",
    "TransferType",
    "TwoLegRail",
    "emit_schema",
    "refresh_matviews_sql",
    "load_instance",
    "posted_requirements_for",
    "validate",
]
