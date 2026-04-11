# Plan: Drill-Down Navigation via QuickSight Actions

## Goal

Allow users to click through the financial pipeline — from a payment to its settlement, and from a settlement to its constituent sales. This uses QuickSight's `VisualCustomAction` with `NavigationAction` to jump between sheets with filter context.

## User Experience

1. **Payments table** → click a row → navigates to the **Settlements** sheet, filtered to that `settlement_id`
2. **Settlements table** → click a row → navigates to the **Sales** sheet, filtered to that `settlement_id`
3. Both directions follow the natural pipeline: **Sales ← Settlements ← Payments**

The detail tables will show a subtle subtitle hint like "Click a row to see its settlement" so users discover the feature.

## Data Model (Already in Place)

```
Sales.settlement_id  →  Settlements.settlement_id  ←  Payments.settlement_id
```

All three datasets already have `settlement_id` as a column. The sales detail table doesn't currently display it, but it's available in the dataset.

## QuickSight API Concepts

### VisualCustomAction
Attached to a visual, triggers on user interaction (e.g., clicking a data point). Structure:

```json
{
  "CustomActionId": "action-drill-to-settlements",
  "Name": "View Settlement",
  "Trigger": "DATA_POINT_CLICK",
  "Status": "ENABLED",
  "ActionOperations": [
    {
      "NavigationOperation": {
        "LocalNavigationConfiguration": {
          "TargetSheetId": "sheet-settlements"
        }
      }
    },
    {
      "FilterOperation": {
        "SelectedFieldsConfiguration": {
          "SelectedFieldOptions": "ALL_FIELDS"  -- or specific columns
        },
        "TargetVisualsConfiguration": {
          "SameSheetTargetVisualConfiguration": {
            "TargetVisualOptions": "ALL_VISUALS"
          }
        }
      }
    }
  ]
}
```

**Key question**: QuickSight's `NavigationOperation` navigates to another sheet, and `FilterOperation` passes the clicked row's values as filters. We need to confirm whether `FilterOperation` + `NavigationOperation` together pass filter context to the target sheet, or whether we need `SetParameterValueAction` with analysis-level parameters instead.

### Alternative: Parameters + SetParameterValueAction
If `FilterOperation` doesn't carry across sheets via `NavigationOperation`:
1. Define analysis-level `ParameterDeclaration` for `settlement_id` (string type)
2. Add `SetParameterValueAction` on the source visual to set the parameter from the clicked row
3. Add a `CategoryFilter` on the target sheet tied to the parameter
4. Use `NavigationOperation` to switch sheets

This is more complex but guaranteed to work cross-sheet.

## Implementation Steps

### Phase 1: New Models in `models.py`

Add dataclasses for:
- `VisualCustomAction` — CustomActionId, Name, Trigger, Status, ActionOperations
- `VisualCustomActionOperation` — union of NavigationOperation, FilterOperation, SetParameterValueAction, URLOperation
- `NavigationOperation` / `LocalNavigationConfiguration`
- `FilterOperation` / `SelectedFieldsConfiguration` / `TargetVisualsConfiguration`
- If needed: `ParameterDeclaration`, `SetParameterValueConfiguration`

Update existing visuals to accept actions:
- `TableVisual.Actions: list[VisualCustomAction] | None`
- `BarChartVisual.Actions: list[VisualCustomAction] | None`
- (other visual types as needed)

### Phase 2: Add Actions to Financial Visuals (`visuals.py`)

**Payments detail table** — add action:
- Trigger: `DATA_POINT_CLICK`
- Name: "View Settlement"
- Operations: navigate to `SHEET_SETTLEMENTS`, filter by `settlement_id`

**Settlements detail table** — add action:
- Trigger: `DATA_POINT_CLICK`
- Name: "View Sales"
- Operations: navigate to `SHEET_SALES`, filter by `settlement_id`

**Sales detail table** — add `settlement_id` column to the displayed fields (currently missing from the table but available in the dataset)

Update subtitles:
- Payments table: "Click a row to view its settlement"
- Settlements table: "Click a row to view its sales"

### Phase 3: Update Sheet Definitions (`analysis.py`)

If using the parameter approach:
- Add `ParameterDeclarations` to `AnalysisDefinition` (new field)
- Add parameter-driven `CategoryFilter` for `settlement_id` on Sales and Settlements sheets

### Phase 4: Tests

- Verify actions serialize correctly in JSON output
- Verify the settlement_id column appears in the sales detail table
- Verify action references use correct target sheet IDs
- Integration test: full pipeline generates valid JSON with actions

### Phase 5: Deploy & Validate

- Regenerate JSON and deploy
- Test click-through in QuickSight console
- Verify filters clear when navigating away and back

## Decisions

1. **FilterOperation cross-sheet**: Need to test whether `FilterOperation` + `NavigationOperation` passes context cross-sheet. Try the simple approach first; fall back to parameters if it doesn't work.

2. **Back navigation**: Rely on browser back button / sheet tabs — no custom back actions needed.

3. **Bar chart drill-down**: Yes — clicking a merchant on a bar chart should filter the detail table on the same sheet. This is a same-sheet `FilterOperation` and a natural complement to the cross-sheet navigation.

4. **Reconciliation analysis**: Yes — add bidirectional drill-down:
   - From external transaction detail → internal records (which sales/settlements/payments make up this transaction?)
   - From internal record detail → external transaction (which external transaction does this map to?)
   - Linked via `external_transaction_id` which exists on both sides

## Implementation Phases

### Phase 1: Models + Financial Cross-Sheet Navigation
Build the action models and wire up the Payments → Settlements → Sales drill-down.

### Phase 2: Financial Same-Sheet Bar Chart Filtering
Add `FilterOperation` to bar charts so clicking a merchant/location/type filters the detail table on the same sheet.

### Phase 3: Reconciliation Drill-Down
Add bidirectional navigation between recon overview and per-type sheets, plus internal ↔ external linking via `external_transaction_id`.

## Files to Change

| File | Change |
|------|--------|
| `models.py` | Add action dataclasses (VisualCustomAction, NavigationOperation, FilterOperation), update visual types with Actions field |
| `visuals.py` | Add cross-sheet drill-down on payments/settlements tables, same-sheet filter on bar charts, add settlement_id to sales table |
| `recon_visuals.py` | Add bidirectional drill-down between internal records and external transactions |
| `analysis.py` | Possibly add ParameterDeclarations to AnalysisDefinition |
| `recon_analysis.py` | Same if parameters needed for recon |
| `test_generate.py` | Add action serialization tests |
| `test_recon.py` | Add recon drill-down tests |
| `SPEC.md` | Document drill-down feature |
