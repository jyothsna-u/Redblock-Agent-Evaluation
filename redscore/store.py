"""Local result storage: the system of record for every RedScore number.

results/<task_id>/<gen_version>/record.json      what was scored: GT hash, judge, each run's GEN hash and status
                               /gt.redflow       the GT every run in this record was scored against (snapshot)
                               /run_<n>/gen.redflow, mapping.json (rules-independent), score_<rules_version>.json
                               /superseded/<time>/   an earlier record replaced with --force (kept, never deleted)
results/redscore.db                              index: one row per run and per task, per rules version

A record is append-only. Scoring a task + gen_version that already has a record needs --resume (finish the
failed or missing runs, same GT and judge) or --force (move the old record to superseded/ and start again).
Run status: ok | syntax_fail (a legitimate 0) | error (judge or I/O failure: never a 0, the task stays
incomplete and gets no Task Score).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .files import sha256_text, write_atomic

DEFAULT_ROOT = Path("results")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    task_id TEXT, gen_version TEXT, run INTEGER, rules_version TEXT,
    syntax_ok INTEGER, points REAL, slots INTEGER, base REAL, final REAL, passed INTEGER,
    pen_out_of_sequence REAL, pen_missing_variable REAL, pen_logic_block REAL, pen_critical_step REAL,
    critical_missing TEXT, partial INTEGER, model TEXT, prompt_version TEXT, gen_sha256 TEXT, scored_at TEXT,
    PRIMARY KEY (task_id, gen_version, run, rules_version)
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT, gen_version TEXT, rules_version TEXT,
    task_score REAL, lowest REAL, mean_base REAL, n_runs INTEGER, scored_at TEXT,
    PRIMARY KEY (task_id, gen_version, rules_version)
);
"""
# Provenance columns added after v1; existing databases are migrated in place (old rows keep NULLs,
# which compare treats as "scale unknown" until the record is re-scored).
PROVENANCE = ("gt_sha256", "judge", "rules_sha256", "scoring_code_sha256")
MIGRATIONS = {
    "runs": {"status": "TEXT", "error": "TEXT", **{c: "TEXT" for c in PROVENANCE}, "redscore_commit": "TEXT",
             "gt_valid": "INTEGER", "final_if_runnable": "REAL"},
    "tasks": {"status": "TEXT", "n_expected": "INTEGER", **{c: "TEXT" for c in PROVENANCE}, "gt_valid": "INTEGER"},
}
SCORED = ("ok", "syntax_fail")


class RecordExists(RuntimeError):
    pass


class RecordMismatch(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.root / "redscore.db"), timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for c, sql_type in cols.items():
                if c not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {c} {sql_type}")
        self.db.commit()

    # ------------------------------------------------------------ records

    def record_dir(self, task_id: str, gen_version: str) -> Path:
        return self.root / task_id / gen_version

    def run_dir(self, task_id: str, gen_version: str, run: int) -> Path:
        return self.record_dir(task_id, gen_version) / f"run_{run}"

    def read_record(self, task_id: str, gen_version: str) -> Optional[dict]:
        p = self.record_dir(task_id, gen_version) / "record.json"
        return json.loads(p.read_text()) if p.exists() else None

    def is_legacy(self, task_id: str, gen_version: str) -> bool:
        """Stored runs from before records existed: no GT snapshot, so they cannot be re-scored safely."""
        d = self.record_dir(task_id, gen_version)
        return not (d / "record.json").exists() and any(d.glob("run_*/gen.redflow"))

    def open_record(self, task_id: str, gen_version: str, gt_source: str, judge: str, mode: str = "new") -> dict:
        """Start (mode new|force) or continue (mode resume) the record for one task + gen_version."""
        rec = self.read_record(task_id, gen_version)
        exists = rec is not None or self.is_legacy(task_id, gen_version)
        where = f"{task_id} {gen_version}"
        if exists and mode == "new":
            raise RecordExists(f"{where} is already scored ({self.record_dir(task_id, gen_version)}); "
                               "use --resume to finish its failed runs or --force to replace it (the old record is kept)")
        if exists and mode == "resume":
            if rec is None:
                raise RecordMismatch(f"{where} was stored before records existed; use --force to re-score it")
            if rec["gt_sha256"] != sha256_text(gt_source):
                raise RecordMismatch(f"{where}: the GT changed since this record was started; use --force")
            if rec["judge"] != judge:
                raise RecordMismatch(f"{where}: record was judged by {rec['judge']}, not {judge}; use --force")
            return rec
        if exists and mode == "force":
            self.supersede(task_id, gen_version)
        rec = {"task_id": task_id, "gen_version": gen_version, "gt_sha256": sha256_text(gt_source),
               "judge": judge, "created_at": _now(), "runs": {}}
        d = self.record_dir(task_id, gen_version)
        write_atomic(d / "gt.redflow", gt_source)
        self._write_record(rec)
        return rec

    def adopt_legacy(self, task_id: str, gen_version: str, gt_source: str, judge: str) -> dict:
        """Give pre-record runs a record, using the GT on disk now (said so in the record)."""
        rec = {"task_id": task_id, "gen_version": gen_version, "gt_sha256": sha256_text(gt_source),
               "judge": judge, "created_at": _now(), "gt_adopted_from_live_task": True, "runs": {}}
        for d in sorted(self.record_dir(task_id, gen_version).glob("run_*/gen.redflow")):
            n = d.parent.name.split("_")[1]
            rec["runs"][n] = {"gen_sha256": sha256_text(d.read_text()),
                              "status": "ok" if (d.parent / "mapping.json").exists() else "syntax_fail"}
        write_atomic(self.record_dir(task_id, gen_version) / "gt.redflow", gt_source)
        self._write_record(rec)
        return rec

    def stored_gt(self, task_id: str, gen_version: str) -> str:
        return (self.record_dir(task_id, gen_version) / "gt.redflow").read_text()

    def supersede(self, task_id: str, gen_version: str) -> Path:
        d = self.record_dir(task_id, gen_version)
        dest = d / "superseded" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest.mkdir(parents=True, exist_ok=False)
        for item in d.iterdir():
            if item.name != "superseded":
                shutil.move(str(item), str(dest / item.name))
        with self.db:
            self.db.execute("DELETE FROM runs WHERE task_id=? AND gen_version=?", (task_id, gen_version))
            self.db.execute("DELETE FROM tasks WHERE task_id=? AND gen_version=?", (task_id, gen_version))
        return dest

    def _write_record(self, rec: dict) -> None:
        write_atomic(self.record_dir(rec["task_id"], rec["gen_version"]) / "record.json", json.dumps(rec, indent=2))

    def records(self) -> List[Tuple[str, str]]:
        """(task_id, gen_version) of every stored record, including legacy ones."""
        found = {(p.parent.parent.name, p.parent.name) for p in self.root.glob("*/*/record.json")}
        found |= {(p.parent.parent.parent.name, p.parent.parent.name) for p in self.root.glob("*/*/run_*/gen.redflow")}
        return sorted(found)

    # ------------------------------------------------------------ runs and tasks

    def save_run(self, task_id: str, gen_version: str, run: int, gen_source: str, result: Optional[dict],
                 status: str, rules, scale: Dict, error: Optional[str] = None, commit: Optional[str] = None) -> Path:
        d = self.run_dir(task_id, gen_version, run)
        rec = self.read_record(task_id, gen_version) or {}
        gen_sha = sha256_text(gen_source)
        write_atomic(d / "gen.redflow", gen_source)
        if result is not None:
            if result.get("mapping") is not None:
                write_atomic(d / "mapping.json", json.dumps(result["mapping"], indent=2))
            result["provenance"] = dict(scale, gt_sha256=rec.get("gt_sha256"), gen_sha256=gen_sha,
                                        redscore_commit=commit)
            write_atomic(d / f"score_{rules.version}.json", json.dumps(result, indent=2))
        if rec:
            rec["runs"][str(run)] = {"gen_sha256": gen_sha, "status": status, **({"error": error} if error else {})}
            self._write_record(rec)
        r = result or {}
        meta = (r.get("mapping") or {}).get("meta", {})
        pen = r.get("penalties") or {}
        p = lambda k: pen[k]["points"] if k in pen else None  # noqa: E731
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO runs (task_id, gen_version, run, rules_version, syntax_ok, points, slots, base, "
                "final, passed, pen_out_of_sequence, pen_missing_variable, pen_logic_block, pen_critical_step, "
                "critical_missing, partial, model, prompt_version, gen_sha256, scored_at, status, error, gt_sha256, "
                "judge, rules_sha256, scoring_code_sha256, redscore_commit, gt_valid, final_if_runnable) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, gen_version, run, rules.version,
                 int(r["syntax"]["ok"]) if r else None, r.get("points"), r.get("slots"), r.get("base"), r.get("final"),
                 int(r["passed"]) if r else None,
                 p("out_of_sequence"), p("missing_variable"), p("logic_block"), p("critical_step"),
                 json.dumps(r["critical_missing"]) if r else None, int(r["partial"]) if r else None,
                 meta.get("model"), meta.get("prompt_version"), gen_sha, r.get("scored_at") or _now(),
                 status, error, rec.get("gt_sha256"), scale["judge"], scale["rules_sha256"],
                 scale["scoring_code_sha256"], commit, rec.get("gt_valid"), r.get("final_if_runnable")))
        return d

    def note_gt(self, task_id: str, gen_version: str, issues: List[dict]) -> None:
        """Record the GT's problems (with their GT steps) in the record; the GT file itself is never changed."""
        rec = self.read_record(task_id, gen_version)
        if rec is not None:
            rec["gt_valid"] = int(not any(i["severity"] == "error" for i in issues))
            rec["gt_issues"] = issues
            self._write_record(rec)

    def finish_task(self, task_id: str, gen_version: str, rules, scale: Dict, task: Optional[dict],
                    mean_base: Optional[float], n_expected: int) -> None:
        rec = self.read_record(task_id, gen_version) or {}
        status = "complete" if task else "incomplete"
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO tasks (task_id, gen_version, rules_version, task_score, lowest, mean_base, "
                "n_runs, scored_at, status, n_expected, gt_sha256, judge, rules_sha256, scoring_code_sha256, gt_valid) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, gen_version, rules.version, task and task["task_score"], task and task["lowest"],
                 mean_base, task and task["n_runs"], _now(), status, n_expected, rec.get("gt_sha256"),
                 scale["judge"], scale["rules_sha256"], scale["scoring_code_sha256"], rec.get("gt_valid")))

    def runs(self, gen_version: str, rules_version: str) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM runs WHERE gen_version=? AND rules_version=? ORDER BY task_id, run",
                               (gen_version, rules_version)).fetchall()

    def tasks(self, gen_version: str, rules_version: str) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM tasks WHERE gen_version=? AND rules_version=? ORDER BY task_id",
                               (gen_version, rules_version)).fetchall()

    def rules_versions(self, gen_version: str) -> List[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT rules_version FROM tasks WHERE gen_version=? "
                                              "ORDER BY rules_version", (gen_version,))]
