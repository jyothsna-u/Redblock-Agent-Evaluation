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

## Code (RedScore v1, Python 3.9+, venv in `.venv/`)
- `redscore/` — `parser` (redflow → AST, action + extraction), `validator` (syntax gate), `mapping`
  (mapping model, validation, prompt rendering), `llm` (pinned OpenAI-compatible call + cache),
  `checks` (variables, sequence via LIS, logic blocks), `scorer`, `store` (files + SQLite), `compare`, `cli`.
- `rules/v1.yaml` — weights/penalties/pass mark (spec values). New values = new file + new version.
- `prompts/mapping_v1.md` — pinned mapping prompt; its content hash is recorded as `prompt_version`.
- `tasks/<id>/` — `gt.redflow` + `gen/run_N.redflow` (the current runs; Heet's layout, may also hold the source
  `video.mp4`). The folder name is the task id; no other per-task file. `task --gen-version V` stores results
  under V and copies each scored GEN into `results/`, so `gen/` is overwritten for the next generator version.
- `results/` (git-ignored) — run artefacts, `redscore.db`, LLM mapping cache.
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
- Syntax: only keywords in the syntax reference are supported (Heet: no others for now; tc2's GT uses an
  undocumented `NEAR` and fails until rewritten). Intent binding is enforced only for the FILL/FILL_AND_ENTER/
  SELECT value variable; a variable inside element text that the INTENT doesn't mention is only a warning,
  because proven GTs (tc2, tc4) do this.
- Results local (files + SQLite) for now; LangSmith integration later.
- Extraction scripts: parsed, validated, STEPS scored; results flagged `partial` until field-level scoring
  rules are agreed (Heet will share the full redflow docs).

## Key rules
- The URL line is never scored (user supplies it each run).
- LLM calls used for scoring/mapping must be pinned (model + prompt version, temperature 0).
- Store every GEN redflow, its mapping, and the weights/penalties version so results can be re-scored.
- Don't change RedScore weights or penalties without confirming with the user.
