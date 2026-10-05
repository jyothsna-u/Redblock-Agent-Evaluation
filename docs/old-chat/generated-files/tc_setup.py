from tc_common import T

# ---------------------------------------------------------------- Agents List
M = "Agents List"
T(M, "Fleet view", "Agents list shows all columns",
  "At least 3 Agents exist in different states",
  ["Open AI Studio > Agents"],
  "-",
  "Columns shown: Agent Name (with agt- ID), Authentication Status, Active Skills, Tags, Last Updated, Purpose, Actions.", "P2")
T(M, "Fleet view", "Agent ID copy button copies the full agt- ID",
  "Agent exists",
  ["Open Agents list", "Click copy icon under an Agent name", "Paste into a text editor"],
  "-",
  "Clipboard holds the complete agt-<uuid>; matches the ID in the Agent URL.", "P2")
T(M, "Status", "Authentication Status shows all four states correctly",
  "Agents with: no credentials; valid creds; wrong password; check running",
  ["Open Agents list", "Compare each Agent's status badge"],
  "-",
  "Not Provided (grey), Valid (green), Invalid (red), In Progress (blue) shown for the matching Agents.", "P1")
T(M, "Search", "Search by Agent name (full, partial, case-insensitive)",
  "Agents named 'Github BOA 2', 'Atlassian BOA dev'",
  ["Search 'github'", "Search 'BOA'", "Search 'GITHUB boa'", "Search 'zzz-no-match'"],
  "-",
  "Matching Agents only; partial and case-insensitive matches work; clear empty state for no results.", "P2")
T(M, "Search", "Search with special characters does not break the page",
  "-",
  ["Search each value in the data column"],
  "%, _, ', \", <script>, \\, emoji",
  "No error, no script execution, no unfiltered list; empty state or correct matches.", "P2", "Negative")
T(M, "Filter", "Filter by Authentication Status and by Tags, combined with search",
  "Agents with mixed statuses and tags",
  ["Filter Status = Valid", "Add Tag = prod", "Type a search term", "Clear filters"],
  "-",
  "Results satisfy all active filters; clearing restores the full list.", "P2")
T(M, "Pagination", "Pagination with many Agents",
  "> 1 page of Agents (e.g., 30+)",
  ["Page forward/back", "Change page size if available", "Apply a filter while on page 2"],
  "-",
  "No duplicates or missing rows across pages; filtering resets to page 1.", "P3")
T(M, "Active Skills", "Active Skills column reflects only published Skills",
  "Agent with 1 published and 1 Pending Skill",
  ["Open Agents list", "Check Active Skills for that Agent"],
  "-",
  "Only the published Skill is listed/counted.", "P1")
T(M, "Last Updated", "Last Updated changes after profile/identity/skill edits",
  "Agent exists",
  ["Note Last Updated", "Edit Agent Purpose and save", "Return to list"],
  "-",
  "Last Updated shows the new time in the user's timezone.", "P3")

# ---------------------------------------------------------------- Agent Profile
M = "Agent Profile"
T(M, "Create entry", "+ Create Agent offers Certified and Custom paths",
  "-",
  ["Click + Create Agent"],
  "-",
  "Two options: Use Redblock Certified Agent, Build Custom Agent.", "P2")
T(M, "Create", "Create custom Agent with valid Name, Purpose, Tags",
  "-",
  ["Build Custom Agent", "Enter Name, Purpose, 2 tags", "Click Create"],
  "Name: 'QA Salesforce Sandbox', Purpose: 'QA JML testing', Tags: sandbox, qa",
  "Agent created with agt- ID; Authentication Status = Not Provided; appears in list; creation logged in Logs with user and timestamp.", "P0")
T(M, "Validation", "Agent Name is required",
  "-",
  ["Leave Name empty, fill Purpose", "Try to Create"],
  "-",
  "Create blocked with a required-field message.", "P1", "Negative")
T(M, "Validation", "Agent Purpose is required",
  "-",
  ["Fill Name, leave Purpose empty", "Try to Create"],
  "-",
  "Create blocked with a required-field message.", "P1", "Negative")
T(M, "Validation", "Whitespace-only Name/Purpose rejected",
  "-",
  ["Enter only spaces in Name and Purpose", "Try to Create"],
  "'   '",
  "Treated as empty; Create blocked.", "P2", "Negative")
T(M, "Validation", "Agent Name max length 64 (boundary)",
  "-",
  ["Enter 63, 64, then 65 characters", "Try to Create each"],
  "63 / 64 / 65 char strings",
  "63 and 64 accepted; 65 blocked or truncated with a clear message.", "P1", "Boundary")
T(M, "Validation", "Agent Name must be unique",
  "Agent 'QA Dup' exists",
  ["Create another Agent named 'QA Dup'", "Repeat with 'qa dup' and ' QA Dup '"],
  "-",
  "Exact duplicate rejected. Case/whitespace variants: behaviour matches product decision (record it).", "P1", "Negative",
  "Confirm whether uniqueness is case-insensitive and trims spaces.")
T(M, "Validation", "Special characters and unicode in Name/Purpose",
  "-",
  ["Create Agents using each value"],
  "O'Brien App, App & Co, Zürich-HR, 日本語, emoji, <b>x</b>",
  "Saved and displayed exactly as typed; HTML not rendered; no broken layout.", "P2", "Edge")
T(M, "Immutability", "Agent Name cannot be changed after creation",
  "Agent exists",
  ["Open Agent Profile", "Click Edit"],
  "-",
  "Name field is read-only in edit mode; Purpose and Tags are editable.", "P0")
T(M, "Edit", "Edit Purpose and Tags and save",
  "Agent exists",
  ["Click Edit", "Change Purpose", "Add and remove tags", "Save"],
  "-",
  "Changes persist after reload; Save disabled until something changes.", "P1")
T(M, "Edit", "Cancel / navigate away with unsaved profile changes",
  "Agent exists",
  ["Click Edit and change Purpose", "Switch tab or click browser back"],
  "-",
  "Either a discard warning, or changes are not saved. Record which.", "P3", "Edge")
T(M, "Tags", "Tag input: Enter adds, duplicates, long tags, many tags",
  "-",
  ["Type tag + Enter", "Add same tag again", "Add a 100-char tag", "Add 30 tags"],
  "-",
  "Tags added on Enter; duplicate prevented; long/many tags handled without layout break.", "P3", "Edge")
T(M, "Tabs gating", "Identity, Skills, Settings tabs disabled until profile saved",
  "Creating a new Agent",
  ["Before clicking Create, hover each other tab"],
  "-",
  "Tabs disabled with tooltip 'Available after you save the Agent Profile.'", "P2")
T(M, "ITSM naming", "Agent Name must exactly match ITSM application name",
  "ITSM automation configured; ticket references 'Github'",
  ["Create Agent named 'GitHub'", "Raise ITSM ticket for 'Github'"],
  "-",
  "Ticket does not route. Check whether the failure is visible anywhere (docs say it fails silently).", "P1", "Negative",
  "Silent failure is a UX risk; raise as improvement if nothing is logged.")
T(M, "Audit", "Agent creation recorded in Logs",
  "-",
  ["Create an Agent", "Open Logs"],
  "-",
  "Log entry with creating user, Agent name/ID, timestamp.", "P2")
T(M, "Double submit", "Double-clicking Create does not create duplicate Agents",
  "-",
  ["Fill form", "Double-click Create quickly"],
  "-",
  "Exactly one Agent created.", "P2", "Edge")

# ---------------------------------------------------------------- Agent Identity
M = "Agent Identity"
T(M, "Manual", "Manual mode: valid credentials verify successfully",
  "Agent created; creds verified by manual login",
  ["Agent Identity > Manual", "Enter Username, Password, Login URL", "Save"],
  "Valid service account",
  "Real login attempted; green banner 'Agent Identity successfully verified' with View Body Cam Footage link; status = Valid.", "P0")
T(M, "Manual", "Body Cam of identity verification shows the login",
  "Verified identity",
  ["Click View Body Cam Footage"],
  "-",
  "Recording shows login page, credential entry (password masked), landing page after login.", "P1")
T(M, "Manual", "Wrong password",
  "-",
  ["Enter wrong password", "Save"],
  "-",
  "Verification fails; status Invalid; clear error; footage shows the login error.", "P0", "Negative")
T(M, "Manual", "Wrong username / non-existent user",
  "-",
  ["Enter unknown username", "Save"],
  "-",
  "Status Invalid with clear error.", "P1", "Negative")
T(M, "Manual", "Required fields: Username, Password, Login URL",
  "-",
  ["Leave each required field empty in turn", "Save"],
  "-",
  "Save blocked with required-field messages.", "P1", "Negative")
T(M, "Login URL", "Invalid / malformed Login URL",
  "-",
  ["Enter each value", "Save"],
  "'abc', 'htp://x', 'https://', 'https://doesnotexist.invalid'",
  "Format errors caught before save; unreachable host gives a clear failure, not an endless spinner.", "P1", "Negative")
T(M, "Login URL", "Login URL http vs https, trailing slash, query params",
  "-",
  ["Try http://, https://, with trailing '/', with '?returnTo=' param"],
  "-",
  "All valid forms work; redirects are followed to the login page.", "P3", "Edge")
T(M, "Login URL", "Login URL is not the login page (home page / deep link)",
  "-",
  ["Set Login URL to app home page that redirects to login"],
  "-",
  "Agent follows redirect and logs in, or fails with a clear message.", "P2", "Edge")
T(M, "Login variants", "Two-step login (username -> Next -> password)",
  "App with split login (e.g., Microsoft, Google-style)",
  ["Configure identity", "Save"],
  "-",
  "Agent completes both steps and verifies.", "P0", "Edge")
T(M, "Login variants", "SSO redirect login (IdP page on another domain)",
  "App redirects to Okta/Entra for login",
  ["Configure identity", "Save"],
  "-",
  "Agent completes login on IdP domain and returns to app. Check Safe URLs include IdP domain.", "P1", "Edge")
T(M, "Login variants", "Login page with cookie banner / popup over the form",
  "App shows cookie consent on login page",
  ["Configure identity", "Save"],
  "-",
  "Agent dismisses banner and logs in.", "P2", "Edge")
T(M, "Login variants", "Login page with 'Remember me', tenant/domain field, or org selector",
  "App requires a third field (tenant / domain / company ID)",
  ["Put the extra value in Additional Information JSON", "Save"],
  "{\"tenant\": \"acme\"}",
  "Agent fills the extra field (or documents that this isn't supported).", "P2", "Edge",
  "Confirm whether Additional Information is used during login or only by redflows.")
T(M, "Login variants", "CAPTCHA on login page",
  "App shows CAPTCHA",
  ["Configure identity", "Save"],
  "-",
  "Agent fails gracefully with a clear 'CAPTCHA' reason; no endless retries.", "P2", "Negative")
T(M, "Login variants", "Account locked / password expired / forced password change screen",
  "Service account in each state",
  ["Save identity for each"],
  "-",
  "Status Invalid with a message that reflects the real reason; Agent does not change the password on its own.", "P1", "Negative")
T(M, "Login variants", "Push-MFA or SMS OTP (not TOTP)",
  "App enforces push/SMS MFA",
  ["Configure identity", "Save"],
  "-",
  "Clear failure stating unsupported MFA type; no hang.", "P2", "Negative")
T(M, "TOTP", "Valid TOTP seed with 2FA-enabled app",
  "App enforces TOTP",
  ["Enter creds + TOTP seed", "Save"],
  "Base32 seed",
  "Agent enters generated code and verifies.", "P0")
T(M, "TOTP", "Missing TOTP seed on 2FA app",
  "App enforces TOTP",
  ["Save without seed"],
  "-",
  "Verification fails at the 2FA prompt with a clear reason.", "P1", "Negative")
T(M, "TOTP", "Invalid TOTP seed format",
  "-",
  ["Enter non-Base32 / too-short seed", "Save"],
  "'12345', 'abc!@#', seed shorter than Minimum Secret Key Length",
  "Validation error before save.", "P2", "Negative")
T(M, "TOTP", "Generate Test Code matches authenticator app",
  "Seed also loaded in an authenticator app",
  ["Click Generate Test Code", "Compare with authenticator"],
  "-",
  "Codes match within the same time window.", "P1")
T(M, "TOTP", "Advanced Settings: non-default length, step, algorithm",
  "IdP using 8 digits / 60s / SHA256",
  ["Set Advanced Settings accordingly", "Generate Test Code", "Save"],
  "-",
  "Codes match IdP; login succeeds. Defaults are 6 digits, 30s, SHA1.", "P2")
T(M, "TOTP", "Code near window boundary",
  "2FA app",
  ["Trigger verification in last 2-3 s of a 30 s window (repeat several times)"],
  "-",
  "Agent handles expiry (regenerates code) and still logs in.", "P2", "Edge")
T(M, "Vault", "Vault mode: 1Password item",
  "1Password vault connected",
  ["Toggle Vault", "Select instance and item", "Save"],
  "-",
  "Login URL pre-fills if present on item; TOTP supplied by vault; verification succeeds.", "P0")
T(M, "Vault", "Vault mode: CyberArk (WPM / CCP / Conjur)",
  "CyberArk connected",
  ["Select CyberArk item", "Save"],
  "-",
  "Verification succeeds; TOTP comes from vault; Advanced Settings hidden.", "P1")
T(M, "Vault", "Vault mode: BeyondTrust with 2FA app requires manual TOTP seed",
  "BeyondTrust connected; app enforces 2FA",
  ["Select item without entering seed, Save", "Enter seed, Save"],
  "-",
  "Without seed: fails at 2FA. With seed: succeeds.", "P1", "Negative")
T(M, "Vault", "Password rotated in vault is picked up automatically",
  "Vault identity verified",
  ["Rotate password in vault", "Execute any Skill"],
  "-",
  "Run logs in with the new password; no change needed in Redblock.", "P0")
T(M, "Vault", "Vault item deleted / vault unreachable",
  "Vault identity configured",
  ["Delete the item or disconnect the vault", "Re-Authenticate / Execute"],
  "-",
  "Clear error naming the vault problem; status Invalid.", "P1", "Negative")
T(M, "Manual", "Manual password rotation requires update",
  "Manual identity verified",
  ["Change password in target app", "Execute a Skill", "Update password in Redblock and re-run"],
  "-",
  "First run fails at login (Invalid); after update it succeeds.", "P1")
T(M, "Additional Info", "Additional Information accepts valid JSON only",
  "-",
  ["Enter valid JSON, save", "Enter invalid JSON, save"],
  "{\"account\":\"acme\"} / {account:acme}",
  "Valid saved; invalid rejected with a JSON error.", "P2", "Negative")
T(M, "Re-Authenticate", "Re-Authenticate re-runs the login check",
  "Verified identity",
  ["Click Re-Authenticate"],
  "-",
  "Status In Progress then Valid; new footage available.", "P2")
T(M, "Security", "Password masked and not retrievable in UI",
  "Manual identity saved",
  ["Reopen identity", "Inspect field, page source, network responses"],
  "-",
  "Password shown only as dots; not returned in clear text by the API.", "P0", "Security")
T(M, "Mode switch", "Switching Vault <-> Manual after saving",
  "Manual identity saved",
  ["Switch to Vault, select item, Save", "Switch back to Manual"],
  "-",
  "Only the active mode is used; no stale credentials; clear what happens to old values.", "P2", "Edge")
T(M, "Gating", "Execute blocked until identity configured",
  "Agent without identity; Skill with redflow",
  ["Open Playground", "Try Execute"],
  "-",
  "Execute disabled with explanation; editing and saving redflow still allowed.", "P1")

# ---------------------------------------------------------------- Skills Tab
M = "Skills Tab"
T(M, "Add", "Add Skill menu lists Account Skills",
  "Agent exists",
  ["Skills tab > + Add Skill"],
  "-",
  "Account Aggregation, Activate, Certificate Update, Deactivate, Remove, Update Account, plus Create Account (if not added).", "P1")
T(M, "Add", "Skill already added is removed from the menu",
  "Create Account already added",
  ["Open + Add Skill"],
  "-",
  "Create Account not offered again.", "P2")
T(M, "Entitlements", "Entitlement Skills appear per Entitlement Type from the Activation",
  "Activation with Single, Multi and Variable entitlement types",
  ["Open + Add Skill", "Hover Add / Remove / Change / Entitlement Aggregation"],
  "-",
  "Change {Type} for single-valued; Add/Remove {Type} for multi-valued; Aggregation {Type} for variable.", "P1")
T(M, "Entitlements", "No Activation -> entitlement submenus",
  "Agent not used by any Activation",
  ["Open + Add Skill", "Hover entitlement items"],
  "-",
  "Submenus empty or hidden with guidance to configure an Activation.", "P2", "Edge")
T(M, "Table", "New Skill row shows Pending with a copyable Skill ID",
  "-",
  ["Add a Skill"],
  "-",
  "Row: skill name, skl- ID with copy, Status Pending, empty Live Since.", "P2")
T(M, "Table", "Hourglass shown while a run is in flight",
  "-",
  ["Start execution", "Return to Skills tab"],
  "-",
  "Hourglass next to the Skill until the run finishes.", "P3")
T(M, "Table", "Warning icon on a Skill whose last run failed",
  "Skill with failed last run",
  ["Open Skills tab", "Hover the red icon"],
  "-",
  "Tooltip explains the failure; icon clears after a successful run.", "P3", "Functional",
  "Icon seen in UI but not documented; confirm meaning.")
T(M, "Remove", "Remove a never-run, unpublished Skill",
  "Newly added Skill",
  ["Actions > Remove", "Confirm"],
  "-",
  "Skill removed and reappears in Add Skill menu.", "P2")
T(M, "Remove", "Remove disabled once Skill has run or is published",
  "Skill executed at least once",
  ["Open Actions menu"],
  "-",
  "Remove disabled with explanation.", "P1", "Negative")
T(M, "Navigation", "Clicking a Skill row opens its Playground; skill switcher works",
  "2+ Skills",
  ["Click a Skill row", "Use breadcrumb Skill dropdown to switch Skill"],
  "-",
  "Correct Playground opens; switching loads the other Skill's redflow and parameters.", "P2")

# ---------------------------------------------------------------- Agent Settings
M = "Agent Settings"
T(M, "Safe URLs", "At least one Safe URL required",
  "No Safe URLs",
  ["Open Agent Settings"],
  "-",
  "Save disabled until one Safe URL is added.", "P1", "Negative")
T(M, "Safe URLs", "Add, edit, delete Safe URLs",
  "-",
  ["+ Add URLs, save", "Edit an entry", "Delete an entry", "Save"],
  "-",
  "Table reflects changes after reload.", "P2")
T(M, "Safe URLs", "Navigation outside Safe URLs is blocked",
  "Safe URLs = app domain only; redflow step leads to an external link",
  ["Execute"],
  "-",
  "Navigation blocked; run fails safely with a message naming the blocked URL.", "P0", "Security")
T(M, "Safe URLs", "Wildcard * allows any navigation",
  "Safe URL = *",
  ["Execute a flow that visits an external domain"],
  "-",
  "Navigation allowed (fine for testing; flag for production).", "P2")
T(M, "Safe URLs", "SSO / IdP domain missing from Safe URLs",
  "Login redirects to IdP domain not in list",
  ["Execute"],
  "-",
  "Blocked at IdP with a clear message (so users know to add it).", "P1", "Edge")
T(M, "Safe URLs", "Pattern matching: subdomains, paths, http vs https",
  "-",
  ["Test entries like https://app.com, *.app.com, https://app.com/admin/*"],
  "-",
  "Matching rules behave as documented; record exact semantics.", "P2", "Edge",
  "Pattern syntax is not documented.")
T(M, "Safe URLs", "Invalid Safe URL input",
  "-",
  ["Enter 'not a url', empty, spaces, javascript:alert(1)"],
  "-",
  "Rejected with validation message.", "P2", "Negative")
T(M, "Proxy", "Proxy dropdown empty state links to Proxy Profiles",
  "No proxy profiles",
  ["Open Proxy Server"],
  "-",
  "Empty dropdown with a working link to Settings > Proxy Profile.", "P3")
T(M, "Proxy", "Execution routes through selected proxy",
  "Target app allowlists proxy IP only",
  ["Select proxy, Save", "Execute"],
  "-",
  "Run succeeds; without proxy it is blocked by the app.", "P1")
T(M, "Toggles", "Allow parallel execution ON/OFF",
  "2 published Skills",
  ["Toggle OFF: trigger both via API", "Toggle ON: trigger both"],
  "-",
  "OFF: runs queue one after another. ON: run in parallel without session clash.", "P1")
T(M, "Toggles", "Logout after execution",
  "App limits concurrent sessions",
  ["Toggle ON, run twice", "Toggle OFF, run twice"],
  "-",
  "ON: each run logs out; second run succeeds. OFF: record behaviour.", "P2")
T(M, "Toggles", "Always clear previous cookie",
  "-",
  ["Toggle ON and OFF, execute each"],
  "-",
  "ON: fresh login every run (visible in Body Cam). OFF: session reused if valid.", "P2")
T(M, "Toggles", "Allow animations on UI",
  "App with heavy animations",
  ["Toggle OFF and ON, compare run time and success"],
  "-",
  "OFF faster; ON only needed if app breaks without animations.", "P3")
T(M, "Save", "Changes are staged until Save",
  "-",
  ["Change a toggle", "Leave the tab without saving", "Return"],
  "-",
  "Change not applied.", "P2")

# ---------------------------------------------------------------- Certified Agents
M = "Certified Agents"
T(M, "Create", "Create from Redblock Certified Agent",
  "-",
  ["+ Create Agent > Use Redblock Certified Agent", "Pick Airbyte"],
  "-",
  "Agent created with Certified chip and pre-trained, published Skills.", "P1")
T(M, "Ownership", "Adding/removing a Skill warns and drops certification",
  "Certified Agent",
  ["Add a Skill", "Read warning", "Confirm"],
  "-",
  "Warning shown first; after confirming, Certified chip removed.", "P1")
T(M, "Ownership", "Changing Agent Settings warns and drops certification",
  "Certified Agent",
  ["Change a toggle", "Save"],
  "-",
  "Warning shown; confirming removes Certified chip; cancelling keeps it.", "P2")
T(M, "Ownership", "Identity change does not drop certification",
  "Certified Agent",
  ["Update credentials"],
  "-",
  "Certified chip stays (identity is not listed as a certification-breaking change).", "P3", "Edge",
  "Confirm intended behaviour.")
