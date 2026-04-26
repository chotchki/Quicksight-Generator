"""L2 instance loader + build-pipeline seam for the AR app (M.2.3).

The AR app's pre-M.2 build flow took only a ``Config`` and read all of
its data shape from hardcoded table names + per-dataset SQL strings
(see ``apps/account_recon/datasets.py``). M.2.3 introduces an
``L2Instance`` parameter to the build pipeline so M.2.4+ can rewrite
those datasets to use the L2 prefix + L2-derived account dim / scope
predicates.

This module owns:
- ``default_l2_instance()`` — loads + validates the canonical Sasquatch
  AR L2 fixture from ``tests/l2/sasquatch_ar.yaml``. Default for the
  build pipeline; callers MAY override (e.g., tests or alternative-
  persona deployments) via the ``l2_instance`` kwarg on
  ``build_account_recon_app``.
- The path constant naming the test-side YAML location. M.5/M.6 will
  move this to a published location (likely ``src/quicksight_gen/personas/``)
  once the CLI-driven persona workflow lands; the constant is a single
  source of truth that those substeps can update.

Why a thin module: keeping the loader in its own file isolates the
test-fixture-path detail (M.2.3-only concern) from the rest of the AR
build code, so M.5/M.6 can swap the path without touching app.py.
"""

from __future__ import annotations

from pathlib import Path

from quicksight_gen.common.l2 import L2Instance, load_instance, validate


# Path to the canonical Sasquatch AR L2 instance. Test fixture today;
# M.5/M.6 will publish to a permanent location.
_SASQUATCH_AR_YAML: Path = (
    Path(__file__).resolve().parents[4]
    / "tests" / "l2" / "sasquatch_ar.yaml"
)


def default_l2_instance() -> L2Instance:
    """Load + validate the canonical Sasquatch AR L2 instance.

    Used by ``build_account_recon_app`` when the caller doesn't supply
    an ``l2_instance`` explicitly. Validation runs at load time so a
    malformed fixture fails immediately rather than at first-use.
    """
    instance = load_instance(_SASQUATCH_AR_YAML)
    validate(instance)
    return instance
