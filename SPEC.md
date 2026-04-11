Goal: 
	- [  ] To create one or more AWS Quicksight analyses with a series of tabs to help understand a financial application.

Background:
	- [  ] This financial application uses a SQL datasource. For production use, a pre-existing datasource ARN is provided. For demo mode, the project creates a QuickSight data source definition from the demo database connection URL.

	- [  ] This SQL datasource will be accessed using quicksight custom sql data sets that this project will need to create against the data source. Dummy SQL queries are fine for the moment.

	- [  ] The financial application cares about a series of steps revolving around merchants taking in sales, this application bundles those sales to settle them and then pays those merchants at the end. 

	- [  ] This analysis will want to make queries to support each of those steps, provide controls to filter and easy ways to check if a settlement didn’t happen or payments were returned.
	- [  ] The financial application needs to ensure the sales, settlement, payments match to other systems. There will be successful matches, not yet matched and late matching which will be exceptions. This should be a separate quicksight analysis from the sales/settlement/payment one.

Key Domain Models to Understand:
	- Merchants make sales at a location

	- Sales may have additional metadata that may or may not be populated, merchant, amount, timestamp will be populated

        - Locations care only about merchants at their location but other people care about all the locations

        - Merchants sales are settled to them, the settlement type depends on the merchant type

        - Settlements are paid based on the merchant

	- There are unique identifiers for locations, merchants, sales,
	- The sales, settlements and payments are aggregated in multiple external systems as a series of transactions. Those transactions have unique identifiers and will each contain a certain amount of sales/settlements/payments. All external system data is accessed through the single configured datasource.
	- A match is only valid when the aggregation in the external system AND the sales/settlements/payments equal each other exactly. No partial matches — totals must be equal.
	- Something being late may have different static meaning depending on the type of the thing. We should show in the eventual analysis what it is set to but it does not need to be editable in quicksight. Unmatched items become late based on their type; the analysis should allow filtering by days outstanding so users can focus on the most overdue items.


Output:
	- [  ] Create something that creates the json that could be imported using the AWS cli to create the described analysis. The thing could be python, terraform, some combination of it.

	- [  ] The customer of these aws quicksight reports doesn’t know what they want so an ability to mutate this project either via you (Claude) OR some level of structured code that generates the quick sight reports will be VERY helpful.
	- [ ] The customer likely doesn't understand this spec, the quicksight dashboards should include easy to understand explations to help someone understand what each analysis, sheet, visualization does.

	- [  ] Build a consistent theme that looks nice, color theme blues and greys but must be easily read. Apply the theme and reasonable styling to everything produced.

	- [x] All generated AWS resources (themes, datasets, analyses) must have a common tag (`ManagedBy: quicksight-gen`) so they can be found. Additional tags can be specified via `extra_tags` in config.yaml. The common tag is always applied on top of any other tags.

	- [x] Published dashboards. Each analysis (financial and reconciliation) also produces a published Dashboard resource. Dashboards enable ad-hoc filtering, CSV export, and expanded sheet controls. The dashboard is accessible to the configured `principal_arn`.

	- [x] Visual layout sizing. KPI visuals use compact grid sizing (half-width, 6 rows) so they don't dominate the page. Charts get moderate height (12 rows), detail tables get the most space (18 rows, full-width).

	- [x] Descriptive axis labels. All bar chart and pie chart axes display human-readable labels (e.g. "Merchant", "Sales Amount ($)", "Match Status") instead of raw column names like `transaction_id (Count)` or `external_system`.
