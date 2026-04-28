"""L2 Flow Tracing — datasets (M.3.4 skeleton).

The skeleton ships with zero datasets — sheets are placeholders. The
per-tab datasets land at:

- M.3.5 — Rails tab — ``<prefix>-l2ft-rails-dataset``
- M.3.6 — Chains tab — ``<prefix>-l2ft-chains-dataset``
- M.3.7 — L2 Exceptions tab — six small KPI datasets (one per
  exception kind), each backed by a SQL view.
- M.3.8 — Auto metadata-driven filter dropdown sources.

Keeping the function present (returning ``[]``) lets the CLI's
``_all_dataset_filenames`` and ``_generate_l2_flow_tracing`` plumb the
app through unchanged; M.3.5+ just expands the body.
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.tree import Dataset


def build_all_l2_flow_tracing_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[Dataset]:
    """Return every Dataset the L2 Flow Tracing app needs.

    M.3.4 skeleton: empty. M.3.5+ populates per-tab.
    """
    return []
