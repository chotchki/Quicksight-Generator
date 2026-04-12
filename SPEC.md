Goal: 
	- To create one or more AWS Quicksight dashboards with a series of tabs to help understand financial applications.

Users:
 - There are two users of this code base:
  - Developers/Product Owners seeking to customize these financial applications to work with their own existing backends
    - It is important for them to be able to customize the sql queries that feed the data sets and the columns being reported in the final views
    - It is expected they have the skills to change code but they will want to be able to edit this code in a single location for a change (meaning adhere to DRY principles)
    - These users also want to know that they didn't break anything, so a comprehensive test suite is important
    - These users want to be able to iterate quickly on changes with the non technical customers, so an ability to regenerate and redeploy is important
    - This application will need to apply themes to so it can be incorporated into the real systems. Demos should be themed differently.
  - Non technical customers of the dashboards who are expected to use these applications to accomplish their jobs
    - Their job is to find problems using these applications and then work with other teams to fix them so the reports here are clean.
    - To them these applications will be completely foreign to what they've dealt with previously
    - Plain English labels, hint test and even additional text blocks on the screens will be critical for them to adapt to the application
    - These people underderstand accounting VERY well but they are not programmers, they need to know when errors result in things they need to investigate

Background:
  - There are now two different financial reporting applications:
    - The first one is what has already been built "Payment Recon": a series of steps revolving around merchants taking in sales, this application bundles those sales to settle them and then pays those merchants at the end
    - The second one is about a financial application "Account Recon": that is focused on bank accounts and transfers. It uses double entry accounting for all transactions and needs to maintain an accurate balance and be eventually consistent.
  
    - Both applications use the same SQL datasource. For production use, a pre-existing datasource ARN is provided. For demo mode, the project creates a single QuickSight data source definition from the demo database connection URL.

	- This SQL datasource will be accessed using quicksight custom sql data sets that this project will need to create against the data source. 
    - It will be expected that this project creates example tables, data, queries against the data.
    - The queries used in the datasets are expected to be replaced by the end user of these applications since they will already have their own financial systems.

  - The focus of the two applications is different:
    - The first application "Payment Recon" continues to 
      - make queries to support reporting on each of the steps: sales -> settlement -> payment -> matching to external systems.
      - provide controls to filter and easy ways to check if a settlement didn’t happen or payments were returned.
      - ensure the payments match to other external systems since only payments would leave the system. 
      - There will be successful matches, not yet matched and late matching which will be exceptions. (Consolidated into a single analysis as the Payment Reconciliation tab rather than a separate analysis.)
    - The second application "Account Recon" is focused on consistency and tracibility:
        - do the balances match transactions?
          - if not what does not match?
        - do the the transfers end up consistent?
          - meaning the final effect of the transfer should be zero
          - if not what is out of sync?

Key Domain Models to Understand:
  - The domain models are not necessarily separate, however their focus is very different. It recommended at the moment to keep them distinct to manage the overall complexity.
  - The first application "Payment Recon": (What follows I believe is true in the existing implementation unless I note differently)
    - Locations
      - Have merchants that are tied to a location
      - Care only about merchants at their location but other people care about all the locations
    - Merchants
      - Make sales at a location, they do have a name (this was not called out explicitly in the earlier spec)
      - Have different types that determines settlement type
      - Have different configured payment methods
    - Sales 
      - Has mandatory metadata
        - Merchant
        - Amount
        - Timestamp
      - Optional metadata examples (This application could expose them on the sales tab/let them be filtered on but otherwise doesn't care)
        - Taxes
        - Tips
        - Discount Percentage
        - Cashier
      - Sales are settled to the merchant, the settlement type depends on the merchant type
      - sales could be refunded and should be netted out of a settlement
      - a refund should be treat like a sale type with a negative amount
      - sales/refunds know what settlement they belong to if its there, it could be null
    - Settlements
      - bundle sales
      - are credited to a merchant
      - settlements know what payment they belong to if its there, it could be null
    - Payments
      - the only transactions that leave the system
      - consist of usually a single settlement but could be multiple settlements from different merchants
      - a given payment only will land in a single external system
      - payments ARE NOT instantaneous
      - payments can fail and could be returned
      - payments will know what external system transaction they belong to if its there, it could be null
    - External System Transactions
      - represent one or more payments
      - external system transactions NOT tied to a payment are a problem
      - external system transactions are also availible through the single datasource above

	  - There are unique identifiers for locations, merchants, sales, settlements, payments and external system identifiers
		- At each step, a valid match from one to the other is only valid if the net effect is equal.
  		- This means the totals on each side of the step should equal out accounting for refunds/returns.
      - this is NOT subject to time delay, if a step is linked to the next step, the amount MUST match or its a problem to be highlighted
    - There is an underlying theme that each of these steps happen over time
      - Being late has a different definition depending on the step and even on the mentioned types above
      - Deing able to easily tell late vs didn't happen should be easily configurable
    
  - The second application "Account Recon":
    - Money
      - Decimal Amount
      - Should not be created or destroyed (This application does not handle fractional reserves)
      - Assume single currency denominated to 2 decimal places (This application does not handle fractional currency, or currency conversions)
    - Accounts
      - May be internal or external
        - External accounts its not this application's job to track their balance (That's for regulators)
        - Internal accounts have a daily final balance
          - This amount should match net amount of transactions done in a day
      - Will be linked to a parent account
      - Will have a name
    - Parent accounts
      - May be internal or external 
        - External parent accounts are not the focus of this application (That's for regulators)
      - Have a daily final balance
        - This is a saved amount and intended to be an aggregation of the children's balances
      - Will have a name
    - Transfers
      - Are the movement of money between accounts
      - Are done via double entry accounting transactions, meaning debits and credits
      - Cannot fail in aggregate, you cannot destroy money
      - Some transfers will be done externally and some are internal
      - More than two transactions may make up a transfer (for example if something fails)
      - Have a memo line to describe the why
    - Transactions
      - Have an amount in money
      - Have a timestamp when posted
      - Could fail individually
      - If it affects an internal account the daily balance MUST be updated in lockstep
        
Demo Scenarios:
  - These reporting applications can be hard to understand on their own due to the abstract nature of financial work, this section sets out a narrative to help generate example data and scenarios so that someone wanting to evaluate these applications can understand a logical theme.
  - In general chose names of things to fit the theme in a humerous / inoffensive way. 
    - Puns are highly encourgaged whenever possible with the hope being if someone looks carefully at the applications' demo output, which could be rather dry and boring brightens their day.
  - Demo scenarios needs a good mix of success and failure cases. An 80% success / 20% failure should illustrate the value of these tools to find problems. 
  - These scenarios need to happen over time but don't need huge volumes of data

  - The first application "Payment Recon"'s scenario is thus:
    - It is a tool for Sasqutch Bank who is a merchant bank in the pacific northwest to process sales from merchant customers. 
    - Its customers are primarily a series of coffee shops, their sales should reflect typical morning focused sales
    - The optional metadata on sales and/or merchant names are good place for variety
      
  - The second application "Account Recon"'s scenario is thus:
    - It is a tool for Farmers Exchange Bank which is a bank located in Stardew Valley
    - Its customer are local farmers, suppliers, and buyers for the farmer's goods
    - The memo line on transfers plus the date of the transactions should tell a story

Code Base Guideance:
  - The exisiting code base has significant value, its not recommended to change the technology selection.
    - aka mainly python that outputs the quicksight json with the shell deploy script
    - the demo datasource is an aws aurora postgresql instance
  - The final output should be two quicksight databoards using the exisiting config process
  - The code may need to be restructured to allow for code sharing especially of interating between the quicksight api
  - A layered testing approach is still critical, the existing test scripts should be reused wherever possible
  - Theming support is still wanted
    
Output:
  - The final output should still be quicksight json and be repeated deployable using the deploy script.

  - If the demo deployment is done, an additional sheet at the front of the dashboard should be added explaining the scenario and what the other sheets are for.
	
	- All generated AWS resources (themes, datasets, analyses) must have a common tag (`ManagedBy: quicksight-gen`) so they can be found. Additional tags can be specified via `extra_tags` in config.yaml. The common tag is always applied on top of any other tags.

	- Published dashboards. Each analysis (financial and reconciliation) also produces a published Dashboard resource. Dashboards enable ad-hoc filtering, CSV export, and expanded sheet controls. The dashboard is accessible to the configured `principal_arn`.

	- Visual layout sizing. KPI visuals use compact grid sizing (half-width, 6 rows) so they don't dominate the page. Charts get moderate height (12 rows), detail tables get the most space (18 rows, full-width). Try to minimize excessive white space.

	- Descriptive axis labels. All bar chart and pie chart axes display human-readable labels (e.g. "Merchant", "Sales Amount ($)", "Match Status") instead of raw column names like `transaction_id (Count)` or `external_system`.

	- End-to-end test harness. Two-layer validation against a deployed dashboard: API tests (boto3) verify resource health, dashboard structure, and dataset import status; browser tests (Playwright WebKit, headless) load the dashboard via a pre-authenticated embed URL and verify sheet tabs render, per-sheet visual counts, drill-down navigation (Settlements→Sales, Payments→Settlements), Payment Reconciliation mutual table filtering, and date-range filter behavior. Single-command runner (`./run_e2e.sh`) regenerates JSON, redeploys, and runs the tests so iteration is hands-off.
