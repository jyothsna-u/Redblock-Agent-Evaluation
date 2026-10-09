"""Command line: python -m redscore <validate|score|task|rescore|compare> ..."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from .compare import compare, format_report
from .files import sha256_text
from .history import History
from .mapping import Mapper, MappingError, fixture_mapper, validate_mapping
from .parser import parse
from .provenance import git_commit, scale, scale_key
from .rules import load_rules
from .scorer import gt_issues, load_gt, score_run, task_score
from .store import SCORED, RecordMismatch, Store
from .validator import errors, validate


def load_task(task_dir: Path) -> dict:
    """A task is a folder: gt.redflow + gen/run_<n>.redflow. The folder name is the task id."""
    task_dir = Path(task_dir)
    gt_path = task_dir / "gt.redflow"
    if not gt_path.is_file():
        raise FileNotFoundError(f"{gt_path} not found (each task folder needs a gt.redflow)")
    return {"id": task_dir.name, "dir": task_dir, "gt_source": gt_path.read_text()}


def _critical_label(steps) -> str:
    return ", ".join(f"GT{n}" for n in steps) or "none marked"


def _mapper(fixture: Optional[str], results: str = "results", refresh: bool = False) -> Mapper:
    if fixture:
        return fixture_mapper(fixture)
    from .llm import llm_mapper
    return llm_mapper(cache_dir=Path(results) / "cache" / "mapping", refresh=refresh)


def format_run(res: dict) -> str:
    out = []
    if not res["syntax"]["ok"]:
        out.append("SYNTAX FAILED → Final 0 (the GEN cannot run); step scores below are kept for diagnosis")
        out += [f"  line {i['line']}: {i['code']} {i['message']}" for i in res["syntax"]["issues"] if i["severity"] == "error"]
        if res.get("final_if_runnable") is None:
            out.append(f"  step scores unavailable: {res.get('diagnostics_error')}")
            return "\n".join(out)
        out.append("")
    out.append(f"{'GT':>4} {'GEN':>4}  {'kw':>4} {'elem':>4} {'var':>4} {'int':>4} {'pts':>5}  status")
    for s in res["steps"]:
        crit = " CRITICAL" if s["critical"] else ""
        gen = s["gen"] if s["gen"] is not None else "—"
        out.append(f"{s['gt']:>4} {gen:>4}  {s['keyword']:>4.1f} {s['element']:>4.1f} {s['variables']:>4.1f} "
                   f"{s['intent']:>4.1f} {s['points']:>5.2f}  {s['status']}{crit}"
                   + (f"  [{s['variables_reason']}]" if s.get("variables_reason") else ""))
    for e in res["extra"]:
        out.append(f"   — {e['gen']:>4}  extra: {e['gen_text']}")
    out.append(f"\nBase {res['base_display']}  = {res['points']:g} / {res['slots']} slots")
    for k, p in res["penalties"].items():
        if p["count"]:
            out.append(f"  −{p['points']:g}  {k.replace('_', ' ')} ×{p['count']}")
    for b in res["blocks"] or []:
        if not b["ok"]:
            out.append(f"       block {b['gt_block']} {b['condition']}: {b['reason']}")
    if res["variables"]["missing"]:
        out.append(f"       missing variables: {', '.join('$' + v for v in res['variables']['missing'])}")
    out.append(f"       critical steps: {_critical_label(res['critical_steps'])}")
    if not res["syntax"]["ok"]:
        out.append(f"Final if it could run {res['final_if_runnable_display']}  →  syntax gate  →  Final 0")
    else:
        out.append(f"Final {res['final_display']}  ({'PASS' if res['passed'] else 'below pass mark'})")
    if res["partial"]:
        out.append(f"PARTIAL: {res['partial_reason']}")
    for note in (res.get("mapping") or {}).get("notes", []):
        out.append(f"note: {note}")
    return "\n".join(out)


def cmd_validate(a) -> int:
    issues = validate(parse(Path(a.file).read_text()))
    for i in issues:
        print(f"{a.file}:{i.line}: {i.severity}: {i.code} {i.message}")
    print("valid" if not errors(issues) else f"{len(errors(issues))} error(s)")
    return 1 if errors(issues) else 0


def print_gt_flags(flagged) -> None:
    """GT problems: the GT is never edited and scoring goes on; the steps they are on are the GT's mistake."""
    errs = [i for i in flagged if i["severity"] == "error"]
    for i in flagged:
        label = "GT FLAGGED" if i["severity"] == "error" else "GT note"
        print(f"  {label} {i['step'] or '-'} (line {i['line']}): {i['code']} {i['message']}")
    if errs:
        print(f"  GT has {len(errs)} error(s): scored anyway; fix the GT, these are not generator mistakes")


def cmd_score(a) -> int:
    task = load_task(Path(a.task))
    gt = load_gt(task["gt_source"])
    print_gt_flags(gt_issues(gt))
    res = score_run(gt, Path(a.gen).read_text(), load_rules(a.rules), _mapper(a.mapping, a.results, a.no_cache))
    print(json.dumps(res, indent=2) if a.json else format_run(res))
    if not a.json:
        print("(not stored: a quick check only; benchmark numbers come from `task`)")
    return 0


def _score_task(store: Store, task: dict, version: str, gens, rules, mapper_for_run, judge: str,
                command=(), kind: str = "task") -> int:
    """Score the runs of one record and store them. Returns 0 (complete) or 2 (incomplete: no Task Score)."""
    gt = load_gt(task["gt_source"])
    sc, commit = scale(rules, judge), git_commit()
    print(f"{task['id']}  gen {version}  rules {rules.version}  judge {judge}  scale {scale_key(sc)}  "
          f"critical: {_critical_label(gt.critical_steps)}")
    flagged = gt_issues(gt)
    store.note_gt(task["id"], version, flagged)
    print_gt_flags(flagged)
    history = History(store.root, task, version, rules, gt, command, kind, sc)
    finals, bases, failed = [], [], []
    try:
        for run, gen_source in gens:
            try:
                res = score_run(gt, gen_source, rules, mapper_for_run(run))
            except (MappingError, RuntimeError, OSError) as e:   # the judge or I/O failed: never a 0
                err = f"{type(e).__name__}: {e}"
                store.save_run(task["id"], version, run, gen_source, None, "error", rules, sc, err, commit)
                history.add_error(run, gen_source, err)
                failed.append(run)
                print(f"  run {run}: NOT SCORED  {err}")
                continue
            store.save_run(task["id"], version, run, gen_source, res,
                           "ok" if res["syntax"]["ok"] else "syntax_fail", rules, sc, None, commit)
            history.add_run(run, gen_source, res)
            finals.append(res["final"])
            bases.append(res["base"])
            print(f"  run {run}: Base {res['base_display']:>5}  Final {res['final_display']:>5}"
                  + ("" if res["syntax"]["ok"] else "  SYNTAX FAIL (Final if it could run "
                     + (f"{res['final_if_runnable_display']}" if res.get("final_if_runnable") is not None else "n/a")
                     + ")")
                  + (f"  critical missing {res['critical_missing']}" if res["critical_missing"] else ""))
    except BaseException as e:   # Ctrl+C or a bug: the record stays incomplete and the history says why
        store.finish_task(task["id"], version, rules, sc, None, None, rules.runs_per_task)
        history.finish(None, None, error=f"{type(e).__name__}: {e}")
        raise
    problems = []
    if failed:
        problems.append(f"run(s) {', '.join(map(str, failed))} not scored")
    if len(gens) != rules.runs_per_task:
        problems.append(f"{len(gens)} run(s), rules expect {rules.runs_per_task}")
    t = None if problems else task_score(finals)
    mean_base = sum(bases) / len(bases) if t else None
    store.finish_task(task["id"], version, rules, sc, t, mean_base, rules.runs_per_task)
    if t:
        print(f"  Task Score {t['task_score_display']}  lowest {t['lowest_display']}  ({t['n_runs']} runs)")
    else:
        print(f"  INCOMPLETE ({'; '.join(problems)}): no Task Score; fix the cause and re-run with --resume")
    print(f"  history: {history.finish(t, mean_base, incomplete_reason='; '.join(problems) or None)}")
    return 0 if t else 2


def _gen_files(task: dict):
    gen_dir = task["dir"] / "gen"
    return sorted((int(m.group(1)), p) for p in gen_dir.glob("run_*.redflow")
                  if (m := re.fullmatch(r"run_(\d+)\.redflow", p.name)))


def _stored_mapper(store: Store, task_id: str, version: str, run: int) -> Mapper:
    """The mapping stored with a run, re-validated against the GT and GEN (no LLM call)."""
    path = store.run_dir(task_id, version, run) / "mapping.json"

    def mapper(gt, gen):
        if not path.exists():
            raise MappingError(f"run {run} has no stored mapping (it failed the syntax gate when first scored); "
                               f"map it with `task --force`")
        stored = json.loads(path.read_text())
        return validate_mapping(gt, gen, stored, dict(stored.get("meta", {}), rescored=True))
    return mapper


def cmd_task(a) -> int:
    task = load_task(Path(a.task))
    rules = load_rules(a.rules)
    # The task's gen/ folder holds the current runs; --gen-version is the name they are stored under,
    # and results/ keeps a copy of every scored GEN, so gen/ can be overwritten for the next version.
    files = _gen_files(task)
    if not files:
        print(f"no run_<n>.redflow files in {task['dir'] / 'gen'}", file=sys.stderr)
        return 1
    store = Store(Path(a.results))
    if a.mappings:
        judge, mapper_for_run = "fixture", lambda run: fixture_mapper(Path(a.mappings) / f"mapping_run_{run}.json")
    else:
        llm = _mapper(None, a.results, a.no_cache)
        judge, mapper_for_run = llm.judge, lambda run: llm
    mode = "force" if a.force else "resume" if a.resume else "new"
    rec = store.open_record(task["id"], a.gen_version, task["gt_source"], judge, mode)
    gens = [(n, p.read_text()) for n, p in files]
    if mode == "resume":
        done = {int(n): r for n, r in rec["runs"].items() if r["status"] in SCORED}
        for n, src in gens:
            if n in done and done[n]["gen_sha256"] != sha256_text(src):
                raise RecordMismatch(f"run {n}'s GEN changed since it was scored; use --force")

        def mapper_for_run(run, fresh=mapper_for_run):   # scored runs keep their stored mapping; only the rest call the judge
            return _stored_mapper(store, task["id"], a.gen_version, run) if run in done else fresh(run)
    return _score_task(store, task, a.gen_version, gens, rules, mapper_for_run, judge, a.argv)


def _judge_of_stored_runs(store: Store, task_id: str, version: str) -> str:
    judges = set()
    for p in store.record_dir(task_id, version).glob("run_*/mapping.json"):
        meta = json.loads(p.read_text()).get("meta", {})
        src = meta.get("source") or ""
        judges.add(f"llm:{meta.get('model')}@{meta.get('prompt_version')}" if src == "llm"
                   else "fixture" if src.startswith("fixture") else src or "unknown")
    return judges.pop() if len(judges) == 1 else f"mixed({', '.join(sorted(judges))})" if judges else "unknown"


def cmd_rescore(a) -> int:
    """Re-score every stored record with a rules file, from its stored GT and mappings (no LLM calls)."""
    store = Store(Path(a.results))
    rules = load_rules(a.rules)
    worst = 0
    for task_id, version in store.records():
        if store.is_legacy(task_id, version):
            if not a.adopt_live_gt:
                print(f"skip {task_id} {version}: stored before GT snapshots were kept, so the GT it was scored "
                      f"against is unknown; re-run the task with --force, or rescore with --adopt-live-gt to "
                      f"accept tasks/{task_id}/gt.redflow as it is now", file=sys.stderr)
                worst = max(worst, 2)
                continue
            live = load_task(Path(a.tasks) / task_id)["gt_source"]
            store.adopt_legacy(task_id, version, live, _judge_of_stored_runs(store, task_id, version))
            print(f"adopted {task_id} {version}: GT snapshot taken from tasks/{task_id}/gt.redflow as it is now")
        rec = store.read_record(task_id, version)
        gens = [(int(n), (store.run_dir(task_id, version, int(n)) / "gen.redflow").read_text())
                for n in sorted(rec["runs"], key=int)]
        task = {"id": task_id, "dir": store.record_dir(task_id, version), "gt_source": store.stored_gt(task_id, version)}
        code = _score_task(store, task, version, gens, rules,
                           lambda run, t=task_id, v=version: _stored_mapper(store, t, v, run),
                           rec["judge"], a.argv, kind="rescore")
        worst = max(worst, code)
    return worst


def cmd_compare(a) -> int:
    store = Store(Path(a.results))
    rules_version = a.rules_version
    if not rules_version:
        common = sorted(set(store.rules_versions(a.old)) & set(store.rules_versions(a.new)))
        if len(common) != 1:
            raise RuntimeError(f"{a.old} and {a.new} share rules versions {common or 'none'}; pass --rules-version")
        rules_version = common[0]
    report = compare(store, a.old, a.new, rules_version)
    print(json.dumps(report, indent=2) if a.json else format_report(report))
    return 0


NO_CACHE_HELP = ("ask the mapping LLM again instead of reusing its cached answer; the previous answer is kept "
                 "in cache/mapping/replaced/")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="redscore", description="RedScore: score generated redflows against GT",
                                epilog="exit codes: 0 ok, 1 error, 2 incomplete (some runs not scored: no Task Score)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--results", default="results", help="results directory (default: results)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", parents=[common], help="syntax-check a redflow file")
    s.add_argument("file")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("score", parents=[common], help="score one GEN redflow (not stored)")
    s.add_argument("--task", required=True, help="task folder (holds gt.redflow)")
    s.add_argument("--gen", required=True, help="GEN redflow file")
    s.add_argument("--mapping", help="mapping JSON fixture instead of the LLM")
    s.add_argument("--rules", help="rules YAML (default rules/v1.yaml)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-cache", action="store_true", help=NO_CACHE_HELP)
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("task", parents=[common], help="score a task's gen/run_*.redflow and store results under --gen-version")
    s.add_argument("--task", required=True, help="task folder (holds gt.redflow and gen/run_<n>.redflow)")
    s.add_argument("--gen-version", required=True, help="name to save these runs under, e.g. the generator version (v1)")
    s.add_argument("--mappings", help="directory of mapping_run_<n>.json fixtures instead of the LLM")
    s.add_argument("--rules")
    again = s.add_mutually_exclusive_group()
    again.add_argument("--resume", action="store_true",
                       help="finish an existing record: score its failed or missing runs (same GT and judge)")
    again.add_argument("--force", action="store_true",
                       help="replace an existing record; the old one is kept under superseded/")
    s.add_argument("--no-cache", action="store_true", help=NO_CACHE_HELP)
    s.set_defaults(fn=cmd_task)

    s = sub.add_parser("rescore", parents=[common],
                       help="re-score every stored record with a rules file, from its stored GT and mappings")
    s.add_argument("--rules", required=True)
    s.add_argument("--tasks", default="tasks", help="tasks directory, only for --adopt-live-gt (default: tasks)")
    s.add_argument("--adopt-live-gt", action="store_true",
                   help="for records stored before GT snapshots existed: take the GT on disk now as their snapshot")
    s.set_defaults(fn=cmd_rescore)

    s = sub.add_parser("compare", parents=[common], help="compare two generator versions")
    s.add_argument("old")
    s.add_argument("new")
    s.add_argument("--rules-version", help="default: most recently used")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_compare)

    a = p.parse_args(argv)
    a.argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        return a.fn(a)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as e:   # incl. invalid GT, mapping, record conflicts
        print(f"error: {e}", file=sys.stderr)
        return 1
