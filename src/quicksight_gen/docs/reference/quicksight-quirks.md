# QuickSight quirks log

Bugs, undocumented behaviors, and silent-failure modes we've hit
while building the four shipped dashboards. Each entry captures the
observed behavior, the user-visible symptom, the workaround we
ship, and the suggested fix on the QuickSight side.

This page exists for two reasons:

1. **Defect reports.** We've collected enough QS-side issues that
   filing them with the QuickSight team needs a single canonical
   reference, not bug-by-bug archeology across this repo's commit
   history.
2. **Operator survival kit.** When a dashboard renders blank or a
   control behaves oddly, scan this page first — most of the
   "didn't I just fix that?" moments are a returning instance of one
   of these classes.

---

## 1. Silent rendering failures

### 1.1 Spinner-forever — entire dashboard stuck, no error surfaced

**Observed.** Every visual on every sheet shows the loading spinner
indefinitely. No error banner, no narrowing-to-zero filter, no
API-level error from `describe-dashboard`. Datasets describe as
`CREATION_SUCCESSFUL` and return rows when queried directly through
the QS data-source connection. The database itself responds in
milliseconds.

**Diagnostic ladder we use:**

1. Verify the database returns rows for the underlying SQL via
   `psycopg2` / `oracledb` — proves the data is there.
2. Verify `describe_data_set` returns `CREATION_SUCCESSFUL` —
   proves the dataset exists.
3. Open the dashboard in a fresh incognito window — rules out
   browser cache.
4. Assume QuickSight itself is the broken layer. Either wait it out
   (sometimes clears on its own) or force a full
   delete-then-create of the entire QS resource graph (theme,
   datasource, all datasets, analysis, dashboard) plus a clean
   re-seed + matview refresh.

**Workaround.** Capture the diagnostic ladder in CLAUDE.md so we
don't keep re-checking the SQL or the data when the data is fine.

**Suggested fix.** Either surface a useful error to the user when
the QS rendering pipeline stalls, or expose a `dashboard health`
endpoint so the cause is debuggable without blind delete-then-create.

---

### 1.2 KPI silently renders blank with a partially-populated `KPIOptions`

**Observed.** `CreateAnalysis` accepts a `KPIOptions` shape that's
missing a few fields the QS UI always populates. The KPI then
renders as a blank tile in the deployed dashboard — no error at
create time, no warning in the UI. A separately-emitted error
message ("Only `PrimaryValueFontSize` display property...") shows
up only when emitting *certain* partial shapes — not all of them.

**Workaround.** Mirror exactly what QS UI defaults to: emit the
full `KPIOptions` block with `Comparison`, `PrimaryValueDisplayType`,
`SecondaryValueFontConfiguration`, `TargetValues=[]`,
`TrendGroups=[]` even when not used. See `common/tree/visuals.py`
`KPI.emit()` for the canonical shape (M.4.4.8).

**Suggested fix.** Document `KPIOptions` as required (not optional)
on `KPIVisual.ChartConfiguration`, OR make the API server-side fill
in the missing defaults when CLI sends a partial shape.

---

### 1.3 Filter binding to a parameter the analyst can't set silently
empties every visual

**Observed.** A `CategoryFilter.with_parameter(...)` /
`TimeEqualityFilter` / `NumericRangeFilter` (with
`minimum_parameter` / `maximum_parameter`) bound to a parameter
that has *no* sheet control becomes a `WHERE clause matches nothing`
at runtime. Every visual that depends on the filter renders
empty. No error.

**Workaround.** Tree validator
(`App._validate_filter_param_settability`) walks the tree at
construction time and rejects any parameter-bound filter whose
parameter isn't reachable from a sheet control. Catches the bug
class at emit time, not at deploy time.

**Suggested fix.** QS could surface a "filter parameter is
unreachable" warning in the UI when the analyst hovers the empty
visual.

---

## 2. Drill / parameter-write quirks

### 2.1 URL parameter doesn't sync sheet controls

**Observed.** When a deep-link URL sets a parameter via the
`p.<name>=<value>` query-string convention, the parameter value
*is* applied to data filters — but the sheet control widget shows
"All" (or the unmodified default). The control text and the
filtered data disagree. The same defect hits QS's own Navigation
Action — there's no way to re-sync the control text with the
parameter from the embedding side.

**Workaround.** Per memory `project_qs_url_parameter_no_control_sync`:
K.4.7 cross-app drills dropped because of this. The sheet
description for affected sheets tells analysts "trust the chart,
not the control text".

**Suggested fix.** Make `p.<name>=<value>` URL params propagate
into the sheet control's display value, OR expose a `setParameters`
method on the embedding SDK that does propagate.

---

### 2.2 In-app drill writes to a `DateTimeParam` snap the picker
visibly to the static value

**Observed (v8.5.7).** `SetParametersOperation.ParameterValueConfigurations`
that writes a `CustomValuesConfiguration.CustomValues.DateTimeValues`
to a destination `DateTimeParam` correctly updates the parameter
AND snaps the destination's picker control to that value. There's
no way to "write the parameter value but leave the picker alone"
or "widen the parameter without changing the picker".

**Workaround.** When a cross-sheet drill needs the destination's
universal date filter to be wide enough that the target row is
visible (e.g. drilling a stuck-pending leg older than 7 days into
the date-scoped Transactions sheet), we write
`pL1DateStart=1990-01-01` and `pL1DateEnd=2099-12-31` — the
"all time" sentinel pair. The picker visibly snaps to those values.
Documented as a UX wart.

**Suggested fix.** Either (a) allow writes that update the param
without re-rendering the picker control, or (b) expose a
`SetParameters` operation that takes an *expression* (e.g.
`addDateTime(-N, 'DD', truncDate('DD', now()))`) so the rolling
default can re-anchor without a static literal showing in the
picker.

---

### 2.3 `SetParametersOperation` only accepts static values or
column refs — no `now()` or rolling-date expressions

**Observed.** Drill writes to `DateTimeParam` destinations can only
carry one of: a `SourceField` reading from a clicked row column, or
a `CustomValues.DateTimeValues=[<ISO-8601 literal>]` static value.
The `RollingDate.Expression` shape that `ParameterDeclaration.DefaultValues`
accepts is NOT accepted as a `SetParametersOperation` value — there's
no way to write "today minus 7 days" via a drill.

**Workaround.** Use the static far-past + far-future literals
(see 2.2). Authors who want a rolling drill-write would have to
build it from the embedding SDK at click time, which defeats the
purpose of declarative drill actions.

**Suggested fix.** Allow `RollingDate.Expression` as a value type
on `SetParametersOperation`.

---

### 2.4 Sankey right-click drill is non-functional in practice

**Observed.** Wiring a `Drill` action to a Sankey visual's
right-click trigger emits successfully but the menu either doesn't
appear or doesn't fire on click. Verified across multiple
configurations.

**Workaround.** Investigation Account Network sheet uses two
separate left-click Sankeys (inbound + outbound) instead of one
bidirectional Sankey with right-click drill. Pattern documented
in `walkthroughs/investigation/what-does-this-accounts-money-network-look-like.md`.

**Suggested fix.** Either fix the right-click drill on Sankey or
remove the option from the API so it doesn't look supported.

---

## 3. Control / widget UX quirks

### 3.1 `ParameterDropDownControl` only opens on the inner grey bar

**Observed.** The dropdown widget renders a wider visible area
than the actual click target. Clicking the visible outer edge of
the control does nothing — the popover only opens when the click
hits the narrow grey bar in the middle of the control. Confused
users assume the dropdown is broken.

**Workaround.** Documented in sheet descriptions where the
dropdown matters (e.g. Account Network anchor picker). Per memory
`project_qs_dropdown_click_target`: suggest as the first thing to
check when an analyst reports an "unresponsive dropdown".

**Suggested fix.** Make the entire control area click-targetable.

---

### 3.2 Single-character sheet names are hidden from the rendered
tab strip

**Observed.** Naming a sheet `"i"` (1-char) makes the tab
invisible in the deployed dashboard's tab strip. The sheet still
exists and is reachable via deep link, but the navigation tab is
gone. Verified against `us-east-2`.

**Workaround.** All app-info / canary sheets renamed to a 2+ char
display name (we ship as `Info`).

**Suggested fix.** Either drop the implicit 1-char filter or
document it.

---

### 3.3 Tables virtualize ~10 DOM rows regardless of page size

**Observed.** Even with the table's page size set to a large value
(say 10000), the DOM only mounts ~10 rows at a time. Browser-side
e2e assertions that count visible rows saturate at 10. This isn't
a bug per se, but it's surprising to anyone treating the table as
"all rows in the DOM" for assertion purposes.

**Workaround.** `count_table_rows` returns DOM-visible (saturates
at ~10). For accurate post-filter counts, use
`count_table_total_rows` which scrolls + accumulates the true
total. Slower; bumps page size to 10000 and walks the inner
`.grid-container`.

**Suggested fix.** Either document the virtualization behavior or
expose a "snapshot total row count" property the client can read
without scrolling.

---

### 3.4 QS holds open WebSocket connections so `networkidle` never
fires

**Observed.** Playwright's `wait_for_load_state('networkidle')`
never fires on a deployed QS dashboard because QS holds open
WebSocket / long-polling connections continuously. Naively waiting
for networkidle burns the entire page timeout.

**Workaround.** Wait on a DOM signal instead — the
`[role="tab"]` selector attaching is the authoritative
"chrome is up" signal, in practice ~1s after embed-URL load
completes. See `wait_for_dashboard_loaded` in
`common/browser/helpers.py`.

**Suggested fix.** Document the network behavior or expose a
"dashboard ready" event the embedding SDK can wait on.

---

## 4. Data type / shape quirks

### 4.1 `DateDimensionField` vs `CategoricalDimensionField` — column
type must match

**Observed.** A column declared as `DATETIME` in the dataset
contract MUST be wrapped in a `DateDimensionField` when used as a
chart Category. Wrapping it in a `CategoricalDimensionField` (the
default for non-date columns) produces a dashboard that
silently fails to render the visual — the field appears in the
field-well but the chart is blank.

**Workaround.** Per memory `project_qs_date_dimensions`: enforced
by the typed `Dim.date()` factory in `common/tree/datasets.py`.
The bare `Dim()` constructor for a date column raises at
construction time.

**Suggested fix.** Auto-detect the column type from the dataset
contract and pick the right `DimensionField` subtype, OR raise a
useful error at create-analysis time.

---

### 4.2 Conditional formatting expression must guard against the
zero-rows case

**Observed.** A `ConditionalFormatting` expression like
`{column} > 0` (numeric threshold) silently breaks when the table
has zero rows — no error, the table just doesn't apply the
formatting. Empirically the formatting only fires when the
expression contains a "self-equality" guard.

**Workaround.** Per memory `project_qs_conditional_formatting`:
always wrap the expression as `{col} <> "<sentinel>"` so the
expression is *always true* when the column is non-null. The
formatting then fires unconditionally, and we use the column value
itself for the actual styling decision elsewhere.

**Suggested fix.** Document the empty-table behavior or fix the
expression evaluator to treat zero rows as "format nothing"
gracefully.

---

### 4.3 `DateTimeParam.default` is required — UI errors with
"epochMilliseconds must be a number, you gave: null"

**Observed.** A `ParameterDeclaration` for a `DateTimeParameter`
that omits `DefaultValues` deploys cleanly. When the analyst opens
the dashboard, the UI throws "epochMilliseconds must be a number,
you gave: null" — visible only in the JS console — and the
DateTime picker control associated with the param fails to
hydrate.

**Workaround.** Type-encode in `tree/parameters.py`:
`DateTimeParam.default` is REQUIRED (not optional). Attempts to
construct `DateTimeParam(default=None)` raise at construction
time. See M.4.4.10d.

**Suggested fix.** Either reject `DateTimeParameter` declarations
without a default at create-analysis time, or make the picker
hydrate cleanly with a null param value (e.g. show empty until
analyst picks).

---

### 4.4 `SheetTextBox.Content` rejects `<br>` as a child of `<li>`

**Observed.** The text-box XML grammar accepts `<br/>` for line
breaks AND `<ul><li>...</li></ul>` for bullet lists. Putting one
inside the other — `<li>foo<br/>bar</li>` — is rejected by the
parser at `CreateAnalysis` time with
`Element 'li' cannot have 'br' elements as children`. The error
message names the offending text-box by `TextBoxId` and the
sheet by `SheetId`, but no other rich-text element class is
called out (e.g. `<li>` is fine inside `<ul>` and `<a>` is fine
inside `<li>`). Surfaces silently up to deploy: the JSON
serialises cleanly and the dataset describes cleanly.

**Workaround.** `common/rich_text.py::bullets()` post-processes
each item to strip `<br>`, `<br/>`, and `<br />` (case-insensitive)
and emits a `UserWarning` per offender. Triggered by L2 YAML
descriptions authored as `description: |` block scalars: the
embedded `\n` from human-readable line wrapping reflowed to
`<br/>` via `markdown()` and crashed the L1 Drift sheet's
`l1-drift-accounts` text box — see `common/rich_text.py` and
`tests/json/test_text_box_safety.py::test_no_br_inside_li_in_text_box_content`
(v8.5.8).

**Suggested fix.** Either accept `<br/>` inside `<li>` (the most
permissive web-HTML behavior matches most authors' expectations),
or surface the rejection at JSON-validation time (before the
`CreateAnalysis` round-trip) so callers learn about it without
deploying.

---

## 5. Backend / refresh quirks

### 5.1 Embed URL must be signed by the dashboard's region (not
the QuickSight identity region)

**Observed.** `generate_embed_url_for_registered_user` called via
a boto3 client constructed in the QS identity region (`us-east-1`)
returns a URL that, when opened, errors with "We can't open that
dashboard, another QuickSight account or it was deleted" — even
though the dashboard, account, and permissions are all correct.
The error message is misleading: it implies an account/permission
problem when the actual cause is region mismatch.

**Workaround.** Construct the boto3 client in the *dashboard's*
region (not the identity region). See
`common/browser/helpers.py::generate_dashboard_embed_url` —
takes `aws_region` keyword and constructs the client itself so
callers can't pass the wrong-region client. Burned ~1 hour
debugging this on the M.4.1.i first AWS-side dry-run.

**Suggested fix.** Either accept identity-region-signed URLs for
cross-region dashboards, or surface a "region mismatch" error
instead of the misleading "another account" message.

---

### 5.2 `boto3.client("quicksight")` overload set is so large
pyright reports "type partially unknown"

**Observed (v8.5.2).** `boto3-stubs[quicksight]` typing is
correct, but pyright's overload resolution on `boto3.client` —
which has Literal-overloads for every AWS service — reports the
return type as "partially unknown" even when the inferred type is
the right `QuickSightClient`. Two contradictory errors at the same
line.

**Workaround.** `qs: QuickSightClient = boto3.client(...)  # pyright: ignore[reportUnknownMemberType]`
— targeted suppression at the call site that lets the LHS type
annotation drive downstream inference.

**Suggested fix.** This is more of a `boto3-stubs` packaging
concern than QS itself, but flagging because every typed Python
client of the QS SDK hits this.

---

### 5.3 Materialized views don't auto-refresh

**Observed.** L1 invariant matviews + Investigation matviews
created via `CREATE MATERIALIZED VIEW` don't auto-refresh on
underlying-table changes. Every ETL load (and every `data apply`)
must explicitly call `REFRESH MATERIALIZED VIEW`. Not a QS bug —
a Postgres / Oracle behavior — but the dashboard reads stale data
silently when the refresh is missed, with no error.

**Workaround.** `quicksight-gen data refresh --execute` runs the
refresh in dependency order. CLAUDE.md "Operational Footguns"
section flags this as a footgun.

**Suggested fix.** Not a QS bug per se. Documenting here because
"the dashboard shows old data" is often initially blamed on QS.

---

## How to use this page when filing defects

For each issue you want to file with the QuickSight team:

1. Find the entry above (or add a new one if it's a new class).
2. Reproduce against a minimal hand-built analysis JSON — strip
   our generator's wrappers down to the smallest dict that
   triggers the behavior.
3. Capture the JSON, the API response (if any), and a screen
   recording of the misbehavior.
4. Cross-reference this page in the report so the QS team can see
   the workaround context — sometimes the workaround clue helps
   diagnose the root cause faster than the bare repro.
