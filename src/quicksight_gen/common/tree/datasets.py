"""Dataset tree nodes (L.1.7).

Dataset is a first-class tree concept: visuals and filters reference a
``Dataset`` instance by object ref instead of by string identifier,
and the ``App`` walks the tree to derive the precise dependency
graph — which Sheet / Visual / FilterGroup uses which Dataset.

The dependency graph drives:
- Selective deploy (only re-create datasets that downstream changes
  touch).
- Matview REFRESH ordering (REFRESH only the matviews backing
  Datasets that an updated deploy surface depends on).

Construction-time check (in App.emit_analysis): every Dataset
referenced from the tree must be registered on the App via
``app.add_dataset()``. Catches "visual references undeclared dataset"
at emit time, where the existing string-keyed pattern lets the
mismatch flow through to deploy.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.common.models import DataSetIdentifierDeclaration


@dataclass(frozen=True)
class Dataset:
    """Tree node for one dataset registration on the App.

    ``identifier`` is the logical identifier visuals/filters reference
    (the existing per-app DS_INV_ACCOUNT_NETWORK / DS_AR_TRANSACTIONS
    strings — values like ``"inv-account-network-ds"``). ``arn`` is
    the AWS QuickSight DataSetArn the deployed analysis points at.

    Frozen because Dataset acts as the dependency-graph KEY: it must
    be hashable so visuals/filters that reference it can be collected
    into ``set[Dataset]`` for the dependency walk.
    """
    identifier: str
    arn: str

    def emit_declaration(self) -> DataSetIdentifierDeclaration:
        return DataSetIdentifierDeclaration(
            Identifier=self.identifier, DataSetArn=self.arn,
        )
