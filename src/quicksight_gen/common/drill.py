"""Typed cross-sheet drill helpers.

K.2 spike caught a sneaky bug class: a drill action bound a DATETIME
source column (``exception_date``) to a SINGLE_VALUED string parameter
(``pArActivityDate``), and QuickSight silently coerced it to a full
timestamp text ``"2026-04-07 00:00:00.000"`` that never matched the
destination's TO_CHAR-formatted ``posted_date`` column. Both ends were
"STRING" at the AWS coarse-type level, but the textual encodings
differed and the destination filter quietly produced zero rows. Bugs
like this look like missing data, not broken wiring — corrosive to
user trust.

Per the user's "encode invariants in the type system" preference, the
fix isn't a validation test that walks the generated output; it's a
typed constructor that refuses to wire incompatible shapes at all. The
typed wrappers here let any wrong wiring fail at the call site with a
TypeError that names both sides of the mismatch.

Usage::

    from quicksight_gen.common.drill import (
        DrillParam, DrillResetSentinel, cross_sheet_drill, field_source,
    )

    P_AR_ACCOUNT = DrillParam("pArAccountId", ColumnShape.ACCOUNT_ID)

    cross_sheet_drill(
        action_id="...",
        name="View Transactions for Account-Day",
        target_sheet=SHEET_AR_TRANSACTIONS,
        writes=[
            (P_AR_ACCOUNT, field_source("ar-todays-exc-account",
                                        DS_AR_UNIFIED_EXCEPTIONS, "account_id")),
            (P_AR_ACTIVITY_DATE, field_source(...)),
            (P_AR_TRANSFER, DrillResetSentinel()),
        ],
        trigger="DATA_POINT_MENU",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from quicksight_gen.common.dataset_contract import (
    ColumnShape,
    get_contract,
)
from quicksight_gen.common.ids import ParameterName, SheetId
from quicksight_gen.common.models import (
    CustomActionNavigationOperation,
    CustomActionSetParametersOperation,
    CustomActionURLOperation,
    LocalNavigationConfiguration,
    VisualCustomAction,
    VisualCustomActionOperation,
)


# Sentinel value for the K.2 calc-field PASS pattern. Any drill that
# wants to clear a parameter to "no filter" writes this literal value;
# the destination calc-field expression special-cases it to PASS.
DRILL_RESET_SENTINEL_VALUE = "__ALL__"


@dataclass(frozen=True)
class DrillParam:
    """Destination parameter on a drill action — name + expected shape.

    The shape captures the parameter's value semantics; ``set_drill_parameters``
    refuses to write a source field whose shape differs.
    """

    name: ParameterName
    shape: ColumnShape


@dataclass(frozen=True)
class DrillSourceField:
    """Source field on a drill action — visual field id + resolved shape.

    Build via ``field_source(field_id, dataset_id, column_name)`` so the
    shape is read from the dataset contract, not duplicated by hand.
    """

    field_id: str
    shape: ColumnShape


@dataclass(frozen=True)
class DrillResetSentinel:
    """Marker that a drill should reset a parameter to the sentinel value.

    The destination calc-field filter recognizes the sentinel as PASS,
    so writing this clears the filter without needing an empty-string
    or null-value path that QuickSight's drill-action code path won't
    deliver to calc fields cleanly.
    """

    value: str = DRILL_RESET_SENTINEL_VALUE


DrillWriteValue = Union[DrillSourceField, DrillResetSentinel]
DrillWrite = tuple[DrillParam, DrillWriteValue]


def field_source(
    field_id: str,
    dataset_id: str,
    column_name: str,
) -> DrillSourceField:
    """Resolve ``column_name``'s shape from its registered dataset contract.

    Raises ``TypeError`` if the column has no shape tag (it isn't drill-
    eligible), pointing at the call site so the developer can either
    tag the column in the contract or pick a different source column.
    Raises ``KeyError`` if the dataset_id isn't registered (usually
    means the dataset hasn't been built in this process yet — ensure
    ``build_all_datasets`` runs before visuals).
    """
    contract = get_contract(dataset_id)
    col = contract.column(column_name)
    if col.shape is None:
        raise TypeError(
            f"{dataset_id}.{column_name} is not drill-eligible (no "
            f"ColumnShape tag in its DatasetContract). Tag it in the "
            f"contract — and pick the shape carefully — or pick a "
            f"different source column for field_id {field_id!r}."
        )
    return DrillSourceField(field_id=field_id, shape=col.shape)


def set_drill_parameters(
    *writes: DrillWrite,
) -> CustomActionSetParametersOperation:
    """Construct a ``CustomActionSetParametersOperation`` from typed writes.

    Validates shape compatibility at construction time: writing a
    ``DrillSourceField`` whose shape doesn't match the ``DrillParam``
    raises ``TypeError`` at the call site. ``DrillResetSentinel`` is
    always shape-compatible (it writes a literal sentinel string that
    the destination calc-field interprets, regardless of param shape).

    Refuses an empty writes list — a no-op SetParametersOperation is
    almost certainly a wiring bug.
    """
    if not writes:
        raise ValueError(
            "set_drill_parameters requires at least one write. An empty "
            "drill action is almost certainly a programming error — if "
            "you really want navigation only, omit SetParametersOperation."
        )

    seen: set[str] = set()
    configs: list[dict] = []
    for param, value in writes:
        if param.name in seen:
            raise ValueError(
                f"Duplicate drill parameter {param.name!r} in writes — "
                f"each parameter can be written at most once per action."
            )
        seen.add(param.name)

        if isinstance(value, DrillSourceField):
            if not value.shape.can_assign_to(param.shape):
                raise TypeError(
                    f"Drill source shape mismatch: writing field "
                    f"{value.field_id!r} ({value.shape.name}) into "
                    f"parameter {param.name!r} (expects {param.shape.name})."
                    f" This is the K.2 bug class — pick a source column "
                    f"whose contract shape is assignable to the parameter, "
                    f"widen the parameter's shape if both subtypes are "
                    f"valid, or redefine the parameter's shape if you "
                    f"genuinely want a different semantic."
                )
            configs.append({
                "DestinationParameterName": param.name,
                "Value": {"SourceField": value.field_id},
            })
        elif isinstance(value, DrillResetSentinel):
            configs.append({
                "DestinationParameterName": param.name,
                "Value": {
                    "CustomValuesConfiguration": {
                        "CustomValues": {
                            "StringValues": [value.value],
                        },
                    },
                },
            })
        else:  # defensive — Union exhaustiveness
            raise TypeError(
                f"Unsupported drill write value {value!r} for parameter "
                f"{param.name!r}. Expected DrillSourceField or "
                f"DrillResetSentinel."
            )
    return CustomActionSetParametersOperation(
        ParameterValueConfigurations=configs,
    )


@dataclass(frozen=True)
class URLSourceColumn:
    """Source column reference for URL-action substitution.

    URL templates substitute ``<<column_name>>`` with the clicked row's
    value at click time, where ``column_name`` is the source dataset's
    column name (not the visual's FieldId — confirmed against a
    hand-built sample). Build via ``url_column(dataset_id, column_name)``
    so the column's shape is read from the dataset contract for
    shape-checking, mirroring ``DrillSourceField``.

    The column must be in use in the host visual's field well — QS only
    binds substitution for fields actively referenced by the visual.
    """

    column_name: str
    shape: ColumnShape


def url_column(dataset_id: str, column_name: str) -> URLSourceColumn:
    """Resolve ``column_name``'s shape from its registered dataset contract.

    Raises ``TypeError`` if the column has no shape tag; raises
    ``KeyError`` if the dataset_id isn't registered. Same constraints as
    ``field_source`` — tag the column in its DatasetContract first.
    """
    contract = get_contract(dataset_id)
    col = contract.column(column_name)
    if col.shape is None:
        raise TypeError(
            f"{dataset_id}.{column_name} is not drill-eligible (no "
            f"ColumnShape tag in its DatasetContract). Tag it in the "
            f"contract — and pick the shape carefully — or pick a "
            f"different source column for this URL substitution."
        )
    return URLSourceColumn(column_name=column_name, shape=col.shape)


URLWrite = tuple[DrillParam, URLSourceColumn]


def _build_url_template(
    region: str,
    dashboard_id: str,
    writes: list[URLWrite],
) -> str:
    """Compose the QuickSight dashboard URL with parameter substitutions.

    Form: ``https://{region}.quicksight.aws.amazon.com/sn/dashboards/{id}#p.x=<<col>>&p.y=<<col>>``

    The ``/account/{alias}/`` and ``/sheets/{sheet_id}`` path components
    QS surfaces in its UI are deliberately omitted: the alias-bearing
    form is account-specific and would require shipping the alias as
    config; the ``/sheets/`` suffix appeared to suppress substitution in
    a hand-built sample. QS auto-redirects through ``/account/{alias}/``
    on click, so the simpler form is what we generate.
    """
    base = f"https://{region}.quicksight.aws.amazon.com/sn/dashboards/{dashboard_id}"
    fragment = "&".join(
        f"p.{param.name}=<<{src.column_name}>>"
        for param, src in writes
    )
    return f"{base}#{fragment}"


def cross_app_drill(
    action_id: str,
    name: str,
    target_dashboard_id: str,
    region: str,
    writes: list[URLWrite],
    trigger: Literal["DATA_POINT_CLICK", "DATA_POINT_MENU"] = VisualCustomAction.DATA_POINT_MENU,
    url_target: Literal["SAME_TAB", "NEW_TAB", "NEW_WINDOW"] = "NEW_TAB",
) -> VisualCustomAction:
    """Build a URL-action drill that deep-links into a sibling dashboard.

    Used for cross-analysis drills (Investigation → AR/PR) since QS
    ``LocalNavigationConfiguration`` only navigates within the same
    analysis. Substitutes the clicked row's value into the destination
    dashboard URL via the ``<<column_name>>`` placeholder syntax.

    Default ``trigger=DATA_POINT_MENU`` (right-click) and ``url_target=
    NEW_TAB``: drills moving deeper / further-along the pipeline live on
    the right-click menu (per the drill direction convention), and
    opening in a new tab keeps the source analysis available so the
    analyst doesn't lose their place.

    Per K.2 cleanup: shape compatibility is validated at construction
    time — writing a ``URLSourceColumn`` whose shape doesn't match its
    paired ``DrillParam`` raises ``TypeError`` here, naming both sides.
    """
    if not writes:
        raise ValueError(
            "cross_app_drill requires at least one URL write. A URL "
            "action with no parameter substitution is just navigation; "
            "use a static URL helper if that's what you want."
        )

    seen: set[str] = set()
    for param, src in writes:
        if param.name in seen:
            raise ValueError(
                f"Duplicate URL drill parameter {param.name!r} — each "
                f"destination parameter can be written at most once."
            )
        seen.add(param.name)
        if not src.shape.can_assign_to(param.shape):
            raise TypeError(
                f"URL drill source shape mismatch: writing column "
                f"{src.column_name!r} ({src.shape.name}) into parameter "
                f"{param.name!r} (expects {param.shape.name}). Same K.2 "
                f"bug class as cross_sheet_drill — pick a column whose "
                f"contract shape is assignable to the parameter."
            )

    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger=trigger,
        ActionOperations=[
            VisualCustomActionOperation(
                URLOperation=CustomActionURLOperation(
                    URLTemplate=_build_url_template(
                        region=region,
                        dashboard_id=target_dashboard_id,
                        writes=writes,
                    ),
                    URLTarget=url_target,
                ),
            ),
        ],
    )


def cross_sheet_drill(
    action_id: str,
    name: str,
    target_sheet: SheetId,
    writes: list[DrillWrite],
    trigger: Literal["DATA_POINT_CLICK", "DATA_POINT_MENU"] = VisualCustomAction.DATA_POINT_CLICK,
) -> VisualCustomAction:
    """Build a NavigationOperation + SetParametersOperation drill.

    QuickSight requires a NavigationOperation before a
    SetParametersOperation, even when the target is the current sheet
    (used for same-sheet ledger→subledger filtering). This helper
    wraps both operations in the canonical order so callers don't
    re-derive the shape.

    Per K.2 cleanup: the typed ``writes`` list passes through
    ``set_drill_parameters`` so any shape mismatch fails here, at the
    wiring site, with both sides named.
    """
    return VisualCustomAction(
        CustomActionId=action_id,
        Name=name,
        Trigger=trigger,
        ActionOperations=[
            VisualCustomActionOperation(
                NavigationOperation=CustomActionNavigationOperation(
                    LocalNavigationConfiguration=LocalNavigationConfiguration(
                        TargetSheetId=target_sheet,
                    ),
                ),
            ),
            VisualCustomActionOperation(
                SetParametersOperation=set_drill_parameters(*writes),
            ),
        ],
    )
