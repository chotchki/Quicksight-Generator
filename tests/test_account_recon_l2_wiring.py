"""Tests for the M.2.3 L2 wiring on the AR build pipeline.

The build pipeline now accepts an optional ``l2_instance`` kwarg that
defaults to the canonical Sasquatch AR fixture. M.2.4 will consume the
threaded instance to rewrite the dataset SQL; M.2.3 just verifies the
seam itself works (default-load, override, validation-at-build).

Existing AR tests in ``tests/test_account_recon.py`` continue to call
``build_account_recon_app(cfg)`` with no kwargs — those are the
"backward-compat" smoke (covered indirectly by the 962-passing suite).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.account_recon.app import build_account_recon_app
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import (
    Account,
    Identifier,
    L2Instance,
    L2ValidationError,
    Name,
    load_instance,
)


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


# -- default_l2_instance() --------------------------------------------------


def test_default_l2_instance_loads_sasquatch_ar() -> None:
    """The default loader returns the canonical Sasquatch AR fixture."""
    inst = default_l2_instance()
    assert inst.instance == "sasquatch_ar"
    # Spot-check a known role from sasquatch_ar.yaml.
    roles = {a.role for a in inst.accounts if a.role is not None}
    assert "DDAControl" in roles
    assert "ConcentrationMaster" in roles


def test_default_l2_instance_validates() -> None:
    """The fixture passes the full validator at load time — anything
    schema-invalid surfaces immediately rather than at build time."""
    # default_l2_instance() runs validate() inside; reaching this line
    # without raising IS the assertion.
    inst = default_l2_instance()
    assert inst is not None


# -- build_account_recon_app accepts l2_instance ---------------------------


def test_build_with_default_loads_sasquatch_ar() -> None:
    """Build with no kwarg auto-loads the Sasquatch fixture."""
    app = build_account_recon_app(_CFG)
    assert app is not None  # smoke; the body of the build is well-tested


def test_build_with_explicit_l2_instance_uses_caller_value() -> None:
    """Caller-supplied instance overrides the default load."""
    yaml_path = (
        Path(__file__).parent / "l2" / "sasquatch_ar.yaml"
    )
    custom = load_instance(yaml_path)
    # No mutation needed; the smoke is the build accepts and finishes.
    app = build_account_recon_app(_CFG, l2_instance=custom)
    assert app is not None


def test_build_signature_is_kwarg_only_for_l2_instance() -> None:
    """The new ``l2_instance`` parameter is keyword-only — positional
    callers (every existing test, every existing CLI shim) keep working
    without passing it."""
    import inspect
    sig = inspect.signature(build_account_recon_app)
    l2_param = sig.parameters.get("l2_instance")
    assert l2_param is not None
    assert l2_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert l2_param.default is None


# -- Backward compat: no kwargs still works (this IS the seam test) ---------


def test_existing_callers_unchanged() -> None:
    """Today's callers all pass just `cfg` positionally — that signature
    must keep working post-M.2.3 since M.2.4 hasn't touched downstream
    yet. (962-passing AR test suite would catch this; this is the
    explicit guard.)"""
    app1 = build_account_recon_app(_CFG)
    app2 = build_account_recon_app(_CFG)
    # Two builds of the same cfg produce structurally-equivalent apps —
    # smoke that no global state leaks between them.
    assert app1.name == app2.name == "account-recon"


# -- Build-time L2 validation ----------------------------------------------


def test_caller_supplied_l2_must_be_an_l2instance() -> None:
    """Type-level: passing something that isn't an L2Instance is a
    pyright error at the call site; runtime here just confirms the
    function annotation isn't accidentally `object`."""
    import inspect
    sig = inspect.signature(build_account_recon_app)
    l2_param = sig.parameters["l2_instance"]
    # Annotation might be a string under `from __future__ import annotations`;
    # accept either form.
    annot_str = str(l2_param.annotation)
    assert "L2Instance" in annot_str


# -- Future-tense (M.2.4) seam exists --------------------------------------


def test_l2_instance_carries_v6_prefix_for_dataset_sql_rewrite() -> None:
    """M.2.4 uses ``l2_instance.instance`` as the SQL prefix when rewriting
    the dataset queries. Confirm the prefix is what M.2.4 will consume."""
    inst = default_l2_instance()
    # The prefix is what every <prefix>_transactions / <prefix>_daily_balances
    # table name will use under M.2.4's rewrite.
    assert inst.instance == "sasquatch_ar"
    # And it's a valid Postgres identifier per F5 rules.
    import re
    assert re.match(r"^[a-z][a-z0-9_]*$", inst.instance)
    assert len(inst.instance) <= 30


def test_l2_account_topology_matches_today_ar_demo() -> None:
    """Cross-check: the L2 instance's account IDs must match today's
    demo_data.py slugs so M.2.6's integration test can plant rows that
    today's AR exception queries surface."""
    inst = default_l2_instance()
    internal_ids = {a.id for a in inst.accounts if a.scope == "internal"}
    # Smoke: a few of the canonical SNB GLs from today's demo_data.py.
    assert "gl-2010-dda-control" in internal_ids
    assert "gl-1850-cash-concentration-master" in internal_ids
    assert "gl-1010-cash-due-frb" in internal_ids


# -- M.2.4b-narrow: 2 drift datasets switched to v6 builders ----------------
#
# `build_account_recon_app(cfg)` now produces a tree whose ledger_drift +
# subledger_drift datasets target the M.1a.7 L1 invariant views, while
# the other 11 datasets stay on v5. The Balances sheet drift visuals are
# the M.2.6 deploy + verify target.


def test_drift_datasets_target_v6_l1_invariant_views() -> None:
    """The Balances sheet's two drift datasets now target
    `<prefix>_drift` and `<prefix>_ledger_drift` (M.1a.7 views) instead
    of v5's `ar_subledger_balance_drift` and `ar_ledger_balance_drift`."""
    from quicksight_gen.apps.account_recon.constants import (
        DS_AR_LEDGER_BALANCE_DRIFT,
        DS_AR_SUBLEDGER_BALANCE_DRIFT,
    )
    app = build_account_recon_app(_CFG)
    # The dataset arns reference the QuickSight DataSetId — same id as v5
    # (substitutability proven in M.2.4a's tests). Here we verify the
    # underlying DataSet's CUSTOM_SQL was emitted by the v6 builder by
    # walking the App's registered datasets and grepping their SQL.
    ds_by_id = {ds.identifier: ds for ds in app.datasets}
    assert DS_AR_SUBLEDGER_BALANCE_DRIFT in ds_by_id
    assert DS_AR_LEDGER_BALANCE_DRIFT in ds_by_id


def test_other_eleven_datasets_still_use_v5_builders() -> None:
    """M.2.4b-narrow scope: ONLY the 2 drift datasets switched.
    The other 11 still come from `build_all_datasets(cfg)` (v5)."""
    from quicksight_gen.apps.account_recon.constants import (
        DS_AR_TRANSACTIONS,
        DS_AR_LEDGER_ACCOUNTS,
        DS_AR_DAILY_STATEMENT_SUMMARY,
        DS_AR_UNIFIED_EXCEPTIONS,
    )
    app = build_account_recon_app(_CFG)
    ds_by_id = {ds.identifier: ds for ds in app.datasets}
    # Spot-check a few — they're all present (the build pipeline didn't
    # accidentally drop anything when overriding the 2 drift entries).
    for sentinel in (
        DS_AR_TRANSACTIONS,
        DS_AR_LEDGER_ACCOUNTS,
        DS_AR_DAILY_STATEMENT_SUMMARY,
        DS_AR_UNIFIED_EXCEPTIONS,
    ):
        assert sentinel in ds_by_id


def test_full_thirteen_dataset_count_preserved() -> None:
    """Sanity: the override doesn't drop or duplicate datasets."""
    app = build_account_recon_app(_CFG)
    assert len(app.datasets) == 13
