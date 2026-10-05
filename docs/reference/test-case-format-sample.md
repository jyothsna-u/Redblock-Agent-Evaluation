CLK-P1	CLICK / HOVER	Positive	Video	Click a 'New User' button on an admin page.	URL line + one CLICK ON with element description and INTENT.	Extra invented actions.
CLK-N1	CLICK / HOVER	Negative	Video	Menu is visible without hovering; click an item in it.	Plain CLICK ON for the item.	HOVER ON for a menu that is already visible.
CLK-E1	CLICK / HOVER	Edge	Video	Page has two 'Save' buttons (one in a dialog); click the dialog one.	Element description disambiguates, e.g. 'Save button in the dialog'.	Ambiguous 'Save Button' description.
HOV-P1	HOVER	Positive	Video	Hover a user row to reveal edit options, then click 'Edit Permissions'.	HOVER ON row, then CLICK ON the revealed item, in that order.	CLICK before HOVER; HOVER missing.
HOV-N1	HOVER	Negative	Video	Mouse passes over a row by accident while moving to a button.	No HOVER step.	HOVER generated from incidental cursor movement.
HOV-E1	HOVER	Edge	Video	Hover to reveal a tooltip, read it, then continue without clicking it.	HOVER ON element with INTENT.	A CLICK on the tooltip.
VAR-P1	Variables & INTENT	Positive	Video	Fill first name, last name and email in a new-user form.	$first_name, $last_name, $user_email defined at the bottom; each used in its action's INTENT.	Hardcoded typed values inside actions; variable missing from INTENT.
VAR-N1	Variables & INTENT	Negative	Video	Navigate by clicking fixed tabs/buttons (Administration, Save).	Literal element descriptions.	Fixed UI labels turned into variables.
VAR-E1	Variables & INTENT	Edge	Video	Type a password; form field labelled 'User Email ID'.	Sensitive value as a variable; name is snake_case (e.g. $user_email_id).	Hardcoded password; camelCase or spaced names.
FIL-P1	FILL vs FILL_AND_ENTER	Positive	Video	Type an email into a search bar and press Enter.	FILL_AND_ENTER $var INTO search field, variable in INTENT.	Plain FILL (Enter never sent).
FIL-N1	FILL vs FILL_AND_ENTER	Negative	Video	Type a name into a form field, then click Save.	FILL, then CLICK ON Save.	FILL_AND_ENTER when Enter was not pressed.
FIL-E1	FILL vs FILL_AND_ENTER	Edge	Video	Search box filters results while typing; no Enter pressed.	FILL.	FILL_AND_ENTER.
SEL-P1	SELECT	Positive	Video	Choose 'Regional Sales Manager' from a native Role dropdown.	SELECT $role FROM 'Role Dropdown'; $role value equals the on-screen text exactly.	Value that differs from the on-screen option text.
SEL-N1	SELECT	Negative	Video	Type into an autocomplete text box and press Enter (not a dropdown).	FILL_AND_ENTER.	SELECT on a text field.
SEL-E1	SELECT	Edge	Video	Option text with special characters, e.g. 'Sales (EMEA) - Senior'.	Variable value matches text exactly, punctuation and case included.	Normalised or shortened option text.
IF-P1	IF / ELSE	Positive	PDF	PDF: 'If department is Sales, assign the Sales role; otherwise assign the platform licence.'	IF $department EQUALS 'Sales' with ELSE; bodies indented exactly 4 spaces; $department defined.	Both branches executed in sequence with no IF.
IF-N1	IF / ELSE	Negative	Video	Single fixed path; nothing on screen or in narration suggests alternatives.	Linear steps.	Any IF/ELSE.
IF-E1	IF / ELSE	Edge	PDF	PDF with a 'not equal' rule inside a per-role loop.	IF inside FOR_EACH using NOT_EQUALS or !=; 4-space indent per level.	Wrong operator; broken indentation.
EXS-P1	EXISTS (scalar)	Positive	PDF	PDF: 'If a manager is provided, transfer the data to them.'	IF $transfer_data_to EXISTS; variable defined as $transfer_data_to? = ...	Variable defined without '?'.
EXS-N1	EXISTS (scalar)	Negative	Video	Email field that is always filled.	Required variable, no EXISTS.	Optional '?' or EXISTS on a required field.
EXS-E1	EXISTS (scalar)	Edge	PDF	PDF: 'If recipient given transfer, otherwise delete the data.'	IF ... EXISTS with ELSE branch.	ELSE missing; EXISTS on a list variable.
LST-P1	EMPTY / NOT_EMPTY (list)	Positive	PDF	PDF: 'If roles are given assign each; otherwise click Skip.'	IF $roles NOT_EMPTY ... and IF $roles EMPTY ... branches.	EXISTS used on $roles.
LST-N1	EMPTY / NOT_EMPTY (list)	Negative	Video	Single-value field used for a list-like label.	Scalar variable, no NOT_EMPTY/EMPTY.	List operators on a scalar.
LST-E1	EMPTY / NOT_EMPTY (list)	Edge	PDF	Optional list driving a loop.	FOR_EACH guarded by IF $roles NOT_EMPTY.	Unguarded FOR_EACH over an optional list.
LOOP-P1	FOR_EACH	Positive	Video	Tick three role checkboxes one after another.	One FOR_EACH $role IN $roles with a single body step; $roles = [..] list.	Three separate CLICK steps.
LOOP-N1	FOR_EACH	Negative	Video	Tick exactly one checkbox.	Single CLICK.	FOR_EACH for a single item.
LOOP-E1	FOR_EACH	Edge	Video	For each role: click checkbox, then confirm in a popup.	FOR_EACH with two body steps at 4-space indent; $role in INTENT of each.	Second step outside loop.
WHEN-P1	WHEN (runtime if)	Positive	Video	Cookie banner appears; user clicks 'Accept all'.	WHEN 'a cookie consent banner is visible' with CLICK body.	Unconditional CLICK on the banner.
WHEN-N1	WHEN (runtime if)	Negative	Video	A confirmation dialog appears on every save.	Plain CLICK on confirm.	WHEN for an always-present dialog.
WHEN-E1	WHEN (runtime if)	Edge	Video	User already exists -> open it; otherwise invite (shown in two recordings).	WHEN with ELSE; $email used inside the condition text.	Missing ELSE; ELIF used.
UNT-P1	UNTIL (runtime loop)	Positive	Video	Click Refresh several times until an export finishes.	UNTIL 'Refresh icon is still visible ...' with CLICK Refresh body.	Several fixed CLICK steps.
UNT-N1	UNTIL (runtime loop)	Negative	Video	Click Refresh once and the result appears.	Single CLICK.	UNTIL for a one-off click.
UNT-E1	UNTIL (runtime loop)	Edge	Video	Click 'Load more' until no more rows appear.	UNTIL with condition on the button still being visible.	Body missing; condition phrased as a variable comparison.
WAIT-P1	WAIT_UNTIL	Positive	Video	Click Generate Report, spinner shows, then status says Completed, then Download.	CLICK, WAIT_UNTIL 'status shows Completed', CLICK Download.	Indented body under WAIT_UNTIL.
WAIT-N1	WAIT_UNTIL	Negative	Video	Page changes instantly after a click.	No wait.	Unneeded WAIT_UNTIL.
WAIT-E1	WAIT_UNTIL	Edge	Video	Two async stages in one flow (upload, then processing).	Two WAIT_UNTIL lines, each a single line with its own condition.	Merged into one wait; nested body.
PRE-P1	Top-level STEPS (pre-extraction)	Positive	Video	Click Search to load a groups table, then read it.	STEPS before RESOURCE containing the Search click.	Click placed inside FROM LIST.
PRE-N1	Top-level STEPS (pre-extraction)	Negative	Video	Table loads automatically; user only scrolls.	No STEPS block.	Invented pre-steps.
PRE-E1	Top-level STEPS (pre-extraction)	Edge	Video	Apply a role filter (open dropdown, pick value) before reading the list.	Two-step STEPS block before RESOURCE.	Filter steps after the EXTRACT.
RES-P1	RESOURCE / FROM LIST	Positive	Video	Scroll a users table (email, first name, last name, role, status).	RESOURCE: 'Users' IDENTIFIED_BY 'email'; FROM LIST with one INSTRUCT per field.	Missing IDENTIFIED_BY; field without INSTRUCT.
RES-N1	RESOURCE / FROM LIST	Negative	Video	Page shows one user profile, no table.	FROM DETAILS only, no FROM LIST.	FROM LIST on a single-record page.
RES-E1	RESOURCE / FROM LIST	Edge	Video	Table where no single column is obviously unique (name + team).	Sensible IDENTIFIED_BY chosen from visible fields.	IDENTIFIED_BY field not extracted.
POSV-P1	POSSIBLE_VALUES	Positive	Video	Status badge column showing Active / Inactive / Pending.	POSSIBLE_VALUES ["Active","Inactive","Pending"] on that field.	Missing on a fixed-option column.
POSV-N1	POSSIBLE_VALUES	Negative	Video	Free-text columns (Name, Email, Description).	No POSSIBLE_VALUES.	POSSIBLE_VALUES on free text.
POSV-E1	POSSIBLE_VALUES	Edge	Video	Only 2 of 4 possible statuses appear in visible rows.	Only values actually seen/known; none invented.	Made-up values.
ARR-P1	Array fields [ ]	Positive	Video	Tags column with several tags per row.	"tags"[] INSTRUCT ...	Plain "tags" field.
ARR-N1	Array fields [ ]	Negative	Video	Single-value Team column.	Plain field, no [].	[] on a single-value field.
ARR-E1	Array fields [ ]	Edge	Video	Detail page section listing several team memberships (not a table).	"team_memberships"[] in FROM DETAILS.	Treated as a nested FROM LIST.
DET-P1	FROM DETAILS + per-item STEPS	Positive	Video	Open each user row and read labeled Role and Team fields.	Per-item STEPS inside FROM LIST; EXTRACT FROM DETAILS with only new fields.	STEPS at top level.
DET-N1	FROM DETAILS + per-item STEPS	Negative	Video	List-only extraction, no row is opened.	No per-item STEPS, no FROM DETAILS.	Invented detail navigation.
DET-E1	FROM DETAILS + per-item STEPS	Edge	Video	Detail page shows the same fields already in the list.	FROM DETAILS omitted (or only new fields kept).	Duplicate fields re-listed.
NEST-P1	Nested RESOURCE	Positive	Video	Open a group and read its members sub-table.	Nested RESOURCE 'group_members' (short form) directly above FROM LIST.	IDENTIFIED_BY on the nested resource; FROM LIST with no RESOURCE.
NEST-N1	Nested RESOURCE	Negative	Video	Detail page has labeled fields only.	FROM DETAILS, no nested RESOURCE.	Nested RESOURCE without a table.
NEST-E1	Nested RESOURCE	Edge	Video	Group -> member -> that member's permissions table (two nesting levels).	RESOURCE above every nested FROM LIST at each depth.	Missing RESOURCE at depth 2.
TAB-P1	Multi-tab detail pages	Positive	Video	User detail with Destinations and Connections tabs.	STEPS / RESOURCE / EXTRACT blocks are siblings at the same indent.	Second tab nested inside first EXTRACT.
TAB-N1	Multi-tab detail pages	Negative	Video	Detail page opens directly on the needed tab (URL ends #/skills).	No click step for that tab.	Redundant tab click.
TAB-E1	Multi-tab detail pages	Edge	Video	Three tabs visited in a different order than shown on screen.	Blocks follow recorded order; all siblings.	Reordered to UI order.
JOIN-P1	Cross-URL JOIN	Positive	Video	Read employees in payroll app, then device list in an IT-assets app.	GOTO inside STEPS, then RESOURCE 'Assets' JOIN ON 'employee_id'.	GOTO outside STEPS; JOIN key not extracted earlier.
JOIN-N1	Cross-URL JOIN	Negative	Video	Extraction from one app only.	No GOTO / JOIN.	Invented second URL.
JOIN-E1	Cross-URL JOIN	Edge	Video	Second list has the join key in a column with a different header.	Join field INSTRUCT points to the correct column header.	Wrong column mapped.
E2E-P1	End-to-end (mixed)	Positive	Video	Joiner: create a Salesforce-style user with department-dependent role and licence.	Variables + IF/ELSE + SELECT + FILL, valid syntax throughout.	Dropped steps; wrong branch structure.
E2E-P2	End-to-end (mixed)	Positive	PDF	Leaver procedure PDF: suspend user, optional data transfer, else delete data.	FILL_AND_ENTER search, IF EXISTS/ELSE, optional variable.	Transfer step unconditional.
E2E-P3	End-to-end (mixed)	Positive	Video	Async export: confirm dialog (sometimes), refresh loop, wait for ready, download.	WHEN, UNTIL and WAIT_UNTIL in the right order.	Hardcoded waits; dialog unconditional.
E2E-P4	End-to-end (mixed)	Positive	Video	Users extraction with detail fields plus two tabs.	RESOURCE + FROM LIST + per-item STEPS + FROM DETAILS + sibling tab blocks.	Nested tab blocks; duplicate fields.