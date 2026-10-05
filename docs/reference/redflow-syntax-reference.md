redflow Syntax Reference
The language reference for redflow scripts: script structure, variables, actions, control flow, advanced controls, and data extraction. For how to record assets and generate redflows, see the Agents guide.

What's new in this version
FOR_EACH … EXECUTE_PARALLEL: run every iteration of a same-page loop as one batch. This is the only way to use EXECUTE_PARALLEL (§6.1).
GRAB / GRAB ALL: read a value, or a list of values, off the live page into a variable (§6.2).
BROWSER_FIND $variable: find known text on the page like Ctrl+F and scroll it into view. It takes no INTENT (§6.3).
Comparisons: use EQUALS and NOT_EQUALS. The == and != forms are not supported (§4.1, §4.2).
New sections are marked New. Everything else is unchanged.

1. Script Anatomy
Every redflow script is made of three blocks, in this order: the Target Definition, the Execution Logic, and the Variable Definitions.

URL "https://target-application.com/path"

# Main execution block
STEPS
    - CLICK ON "..." INTENT "..."
    - IF ...

$variable_name = "value"

The target can also be CONTINUE_FROM_LOGIN instead of a quoted URL. See 6.6 CONTINUE_FROM_LOGIN.

1.1 Comments
Any text after # on a line is a comment and is ignored.

# This is a comment

2. The Variable System
Variables are how data gets into a script. Define them at the bottom of the script and reference them with the $ prefix.

2.1 Naming Convention
All variables use snake_case.

Status	Example
Correct	$user_email, $role_name
Incorrect	$UserEmail, $roleName

2.2 Variable Types
Standard Input: a required value.

$variable = "value"

List Input: a collection of values to loop over.

$variable = ["Value1", "Value2"]

Optional Input: a value that may be missing on some runs. Add ? to the name and initialize it as EMPTY.

$variable? = EMPTY

Map Input: a set of keys, each with its own value, declared one entry per line. A value is a string or a list of strings. Use a map when each item has its own settings, for example the permissions to grant on each account. Loop over it with FOR_EACH $key, $value IN $map (see 6.4).

$access["Reserve"] = ["Request payments", "Send money"]
$access[Operating] = ["Send money"]
$access["Petty cash"] = "View bank accounts"

- Quotes around a key are optional unless the key has spaces: write ["Petty cash"], not [Petty cash].
- Maps are one level deep. $access["a"]["b"] and an entry that is itself a map are not allowed.
- Each entry is a string or a list of strings. Use [] for a key with no values; EMPTY is not allowed as an entry.
- Declare each entry on its own line. Don't write the whole map as one object ($access = {"Reserve": [...]}).
- Keys and values are plain text, so variables are not substituted in them. $access[$role] = [...] is an error.
- A key can't be repeated, and a name can't be both a map and a single value.
- To make a map optional, mark every entry with ? ($access?["Reserve"] = [...]) or mark none.

3. Action Reference
Every action needs an INTENT string that describes its purpose. The exceptions are GOTO, WAIT and BROWSER_FIND, which take no INTENT.

3.1 CLICK
Clicks a UI element.

CLICK ON "Element Description" INTENT "Description"

3.2 FILL
Types text into a form field. Does not submit.

FILL $variable INTO "Element Description" INTENT "Description containing $variable"

3.3 SELECT
Chooses an option from a dropdown. The value is always a $variable, written without quotes.

SELECT $variable FROM "Element Description" INTENT "Description containing $variable"

# Invalid
- SELECT "Sales Rep" FROM "Role dropdown" INTENT "Assign the role"
- SELECT "$role" FROM "Role dropdown" INTENT "Assign the role $role"

# Valid
- SELECT $role FROM "Role dropdown" INTENT "Assign the role $role"

Strict validation: the text on the actual browser element must match the $variable value exactly.

3.4 FILL_AND_ENTER
Types text and then presses ENTER. Use it when FILL alone isn't enough.

FILL_AND_ENTER $variable INTO "Element Description" INTENT "Description containing $variable"

3.5 HOVER
Moves the mouse over an element, for example to reveal a tooltip or menu.

HOVER ON "Element Description" INTENT "Description"

3.6 DOUBLE_CLICK
Double-clicks an element, for example to open a row or select a word in a text box.

DOUBLE_CLICK ON "Element Description" INTENT "Description"

3.7 RIGHT_CLICK
Right-clicks an element to open its context menu.

RIGHT_CLICK ON "Element Description" INTENT "Description"

3.8 UPLOAD
Uploads a file into a file input or upload area. The value is the file reference stored in the vault, not a local file path.

UPLOAD $file INTO "Element Description" INTENT "Description containing $file"

3.9 GOTO
Navigates to a new URL partway through a script. It takes the quoted URL and nothing else: no INTENT and no DESCRIPTION. Variables can be embedded in the URL.

GOTO "https://github.com/$org/$repo/settings"

GOTO cannot take CONTINUE_FROM_LOGIN, which only works on the URL line.

4. Control Flow (Logic)
Logic uses IF blocks and FOR_EACH loops. Indentation sets the scope.

4.1 Value Comparison
Checks whether a variable matches a string literal.

IF $variable EQUALS "Target String"

4.2 Negative Value Comparison
Checks whether a variable does not match a string literal.

IF $variable NOT_EQUALS "Target String"

Not supported: write comparisons with EQUALS and NOT_EQUALS only. Don't use ==, != or other symbol operators.

4.3 Existence & Emptiness Checks
Use EXISTS for single-value variables, and EMPTY / NOT_EMPTY for list variables.

EXISTS checks whether an optional single-value variable has been set (is not EMPTY).

IF $variable EXISTS

NOT_EMPTY / EMPTY check whether a list has any items. A list counts as EMPTY when it is absent or has no elements. Use them to guard a FOR_EACH over an optional list.

IF $roles NOT_EMPTY
    - FOR_EACH $role IN $roles
        - CLICK ON "$role option" INTENT "Select the role $role"

IF $roles EMPTY
    - CLICK ON "Skip button" INTENT "Skip role assignment"

Note: EXISTS on a list is always true, because a present list exists even when it's empty. The editor blocks EXISTS on lists.

4.4 List Membership (IN)
Checks whether a variable's value is one of the values in a list variable. The comparison is exact, like EQUALS. It works with IF and ELIF, and ELSE runs when the value is in none of them.

- IF $region IN $eu_regions
    - CLICK ON "GDPR consent checkbox" INTENT "Enable GDPR consent for $region"
- ELSE
    - CLICK ON "Standard terms checkbox" INTENT "Accept standard terms"

$region = "Germany"
$eu_regions = ["Germany", "France", "Spain"]

- The right-hand side must be a list variable. A literal list such as IF $x IN ["a", "b"] is rejected.
- An empty or missing list contains nothing, so the check is false and the ELIF / ELSE branch runs.
- The left-hand side can be an input variable, a FOR_EACH loop variable, or a GRAB value (see 6.2). Input variables are decided before the run starts, loop variables on each iteration, and GRAB values when the value is read.
- IN is checked once. The steps after the IF block run once, not once per list value.

4.5 Conditional Branching
ELIF adds another condition, checked only when the IF or ELIF before it was false. It takes the same conditions as IF. ELSE runs when every earlier condition was false.

- IF $department EQUALS "Sales"
    - SELECT $sales_role FROM "Role dropdown" INTENT "Assign the $sales_role role for $department"
- ELIF $department EQUALS "Support"
    - SELECT $support_role FROM "Role dropdown" INTENT "Assign the $support_role role for $department"
- ELSE
    - SELECT $default_role FROM "Role dropdown" INTENT "Assign the default role $default_role"

$department = "Support"
$sales_role = "Sales Rep"
$support_role = "Support Agent"
$default_role = "Standard User"

ELIF must directly follow an IF or another ELIF at the same indentation. ELSE must directly follow an IF, ELIF or WHEN, and takes no condition.

4.6 Iteration
FOR_EACH $item IN $list_variable loops over a list, running the body once per value with $item set to that value. To loop over a map, see 6.4 Map Loop.

FOR_EACH $item IN $list_variable

The variable after IN must be a list. Looping over a single value is an error, and looping over a map gives an error that points you to the map form.

4.7 Runtime AI Conditions
IF/ELSE and FOR_EACH are static: they are resolved from variable values before the script runs. Three runtime keywords are instead checked by AI against the live page while the script runs. Each takes a plain-language condition in double quotes describing something visible on the page, not a variable comparison.

Keyword	Behaviour	Body
WHEN	Branch once: run the body if the condition is true (optional ELSE for false).	Required
UNTIL	Loop the body while the condition is true (capped, with a wait between checks).	Required
WAIT_UNTIL	Pause and check until the condition becomes true, then continue. Takes no action.	None

The condition is checked against the page every time (never cached), so these keywords suit UI that varies between runs: optional popups, slow loads, and states that take time to settle. $variables can be used inside the condition.

4.7.1 WHEN
Runs the indented body only if the described state is on the page.

- WHEN "a cookie consent banner is visible"
    - CLICK ON "Accept all button" INTENT "Dismiss the cookie banner"

An optional ELSE runs when the condition is false. WHEN supports ELSE but not ELIF, and must have at least one nested step.

- WHEN "the user $email already appears in the results"
    - CLICK ON "the row for $email" INTENT "Open the existing user $email"
- ELSE
    - CLICK ON "Invite user button" INTENT "Invite a new user"

4.7.2 UNTIL
Repeats the indented body while the condition stays true, re-checking the page and waiting between passes. The loop exits as soon as the condition is false, or after a fixed maximum number of iterations. Use it for refresh, retry and poll-and-act patterns.

- UNTIL "the Refresh icon is still visible in the export row"
    - CLICK ON "Refresh icon" INTENT "Refresh the export status"

Here the agent keeps clicking Refresh while the icon is shown (the job is still running) and moves on once it disappears. UNTIL must have a body.

4.7.3 WAIT_UNTIL
Pauses and checks the page until the described state appears, then continues. It performs no action and has no body.

- CLICK ON "Generate report button" INTENT "Start the report"
- WAIT_UNTIL "the report status shows Completed"
- CLICK ON "Download button" INTENT "Download the finished report"

An indented body means WHEN/UNTIL; no body means WAIT_UNTIL. If the state never appears within the polling window, the agent carries on anyway, and the next step that can't proceed reports the failure.

5. System Constraints
A script must follow these rules to compile and run.

- Indentation: nested steps inside IF, ELIF, ELSE, FOR_EACH, WHEN or UNTIL are indented exactly 4 spaces. Only these keywords may have nested steps.
- Block bodies: WHEN and UNTIL need at least one nested step. WAIT_UNTIL, WAIT, GRAB and BROWSER_FIND are single lines and must not have a body.
- One command per step: each step line holds exactly one command. A trailing # comment is allowed.
- Runtime conditions: WHEN, UNTIL and WAIT_UNTIL take a non-empty, double-quoted condition describing a visible page state, not a variable comparison or an INTENT.
- Intent binding: if a variable is used in an action, that variable must also appear in the INTENT.

# Invalid
- FILL_AND_ENTER $name INTO "Search box" INTENT "Find the user"

# Valid
- FILL_AND_ENTER $name INTO "Search box" INTENT "Find the user $name"

6. Advanced Controls
Use with caution: use these keywords only when they are required.

These keywords change how steps run: grouping them, reading values from the live page, finding text, pausing, and choosing where the script starts.

Keyword	What it does	Body
FOR_EACH … EXECUTE_PARALLEL	Runs every iteration of a loop as one batch, without re-checking the page after each one.	Required
GRAB / GRAB ALL	Reads a value (or a list of values) off the live page into a new variable.	None
BROWSER_FIND	Finds the text in a variable on the page like Ctrl+F and scrolls it into view. No INTENT.	None
FOR_EACH $key, $value IN $map	Loops over a map, once per entry.	Required
WAIT	Pauses for a fixed number of seconds.	None
CONTINUE_FROM_LOGIN	Starts on the page where login ended instead of opening a URL.	n/a

6.1 FOR_EACH … EXECUTE_PARALLEL (New)
Adding EXECUTE_PARALLEL to the end of a FOR_EACH line runs all the loop's iterations as one batch. The agent locates every iteration's target against one snapshot of the page, clicks them back to back, then checks them together, instead of checking the page after every iteration.

- FOR_EACH $role IN $roles EXECUTE_PARALLEL
    - CLICK ON "The $role checkbox in the Roles section" INTENT "Assign the role $role"

- Use it only when every iteration acts on the same page and nothing navigates between iterations, for example ticking several checkboxes in one list.
- If any iteration can't be located, the batch falls back to the normal one-by-one loop.
- EXECUTE_PARALLEL is only used this way, at the end of a FOR_EACH line. Don't write it as a standalone block.
- EXECUTE_PARALLEL is the only thing allowed after FOR_EACH $item IN $list.
- It can't be used on a map loop or on a loop over a map value.

6.2 GRAB and GRAB ALL (New)
GRAB reads a value from the live page while the script runs and stores it in a new variable. Later steps can use that variable, for example to type a confirmation word the page displays.

- GRAB "the confirmation keyword shown in the delete dialog" INTO $confirm_kw INTENT "Read the word needed to confirm deletion"
- FILL $confirm_kw INTO "Confirmation input" INTENT "Type the confirmation keyword $confirm_kw"

GRAB can take an optional POSSIBLE_VALUES list after the INTENT to limit what the value can be. The list must hold at least one non-empty quoted value.

- GRAB "the user's current status" INTO $status INTENT "Read the current status" POSSIBLE_VALUES ["Active", "Suspended"]

A grabbed value can then drive a branch:

- IF $status EQUALS "Suspended"
    - CLICK ON "Reactivate button" INTENT "Reactivate the account"

GRAB ALL reads every matching item into a list variable, marked with []. A later FOR_EACH can loop over that list:

- GRAB ALL "ticked subscriptions other than Forgot Password" INTO $subs[] INTENT "List the active subscriptions"
- FOR_EACH $sub IN $subs
    - CLICK ON "$sub" INTENT "Expand the subscription $sub"

Rules:

- The pattern is GRAB "<what to read>" INTO $variable INTENT "<why>", or GRAB ALL "<items>" INTO $list[] INTENT "<why>".
- The target must be a new variable name that is not already defined.
- GRAB ALL must write into a list (INTO $name[]), and only GRAB ALL may do so. POSSIBLE_VALUES cannot be used with GRAB ALL.
- GRAB ALL reads at most 30 items. If more match, the task fails rather than running an unbounded loop, so describe the items narrowly.
- The grabbed variable is available only to later steps at the same indentation or deeper. A GRAB inside a WHEN or IF branch can't be used after that block ends.
- A grabbed value doesn't exist until the script runs, so it can't be tested with EXISTS, EMPTY or NOT_EMPTY, which are resolved before the run starts. Compare it with EQUALS / NOT_EQUALS or IN.
- The grabbed variable does not need to appear in the INTENT.
- GRAB is a single line and has no nested body.

6.3 BROWSER_FIND (New)
BROWSER_FIND does what the browser's Ctrl+F does. It finds the text held in a variable, searching the main page and any embedded frames, and scrolls the match into view. Write the keyword and the variable only.

- BROWSER_FIND $employee_id
- CLICK ON "The row for $employee_id" INTENT "Open the employee $employee_id"

Rules:

- It must be followed by a $variable holding the text to find, not a quoted literal.
- Nothing follows the variable: no INTENT.
- The text must match exactly one place on the page. If it matches nothing, or more than one place, the step fails.
- Use it to bring known off-screen text into view, not in place of a CLICK on a button or link.
- BROWSER_FIND is a single line and has no nested body.

6.4 Map Loop
FOR_EACH $key, $value IN $map loops over a map (see 2.2), once per entry, with $key and $value set to that entry. When a value is a list, loop over it with a nested FOR_EACH:

- FOR_EACH $account, $permissions IN $access
    - FOR_EACH $permission IN $permissions
        - CLICK ON "the checkbox in the $permission row under the $account column" INTENT "Grant $permission on $account"

$access["Reserve"] = ["Request payments", "Send money"]
$access["Operating"] = ["Send money"]

When every value is a single string, use $value directly:

- FOR_EACH $email, $role IN $role_of
    - SELECT $role FROM "the role dropdown in the row for $email" INTENT "Set $email to $role"

$role_of["john@acme.com"] = "Admin"
$role_of["mary@acme.com"] = "Viewer"

- $key and $value need different names, and neither can already be defined.
- A map can only be used in a map loop. It can't be written as text ("$access"), read by key in a step ($access["Reserve"]), or looped with the list form.
- If a value is a list for any key, $value can't be used as text. Loop over it with FOR_EACH $item IN $value.
- Maps are one level deep: $key is a single value and $value is never a map.
- EXECUTE_PARALLEL can't be used on a map loop or on a loop over a map value.
- Inside a map loop, $key and $value can only be tested with EQUALS / NOT_EQUALS.

6.5 WAIT
WAIT pauses for a fixed number of whole seconds, without checking the page. It takes no target and no INTENT. Use it only for a slow page with no visible state to wait for; otherwise use WAIT_UNTIL (4.7.3).

- CLICK ON "Search button" INTENT "Run the search"
- WAIT 30

WAIT 0, WAIT 2.5 and WAIT "30" are all invalid.

6.6 CONTINUE_FROM_LOGIN
Write URL CONTINUE_FROM_LOGIN instead of a quoted URL when the script should start on whatever page the login flow lands on.

URL CONTINUE_FROM_LOGIN

STEPS
    - CLICK ON "Admin tab in the top navigation" INTENT "Open the admin area"

Nothing else may follow it on the URL line. It works only with URL, not GOTO. Data extraction scripts support it too.

7. Real-World Examples
Standard Joiner, Mover and Leaver (JML) operations.

7.1 Example A: Joiner (New User Provisioning)
Scenario: creating a new account in Salesforce and assigning a license.

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

7.2 Example B: Mover (Role Transition)
Scenario: updating a user's permissions when they move departments.

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

7.3 Example C: Leaver (Deactivation & Transfer)
Scenario: deactivating a user and optionally transferring their data to a manager.

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

7.4 Example D: Bulk Role Assignment (Iteration)
Scenario: assigning several roles to a user with a loop.

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

7.5 Example E: Asynchronous Export (Runtime Conditions)
Scenario: exporting users where the export runs as a background job. A confirmation dialog may appear for large exports, the row shows a refresh control while processing, and the file must be polled until it's ready.

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

8. Data Extraction Scripts
In addition to action-based scripts (Joiner, Mover, Leaver), redflow supports a dedicated script type for extracting structured data from web applications. These scripts define what data to collect from list views, detail pages, and nested tables, and output the results as structured JSON.

8.1 Script Structure
A data extraction script has four main components executed in order:

URL — The target page to extract data from.
STEPS (optional) — Pre-extraction actions such as clicking filters or search buttons.
RESOURCE — Declares the resource being extracted and its unique identifier.
EXTRACT — Defines which fields to collect and from where (list or detail views).
8.2 RESOURCE Declaration
Every extraction script must declare a top-level RESOURCE with an IDENTIFIED_BY clause to prevent duplicate records.

RESOURCE: "ResourceName" IDENTIFIED_BY "unique_field"

Example:

RESOURCE: "Users" IDENTIFIED_BY "email"

8.3 EXTRACT Block
The EXTRACT block defines the data to collect. It supports two extraction modes:

FROM LIST — Extracts data from a table or repeating rows (multiple items, same structure).
FROM DETAILS — Extracts standalone labeled attributes from a detail page (single values, toggles, dropdowns).
If a detail page has both a table and standalone fields, use both at the same indentation level. If a detail page has only a table and no new standalone fields, do not include FROM DETAILS.

8.4 Field Syntax
Every field requires a name and an INSTRUCT clause describing where to find it on the page.

- "field_name" INSTRUCT "description of location"

POSSIBLE_VALUES — For fields with a universal, fixed set of options (dropdowns, badges, status indicators).

- "status" INSTRUCT "in Status column" POSSIBLE_VALUES ["Active", "Inactive", "Pending"]

Array Fields — Append [] to field names that collect multiple non-tabular values as an array.

- "tags"[] INSTRUCT "in Tags column"

Field names must use snake_case.

8.5 Top-Level STEPS
If any actions must be performed before extraction begins (e.g., clicking a search button, applying filters, or navigating menus), capture them as top-level STEPS before the RESOURCE declaration.

STEPS
    - CLICK ON "Search button in top right corner" INTENT "Load all groups into the table"

8.6 Detail Page Navigation
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
8.7 Nested Resources
When a detail page contains a sub-table, declare a nested RESOURCE directly above its FROM LIST block. The nested RESOURCE uses the short form without IDENTIFIED_BY.

        STEPS
            - CLICK ON "Group_name" INTENT "Open group"
        RESOURCE "group_members"
        EXTRACT
            FROM LIST
                - "email" INSTRUCT "email column"
                - "status" INSTRUCT "status column"

Every nested FROM LIST must have a RESOURCE declaration directly above it. This applies at every nesting depth.

8.8 Multi-Tab Detail Pages
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

8.9 Cross-URL JOIN
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

8.10 Key Rules
Every top-level RESOURCE must have IDENTIFIED_BY.
Per-item detail clicks go inside FROM LIST as indented STEPS, not at the top level.
Nested FROM LIST inside a detail page requires a RESOURCE declaration directly above it.
All tab-related blocks must be siblings at the same indentation level.
GOTO must always be inside a STEPS block.
Every field needs an INSTRUCT clause.
Use POSSIBLE_VALUES only for fields with a universal, fixed set of options.
Append [] to field names that collect multiple non-tabular values.
FROM DETAILS should only contain fields not already extracted in FROM LIST.
8.11 Examples
8.11.1 Example A: Flat List Extraction (No Detail Navigation)
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

8.11.2 Example B: List with Pre-Extraction Steps
Scenario: Loading groups by clicking a search button before extracting the list.

URL "http://synqa.rjf.com:8888/syn/#simpleBrowser/type=SynGroup/seq=2097258837-3"
STEPS
    - CLICK ON "Search button in top right corner" INTENT "Load all groups into the table"
RESOURCE: "Groups" IDENTIFIED_BY "unique_id"
EXTRACT
    FROM LIST
        - "unique_id" INSTRUCT "in Unique ID column"
        - "description" INSTRUCT "in Description column"

8.11.3 Example C: Detail Page with Nested List
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

8.11.4 Example D: Multi-Tab Detail Page (FROM DETAILS + Nested Lists)
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

8.11.5 Example E: Cross-URL JOIN
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
