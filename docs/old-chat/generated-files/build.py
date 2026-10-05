import re
from collections import OrderedDict, defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.utils import get_column_letter

import tc_common, tc_setup, tc_generation, tc_execution  # noqa: F401 (register cases)
from tc_common import CASES, PREFIX

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F2937")
HDR_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
INPUT_FILL = PatternFill("solid", fgColor="FFF9DB")
BAND = PatternFill("solid", fgColor="F3F4F6")
thin = Side(style="thin", color="D1D5DB")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="top", wrap_text=True)

# ---------------------------------------------------------------- assign IDs
counters = defaultdict(int)
for c in CASES:
    p = PREFIX[c["module"]]
    counters[p] += 1
    c["id"] = f"{p}-{counters[p]:03d}"

# module order as first seen, grouped by phase
PHASE = OrderedDict([
    ("1. Setup", ["Agents List", "Agent Profile", "Agent Identity", "Skills Tab", "Agent Settings", "Certified Agents"]),
    ("2. redflow creation", ["Asset Upload", "Generation Lifecycle", "Generation Quality - Actions",
                             "Generation Quality - Docs & Instructions", "Generation Quality - Aggregation",
                             "Select Existing redflow", "Editor & Syntax", "Versions & Drafts"]),
    ("3. Execution", ["Execution Parameters", "Execution Control", "Agent Runtime - Element Targeting",
                      "Agent Runtime - Page & App Conditions", "Agent Runtime - Data & Outcome",
                      "Aggregation Execution & Output", "Results Review"]),
    ("4. Go-live", ["Publish", "API Trigger", "Security", "Performance & Reliability"]),
])
order = [m for ms in PHASE.values() for m in ms]
assert set(order) == set(c["module"] for c in CASES)
phase_of = {m: ph for ph, ms in PHASE.items() for m in ms}
CASES.sort(key=lambda c: (order.index(c["module"]), c["id"]))

# ---------------------------------------------------------------- test assets
ASSETS = [
    ("VID-01", "Video", "Clean Create Account recording, login to confirmation screen, one take, no noise", "Baseline for completeness, variables and end-to-end success"),
    ("VID-02", "Video", "Same flow but recording starts after login (on the admin page)", "Recording without login"),
    ("VID-03", "Video", "Same flow with a jump-cut: 2 steps edited out of the middle", "Missing steps in video"),
    ("VID-04", "Video", "Recorder clicks the wrong menu item, goes back, then continues correctly", "Mistakes / undo noise"),
    ("VID-05", "Video", "Recorder switches browser tab mid-flow; an OS notification pops up", "Noise from other tabs/apps"),
    ("VID-06", "Video", "Very fast execution: several clicks per second", "Dropped or merged steps"),
    ("VID-07", "Video", "Very slow: long idle pauses, slow typing, cursor wandering", "Idle time and spurious hovers"),
    ("VID-08", "Video", "Page with two Save buttons (e.g., Profile section Save and Roles section Save); recorder uses the Roles one", "Ambiguous buttons"),
    ("VID-09", "Video", "Flow that uses icon-only tiny buttons (pencil, trash, kebab, gear)", "Small icon targeting"),
    ("VID-10", "Video", "Dense admin page: big user table, many fields, per-row Edit buttons, nav link and tab with same text", "Dense pages and repeated labels"),
    ("VID-11", "Video", "Long form where Save is below the fold (scrolling needed)", "Scrolling"),
    ("VID-12", "Video", "Row actions only visible on hover", "HOVER generation"),
    ("VID-13", "Video", "Form with native dropdown, custom dropdown, typeahead, date picker, checkbox, radio, toggle", "Control types"),
    ("VID-14", "Video", "Action that opens a confirmation modal", "Modal dialogs"),
    ("VID-15", "Video", "Flow where an optional popup (tour / what's new) appears", "WHEN generation"),
    ("VID-16", "Video", "Link opens a new tab and flow continues there", "Multi-tab support"),
    ("VID-17", "Video", "Form embedded in an iframe", "iframe support"),
    ("VID-18", "Video", "Multi-page wizard (Next, Next, Finish) with card-style large buttons", "Wizards and large targets"),
    ("VID-19", "Video", "Create a user AND then deactivate another user in one recording", "Two operations in one video"),
    ("VID-20", "Video", "Remove Account recording (used on a Create Account Skill)", "Intent mismatch"),
    ("VID-21", "Video", "VID-01 re-encoded at 480p / blurry", "Low quality input"),
    ("VID-22", "Video", "VID-01 recorded at 150% zoom or portrait window", "Resolution / zoom"),
    ("VID-23", "Video", "VID-01 recorded in dark mode and with non-English UI", "Theme / language"),
    ("VID-24", "Video", "Flow where an initial password is typed for the new user", "Secrets in recordings"),
    ("VID-25", "Video", "Search returns several similar users; recorder picks the exact one", "Search + exact match"),
    ("VID-26", "Video", "Export or report job that needs waiting/refreshing before download", "WAIT_UNTIL / UNTIL generation"),
    ("VID-27", "Video", "Aggregation: paginated user table (e.g., 95 users, 10 per page), no export button", "Extraction script generation"),
    ("VID-28", "Video", "Aggregation: open each user's detail page, which has 2-3 tabs with sub-tables", "Detail drill-down, nested RESOURCE, tabs"),
    ("VID-29", "Video", "Aggregation: admin exports users as CSV/Excel", "File-export flow"),
    ("VID-30", "Video", "Black / static screen with no actions; also a corrupt/truncated MP4", "Failure handling"),
    ("VID-31", "Video", "Long recording compressed to just under 10 MB", "Size limit / tail steps"),
    ("VID-32", "Video", "Recording with voice narration explaining the steps", "Audio handling (record behaviour)"),
    ("VID-33", "Video", "Recorder triggers a form validation error, then fixes it", "Error-and-fix noise"),
    ("VID-34", "Video", "Recorder assigns 3 roles from a multi-select list", "List variable + FOR_EACH"),
    ("VID-35", "Video", "VID-01 recorded with cursor hidden", "Cursor-less inference"),
    ("VID-36", "Video", "Recording that contains real-looking PII (phone, address)", "PII handling"),
    ("SS-01", "Screenshots", "One screenshot per step of VID-01, named in order", "Screenshot generation"),
    ("SS-02", "Screenshots", "SS-01 with shuffled / random file names", "Ordering"),
    ("SS-03", "Screenshots", "SS-01 with one middle screenshot removed", "Missing screen"),
    ("DOC-01", "PDF", "SOP for the VID-01 flow with embedded screenshots", "Doc-based generation"),
    ("DOC-02", "TXT / MD / PDF", "Text-only SOP (no images)", "Visual-asset gating"),
    ("DOC-03", "PDF", "SOP that contradicts VID-01 (different field order / extra step)", "Conflict handling"),
    ("DOC-04", "DOCX", "Word SOP with embedded images", "DOCX support"),
]

used_by = defaultdict(list)
for c in CASES:
    for aid in set(re.findall(r"\b(?:VID|SS|DOC)-\d\d\b", f"{c['data']} {c['steps']} {c['pre']}")):
        used_by[aid].append(c["id"])

# ---------------------------------------------------------------- open questions
QUESTIONS = [
    ("Docs", "Optional variables: syntax page says `$var? = EMPTY`, but the Agents page and Example 6.3 give optional variables real defaults (`$role? = \"Admin\"`).", "Which is the canonical form? Are both valid?", "PAR-003, EDT"),
    ("Docs", "Example 6.2 uses `IF $new_role EXISTS` but `$new_role` is declared as required.", "Should EXISTS on a required variable be flagged?", "EDT"),
    ("Docs", "Extraction Example 7.11.3 uses `Group_name` / `Members`, breaking the snake_case rule.", "Fix the example or relax the rule?", "EDT"),
    ("Docs", "Example 7.11.2 contains `synqa.rjf.com:8888`, which looks like a real internal host.", "Replace with a placeholder.", "-"),
    ("Docs", "Syntax page says variables live at the bottom of the script; the Playground has a separate Execution Parameters panel.", "Add a note explaining the difference.", "-"),
    ("Docs", "`Update Account` is in the Add Skill menu but not in the Account Skills table.", "Document Update Account.", "SKL-001"),
    ("Docs", "`UNTIL` loops while the condition is true, the opposite of what the word suggests.", "Rename, or make the docs very explicit.", "RTP"),
    ("Product", "Is a successful run required before Publish?", "Decide: block, warn, or allow.", "PUB-004"),
    ("Product", "When a description matches two elements (two 'Save' buttons), does the Agent guess or stop?", "Define expected behaviour.", "RTE-002"),
    ("Product", "Does the Agent check state before toggling (already-on toggle / already-checked box)?", "Define expected behaviour.", "RTE-014, RTE-015"),
    ("Product", "Does the generator flag gaps / low confidence when steps are missing from a video?", "Define expected behaviour.", "GQA-005"),
    ("Product", "Are login steps in a recording stripped from STEPS (since Agent Identity handles login)?", "Confirm.", "GQA-004"),
    ("Product", "Is 10 MB = 10,000,000 or 10,485,760 bytes?", "Confirm for boundary tests.", "UPL-013"),
    ("Product", "Is Agent Name uniqueness case-insensitive and whitespace-trimmed?", "Confirm.", "AGP-006"),
    ("Product", "Is Additional Information used during login (tenant field) or only by redflows?", "Confirm.", "AGI-012"),
    ("Product", "Safe URL pattern syntax (wildcards, subdomains, paths) isn't documented.", "Document matching rules.", "SET-006"),
    ("Product", "What does the red '!' icon on a Skill row mean?", "Confirm and document.", "SKL-007"),
    ("Product", "How do two users editing the same Draft interact?", "Define conflict handling.", "VER-010"),
    ("Product", "Does changing Agent Identity on a Certified Agent remove certification?", "Confirm.", "CRT-004"),
    ("Product", "ITSM name mismatch fails silently. Is anything logged?", "Consider a visible warning.", "AGP-015"),
]

wb = Workbook()

def header(ws, row, cols, widths):
    for i, (name, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(row=row, column=i, value=name)
        cell.font, cell.fill, cell.alignment, cell.border = HDR_FONT, HDR_FILL, Alignment(wrap_text=True, vertical="center"), BORDER
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30

# ================================================================ Test Cases
tc = wb.active
tc.title = "Test Cases"
COLS = ["TC ID", "Phase", "Module", "Sub-area", "Test Scenario", "Preconditions", "Test Steps", "Test Data / Asset",
        "Expected Result", "Priority", "Type", "Status", "Actual Result", "Bug ID", "Tester", "Date Run", "Notes"]
WIDTHS = [10, 14, 22, 14, 38, 28, 42, 30, 48, 8, 12, 11, 30, 10, 12, 11, 30]
header(tc, 1, COLS, WIDTHS)
for r, c in enumerate(CASES, 2):
    vals = [c["id"], phase_of[c["module"]], c["module"], c["sub"], c["title"], c["pre"], c["steps"], c["data"],
            c["expected"], c["pri"], c["typ"], "Not Run", "", "", "", "", c["notes"]]
    for col, v in enumerate(vals, 1):
        cell = tc.cell(row=r, column=col, value=v)
        cell.font, cell.alignment, cell.border = BODY, WRAP, BORDER
        if col in (1, 10, 12):
            cell.alignment = CENTER
        if 12 <= col <= 16:
            cell.fill = INPUT_FILL
    tc.cell(row=r, column=1).font = BOLD
last = len(CASES) + 1
tc.freeze_panes = "F2"
tc.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}{last}"

dv = DataValidation(type="list", formula1='"Not Run,Pass,Fail,Blocked,N/A"', allow_blank=True)
dv.add(f"L2:L{last}")
tc.add_data_validation(dv)
dvp = DataValidation(type="list", formula1='"P0,P1,P2,P3"', allow_blank=False)
dvp.add(f"J2:J{last}")
tc.add_data_validation(dvp)
rng = f"L2:L{last}"
for val, color in [("Pass", "C6EFCE"), ("Fail", "FFC7CE"), ("Blocked", "FFEB9C"), ("N/A", "E5E7EB")]:
    tc.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{val}"'], fill=PatternFill("solid", fgColor=color)))
prng = f"J2:J{last}"
tc.conditional_formatting.add(prng, CellIsRule(operator="equal", formula=['"P0"'], font=Font(name=FONT, bold=True, color="B91C1C")))

# ================================================================ Summary
sm = wb.create_sheet("Summary", 0)
sm["A1"] = "Redblock AI Studio - Test Suite Summary"
sm["A1"].font = Font(name=FONT, size=14, bold=True)
sm["A2"] = "Counts update automatically as Status is filled in on the Test Cases sheet."
sm["A2"].font = Font(name=FONT, size=10, italic=True, color="6B7280")
SCOLS = ["Phase", "Module", "Total", "P0", "P1", "P2", "P3", "Pass", "Fail", "Blocked", "Not Run", "N/A", "Executed %", "Pass % of executed"]
header(sm, 4, SCOLS, [18, 38, 8, 7, 7, 7, 7, 8, 8, 9, 9, 7, 11, 12])
TCR = f"'Test Cases'!$C$2:$C${last}"
PR_ = f"'Test Cases'!$J$2:$J${last}"
ST = f"'Test Cases'!$L$2:$L${last}"
r = 5
first_data = r
for ph, mods in PHASE.items():
    for m in mods:
        row = [ph, m]
        sm.cell(row=r, column=1, value=ph)
        sm.cell(row=r, column=2, value=m)
        sm.cell(row=r, column=3, value=f"=COUNTIF({TCR},B{r})")
        for i, p in enumerate(["P0", "P1", "P2", "P3"]):
            sm.cell(row=r, column=4 + i, value=f'=COUNTIFS({TCR},B{r},{PR_},"{p}")')
        for i, s in enumerate(["Pass", "Fail", "Blocked", "Not Run", "N/A"]):
            sm.cell(row=r, column=8 + i, value=f'=COUNTIFS({TCR},B{r},{ST},"{s}")')
        sm.cell(row=r, column=13, value=f"=IF(C{r}-L{r}=0,0,(H{r}+I{r}+J{r})/(C{r}-L{r}))")
        sm.cell(row=r, column=14, value=f"=IF(H{r}+I{r}=0,0,H{r}/(H{r}+I{r}))")
        for col in range(1, 15):
            cell = sm.cell(row=r, column=col)
            cell.font, cell.border = BODY, BORDER
            if (r - first_data) % 2:
                cell.fill = BAND
        sm.cell(row=r, column=13).number_format = "0%"
        sm.cell(row=r, column=14).number_format = "0%"
        r += 1
last_data = r - 1
sm.cell(row=r, column=1, value="TOTAL")
for col in range(3, 13):
    L = get_column_letter(col)
    sm.cell(row=r, column=col, value=f"=SUM({L}{first_data}:{L}{last_data})")
sm.cell(row=r, column=13, value=f"=IF(C{r}-L{r}=0,0,(H{r}+I{r}+J{r})/(C{r}-L{r}))")
sm.cell(row=r, column=14, value=f"=IF(H{r}+I{r}=0,0,H{r}/(H{r}+I{r}))")
for col in range(1, 15):
    cell = sm.cell(row=r, column=col)
    cell.font, cell.border = BOLD, BORDER
    cell.fill = PatternFill("solid", fgColor="E5E7EB")
sm.cell(row=r, column=13).number_format = "0%"
sm.cell(row=r, column=14).number_format = "0%"
total_row = r
sm.freeze_panes = "C5"

# ================================================================ How to Use
hu = wb.create_sheet("How to Use", 0)
hu.column_dimensions["A"].width = 22
hu.column_dimensions["B"].width = 100
rows = [
    ("Redblock AI Studio - End-to-end Test Suite", None),
    (None, None),
    ("Scope", "Full product path: Agent setup -> asset upload -> video/doc-to-redflow generation -> editor & syntax -> execution by the Agent -> results review -> publish -> API trigger, plus security and performance."),
    ("Sources", "Redblock docs (Agents, redflow Syntax Reference, Guide v3.0, May 2026) and console.dev screenshots from 30 Sep 2026."),
    ("Sheets", "Summary: live counts per module. Test Cases: all cases. Test Assets: recordings/docs to prepare once and reuse. Open Questions: behaviour the docs don't define, and doc inconsistencies."),
    (None, None),
    ("Fill in (yellow cells)", "On Test Cases, fill Status (dropdown), Actual Result, Bug ID, Tester and Date Run. Everything else is the test definition."),
    ("Example row", "Status: Fail | Actual Result: 'Agent clicked Profile Save instead of Roles Save; roles not saved' | Bug ID: RB-1432 | Tester: Heet | Date Run: 01-Oct-2026"),
    ("Status values", "Not Run (default), Pass, Fail, Blocked (can't run: env/data/feature missing), N/A (not applicable to this build)."),
    ("Priority", "P0 = must pass before any customer POC. P1 = core functionality. P2 = important edge cases. P3 = nice to have / cosmetic."),
    ("Type", "Functional, Negative, Boundary, Edge, AI Quality (generation/agent accuracy), Robustness, Security, Performance, Integration."),
    ("'Record' in Expected", "Where the docs don't define behaviour, the Expected Result says 'Record ...'. Note what actually happens and raise it in Open Questions if it looks wrong."),
    (None, None),
    ("AI Quality metrics", "For every video-based case, log: steps in video, steps generated, steps missed, extra steps, and whether the redflow ran first time without edits. These give generation precision/recall and first-run success rate."),
    ("Test Assets", "Record the assets on the Test Assets sheet once, against a stable test app (your SailPoint ISC demo tenant works). Keep a written step list for each so generated redflows can be compared step by step."),
    ("Destructive tests", "Run Remove/Deactivate tests only against test users in a sandbox tenant. Stop Execution does not roll back completed actions."),
]
for i, (a, b) in enumerate(rows, 1):
    if a: hu.cell(row=i, column=1, value=a).font = BOLD if i > 1 else Font(name=FONT, size=14, bold=True)
    if b:
        c = hu.cell(row=i, column=2, value=b)
        c.font, c.alignment = BODY, WRAP
hu["A7"].fill = INPUT_FILL
wb.move_sheet("Summary", -wb.index(wb["Summary"]) + 1)

# ================================================================ Test Assets
ta = wb.create_sheet("Test Assets")
header(ta, 1, ["Asset ID", "Type", "What to record / prepare", "What it tests", "Used by test cases", "Ready? (Y/N)", "File location"],
       [10, 14, 60, 34, 40, 11, 30])
for r, (aid, typ, desc, tests) in enumerate(ASSETS, 2):
    vals = [aid, typ, desc, tests, ", ".join(sorted(used_by.get(aid, []))) or "-", "", ""]
    for col, v in enumerate(vals, 1):
        cell = ta.cell(row=r, column=col, value=v)
        cell.font, cell.alignment, cell.border = BODY, WRAP, BORDER
        if col in (6, 7):
            cell.fill = INPUT_FILL
    ta.cell(row=r, column=1).font = BOLD
ta.freeze_panes = "B2"
dvy = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
dvy.add(f"F2:F{len(ASSETS)+1}")
ta.add_data_validation(dvy)

# ================================================================ Open Questions
oq = wb.create_sheet("Open Questions")
header(oq, 1, ["#", "Area", "Observation", "Question / Recommendation", "Related TCs", "Answer / Owner"], [5, 10, 60, 40, 18, 35])
for r, (area, obs, q, rel) in enumerate(QUESTIONS, 2):
    for col, v in enumerate([r - 1, area, obs, q, rel, ""], 1):
        cell = oq.cell(row=r, column=col, value=v)
        cell.font, cell.alignment, cell.border = BODY, WRAP, BORDER
        if col == 6:
            cell.fill = INPUT_FILL
oq.freeze_panes = "C2"

wb.save("Redblock_AI_Studio_Test_Suite.xlsx")
print("cases", len(CASES), "total_row", total_row, "assets", len(ASSETS))
print("assets unused:", [a[0] for a in ASSETS if not used_by.get(a[0])])
print("refs not in library:", set(used_by) - {a[0] for a in ASSETS})
