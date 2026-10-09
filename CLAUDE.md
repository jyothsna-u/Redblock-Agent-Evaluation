# Redblock Agent Evaluation

Building an AI evaluation / benchmarking system for Redblock's AI Studio, starting with
**RedScore**: scoring how well a redflow generated from a video/PDF (GEN) matches the ground-truth
redflow (GT), so every generator version can be compared against past benchmarks.

## Read first
- `docs/context.md` — full project handoff: product, user flow, decisions, open questions, next steps.
- `docs/redscore-spec.md` — **source of truth** for the scoring algorithm (with worked example: 60.9).
- `docs/reference/redflow-syntax-reference.md` — the redflow DSL.

## Other material
- `docs/reference/` — Redblock docs copies, test-case spreadsheets (445 functional, 160 AI-side),
  Langfuse on-prem proposal.
- `docs/old-chat/transcripts/` — full transcripts of the previous claude.ai chats.
- `docs/old-chat/generated-files/` — code from the old chat. `redscore.py` there is an older,
  superseded algorithm; implement from `docs/redscore-spec.md`.

## Code (RedScore v1, Python 3.12, venv in `.venv/`)
- Python 3.12 is managed by uv (`~/Library/Python/3.9/bin/uv`, interpreter under `~/.local/share/uv/python/`);
  the old 3.9 venv is kept as `.venv-py39` (git-ignored) until 3.12 is proven.
- `redscore/` — `parser` (redflow → AST, action + extraction), `validator` (syntax gate), `mapping`
  (mapping model, validation, prompt rendering), `llm` (pinned OpenAI-compatible call + cache, retries),
  `checks` (variables, sequence via LIS, logic blocks), `scorer`, `store` (append-only records + SQLite),
  `provenance` (scale = rules file hash + judge + scoring-code hash), `history` (per-execution explanations),
  `compare` (refuses mismatched scales), `files` (atomic writes), `cli`.
- `requirements.txt` — exact pinned versions (pip freeze); `.github/workflows/ci.yml` runs pytest.
- `rules/v1.yaml` — weights/penalties/pass mark (spec values). New values = new file + new version.
- `prompts/mapping_v1.md` — pinned mapping prompt; its content hash is recorded as `prompt_version`.
- `tasks/<id>/` — `gt.redflow` + `gen/run_N.redflow` (the current runs; Heet's layout, may also hold the source
  `video.mp4`). The folder name is the task id; no other per-task file. `task --gen-version V` stores results
  under V and copies each scored GEN into `results/`, so `gen/` is overwritten for the next generator version.
- `results/` (git-ignored) — `<task>/<version>/` records (record.json, GT snapshot, run_N/), `redscore.db`,
  `history/`, LLM mapping cache. A record is append-only: re-running needs `task --resume` (finish failed runs)
  or `--force` (old record moved to `superseded/`). Run status ok | syntax_fail (a 0) | error (never a 0; task
  incomplete, no Task Score, exit code 2). `rescore` uses the stored GT snapshot, never the live task.
  `task/score --no-cache` re-asks the mapping LLM; the replaced answer is kept in `cache/mapping/replaced/`.
- Run: `.venv/bin/python -m redscore {validate|score|task|rescore|compare} ...`; tests: `.venv/bin/python -m pytest`.
  The Venus worked example (`tasks/venus-jml-create-account`, fixtures in `tests/fixtures/venus`) is the golden test.

## Decisions (2026-10-05)
- Own Python parser/validator for now; swap in Redblock's validator later if one is exposed.
- Mapping LLM: self-hosted `redblock-visual-reasoning-2.0` via `.env` (`REASONING_MODEL_*`, see `.env.example`).
- Sequence: minimum steps out of place (longest increasing subsequence), not "below max so far".
- Critical steps are optional (decided with Heet, overrides the spec's "each task needs critical steps"): mark
  the GT's commit step with a `# critical` comment at the end of its line. GEN missing a marked step → −30;
  an unmarked GT gets no critical-step penalty. There is no task.yaml.
- GEN files are exported by hand for v1.
- Syntax: only keywords in the syntax reference are supported (Heet: no others for now; a GT using an
  undocumented keyword such as tc12's `NEAR` is flagged and still scored, see 2026-10-06). Intent binding is enforced only for the FILL/FILL_AND_ENTER/
  SELECT value variable; a variable inside element text that the INTENT doesn't mention is only a warning,
  because proven GTs (tc2, tc4) do this.
- Results local (files + SQLite) for now; LangSmith integration later.
- Extraction scripts: parsed, validated, STEPS scored; results flagged `partial` until field-level scoring
  rules are agreed (Heet will share the full redflow docs).

## Decisions (2026-10-06) — goal: numbers that can be trusted and compared across future versions
- Variable pairing: a variable whose sample value was misread still pairs through the steps/loops that use it;
  it keeps the -5 missing-variable penalty but no longer fails those steps and logic blocks (spec updated).
- Hard-coded check only applies when the GEN step does not use the mapped variable.
- Judge: 1 mapping call per run (Heet declined 3-call majority vote for cost).
- LangSmith: integrate behind a flag, local results stay the system of record (LangSmith run retention is
  14-180 days); full GT/GEN text may be uploaded. The current SDK needs Python >= 3.10, so the venv moved to
  Python 3.12 with langsmith 0.14.4 (2026-10-06). Workspace/key: Heet decides later.
- NEVER edit redflows in tasks/ (GT or GEN): they are tool output, and their mistakes are what RedScore measures.
  GEN errors cost points (syntax error = 0 per the spec). GT errors are flagged with their GT step + line
  (`gt_issues` in every score, record.json, history; `GT FLAGGED` in CLI output; `gt_valid` in the DB) and
  scoring continues: the GT is parsed leniently (`load_gt`), malformed GT steps are kept, malformed GT blocks
  are not checked, unused GT variables are not charged.
- GEN syntax failure: Final 0 (the run cannot execute), but mapping, step points, Base and penalties are still
  computed and stored, plus `final_if_runnable`, so the scores stay useful for improving the generator. Invalid
  GEN lines are parsed leniently like GT lines. If the mapping call fails on a syntax-failed run, it is still a
  0 (status syntax_fail), only without diagnostics.
- Critical steps on tc1-tc10: leave unmarked for now.
- tc1-tc10 stay git-ignored; only the Venus golden task and test fixtures are tracked.

## Key rules
- The URL line is never scored (user supplies it each run).
- LLM calls used for scoring/mapping must be pinned (model + prompt version, temperature 0).
- Store every GEN redflow, its mapping, and the weights/penalties version so results can be re-scored.
- Don't change RedScore weights or penalties without confirming with the user.
