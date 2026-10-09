"""What produced a number: the scale a score is measured on, and where the code came from.

Two scores are comparable only if they were measured on the same scale:
    rules_sha256          content of the rules file (weights, penalties, pass mark), not just its version label
    judge                 who made the step mapping: "llm:<model>@<prompt_version>" or "fixture"
    scoring_code_sha256   content of the modules that turn a GT, a GEN and a mapping into a number
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

PACKAGE = Path(__file__).resolve().parent
SCORING_MODULES = ("parser.py", "validator.py", "mapping.py", "checks.py", "scorer.py", "rules.py")


@lru_cache(maxsize=1)
def scoring_code_sha256() -> str:
    h = hashlib.sha256()
    for name in SCORING_MODULES:
        h.update(name.encode() + b"\x00" + (PACKAGE / name).read_bytes() + b"\x00")
    return h.hexdigest()


def git_commit() -> Optional[str]:
    """RedScore's git commit, with '+uncommitted' when scoring code, prompts or rules have local changes."""
    root = PACKAGE.parent
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "redscore", "prompts", "rules"], cwd=root,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (out.stdout.strip() + ("+uncommitted" if dirty else "")) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def scale(rules, judge: Optional[str]) -> Dict[str, Optional[str]]:
    return {"rules_version": rules.version, "rules_sha256": rules.sha256, "judge": judge,
            "scoring_code_sha256": scoring_code_sha256()}


def scale_key(s: Dict) -> str:
    """Short id of a scale, for display and grouping."""
    fields = {k: s.get(k) for k in ("rules_sha256", "judge", "scoring_code_sha256")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:12]
