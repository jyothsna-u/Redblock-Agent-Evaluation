"""RedScore step 2: map GEN steps to GT steps.

The mapping comes from one pinned LLM call (see llm.py / prompts/) or from a JSON fixture.
Either way it goes through `validate_mapping`, so downstream code can trust it.

Mapping JSON:
    {"pairs": [{"gt": 1, "gen": 1, "same_element": true, "same_intent": true}, ...],
     "runtime_blocks": [{"gt_block": "B1", "gen_block": "B2", "same_condition": true}, ...],
     "missing_gt": [...], "extra_gen": [...]}          # optional; derived from pairs
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .parser import RUNTIME_KINDS, Script, strip_comment

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_PROMPT = "mapping_v1"


class MappingError(ValueError):
    pass


@dataclass
class Pair:
    gt: int
    gen: int
    same_element: bool
    same_intent: bool


@dataclass
class RuntimeBlockPair:
    gt_block: str
    gen_block: str
    same_condition: bool


@dataclass
class Mapping:
    pairs: List[Pair]
    runtime_blocks: List[RuntimeBlockPair]
    missing_gt: List[int]
    extra_gen: List[int]
    notes: List[str] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)   # model, prompt_version, cache_key, source

    def to_dict(self) -> dict:
        return {
            "pairs": [p.__dict__ for p in sorted(self.pairs, key=lambda p: p.gt)],
            "runtime_blocks": [r.__dict__ for r in self.runtime_blocks],
            "missing_gt": self.missing_gt,
            "extra_gen": self.extra_gen,
            "notes": self.notes,
            "meta": self.meta,
        }


Mapper = Callable[[Script, Script], Mapping]


def _as_bool(v, where: str) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("yes", "true", "no", "false"):
        return v.strip().lower() in ("yes", "true")
    raise MappingError(f"{where}: expected yes/no boolean, got {v!r}")


def validate_mapping(gt: Script, gen: Script, data: dict, meta: Optional[dict] = None) -> Mapping:
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        raise MappingError("mapping must be an object with a 'pairs' list")
    n_gt, n_gen = len(gt.actions), len(gen.actions)
    problems: List[str] = []
    pairs: List[Pair] = []
    used_gt, used_gen = set(), set()
    for i, p in enumerate(data["pairs"]):
        try:
            g, n = int(p["gt"]), int(p["gen"])
            pair = Pair(g, n, _as_bool(p.get("same_element"), f"pair {i} same_element"),
                        _as_bool(p.get("same_intent"), f"pair {i} same_intent"))
        except (KeyError, TypeError, ValueError) as e:
            problems.append(f"pair {i} malformed: {e}")
            continue
        if not 1 <= g <= n_gt:
            problems.append(f"pair {i}: GT{g} does not exist (GT has {n_gt} steps)")
        elif not 1 <= n <= n_gen:
            problems.append(f"pair {i}: GEN{n} does not exist (GEN has {n_gen} steps)")
        elif g in used_gt:
            problems.append(f"GT{g} is paired more than once")
        elif n in used_gen:
            problems.append(f"GEN{n} is paired more than once")
        else:
            used_gt.add(g)
            used_gen.add(n)
            pairs.append(pair)

    runtime: List[RuntimeBlockPair] = []
    gt_rt = {b.id: b for b in gt.blocks if b.kind in RUNTIME_KINDS}
    gen_rt = {b.id: b for b in gen.blocks if b.kind in RUNTIME_KINDS}
    seen_gt, seen_gen = set(), set()
    for i, r in enumerate(data.get("runtime_blocks") or []):
        try:
            rb = RuntimeBlockPair(str(r["gt_block"]), str(r["gen_block"]),
                                  _as_bool(r.get("same_condition"), f"runtime_blocks {i}"))
        except (KeyError, TypeError, ValueError) as e:
            problems.append(f"runtime_blocks {i} malformed: {e}")
            continue
        if rb.gt_block not in gt_rt:
            problems.append(f"runtime_blocks {i}: GT block {rb.gt_block} is not a WHEN/UNTIL/WAIT_UNTIL")
        elif rb.gen_block not in gen_rt:
            problems.append(f"runtime_blocks {i}: GEN block {rb.gen_block} is not a WHEN/UNTIL/WAIT_UNTIL")
        elif rb.gt_block in seen_gt or rb.gen_block in seen_gen:
            problems.append(f"runtime_blocks {i}: block used more than once")
        else:
            seen_gt.add(rb.gt_block)
            seen_gen.add(rb.gen_block)
            runtime.append(rb)

    if problems:
        raise MappingError("; ".join(problems))

    missing = [g for g in range(1, n_gt + 1) if g not in used_gt]
    extra = [n for n in range(1, n_gen + 1) if n not in used_gen]
    notes = []
    for key, derived in (("missing_gt", missing), ("extra_gen", extra)):
        if key in data and sorted(int(x) for x in data[key]) != derived:
            notes.append(f"LLM {key}={sorted(data[key])} disagrees with pairs; using {derived}")
    return Mapping(pairs, runtime, missing, extra, notes, dict(meta or {}))


def load_mapping_file(path, gt: Script, gen: Script) -> Mapping:
    return validate_mapping(gt, gen, json.loads(Path(path).read_text()), {"source": f"fixture:{path}"})


def fixture_mapper(path) -> Mapper:
    return lambda gt, gen: load_mapping_file(path, gt, gen)


# ---------------------------------------------------------------- prompt rendering

def render_numbered(script: Script, prefix: str) -> str:
    """Source with comments and URL removed; actions labelled [GT3]/[GEN3], blocks [B1]."""
    labels = {a.line: f"[{prefix}{a.num}]" for a in script.actions}
    labels.update({b.line: f"[{b.id}]" for b in script.blocks})
    out = []
    for no, raw in enumerate(script.source.splitlines(), start=1):
        text = strip_comment(raw).rstrip()
        if not text.strip() or text.lstrip().startswith("URL "):
            continue
        label = labels.get(no, "")
        out.append(f"{label:<8}{text}")
    return "\n".join(out)


def load_prompt(name: str = DEFAULT_PROMPT):
    """Return (template, version). Version = name + short hash, so any edit shows up in results."""
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    return text, f"{name}@{hashlib.sha256(text.encode()).hexdigest()[:10]}"


def build_prompt(gt: Script, gen: Script, template: str) -> str:
    return (template.replace("{{GT}}", render_numbered(gt, "GT"))
                    .replace("{{GEN}}", render_numbered(gen, "GEN")))
