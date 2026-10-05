"""Command line: python -m redscore <validate|score|task|rescore|compare> ..."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .compare import compare, format_report
from .history import History
from .mapping import Mapper, MappingError, fixture_mapper, validate_mapping
from .parser import parse
from .rules import load_rules
from .scorer import InvalidGroundTruth, load_gt, score_run, task_score
from .store import Store
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


def _mapper(fixture: Optional[str], results: str = "results") -> Mapper:
    if fixture:
        return fixture_mapper(fixture)
    from .llm import llm_mapper
    return llm_mapper(cache_dir=Path(results) / "cache" / "mapping")


def format_run(res: dict) -> str:
    out = []
    if not res["syntax"]["ok"]:
        out.append("SYNTAX FAILED → Final 0")
        out += [f"  line {i['line']}: {i['code']} {i['message']}" for i in res["syntax"]["issues"] if i["severity"] == "error"]
        return "\n".join(out)
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


def cmd_score(a) -> int:
    task = load_task(Path(a.task))
    gt = load_gt(task["gt_source"])
    res = score_run(gt, Path(a.gen).read_text(), load_rules(a.rules), _mapper(a.mapping, a.results))
    print(json.dumps(res, indent=2) if a.json else format_run(res))
    return 0


def _score_and_store(store: Store, task: dict, version: str, runs, rules, mapper_for_run,
                     command=(), kind: str = "task") -> dict:
    gt = load_gt(task["gt_source"])
    print(f"{task['id']}  gen {version}  rules {rules.version}  critical: {_critical_label(gt.critical_steps)}")
    history = History(store.root, task, version, rules, gt, command, kind)
    finals, bases, scored_at = [], [], None
    try:
        for run, gen_source in runs:
            res = score_run(gt, gen_source, rules, mapper_for_run(run))
            store.save_run(task["id"], version, run, gen_source, res)
            history.add_run(run, gen_source, res)
            finals.append(res["final"])
            bases.append(res["base"])
            scored_at = res["scored_at"]
            print(f"  run {run}: Base {res['base_display']:>5}  Final {res['final_display']:>5}"
                  + ("  SYNTAX FAIL" if not res["syntax"]["ok"] else "")
                  + (f"  critical missing {res['critical_missing']}" if res["critical_missing"] else ""))
    except Exception as e:
        history.finish(None, None, error=f"{type(e).__name__}: {e}")
        raise
    t = task_score(finals)
    mean_base = sum(bases) / len(bases) if bases else None
    if t:
        store.save_task(task["id"], version, rules.version, t, mean_base, scored_at)
        print(f"  Task Score {t['task_score_display']}  lowest {t['lowest_display']}  ({t['n_runs']} runs)")
    print(f"  history: {history.finish(t, mean_base)}")
    return t


def cmd_task(a) -> int:
    task = load_task(Path(a.task))
    rules = load_rules(a.rules)
    # The task's gen/ folder holds the current runs; --gen-version is the name they are stored under,
    # and results/ keeps a copy of every scored GEN, so gen/ can be overwritten for the next version.
    gen_dir = task["dir"] / "gen"
    runs = sorted((int(m.group(1)), p) for p in gen_dir.glob("run_*.redflow")
                  if (m := re.fullmatch(r"run_(\d+)\.redflow", p.name)))
    if not runs:
        print(f"no run_<n>.redflow files in {gen_dir}", file=sys.stderr)
        return 1
    if len(runs) != rules.runs_per_task:
        print(f"warning: {len(runs)} runs found, rules expect {rules.runs_per_task}", file=sys.stderr)
    llm = None if a.mappings else _mapper(None, a.results)
    mapper_for_run = (lambda run: fixture_mapper(Path(a.mappings) / f"mapping_run_{run}.json")) if a.mappings \
        else (lambda run: llm)
    _score_and_store(Store(Path(a.results)), task, a.gen_version,
                     [(run, p.read_text()) for run, p in runs], rules, mapper_for_run, a.argv)
    return 0


def cmd_rescore(a) -> int:
    """Re-score every stored GEN with new rules, re-using its stored mapping (no LLM calls)."""
    store = Store(Path(a.results))
    rules = load_rules(a.rules)
    groups = defaultdict(list)
    for d in store.stored_runs():
        task_id, version, run = d.parent.parent.name, d.parent.name, int(d.name.split("_")[1])
        groups[(task_id, version)].append((run, d))
    for (task_id, version), items in sorted(groups.items()):
        task = load_task(Path(a.tasks) / task_id)
        stored = {run: d for run, d in items}

        def mapper_for_run(run):
            path = stored[run] / "mapping.json"
            return lambda gt, gen: validate_mapping(gt, gen, json.loads(path.read_text()),
                                                    dict(json.loads(path.read_text()).get("meta", {}), rescored=True))

        _score_and_store(store, task, version, [(run, (d / "gen.redflow").read_text()) for run, d in sorted(items)],
                         rules, mapper_for_run, a.argv, kind="rescore")
    return 0


def cmd_compare(a) -> int:
    store = Store(Path(a.results))
    rules_version = a.rules_version or store.latest_rules_version()
    report = compare(store, a.old, a.new, rules_version)
    print(json.dumps(report, indent=2) if a.json else format_report(report))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="redscore", description="RedScore: score generated redflows against GT")
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
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("task", parents=[common], help="score a task's gen/run_*.redflow and store results under --gen-version")
    s.add_argument("--task", required=True, help="task folder (holds gt.redflow and gen/run_<n>.redflow)")
    s.add_argument("--gen-version", required=True, help="name to save these runs under, e.g. the generator version (v1)")
    s.add_argument("--mappings", help="directory of mapping_run_<n>.json fixtures instead of the LLM")
    s.add_argument("--rules")
    s.set_defaults(fn=cmd_task)

    s = sub.add_parser("rescore", parents=[common], help="re-score all stored GENs with a rules file, re-using stored mappings")
    s.add_argument("--rules", required=True)
    s.add_argument("--tasks", default="tasks", help="tasks directory (default: tasks)")
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
    except (FileNotFoundError, InvalidGroundTruth, MappingError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
