"""Run history: one timestamped folder per scoring execution, never overwritten.

results/history/<YYYY-MM-DD_HH-MM-SS>_<task>_<gen_version>_<rules_version>[_rescore]/
    summary.json    the execution: command, code commit, GT, rules, mapper, Task Score,
                    and each run's biggest cuts
    run_<n>.json    one run: GEN source, syntax issues, LLM prompt + raw response, mapping,
                    full score, and `cuts` - every point lost between 100 and the Final score
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from .parser import Script, parse
from .rules import Rules

COMPONENTS = ("keyword", "element", "variables", "intent")


def _r(x: float) -> float:
    return round(x + 1e-9, 2)


def _cut(stage: str, what: str, points: float, why: str) -> dict:
    return {"stage": stage, "what": what, "points": _r(points), "why": why}


def explain(gt: Script, gen_source: str, res: dict, rules: Rules) -> dict:
    """Every cut that takes a run from 100 to its Final score, with the reason.

    Base cuts are exact: each lost step point costs 100/slots, and each extra GEN step costs a
    full slot (100/slots), so 100 - sum(base cuts) == Base. Penalty cuts then take Base to Final.
    """
    if not res["syntax"]["ok"]:
        errs = [f"line {i['line']}: {i['code']} {i['message']}"
                for i in res["syntax"]["issues"] if i["severity"] == "error"]
        return {"start": 100.0, "base": 0.0, "final": 0.0, "passed": False,
                "cuts": [_cut("syntax", "syntax gate", 100.0, "GEN has syntax errors, so the run scores 0")],
                "syntax_errors": errs, "summary": f"Syntax failed ({len(errs)} error(s)) -> Final 0"}

    gen = parse(gen_source)
    w, pen = rules.weights, rules.penalties
    unit = 100 / res["slots"]
    cuts: List[dict] = []

    # Base: points lost per GT step and component
    for s in res["steps"]:
        a = gt.action(s["gt"])
        if s["gen"] is None:
            cuts.append(_cut("step", f"GT{s['gt']} missing", sum(w.values()) * unit,
                             f"no GEN step matches GT{s['gt']}: {s['gt_text']}"))
            continue
        n = gen.action(s["gen"])
        why = {
            "keyword": f"GT{a.num} uses {a.keyword}, GEN{n.num} uses {n.keyword}",
            "element": f'mapping judged the elements different: GT "{a.element or a.text}" '
                       f'vs GEN "{n.element or n.text}"',
            "variables": s.get("variables_reason") or "variables do not match",
            "intent": f'mapping judged the intents different: GT "{a.intent}" vs GEN "{n.intent}"',
        }
        for k in COMPONENTS:
            lost = w[k] - s[k]
            if lost > 1e-9:
                cuts.append(_cut("step", f"GT{s['gt']} {k}", lost * unit, why[k]))
    for e in res["extra"]:
        cuts.append(_cut("extra", f"GEN{e['gen']} extra", unit,
                         f"GEN step with no GT partner adds an empty slot: {e['gen_text']}"))

    # Penalties: Base -> Final
    by_gt = {s["gt"]: s for s in res["steps"]}
    for g in res["sequence"]["out_of_sequence_gt"]:
        cuts.append(_cut("penalty", f"out_of_sequence GT{g}", pen["out_of_sequence"],
                         f"GT{g} is done at GEN{by_gt[g]['gen']}, out of GT order"))
    for v in res["variables"]["missing"]:
        cuts.append(_cut("penalty", f"missing_variable ${v}", pen["missing_variable"],
                         f"GT variable ${v} has no GEN partner"))
    for b in res["blocks"]:
        if not b["ok"]:
            cuts.append(_cut("penalty", f"logic_block {b['gt_block']}", pen["logic_block"],
                             f"{b['condition']}: {b['reason']}"))
    for g in res["critical_missing"]:
        cuts.append(_cut("penalty", f"critical_step GT{g}", pen["critical_step"],
                         f"critical step GT{g} is missing: {gt.action(g).text}"))

    n_gt, n_extra = len(res["steps"]), len(res["extra"])
    penalties = sum(p["points"] for p in res["penalties"].values())
    out = {
        "start": 100.0,
        "base": _r(res["base"]),
        "base_formula": f"{res['points']:g} step points / {res['slots']} slots "
                        f"({n_gt} GT steps + {n_extra} extra GEN steps) x 100 = {_r(res['base'])}",
        "penalties": _r(penalties),
        "final": _r(res["final"]),
        "final_formula": f"Base {_r(res['base'])} - penalties {_r(penalties)} = {_r(res['final'])}",
        "passed": res["passed"],
        "pass_mark": rules.pass_mark,
        "cuts": cuts,
        "summary": f"Base {_r(res['base'])}, Final {_r(res['final'])} "
                   f"({'PASS' if res['passed'] else f'below pass mark {rules.pass_mark:g}'})",
    }
    if res["base"] - penalties < 0:
        out["note"] = f"penalties exceed Base by {_r(penalties - res['base'])}; Final is floored at 0"
    return out


def _git_commit() -> Optional[str]:
    try:
        root = Path(__file__).resolve().parent.parent
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "redscore", "prompts", "rules"], cwd=root,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (out.stdout.strip() + ("+uncommitted" if dirty else "")) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _llm_record(meta: dict, cache_dir: Path) -> Optional[dict]:
    """The exact prompt and raw LLM response behind a mapping, from the mapping cache."""
    if meta.get("source") != "llm":
        return None
    path = cache_dir / f"{meta.get('cache_key')}.json"
    if not path.exists():
        return {"cache_file": str(path), "note": "cache entry not found; prompt and response unavailable"}
    c = json.loads(path.read_text())
    return {"cache_file": str(path), "prompt": c.get("prompt"), "raw_response": c.get("raw"),
            "failed_attempts": c.get("failed_attempts", [])}


class History:
    def __init__(self, root: Path, task: dict, gen_version: str, rules: Rules, gt: Script,
                 command: Sequence[str], kind: str = "task"):
        self.started = datetime.now().astimezone()
        name = f"{self.started:%Y-%m-%d_%H-%M-%S}_{task['id']}_{gen_version}_{rules.version}"
        if kind != "task":
            name += f"_{kind}"
        self.cache_dir = Path(root) / "cache" / "mapping"
        base = Path(root) / "history"
        self.dir, i = base / name, 2
        while self.dir.exists():          # two executions in the same second
            self.dir, i = base / f"{name}_{i}", i + 1
        self.dir.mkdir(parents=True)
        self.task, self.gen_version, self.rules, self.gt = task, gen_version, rules, gt
        self.command, self.kind = list(command), kind
        self.runs: List[dict] = []
        self.mapper: Optional[dict] = None

    def add_run(self, run: int, gen_source: str, res: dict) -> None:
        meta = (res.get("mapping") or {}).get("meta", {})
        if meta and self.mapper is None:
            self.mapper = {k: meta[k] for k in ("source", "model", "prompt_version", "temperature") if k in meta}
        why = explain(self.gt, gen_source, res, self.rules)
        record = {
            "run": run,
            "gen_source": gen_source,
            "gen_sha256": hashlib.sha256(gen_source.encode()).hexdigest(),
            "explanation": why,
            "syntax": res["syntax"],
            "mapping_source": meta.get("source"),
            "llm": _llm_record(meta, self.cache_dir),
            "mapping": res.get("mapping"),
            "score": res,
        }
        (self.dir / f"run_{run}.json").write_text(json.dumps(record, indent=2))
        self.runs.append({
            "run": run, "file": f"run_{run}.json", "syntax_ok": res["syntax"]["ok"],
            "base": _r(res["base"]), "final": _r(res["final"]), "passed": res["passed"],
            "summary": why["summary"],
            "biggest_cuts": sorted(why["cuts"], key=lambda c: -c["points"])[:5],
        })

    def finish(self, task_score: Optional[dict], mean_base: Optional[float], error: Optional[str] = None) -> Path:
        summary = {
            "execution": {
                "id": self.dir.name, "kind": self.kind, "status": "failed" if error else "ok", "error": error,
                "started_at": self.started.isoformat(timespec="seconds"),
                "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "command": "redscore " + " ".join(self.command),
                "redscore_commit": _git_commit(), "python": platform.python_version(),
            },
            "task": {"id": self.task["id"], "dir": str(self.task["dir"]), "gt_source": self.task["gt_source"],
                     "gt_steps": len(self.gt.actions), "critical_steps": self.gt.critical_steps},
            "gen_version": self.gen_version,
            "rules": dataclasses.asdict(self.rules),
            "mapper": self.mapper,
            "result": None if not task_score else {
                "task_score": _r(task_score["task_score"]), "lowest": _r(task_score["lowest"]),
                "n_runs": task_score["n_runs"], "mean_base": _r(mean_base),
            },
            "runs": self.runs,
        }
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return self.dir
