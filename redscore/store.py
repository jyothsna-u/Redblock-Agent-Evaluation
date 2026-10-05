"""Local result storage: run artefacts on disk + a SQLite index.

results/<task_id>/<gen_version>/run_<n>/gen.redflow      the GEN that was scored
                                       /mapping.json     the step mapping (rules-independent)
                                       /score_<rules_version>.json
results/redscore.db                                      one row per run and per task, per rules version
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import List, Optional

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


class Store:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.root / "redscore.db"))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def run_dir(self, task_id: str, gen_version: str, run: int) -> Path:
        return self.root / task_id / gen_version / f"run_{run}"

    def save_run(self, task_id: str, gen_version: str, run: int, gen_source: str, result: dict) -> Path:
        d = self.run_dir(task_id, gen_version, run)
        d.mkdir(parents=True, exist_ok=True)
        (d / "gen.redflow").write_text(gen_source)
        if result.get("mapping") is not None:
            (d / "mapping.json").write_text(json.dumps(result["mapping"], indent=2))
        (d / f"score_{result['rules_version']}.json").write_text(json.dumps(result, indent=2))
        meta = (result.get("mapping") or {}).get("meta", {})
        pen = result["penalties"]
        self.db.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, gen_version, run, result["rules_version"], int(result["syntax"]["ok"]),
             result["points"], result["slots"], result["base"], result["final"], int(result["passed"]),
             pen["out_of_sequence"]["points"], pen["missing_variable"]["points"],
             pen["logic_block"]["points"], pen["critical_step"]["points"],
             json.dumps(result["critical_missing"]), int(result["partial"]),
             meta.get("model"), meta.get("prompt_version"),
             hashlib.sha256(gen_source.encode()).hexdigest(), result["scored_at"]))
        self.db.commit()
        return d

    def save_task(self, task_id: str, gen_version: str, rules_version: str, task: dict,
                  mean_base: float, scored_at: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?)",
                        (task_id, gen_version, rules_version, task["task_score"], task["lowest"],
                         mean_base, task["n_runs"], scored_at))
        self.db.commit()

    def stored_runs(self) -> List[Path]:
        """Every stored run directory that has a GEN and a mapping (or failed syntax)."""
        return sorted(p.parent for p in self.root.glob("*/*/run_*/gen.redflow"))

    def runs(self, gen_version: str, rules_version: str) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM runs WHERE gen_version=? AND rules_version=? ORDER BY task_id, run",
                               (gen_version, rules_version)).fetchall()

    def tasks(self, gen_version: str, rules_version: str) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM tasks WHERE gen_version=? AND rules_version=? ORDER BY task_id",
                               (gen_version, rules_version)).fetchall()

    def latest_rules_version(self) -> Optional[str]:
        row = self.db.execute("SELECT rules_version FROM runs ORDER BY scored_at DESC LIMIT 1").fetchone()
        return row[0] if row else None
