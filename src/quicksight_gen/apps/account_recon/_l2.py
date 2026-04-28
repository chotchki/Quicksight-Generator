"""L2 instance loader + build-pipeline seam (M.2.3, repointed in M.3.2).

Originally the L2 bridge for the AR app — the AR app deletes in M.4.3
and this whole `apps/account_recon/` directory goes with it. M.3.2
repoints ``default_l2_instance()`` from the (now-deleted)
sasquatch_ar.yaml to the persona-neutral ``spec_example.yaml`` so the
L1 dashboard's default behavior post-M.3 doesn't carry implicit
Sasquatch flavor in production library code. Callers wanting the
canonical Sasquatch fixture pass ``l2_instance=...`` explicitly with
the loaded ``sasquatch_pr.yaml``.

This module survives only until M.4.3 — when ``apps/account_recon/``
deletes, callers will import the L1 dashboard's L2 bridge directly
from wherever it lands (likely the L2 dashboard build picks the
default from a CLI flag).
"""

from __future__ import annotations

from pathlib import Path

from quicksight_gen.common.l2 import L2Instance, load_instance


# Path to the persona-neutral SPEC example L2 instance. Test fixture
# today; M.5/M.6 will publish to a permanent location.
_SPEC_EXAMPLE_YAML: Path = (
    Path(__file__).resolve().parents[4]
    / "tests" / "l2" / "spec_example.yaml"
)


def default_l2_instance() -> L2Instance:
    """Load + validate the persona-neutral default L2 instance.

    Used by ``build_l1_dashboard_app`` when the caller doesn't supply
    an ``l2_instance`` explicitly. Returns ``spec_example`` (M.3.2
    repoint) so production library code carries no implicit persona
    flavor; pass ``l2_instance=load_instance("...sasquatch_pr.yaml")``
    explicitly to render the canonical Sasquatch demo.
    """
    return load_instance(_SPEC_EXAMPLE_YAML)
