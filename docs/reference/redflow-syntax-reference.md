redflow Syntax Reference
This page is the language reference for redflow scripts. It covers script structure, variables, actions, control flow, and data extraction.

For an overview of how to record assets and generate redflows, see Agents.

1. Script Anatomy
Every redflow script is composed of three logical blocks executed in order: the Target Definition, the Execution Logic, and the Variable Definitions.

URL "https://target-application.com/path"  <-- 1. Target Definition

# Main execution block
STEPS                                      <-- 2. Execution Logic
    - ACTION ...
    - IF ...

$variable_name = "value"                   <-- 3. Variable Definitions

1.1 Comments
Scripts support documentation using the hash (#) symbol. Any text following # on the same line is treated as a comment and ignored by the interpreter.

# This is a comment

2. The Variable System
Variables are the primary method of data injection. They are defined at the bottom of the script and referenced using the $ prefix.

2.1 Naming Convention
All variables must use snake_case.

Status	Example
Correct	$user_email, $role_name
Incorrect	$UserEmail, $roleName
2.2 Variable Types
Standard Input — Required data points.

$variable = "value"

List Input — A collection of values for iteration.

$variable = ["Value1", "Value2"]

Optional Input — Data that may not be present in every execution run. Suffix with ? and initialize as EMPTY.

$variable? = EMPTY

3. Action Reference
All actions require an INTENT string describing the purpose.

3.1 CLICK
Performs a standard mouse click on a UI element.

CLICK ON "Element Description" INTENT "Description"

3.2 FILL
Inputs text into a form field. Does not trigger submission.

FILL $variable INTO "Element Description" INTENT "Description containing $variable"

3.3 SELECT
Chooses an option from a dropdown.

SELECT $variable FROM "Element Description" INTENT "Description containing $variable"

warning
Strict validation: The text on the actual browser element must match the $variable value exactly.

3.4 FILL_AND_ENTER
Inputs text and explicitly triggers an ENTER key press. Use when FILL is insufficient.

FILL_AND_ENTER $variable INTO "Element Description" INTENT "Description containing $variable"

3.5 HOVER
Moves the mouse cursor over an element (e.g., to reveal tooltips or menus).

HOVER ON "Element Description" INTENT "Description"

4. Control Flow (Logic)
Logic is handled via IF blocks and FOR_EACH loops. Scope is determined by indentation.

4.1 Value Comparison
Checks if a variable matches a specific string literal.

IF $variable EQUALS "Target String"
IF $variable == "Target String"

EQUALS and == are functionally identical.

4.2 Negative Value Comparison
Checks if a variable does NOT match a specific string literal.

IF $variable NOT_EQUALS "Target String"
IF $variable != "Target String"

NOT_EQUALS and != are functionally identical.

4.3 Existence & Emptiness Checks
Use EXISTS for scalar (single-value) variables, and EMPTY / NOT_EMPTY for list variables.

EXISTS — checks whether an optional scalar variable has been populated (is not EMPTY). Use it only with single-value variables.

IF $variable EXISTS

NOT_EMPTY / EMPTY — check whether a list variable has any items. A list counts as EMPTY when it is absent (EMPTY / null) or contains no elements. These are the right way to guard a FOR_EACH over an optional list.

IF $roles NOT_EMPTY
    - FOR_EACH $role IN $roles
        - CLICK ON "$role option" INTENT "Select the role $role"

IF $roles EMPTY
    - CLICK ON "Skip button" INTENT "Skip role assignment"

EXISTS on a list is always true — a present list "exists" even when it is empty — so the editor blocks EXISTS on list variables. Use NOT_EMPTY / EMPTY for lists instead.

4.4 Conditional Branching
Executes if the preceding IF condition was false.

ELSE

4.5 Iteration
Loops through a list of values provided in a list variable.

FOR_EACH $item IN $list_variable

4.6 Runtime AI Conditions
IF/ELSE and FOR_EACH are static — they are resolved from variable values before the script runs. redflow also provides three runtime control-flow keywords that are evaluated by AI against the live page while the script executes. Each takes a natural-language condition (in double quotes) describing a visible page state — not a variable comparison.

Keyword	Behaviour	Body
WHEN	Branch once: run the body if the condition is true (optional ELSE for false).	Required
UNTIL	Loop the body while the condition is true (capped, with a wait between checks).	Required
WAIT_UNTIL	Pause and poll until the condition becomes true, then proceed. Takes no action.	None
The condition is re-evaluated against the page on every execution (it is never cached), so these keywords are the right tool for UI that varies run-to-run: optional popups, asynchronous loads, and states that take time to settle. $variables may be used inside the condition, and these keywords are valid anywhere STEPS are — including extraction pre-steps and per-item detail navigation (see Section 7).

4.6.1 WHEN
Looks at the live page and runs the indented body only if the described state is present. Use it for steps that should happen conditionally based on what is actually on screen (a popup that may or may not appear, a state that differs per user).

- WHEN "a cookie consent banner is visible"
    - CLICK ON "Accept all button" INTENT "Dismiss the cookie banner"

An optional ELSE block runs when the condition is false. (WHEN supports ELSE but not ELIF.)

- WHEN "the user $email already appears in the results"
    - CLICK ON "the row for $email" INTENT "Open the existing user $email"
- ELSE
    - CLICK ON "Invite user button" INTENT "Invite a new user"

WHEN must have at least one nested step.

4.6.2 UNTIL
Repeats the indented body while the condition remains true, re-checking the page after each pass and waiting between iterations. The loop exits as soon as the condition becomes false, or after a fixed maximum number of iterations. Use it for refresh / retry / poll-and-act patterns.

- UNTIL "the Refresh icon is still visible in the export row"
    - CLICK ON "Refresh icon" INTENT "Refresh the export status"

In the example above the agent keeps clicking Refresh as long as the refresh icon is present (the job is still processing) and proceeds once it disappears (the export is ready). UNTIL must have a body — the action(s) to repeat.

4.6.3 WAIT_UNTIL
Pauses execution and polls the page until the described state appears, then continues to the next step. Unlike UNTIL, it performs no action and has no body — it is a pure wait barrier for asynchronous loads or background jobs.

- CLICK ON "Generate report button" INTENT "Start the report"
- WAIT_UNTIL "the report status shows Completed"
- CLICK ON "Download button" INTENT "Download the finished report"

The presence of a body is the visual signal: an indented body means a WHEN/UNTIL; no body means a WAIT_UNTIL. If the awaited state never appears within the polling window, the agent proceeds best-effort (any genuinely-blocked next step then surfaces the failure).

5. System Constraints
To ensure successful compilation and execution, the following rules must be followed:

Indentation: All nested steps (inside IF, ELSE, FOR_EACH, WHEN, or UNTIL) must be indented by exactly 4 spaces.
Block bodies: WHEN and UNTIL must have at least one nested (indented) step. WAIT_UNTIL is a single line and must not have a nested body.
Runtime conditions: WHEN, UNTIL, and WAIT_UNTIL take a non-empty, double-quoted condition describing a visible page state — not a variable comparison or an INTENT.
Intent Binding: If a variable is used in an action statement, that specific variable must be referenced within the INTENT string.
# Invalid
FILL_AND_ENTER $name ... INTENT "Find the user"

# Valid
FILL_AND_ENTER $name ... INTENT "Find the user $name"

6. Real-World Examples
The following examples demonstrate standard administrative Joiner, Mover, and Leaver (JML) operations.

6.1 Example A: Joiner (New User Provisioning)
Scenario: Creating a new account in Salesforce and assigning a license.

URL "https://acme-corp.lightning.force.com/lightning/setup/ManageUsers/home"

STEPS
    # Start the creation flow
    - CLICK ON "New User Button" INTENT "Start the user creation process"
    - FILL $first_name INTO "First Name Input" INTENT "Enter the user's $first_name"
    - FILL $last_name INTO "Last Name Input" INTENT "Enter the user's $last_name"
    - FILL $user_email INTO "Email Input" INTENT "Set the primary email to $user_email"

    # Conditional logic based on department
    - IF $department EQUALS "Sales"
        - SELECT $role FROM "Role Dropdown" INTENT "Assign the Sales $role to the user"
        - CLICK ON "Salesforce License Checkbox" INTENT "Assign standard license"
    - ELSE
        - CLICK ON "Standard Platform License Checkbox" INTENT "Assign platform license"

    - CLICK ON "Save Button" INTENT "Save the new user record"

$first_name = "Alice"
$last_name = "Smith"
$user_email = "alice.smith@acme.com"
$department = "Sales"
$role = "Regional Sales Manager"

6.2 Example B: Mover (Role Transition)
Scenario: Updating a user's permissions when they move departments.

URL "https://app.hubspot.com/settings/users"

STEPS
    - FILL_AND_ENTER $user_email INTO "User Search Bar" INTENT "Find the user by $user_email"
    - HOVER ON "User Row" INTENT "Reveal the edit options"
    - CLICK ON "Edit Permissions" INTENT "Open permissions for editing"

    # Check if a new role is provided
    - IF $new_role EXISTS
        - CLICK ON "Role Dropdown" INTENT "Open the role selector"
        - SELECT $new_role FROM "Role List" INTENT "Change the user's role to $new_role"

    - IF $is_manager EQUALS "True"
        - CLICK ON "Team Management Toggle" INTENT "Enable management access because $is_manager is True"

    - CLICK ON "Save Preferences" INTENT "Confirm the changes"

$user_email = "bob.jones@acme.com"
$new_role = "Marketing Director"
$is_manager = "True"

6.3 Example C: Leaver (Deactivation & Transfer)
Scenario: Deactivating a user and optionally transferring their data to a manager.

URL "https://admin.google.com/ac/users"

STEPS
    - FILL_AND_ENTER $leaver_email INTO "Top Search Bar" INTENT "Locate the account for $leaver_email"
    - CLICK ON "User Profile Row" INTENT "Open the user profile"
    - CLICK ON "Security Settings" INTENT "Access security options"
    - CLICK ON "Suspend User" INTENT "Suspend the account"

    # Transfer data if a recipient is defined
    - IF $transfer_data_to EXISTS
        - CLICK ON "Transfer Data Checkbox" INTENT "Initiate data transfer"
        - FILL_AND_ENTER $transfer_data_to INTO "Recipient Input" INTENT "Transfer Drive files to $transfer_data_to"
        - CLICK ON "Transfer Button" INTENT "Confirm transfer to $transfer_data_to"
    - ELSE
        - CLICK ON "Delete Data Button" INTENT "Delete data as no recipient was provided"

    - CLICK ON "Confirm Suspension" INTENT "Finalize suspension"

$leaver_email = "charlie.doe@acme.com"
$transfer_data_to? = "manager.dave@acme.com"

6.4 Example D: Bulk Role Assignment (Iteration)
Scenario: Assigning multiple roles to a user via iteration.

URL "https://sap-cloud.app"

STEPS
    - CLICK ON "The ADMINISTRATION tab in top nav bar" INTENT "To navigate to the user management section"
    - CLICK ON "The $email in the user list" INTENT "To locate the user $email"

    # Loop through each role in the list
    - FOR_EACH $role IN $roles
        - CLICK ON "The $role checkbox in the Roles section of the User Profile" INTENT "To assign the $role to the user $email"

    - CLICK ON "The Save button at the bottom of the User Profile" INTENT "To save the updated user details with the assigned roles"
    - CLICK ON "OK button in the confirmation dialog" INTENT "To confirm and finalize the role assignment for the user"

$email = "test@company.com"
$roles = ["Production Operator", "Developer"]

6.5 Example E: Asynchronous Export (Runtime Conditions)
Scenario: Exporting users from an admin console where the export runs as a background job: a confirmation dialog may appear for large exports, the row shows a refresh control while processing, and the file must be polled until it is ready to download.

URL "https://admin.example.com/users/export"

STEPS
    - CLICK ON "Export Users button" INTENT "Start the export job"

    # A confirmation dialog appears only for large exports
    - WHEN "a dialog asking to confirm the export is shown"
        - CLICK ON "Confirm export button" INTENT "Confirm the large export"

    # The latest row shows a Refresh control while the job is still processing
    - UNTIL "the Refresh icon is still visible in the latest export row"
        - CLICK ON "Refresh icon in the latest export row" INTENT "Refresh the export status"

    # Make sure the file is actually marked ready before downloading
    - WAIT_UNTIL "the latest export row shows a Download link"

    - CLICK ON "Download link in the latest export row" INTENT "Download the exported file"

7. Data Extraction Scripts
In addition to action-based scripts (Joiner, Mover, Leaver), redflow supports a dedicated script type for extracting structured data from web applications. These scripts define what data to collect from list views, detail pages, and nested tables, and output the results as structured JSON.

7.1 Script Structure
A data extraction script has four main components executed in order:

URL — The target page to extract data from.
STEPS (optional) — Pre-extraction actions such as clicking filters or search buttons.
RESOURCE — Declares the resource being extracted and its unique identifier.
EXTRACT — Defines which fields to collect and from where (list or detail views).
7.2 RESOURCE Declaration
Every extraction script must declare a top-level RESOURCE with an IDENTIFIED_BY clause to prevent duplicate records.

RESOURCE: "ResourceName" IDENTIFIED_BY "unique_field"

Example:

RESOURCE: "Users" IDENTIFIED_BY "email"

7.3 EXTRACT Block
The EXTRACT block defines the data to collect. It supports two extraction modes:

FROM LIST — Extracts data from a table or repeating rows (multiple items, same structure).
FROM DETAILS — Extracts standalone labeled attributes from a detail page (single values, toggles, dropdowns).
If a detail page has both a table and standalone fields, use both at the same indentation level. If a detail page has only a table and no new standalone fields, do not include FROM DETAILS.

7.4 Field Syntax
Every field requires a name and an INSTRUCT clause describing where to find it on the page.

- "field_name" INSTRUCT "description of location"

POSSIBLE_VALUES — For fields with a universal, fixed set of options (dropdowns, badges, status indicators).

- "status" INSTRUCT "in Status column" POSSIBLE_VALUES ["Active", "Inactive", "Pending"]

Array Fields — Append [] to field names that collect multiple non-tabular values as an array.

- "tags"[] INSTRUCT "in Tags column"

Field names must use snake_case.

7.5 Top-Level STEPS
If any actions must be performed before extraction begins (e.g., clicking a search button, applying filters, or navigating menus), capture them as top-level STEPS before the RESOURCE declaration.

STEPS
    - CLICK ON "Search button in top right corner" INTENT "Load all groups into the table"

7.6 Detail Page Navigation
To extract data from an item's detail page, add per-item STEPS indented inside the FROM LIST block. These STEPS run for every row in the list.

EXTRACT
    FROM LIST
        - "name" INSTRUCT "in Name column"
        STEPS
            - CLICK ON "name" INTENT "Open detail page"
        EXTRACT
            FROM DETAILS
                - "role" INSTRUCT "labeled Role"

Rules:

Per-item STEPS must be indented inside FROM LIST, not at the top level.
FROM DETAILS should only contain fields that are NOT already captured in FROM LIST.
If all detail page fields are duplicates of FROM LIST fields, omit FROM DETAILS entirely.
7.7 Nested Resources
When a detail page contains a sub-table, declare a nested RESOURCE directly above its FROM LIST block. The nested RESOURCE uses the short form without IDENTIFIED_BY.

        STEPS
            - CLICK ON "Group_name" INTENT "Open group"
        RESOURCE "group_members"
        EXTRACT
            FROM LIST
                - "email" INSTRUCT "email column"
                - "status" INSTRUCT "status column"

Every nested FROM LIST must have a RESOURCE declaration directly above it. This applies at every nesting depth.

7.8 Multi-Tab Detail Pages
When a detail page has multiple tabs, all tab-related blocks (STEPS for switching, RESOURCE declarations, EXTRACT blocks) must be siblings at the same indentation level. Never nest a second tab's blocks inside the first tab's EXTRACT.

        STEPS
            - CLICK ON "item" INTENT "Open detail page"
        EXTRACT
            FROM DETAILS
                - "field_a" INSTRUCT "labeled Field A"
        STEPS
            - CLICK ON "Tab 2" INTENT "Switch to Tab 2"
        RESOURCE "tab2_items"
        EXTRACT
            FROM LIST
                - "field_b" INSTRUCT "in Field B column"
        STEPS
            - CLICK ON "Tab 3" INTENT "Switch to Tab 3"
        RESOURCE "tab3_items"
        EXTRACT
            FROM LIST
                - "field_c" INSTRUCT "in Field C column"

note
If the detail page lands directly on a specific tab (e.g., the URL ends in #/skills or the tab is already active on load), do NOT generate a STEPS block to click that tab.

7.9 Cross-URL JOIN
To merge data from a second URL into existing records, use GOTO inside a STEPS block followed by a RESOURCE with JOIN ON. The JOIN ON key must match a field already extracted from the first resource.

URL "https://payroll.internal.com/employees"
RESOURCE: "Staff" IDENTIFIED_BY "employee_id"
EXTRACT
    FROM LIST
        - "name" INSTRUCT "Name in the first column"
        STEPS
            - CLICK ON "name" INTENT "Open employee profile"
        EXTRACT
            FROM DETAILS
                - "employee_id" INSTRUCT "Labeled ID in the summary header"

STEPS
    - GOTO "https://it-assets.internal.com/devices"
RESOURCE: "Assets" JOIN ON "employee_id"
EXTRACT
    FROM LIST
        - "serial_number" INSTRUCT "Serial in the first column"
        - "employee_id" INSTRUCT "Employee id in column with header Employee ID"

7.10 Key Rules
Every top-level RESOURCE must have IDENTIFIED_BY.
Per-item detail clicks go inside FROM LIST as indented STEPS, not at the top level.
Nested FROM LIST inside a detail page requires a RESOURCE declaration directly above it.
All tab-related blocks must be siblings at the same indentation level.
GOTO must always be inside a STEPS block.
Every field needs an INSTRUCT clause.
Use POSSIBLE_VALUES only for fields with a universal, fixed set of options.
Append [] to field names that collect multiple non-tabular values.
FROM DETAILS should only contain fields not already extracted in FROM LIST.
7.11 Examples
7.11.1 Example A: Flat List Extraction (No Detail Navigation)
Scenario: Extracting a user list from an admin console without clicking into any detail pages.

URL "https://admin.example.com/users"
RESOURCE: "Users" IDENTIFIED_BY "email"
EXTRACT
    FROM LIST
        - "email" INSTRUCT "in Email column"
        - "first_name" INSTRUCT "in First Name column"
        - "last_name" INSTRUCT "in Last Name column"
        - "role" INSTRUCT "in Role column" POSSIBLE_VALUES ["Admin", "Editor", "Viewer"]
        - "account_status" INSTRUCT "status badge in Status column" POSSIBLE_VALUES ["Active", "Inactive", "Pending"]

7.11.2 Example B: List with Pre-Extraction Steps
Scenario: Loading groups by clicking a search button before extracting the list.

URL "http://synqa.rjf.com:8888/syn/#simpleBrowser/type=SynGroup/seq=2097258837-3"
STEPS
    - CLICK ON "Search button in top right corner" INTENT "Load all groups into the table"
RESOURCE: "Groups" IDENTIFIED_BY "unique_id"
EXTRACT
    FROM LIST
        - "unique_id" INSTRUCT "in Unique ID column"
        - "description" INSTRUCT "in Description column"

7.11.3 Example C: Detail Page with Nested List
Scenario: Extracting groups and drilling into each to capture group members.

URL "https://admin.atlassian.com/groups"
RESOURCE: "Groups" IDENTIFIED_BY "Group_name"
EXTRACT
    FROM LIST
        - "Group_name" INSTRUCT "Column 1"
        - "Members" INSTRUCT "Column 2"
        STEPS
            - CLICK ON "Group_name" INTENT "Drill down into this specific group"
        RESOURCE "group_users"
        EXTRACT
            FROM LIST
                - "user_email" INSTRUCT "Found in the email column"
                - "user_status" INSTRUCT "Found in status column"

7.11.4 Example D: Multi-Tab Detail Page (FROM DETAILS + Nested Lists)
Scenario: Extracting users with detail fields, then navigating Destinations and Connections tabs.

# Double check the URL
URL "https://fivetran.com/dashboard/account/users-permissions/users"
STEPS
    - CLICK ON "Filter by role dropdown" INTENT "Open the role filter dropdown"
    - CLICK ON "Account Administrator" INTENT "Filter users to show only Account Administrators"
RESOURCE: "Users" IDENTIFIED_BY "email"
EXTRACT
    FROM LIST
        - "name" INSTRUCT "Name in the Name column"
        - "email" INSTRUCT "Email in the Email column"
        - "assigned_account_role" INSTRUCT "Role in the Assigned account role column" POSSIBLE_VALUES ["Account Administrator", "Account Analyst", "Account Billing", "Account Reviewer", "Destination Creator", "No Account Role"]
        - "team" INSTRUCT "Team in the Team column"
        STEPS
            - CLICK ON "name" INTENT "Open user detail page"
        EXTRACT
            FROM DETAILS
                - "account_role" INSTRUCT "Account role under ACCOUNT ROLE section"
                - "team_memberships"[] INSTRUCT "Team name under TEAM MEMBERSHIPS section"
        STEPS
            - CLICK ON "Destinations tab" INTENT "Switch to Destinations tab"
        RESOURCE "destinations"
        EXTRACT
            FROM LIST
                - "destination_name" INSTRUCT "Name in the Name column"
                - "destination_type" INSTRUCT "Type in the Type column"
                - "destination_permission" INSTRUCT "Permission in the Destination permission column"
                - "permission_source" INSTRUCT "Source in the Permission source column"
        STEPS
            - CLICK ON "Connections tab" INTENT "Switch to Connections tab"
        RESOURCE "connections"
        EXTRACT
            FROM LIST
                - "connection_name" INSTRUCT "Name in the Connection name column"
                - "source_type" INSTRUCT "Type in the Source type column"
                - "destination" INSTRUCT "Destination in the Destination column"
                - "connection_permission" INSTRUCT "Permission in the Connection permission column"
                - "permission_source" INSTRUCT "Source in the Permission source column"

7.11.5 Example E: Cross-URL JOIN
Scenario: Extracting employee data from payroll and joining device assignments from a second URL.

# Double check the URL
URL "https://payroll.internal.com/employees"
RESOURCE: "Staff" IDENTIFIED_BY "employee_id"
EXTRACT
    FROM LIST
        - "name" INSTRUCT "Name in the first column"
        STEPS
            - CLICK ON "name" INTENT "Open employee profile"
        EXTRACT
            FROM DETAILS
                - "employee_id" INSTRUCT "Labeled ID in the summary header"

STEPS
    - GOTO "https://it-assets.internal.com/devices"
RESOURCE: "Assets" JOIN ON "employee_id"
EXTRACT
    FROM LIST
        - "serial_number" INSTRUCT "Serial in the first column"
        - "employee_id" INSTRUCT "Employee id in column with header Employee ID"

Previous
VWO
