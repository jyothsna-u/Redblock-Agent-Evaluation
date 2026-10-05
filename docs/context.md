# Project context: Redblock AI Eval / Benchmark System

Handoff from the claude.ai chat "Redblock documentation" (2026-09-30 → 2026-10-01) plus the related
"LangSmith vs Langfuse" chat (2026-09-28 → 2026-10-01). Raw sources are in `docs/old-chat/`.

## 1. Company and product

**Redblock** (redblock.ai) builds AI "Execution Agents" for identity/access work on *disconnected apps*,
i.e. apps with no API/connector. If a human can do it through a screen, the agent does it through the UI
using computer vision + LLMs.

- Positioning: SailPoint (or Saviynt, Okta, Entra, ServiceNow…) is the governance/orchestration system of
  record; Redblock is the execution + evidence engine. Upstream triggers Redblock via REST API.
- Use cases: JML (Joiner/Mover/Leaver) provisioning — create account, add/remove entitlement, update,
  disable/remove — plus account aggregation and entitlement aggregation (data extraction), credential
  rotation, SAML cert rotation, API key refresh.
- Agents are deployed **on customer premises**. A client can have 30+ apps; each app has schedulers
  running 8–10 operations daily. Largest account aggregation seen: ~130,000 accounts, 60–70 min.
- Docs: https://console.dev.redblock.ai/docs (copies in `docs/reference/`).

### User flow in AI Studio
1. **Agent Profile** – name + purpose.
2. **Agent Identity** – login URL, username, password. The agent logs into the target app itself.
3. **Skills/Operations** – add JML and aggregation operations one by one.
4. **redflow per operation**, built one of three ways:
   - **Video / PDF → DSL** (AI generation: analyses the recording/SOP, works out pages, buttons,
     clicks/hovers/fills, writes a redflow) ← **main eval target**
   - Reuse a pre-existing redflow
   - Write it manually
5. **Refine & Test** – edit redflow, run against the real app (agent uses CV to find elements from
   plain-English descriptions). Evidence via "Bodycam".
6. **Run from upstream** – SailPoint/API triggers the operation; agent repeats the steps.

The user (Heet) is on the implementation side: sets up customer apps as Agents for POCs, trains Skills,
and now owns building the **AI eval / benchmarking system**.

## 2. redflow (the DSL)

Full reference: `docs/reference/redflow-syntax-reference.md`. Summary:

```
URL "https://app/path"          # target; supplied by the user every run → NOT scored
STEPS
    - CLICK ON "Element description" INTENT "..."
    - FILL $var INTO "Element" INTENT "... $var ..."
    - IF $role EQUALS "Custom"
        - CLICK ON "Next Button" INTENT "..."
$var = "default value"
```

- Actions: `CLICK`, `FILL`, `FILL_AND_ENTER`, `SELECT`, `HOVER` (+ `GOTO` inside STEPS for extraction).
- Static control flow: `IF / ELSE` (`EQUALS`/`==`, `NOT_EQUALS`/`!=`, `EXISTS` for scalars,
  `EMPTY`/`NOT_EMPTY` for lists), `FOR_EACH $x IN $list`.
- Runtime AI control flow: `WHEN "<page state>"` (+ELSE), `UNTIL "<page state>"` (loop with body),
  `WAIT_UNTIL "<page state>"` (no body).
- Variables: snake_case, defined at bottom; list `["a","b"]`; optional `$x? = EMPTY`.
- Rules: 4-space indentation; any variable used in an action must appear in its INTENT.
- Extraction scripts: `RESOURCE: "X" IDENTIFIED_BY "field"`, `EXTRACT` → `FROM LIST` / `FROM DETAILS`,
  `- "field" INSTRUCT "..." [POSSIBLE_VALUES [...]]`, array fields `"tags"[]`, nested RESOURCE, per-item
  STEPS, multi-tab siblings, cross-URL `JOIN ON`.

## 3. What has been done so far

1. **Test cases (functional)** – `docs/reference/Redblock_AI_Studio_Test_Suite.xlsx`: 445 cases across
   Agent setup, video→redflow generation, execution, publish, API. Generator scripts in
   `docs/old-chat/generated-files/tc_*.py`, `build.py`.
2. **AI-side test cases** – `docs/reference/Redblock_redflow_AI_Test_Cases.xlsx`: 160 cases (Heet's 64 +
   96 new) for the generation side only, in format
   `ID | Area | Type (Positive/Negative/Edge) | Input (Video/PDF) | Scenario | Expected redflow | Failure to catch`.
   Heet's original sample: `docs/reference/test-case-format-sample.md`. Generator: `ai_cases_new.py`,
   `build_ai.py`. Also `Redblock_Test_Plan_Restructured.xlsx`.
   Scope note from Heet: test cases should focus on the **AI side**, not every UI page.
3. **Broad eval architecture** was proposed (offline benchmark vs online monitoring; layers
   L1 Generation … L8 Reliability; Gym apps; frozen replays; code graders → LLM judge → human eval;
   failure categories; regression detection with bootstrap/McNemar; CI gates; phased roadmap).
   See transcript, assistant message at 2026-10-01T04:54. Heet then narrowed scope ↓
4. **Decided focus: Video/PDF → DSL generation quality** — "is our agent capturing all the
   steps/clicks/navigations". This produced **RedScore** (section 4).
5. **Tracing**: Redblock currently uses **paid LangSmith**; traces also show a `langfuse_session_id`.
   A proposal exists to add **self-hosted Langfuse on client premises** (decided: Tier 2 = Kubernetes +
   Helm). See `docs/reference/langfuse-onprem-proposal.md`. Trace node names seen: orchestrator,
   `authenticator`, `generate_actions`, `execute_action`, `any_data_aggregator`,
   `navigate_to_listing_page`, `wait_for_target_content`, `redblock-visual-reasoning`,
   `relaxed_muscle_memory`; project `firefly-prod`; traces carry `revision_id` (git SHA).

## 4. RedScore — the agreed algorithm (FINAL, source of truth)

Full spec with worked example: **`docs/redscore-spec.md`**. Compares a generated redflow (GEN) to the
ground-truth redflow (GT). Flow designed by Heet (2026-10-01T10:41):

1. **Syntax validation** – run the redflow validator on GEN. Any error → Final Score 0 for that run.
2. **Map steps and variables** – one LLM call (pinned model, temperature 0) gets both redflows with
   numbered steps, returns: pairs (same action on same element, each step used ≤1×), per pair
   `same_element` / `same_intent` (yes/no), missing GT steps, extra GEN steps. Then code checks:
   - Variables: pair GEN↔GT variables by identical default value; unpaired GT var = missing variable
     (includes hard-coded values).
   - Sequence: walk pairs in GT order; GEN index must keep rising; a drop = out of sequence.
   - Logic blocks: every IF/ELSE, FOR_EACH, WHEN, UNTIL, WAIT_UNTIL in GT must exist in GEN with the same
     condition and contain its steps.
   - Save the mapping for human review.
3. **Score each mapped step (max 1.0)**: keyword same 0.3 (code) · element same 0.4 (LLM) ·
   variables same after mapping, nothing hard-coded 0.2 (code) · intent same 0.1 (LLM). Missing GT step = 0.
4. **Base Score** = Σ step points / (N_GT + N_extra) × 100.
5. **Penalties**: out of sequence −5/step · missing variable −5/var · logic block mismatch −10/block ·
   critical step missing −30. **Final** = max(0, Base − penalties). Double counting is intentional
   (penalty covers what the mistake breaks beyond the one step).
6. **Task Score** = mean of 3 runs' Final Scores; also record the lowest run (stability).

Per task inputs: GT redflow + execution params (proven by a successful run), GT critical steps marked
(the commit step: final Invite/Save/Submit), the video/PDF. URL line not scored.

Worked example (Venus-JML Create Account, 9-step GT, IF block, critical GT9): runs score 55.0, 90.0, 37.8
→ **Task Score 60.9**, lowest 37.8.

Version comparison: same task set, 3 runs each; report Mean Task Score, Mean Base Score, penalties by type,
syntax failures, critical-step misses (any increase = regression). Task-by-task diff; real change only if
95% bootstrap CI of per-task differences excludes 0; list every improved/regressed task. Store every GEN,
its mapping, and the weights/penalties version; re-score stored GENs when rules change.

**Open decisions**: final weights (0.3/0.4/0.2/0.1), penalty sizes (5/5/10/30), pass mark per run
(e.g. ≥90), which LLM + prompt does the mapping (pinned), who marks critical steps on each GT.

> `docs/old-chat/generated-files/redscore.py` + `example.py` are an **earlier, superseded** version
> (similarity-threshold / alignment based). Use only as reference; implement from `redscore-spec.md`.

Earlier alternatives discussed (not chosen, may be useful later): golden step lists recorded with a browser
event recorder (rrweb/Playwright) with essential/critical/noise/optional labels; Needleman-Wunsch
alignment; recall/precision/F1, navigation recall, noise rejection, consistency metrics; diagnosing misses
by time gap, video position, action type, element size, page density.

## 5. Open questions (never answered in the old chat)

1. LangSmith vs Langfuse as source of truth for eval runs/results?
2. Can we build our own resettable "Gym" test apps, or only real sandbox tenants?
3. Do traces store per-step screenshots + chosen element (coordinates/DOM)?
4. Budget: how many full agent runs per night?
5. Human reviewers available, hours/week?
6. Do original videos/PDFs + proven GT redflows exist for existing Skills, or record a fresh set?
7. Is there an existing redflow validator/parser we can call (API/library), and what language is the
   Redblock codebase?

## 6. Next steps

1. Answer open questions; confirm RedScore open decisions.
2. Build the RedScore implementation: redflow parser + syntax validation hook, LLM mapping call
   (pinned prompt/model), code checks, scorer, penalties, task aggregation.
3. Benchmark dataset format: per task {asset, GT redflow, params, critical steps}, ~40 tasks to start.
4. Runner: generate 3× per task per generator version, score, store results (GEN, mapping, scores,
   rules version) in a DB.
5. Version comparison report (bootstrap CI, per-task flips) + trend dashboard.
6. Later: extend to execution evals (outcome/state checks, false-success rate, pass^k), extraction evals,
   human eval + judge calibration, production monitoring.

Note: screenshots shared in the old chat (app UI, sample GT redflows, trace view) were not included in the
export.
