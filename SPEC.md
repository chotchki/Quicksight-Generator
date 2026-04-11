Goal: 
	- [  ] To create one or more AWS Quicksight analyses with a series of tabs to help understand a financial application.

Background:
	- [  ] This financial application uses a SQL datasource that will be already provided to this project.

	- [  ] This SQL datasource will be accessed using quicksight custom sql data sets that this project will need to create against the data source. Dummy SQL queries are fine for the moment.

	- [  ] The financial application cares about a series of steps revolving around merchants taking in sales, this application bundles those sales to settle them and then pays those merchants at the end. 

	- [  ] This analysis will want to make queries to support each of those steps, provide controls to filter and easy ways to check if a settlement didn’t happen or payments were returned.

Key Domain Models to Understand:
	- Merchants make sales at a location

	- Sales may have additional metadata that may or may not be populated, merchant, amount, timestamp will be populated

        - Locations care only about merchants at their location but other people care about all the locations

        - Merchants sales are settled to them, the settlement type depends on the merchant type

        - Settlements are paid based on the merchant

	- There are unique identifiers for locations, merchants, sales,


Output:
	- [  ] Create something that creates the json that could be imported using the AWS cli to create the described analysis. The thing could be python, terraform, some combination of it.

	- [  ] The customer of these aws quicksight reports doesn’t know what they want so an ability to mutate this project either via you (Claude) OR some level of structured code that generates the quick sight reports will be VERY helpful.

	- [  ] Build a consistent theme that looks nice, color theme blues and greys but must be easily read. Apply the theme and reasonable styling to everything produced.

	- [x] All generated AWS resources (themes, datasets, analyses) must have a common tag (`ManagedBy: quicksight-gen`) so they can be found. Additional tags can be specified via `extra_tags` in config.yaml. The common tag is always applied on top of any other tags.
