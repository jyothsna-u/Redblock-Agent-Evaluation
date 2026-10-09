"""Load the versioned RedScore rules (weights, penalties, pass mark)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

import yaml

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "rules" / "v1.yaml"


@dataclass(frozen=True)
class Rules:
    version: str
    weights: Dict[str, float]
    penalties: Dict[str, float]
    pass_mark: float
    runs_per_task: int
    sha256: str = ""      # content of the rules file: two files with the same `version` but different values differ here


def load_rules(path: Union[str, Path, None] = None) -> Rules:
    text = Path(path or DEFAULT_RULES).read_text()
    data = yaml.safe_load(text)
    weights = {k: float(data["weights"][k]) for k in ("keyword", "element", "variables", "intent")}
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1.0, got {sum(weights.values())}")
    penalties = {k: float(data["penalties"][k])
                 for k in ("out_of_sequence", "missing_variable", "logic_block", "critical_step")}
    return Rules(str(data["version"]), weights, penalties, float(data["pass_mark"]), int(data["runs_per_task"]),
                 hashlib.sha256(text.encode()).hexdigest())
