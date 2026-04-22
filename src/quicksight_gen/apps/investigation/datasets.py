"""Custom-SQL datasets for the Investigation app.

K.4.2 ships zero datasets. K.4.3 adds the recipient-fanout dataset,
K.4.4 the rolling-window anomaly dataset, K.4.5 the money-trail
recursive-CTE dataset.
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import DataSet


def build_all_datasets(cfg: Config) -> list[DataSet]:
    """Investigation has no datasets yet — sheets are skeleton-only."""
    return []
