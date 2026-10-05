Agents
What Agents do
If your team still creates accounts by hand, resets passwords by hand, or exports the quarterly user list one screen at a time, you're here to delegate that work to Redblock Execution Agents. This guide walks you through training an Agent on a Disconnected App and activating it to automate complex identity workflows end to end.

IGA / ITSM
⇄
Redblock AI Agents
→
Disconnected Apps
An Agent is an AI worker trained on one application. You show it the task by recording yourself doing it in a browser, and it replays those steps whenever SailPoint, ServiceNow, a cron job, or you ask it to.

One Agent per application instance. Your sandbox Salesforce gets its own Agent; so does production. Agents can learn any identity workflow Redblock supports: Create Account, Remove Account, Activate Account, Deactivate Account, Account Aggregation, and entitlement operations. You pick and choose the ones your app supports and your team actually wants to automate. A PagerDuty Agent might do creates and deactivates. A GitHub Agent might only do quarterly aggregation.

This is your fleet view. You can see every Agent you've created, check their credential status, and see which Skills each one has learned. Search by name, filter by Authentication Status or Tags, paginate through the list.

Column	Description
Agent Name	Application name + unique agent ID (agt-...)
Authentication Status	Valid (green) means credentials passed a real login. Invalid (red) means the last login attempt failed (wrong password, expired token, 2FA not configured). In Progress (blue) means a credential check is running right now. Not Provided (grey) means no credentials yet.
Active Skills	Published Identity Skills for this Agent
Tags	Free-form labels for filtering. Use them for environment (prod, sandbox), business unit, region, or anything else your team tracks.
Last Updated	Date and time of last modification
Purpose	Brief summary of the Agent's purpose
Actions	Per-row menu for the actions available on that Agent
Create an Agent
Creating an Agent takes two steps. Step 1 is the Agent Profile. Step 2 is the credentials it will use to log in. Your Agent is created at the end of Step 1, not the end of Step 2, so you can always come back later to finish the credentials.

Clicking + Create Agent offers two starting points:

Use Redblock Certified Agent — start from a pre-certified application Agent that Redblock builds and maintains, such as Airbyte. Its Skills arrive already trained.
Build Custom Agent — create and certify your own Agent manually. This is the path described below.
Step 1: Agent Profile
Create Agent form: Agent Profile
Step 1: Agent Profile

Click + Create Agent on the Agents page and fill in three fields.

Agent Name (required): name your Agent. Keeping it the same as the target application is a good idea because your team will recognize it at a glance. This is the one field you can't change after creation, so pick carefully.

warning
If you plan to use ITSM automation (e.g., ServiceNow tickets triggering Agent runs), the Agent Name must exactly match the application name in your ITSM tickets, including casing and spelling. If you name the Agent "GitHub" but your ITSM tickets reference "Github," ticket routing will fail silently.

Agent Purpose (required): a one-line summary that shows on the Agent gallery card.

Tags (optional): labels for filtering and discovery later.

Click Create. The Agent appears in the gallery with a unique ID (agt-...) and an Authentication Status of Not Provided. Agent Purpose, Tags, and everything in Step 2 can be edited later. Only Agent Name is permanent.

Agent creation is recorded in Logs with your user identity and the timestamp, so your change-management team can trace who created which Agent and when.

Until the Agent Profile is saved, the Agent Identity, Skills, and Agent Settings tabs stay disabled with the tooltip "Available after you save the Agent Profile."

Step 2: Agent Identity
This is where you give your Agent its identity: the Login URL it opens at the start of every Skill run (usually the app's sign-in page) and the service account credentials it uses to log in. A Vault / Manual toggle at the top of the form picks how the credentials are supplied.

Option A: Vault (recommended). Choose the Vault Instance (your connected vault, such as 1Password, CyberArk, or BeyondTrust), then the Item that holds this service account. Your Agent reads the service account from the vault on every run, so when the password rotates there, your Agent picks it up automatically — no changes needed on the Redblock side. If the vault Item also carries a Login URL, that field pre-fills for you.

Agent Identity with Vault credentials
Agent Identity, Vault mode: Vault Instance and Item, with Login URL and TOTP Seed

Two CyberArk/BeyondTrust gotchas to know about: CyberArk WPM stores the TOTP seed in the vault, so 2FA-enabled apps work out of the box. BeyondTrust does not store TOTP seeds. If you're using BeyondTrust and your target app enforces 2FA, type the TOTP Seed into the field below. Without it, your Agent will get stuck on the 2FA prompt.

important
BeyondTrust does not store TOTP seeds. If your Vault Instance is BeyondTrust and the application enforces 2FA, you must enter the TOTP Seed manually. 1Password and CyberArk (WPM, CCP, and Conjur) supply seeds automatically — see TOTP Support.

Option B: Manual. Use this when the app isn't in your vault yet, or when you're testing. Switch the toggle to Manual and type the Username, Password, Login URL, and TOTP Seed directly. Anything you enter here is encrypted at rest, but it's static, so you'll need to update it yourself when the password rotates.

Agent Identity in Manual mode
Agent Identity, Manual mode: Username, Password, Login URL, TOTP Seed, and Additional Information

Advanced Settings and Additional Information (Optional) are separate fields, and both modes carry both.

Advanced Settings is a collapsible section under the TOTP Seed field that tunes how codes are generated: One Time Password Length, Minimum Secret Key Length, TOTP Time Step Interval, and TOTP Hash Algorithm. The defaults follow RFC 6238 (6 digits, 30 seconds, SHA1) — change them only to match what your identity provider expects. Generate Test Code produces a live code from the seed and settings so you can confirm the configuration before saving. The section is hidden when the vault Item already supplies the TOTP seed, since there's nothing to configure.

Additional Information (Optional) is a free-form JSON field for extra context the redflow can reference, such as an account or container name.

Once you save, the Agent attempts a real login. A green banner confirms "Agent Identity successfully verified" — and because the check is a real browser session, it links to View Body Cam Footage so you can watch the login that proved it.

Before you save, make sure you can log in to the app manually with these same credentials right now. If your own hands can't get past the login screen, your Agent won't either.

Agent tabs
Agent detail page showing the four tabs
Agent detail page: Agent Profile, Agent Identity, Skills, and Agent Settings

Once an Agent exists, its detail page organizes everything into four tabs:

Tab	What it covers	When you need it
Agent Profile	Name, purpose, tags	Step 1 of creation. Return here to edit purpose or tags.
Agent Identity	Login URL, Vault or manual credentials, TOTP Seed	Step 2 of creation. Return here whenever credentials change.
Skills	Add and train Identity Skills, including entitlement Skills	The landing tab for a configured Agent.
Agent Settings	Proxy Server, Safe URLs, Execution Settings	Before production. Safe URLs are required.
Each Agent's ID (agt-...) appears beneath its name on the Agents list, with a copy button. That's the value external systems use when calling the API.

Entitlements, Identity Operations, Cache, and the provider-specific activation lifecycle live on the Activation that uses this Agent — see Activation.

Identity Skills
Teaching an Agent a Skill is like onboarding a new hire. You show them the task, let them try it, watch how they do, and iterate until they've got it. In AI Studio, that loop has four beats:

Give the Agent a redflow — generated from a screen recording, reused from another Agent, or written by hand.
Let the Agent try it against the live app.
Watch the Bodycam to see what happened. Adjust the redflow or execution parameters as needed.
Re-run, re-watch, re-adjust. Once your Agent nails it, click Publish.
One Skill is one operation. If your Agent needs to create accounts and deactivate them, that's two separate Skills, trained independently.

Skills come in two categories:

Account Skills (available for every Agent):

Skill	What it Does
Create Account	Provisions a new user account in the application
Remove Account	Deletes or removes a user account
Activate Account	Re-enables a previously disabled account
Deactivate Account	Disables a user account without deleting it
Certificate Update	Updates a certificate held by the application
Account Aggregation	Exports all user accounts from the application for governance
Entitlement Skills (generated from the Entitlement Types defined on an Activation that uses this Agent):

Skill	When it Appears
Change Entitlement {Type}	Single-Valued entitlement types
Add Entitlement {Type}	Multi-Valued entitlement types
Remove Entitlement {Type}	Multi-Valued entitlement types
Entitlement Aggregation {Type}	Variable entitlement types
To add Skills to an Agent:

Open the Agent from the Agents page
Go to the Skills tab
Click + Add Skill and pick the Skills you want to train
Click a Skill row to open the Playground
Account Skills show up for every Agent. Entitlement Skills only show up once an Activation that uses this Agent has the matching Entitlement Type configured. If you expected an entitlement Skill and it's missing, check the relevant Activation IGA tool flow.

The Skills tab
Skills tab table
Skills tab: one row per Skill, with training and publish state

Column	Description
Learned Skill	Skill name and its copyable Skill ID. An hourglass appears while a training run is in flight.
Status	Published once a version is live, Pending until then.
Last Executed At	When the most recent run finished.
Live Since	How long the current live version has been published.
Actions	Remove takes the Skill off this Agent. Disabled once the Skill has been run or has a live version.
Train an Agent on an Identity Skill
Expect to iterate. Most Skills take 2 or 3 runs before your Agent nails the task, and that's normal, not a sign something is broken.

Step 1: Give the Skill a redflow
A redflow is the Agent's training manual: the step-by-step instructions it follows. Open a Skill that has no redflow yet and the Playground offers three ways to get one.

The three redflow options in the Playground
A Skill with no redflow yet: Generate from assets, Select an existing redflow, or write one manually

Option A: Generate redflow from assets (recommended). Upload a screen recording, SOP documents, or screenshots of the identity operation, and the redflow Engine converts them into automation logic. Accepted formats: MP4, MOV, PDF, DOCX, MD, TXT, PNG, JPG, WEBP, with recordings up to 10 MB. Size limits are configurable per environment, so if your organization runs its own instance the numbers may differ — the upload area always states the limits that apply to you.

Recording tips that make the difference between a clean generation and a messy one:

Start from the most direct page to minimize navigation
Record the complete flow, from login to the final confirmation screen
Avoid switching tabs, screen flickers, or notifications
One recording per Skill. A "Create Account" recording won't work for "Remove Account."
Option B: Select redflow. Reuse a redflow from an existing published Agent Skill. The list fills itself in with the Skills that match the one you're training, and picking one copies both its redflow and its execution parameters — see Option B below. This is the fastest path when you're onboarding a second instance of an app you've already automated.

Option C: Write redflow manually. Start from a blank editor and build the flow yourself. See redflow Syntax for the command reference.

Option A: Generate a redflow from assets
Drop your files on the upload area, or click it to browse. Either way the Generate redflow dialog opens with those files already staged.

The Generate redflow dialog with assets staged
The Generate redflow dialog: staged assets with per-file previews, and the written-instructions field

In the dialog:

Upload assets. Add more files at any time, mix types freely, and remove anything you staged by mistake with the trash icon. Screen recordings and screenshots get an expandable preview so you can confirm you uploaded the right take before spending a generation on it. Limits are per type — up to 5 screen recordings (MP4, MOV), 10 documents (PDF, DOCX, MD, TXT), and 10 screenshots (PNG, JPG, WEBP), each up to 10 MB. Files over the limit, or of an unsupported type, are rejected with an inline message and the rest still upload.
Written instructions (optional). Click + Add written instructions to describe what the assets don't show: when to branch, which values to enter, edge cases to handle. For example, "If the user is a contractor, set the role to 'External' and skip the license step."
Intent. Appears only when the Playground can't infer the intent from the Skill. Pick what the redflow is for: User Lifecycle - Joiner, Mover, Leaver (JML), Data Aggregation (Accounts, Entitlements), Credential Rotation, or File Export.
User Export Available? / Entitlement Export Available? Appears on Aggregation Skills. Answer Yes if the target app can export that data in bulk — the Engine then generates a file-export flow instead of a page-by-page scrape.
Click Generate. A progress bar tracks the upload, and a toast confirms the request was submitted.

note
At least one visual asset is required. Text files alone can't produce a redflow — pair them with a screen recording, screenshots, or a PDF/DOCX that contains screenshots. Generate stays disabled until that's satisfied.

Generation status
Generation runs asynchronously — you can navigate away and come back. The system processes one redflow at a time per user, and generation typically completes within a few minutes. While it runs, the Playground shows a LIVE banner and blocks runs and edits.

When it finishes, one of two alerts appears:

Success — "The redflow has been successfully generated from your assets." Click Click here to open the new version.
Failure — "The redflow generation failed. Please retry by uploading your assets again." Click View Details for the underlying error, or dismiss the alert with the ✕ to keep working on the existing redflow.
Opening it shows the generated redflow side by side with whatever is currently in the editor, with the execution parameters compared underneath — the same comparison view described under Option B.

Accept copies the generated redflow and its execution parameters into your Draft and opens the editor.
Reject discards the generation and leaves your existing redflow untouched.
note
A failed generation does not lock the Playground. You can keep editing, running, and publishing the redflow you already have.

Option B: Select an existing redflow
The list under Select redflow is populated automatically — you don't pick an Agent first. It lists every live redflow in your organization whose Skill is the same kind as the one you're training, labelled Application > Skill:

Training an Aggregation Skill shows Account Aggregation and Entitlement Aggregation redflows
Training any other identity Skill shows the lifecycle operations — Create Account, Activate Account, Deactivate Account, Remove Account, and the Add / Change / Remove Entitlement Skills
So the same Playground offers a different list depending on the Skill you opened. Use Search redflow… to narrow it by application or Skill name.

The Select redflow list narrowed by a search keyword
Searching narrows the list; every entry is labelled Application > Skill

Each entry offers exactly one version: the Live version of that Skill. The Skill's older published versions and its Draft are never listed, so you always start from what that Agent is actually executing today. The dialog names the version you're about to copy — for example Version 3 — which is that Skill's live version, not a version number in your own Skill.

Picking an entry doesn't overwrite anything yet. A Copy to Editor dialog first shows the selected version against your current Draft or Editor, redflow and execution parameters both. Toggle between Split and Unified to change how the comparison is laid out.

The Copy to Editor comparison dialog
Reviewing Version 3 of another Agent's Activate Account redflow before copying it in

Click Copy to Editor and the redflow and its execution parameters land in your Draft, ready to adjust for this application. Anything that was in the Draft is replaced.

Step 2: Versions and drafts
The redflow editor expanded, showing the version dropdown
The redflow editor expanded, showing Version 6 (Live) and the Read-only chip

Every redflow is versioned. The dropdown at the top of the editor lists:

Draft — your working copy, the only editable version
Version 1, Version 2, … — previously published versions
Version N (Live) — the version external systems actually execute
Selecting any published version shows it with a Read-only chip. To make changes, select Draft. Below the editor, a status bar reports the cursor position and the current validation state — 0 errors, 0 warnings when the redflow is clean.

A new Draft is always created from the Live version, along with its execution parameters — never from the older published version you happen to be viewing. So if you open Version 2 while Version 6 is live and then switch to Draft, you get a copy of Version 6, not Version 2. To work from an older version, copy its contents into the Draft yourself. Once a Draft exists, selecting Draft simply reopens it; it isn't reseeded, and it keeps whatever you last saved until you publish it.

While you're in Draft, edits save automatically. The status beside the dropdown reads Saving…, then Autosaved a few seconds ago. Two states need your attention:

Save failed — the last autosave didn't land. Check your connection; your unsaved edits are still in the editor.
Autosave failed: Invalid execution parameters — your execution parameters aren't valid key-value pairs, so the draft can't be saved. Fix them and autosave resumes.
Availability
Depending on how your organization is configured, the redflow editor may sit collapsed in a narrow rail on the left, labelled redflow. Click the chevron to expand it into the full editor shown above, and again to collapse it and give Execution Parameters and Body Cam Footage the full width. The controls are identical either way.

The Playground with the redflow editor collapsed into its left rail

Collapsed: the redflow rail sits on the left, and Execution Parameters and Body Cam Footage take the full width. Click the » chevron to expand it

Step 3: Configure Execution Parameters
Execution parameters are the dynamic inputs your Agent needs at runtime: the user's email, their name, which role to assign. Think of them as what you'd hand a new team member before asking them to perform a task. They live in the Execution Parameters panel beside the editor.

Two types:

Required parameters use $name = "value" syntax. Whatever you enter here is the default used during test runs. At runtime, the calling system (SailPoint, ServiceNow, your custom API client) must supply a value, or the run fails. Example: $email = "jane.doe@example.com".

Optional parameters use $name? = "value" syntax (note the ?). Whatever you enter is the fallback. If the calling system doesn't supply a value at runtime, your Agent uses this default instead of failing. Example: $role? = "Admin".

Which parameters you need depends on the Skill and the application. A "Create Account" Skill usually wants $email, $first_name, $last_name as required, plus something like $role? = "Employee" as an optional fallback. A "Deactivate Account" Skill might only need $email.

Shortcut: look at what the application's form is asking for. Required form fields become required execution parameters. Fields with common defaults become optional execution parameters.

Keep adding required parameters until the validation errors in the editor clear. Three kinds show up:

Reference Error (the most common): a required execution parameter is missing. Add it and the error clears.
Syntax Error: the redflow itself is malformed. Check it against redflow Syntax.
Generic Error: something else in the configuration. Check your execution parameters first.
Step 4: Execute
Playground during a live run
A run in flight: the LIVE banner with an estimated completion time, and Stop Execution

Click Execute. Your Agent opens the target app, logs in, and starts executing the redflow.

While the run is in flight, a LIVE banner reports which version is executing and gives an estimated completion time — for example, "Version 6 execution in progress. Estimated completion by 9:14 AM (PT)."

Runs take 15 to 20 minutes. That's normal, not slow. Your Agent is navigating real web pages, clicking real buttons, and waiting for real responses, exactly as a person would. If you need to step away, your run keeps going in the background.

If you need to stop early, click Stop Execution — it replaces Execute for the duration of the run — then confirm in the Stop Current Execution? dialog. The Agent halts as soon as it can, but actions it already completed in the target application are not rolled back.

note
You can't start a new run while one is already in progress, while a redflow generation is running, or before the Agent Identity has been configured. Until credentials are in place you can still edit and save the redflow — you just can't execute it.

You can execute published versions too, not just the Draft. The redflow stays Read-only, but Execution Parameters remain editable, so you can run the same version against a different user or role. Those edits apply to that run only — they are not written back to the published version, and they don't touch your Draft's saved parameters.

Step 5: Review the results
Run finished. Time to check how your Agent did.

The Body Cam Footage panel sits beside Execution Parameters and plays the recording of the run you just triggered. For everything else — including previous runs — expand the drawer at the bottom of the page. It has two panes:

Executions on the left: every run of this Skill, newest first. Selecting one loads its results, so you can compare iterations and watch the Skill converge.
Execution Results on the right, with tabs for that run:
Tab	What it shows
redflow	The exact redflow that was executed for this run
Output	The records the Agent collected, in JSON or Table view (aggregation Skills)
Body Cam	The step-by-step screen recording of that run
Failure Details	Structured error detail, after a failed run
For every Skill: watch the Bodycam.

Playground after a completed run
A completed run: Execution Parameters and Body Cam Footage side by side

Bodycam is a step-by-step visual recording of everything your Agent did during the run: every page navigated, every field filled, every button clicked. Think of it as watching over your Agent's shoulder. Scrub through looking for three things: did it land on the right pages, did it put the right values in the right fields, and did it reach the confirmation screen at the end?

A run can come back without errors and still do the wrong thing. Bodycam is how you catch that.

For aggregation Skills: check the Output tab.

Playground drawer showing the Output tab
Executions on the left, Execution Results on the right with the Output tab in Table view

For Account Aggregation and Entitlement Aggregation Skills, Bodycam shows the navigation, but the real output is the data. Open the Output tab to see what your Agent actually captured, in either JSON or Table view. The table paginates, so check the total count — "1 – 25 of 45" — as well as the rows on screen. Verify three things: are the right accounts or entitlement values in the list, do the columns look correct, and is the dataset complete, or did your Agent stop before reaching the last page?

When a run fails

Runs fail. That's a normal part of the training process. When it happens, the error alert offers View Forensic Playback, which replays the run so you can see exactly where it went wrong. Failures fall into two categories:

Skill design issue (fix the redflow or execution parameters):

The Agent clicked the wrong button or filled the wrong field
The Agent navigated to the wrong page
A required execution parameter was missing or had the wrong value
Environment issue (transient — retry may fix it):

The page did not load in time
An unexpected popup or MFA prompt appeared
The application was temporarily unavailable
For Skill design issues: select Draft, adjust execution parameters or the redflow, and execute again. For environment issues: re-run without changes and see if it clears. If the same environment issue repeats across runs, check the application's availability and your Agent's credentials.

Most Skills take 2 or 3 iterations to get right. Same as onboarding anyone new.

Step 6: Publish
When the Bodycam shows your Agent completing the task correctly (right pages, right fields, right confirmation screen), and for aggregation Skills when the Output tab shows the data you expected, the Skill is ready.

Click Publish — or Republish, if a live version already exists. That promotes your draft to the live version.

Skills tab showing published Skills
After publishing, the Skill shows Published on the Skills tab, with a Live Since timestamp

After publishing:

Your Skill becomes active and appears under Active Skills on the Agents page, and Published on the Skills tab
External systems (SailPoint, ServiceNow, custom clients) can trigger it via API using an Access Key
If the Skill is attached to a Pipeline, the Pipeline can invoke it on schedule
The header exposes a cURL command helper containing the Agent ID, Skill ID, and parameter names — a ready-made starting point for whoever wires up the integration
tip
Don't rush to publish. AI Studio is built for iterative testing. Execute multiple times, refine execution parameters, adjust the redflow, and review Bodycam and Output until the automation is reliable. A Skill that works 4 out of 5 times is not ready for production.

tip
Checkpoint. Once you've published, go to the Agents page and confirm the new Skill shows up under Active Skills for this Agent. If it doesn't, reopen the Playground and check that the publish completed.

Account Aggregation
Need to export every user account from an application for audit, compliance, or an IGA feed? Account Aggregation is the Skill you want. Unlike other Identity Skills that act on individual users, Account Aggregation exports the full user list. How you configure it depends on what the app lets you do.

Account Aggregation export toggle beside the Execute and Republish buttons
The export availability toggle, on the action row beside Execute and Republish

Aggregation Skills add one required control to the action row, to the left of Execute: User Export Available? (or Entitlement Export Available? on an Entitlement Aggregation Skill). Answer Yes or No before you execute.

Does the application support file export?

Yes: Users can be exported as CSV or Excel from the admin panel. Your Agent triggers the export and downloads the file directly. Faster, more reliable — prefer this path whenever it's an option.
No: App has no export button. Your Agent scrapes user data screen by screen. Your redflow defines which screens to navigate and which attributes to capture.
Is there a direct URL to the user listing page?

Yes: You can bookmark a URL that goes straight to the user management page. A direct URL makes the Agent faster and less prone to navigation errors.
No: The Agent needs to navigate menus to find the user listing. A redflow is required whenever a direct URL is not available or when the Agent needs to scrape data from the screen.
Review the run

Body Cam Footage confirms your Agent landed on the right pages and interacted with the right elements. The Output tab holds the data it actually collected — that's where you confirm the Skill brought back the right records, not just that it visited the right pages.

When the data looks correct, click Publish (or Republish). Your Skill is then ready to be triggered by an attached Pipeline, an API call with an Access Key, or the Execute button on demand.

Agent Settings
Agent Settings tab with all three sections expanded
Agent Settings: Proxy Server, Safe URLs, and Execution Settings

The Agent Settings tab controls how the Agent reaches the target application and what it's allowed to do once there. Changes are staged as you edit and applied when you click Save.

Proxy Server
Routes this Agent's outbound traffic through a proxy profile — useful when the target application allowlists source IPs. Pick a profile from the dropdown.

If no profiles exist yet, the dropdown is empty and a hint links you to Settings → Proxy Profile. See Proxy Profiles for how to create one.

Safe URLs
Agents navigate web pages autonomously. Safe URLs define the boundaries: which URLs the Agent is allowed to visit. If the Agent encounters a URL outside this list, navigation is blocked and the execution fails safely, rather than following the redirect blindly.

This matters in production. Without meaningful Safe URLs, a compromised application page could redirect your Agent to an external site.

Add a URL:

Click + Add URLs
Enter the URL patterns
Click Save
Existing entries can be edited or deleted from the table.

important
At least one Safe URL is required. The Save button stays disabled until the list has an entry.

A wildcard (*) allows the Agent to navigate anywhere. That's fine for initial testing but not for production. For production activations, restrict Safe URLs to only the application pages the Agent needs: the login page, the admin panel, and any specific pages your Skills require.

tip
Look at your Bodycam footage from a successful run. Every URL the Agent visited is a URL that should be on the Safe URLs list. Add those, and nothing else.

Execution Settings
Four toggles control runtime behavior:

Setting	What it does
Allow multiple skills to execute in parallel	The Agent can run several Skills at the same time instead of one after another.
Logout after execution	The Agent logs out of the target application after each execution completes.
Always clear previous cookie before execution	The Agent clears previously stored cookies before starting a new execution.
Allow animations on UI	The Agent lets the target application play its UI animations and transitions.
Leave Logout after execution and Always clear previous cookie on when the target application limits concurrent sessions or reuses session state between logins. Turn Allow animations on UI on only if the application misbehaves with animations suppressed, since animations slow runs down.

