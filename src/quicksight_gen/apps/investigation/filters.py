"""Investigation filter groups + sheet controls.

K.4.2 ships none — skeleton sheets carry no filters. K.4.3-K.4.5 add
per-sheet controls (window length / fanout threshold; σ threshold /
window length; starting transfer_id / max hops / min hop amount).
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import FilterGroup


def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    """No filter groups yet — skeleton sheets are static."""
    return []
