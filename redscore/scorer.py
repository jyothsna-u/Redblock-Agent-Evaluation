"""RedScore steps 1-6: syntax gate, step points, Base Score, penalties, Final, Task Score."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .checks import check_blocks, out_of_sequence, pair_variables, step_variables_ok
from .mapping import Mapper, Mapping
from .parser import Script, parse
from .rules import Rules
from .validator import errors, validate


class InvalidGroundTruth(ValueError):
    pass


def load_gt(source: str) -> Script:
    gt = parse(source)
    errs = errors(validate(gt))
    if errs:
        raise InvalidGroundTruth("GT redflow has syntax errors: " +
                                 "; ".join(f"line {e.line}: {e.message}" for e in errs))
    return gt


def score_run(gt: Script, gen_source: str, rules: Rules, mapper: Mapper) -> dict:
    """Score one generated redflow against the GT. Returns a JSON-serialisable result.

    Critical steps are the GT action lines marked `# critical`; an unmarked GT gets no
    critical-step penalty.
    """
    critical_steps = gt.critical_steps
    result = {
        "rules_version": rules.version,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "partial": gt.is_extraction,
        "n_gt": len(gt.actions),
        "critical_steps": critical_steps,
    }
    if gt.is_extraction:
        result["partial_reason"] = ("extraction script: only STEPS are scored; field-level scoring "
                                    "is not defined yet")

    # Step 1: syntax gate
    gen = parse(gen_source)
    issues = validate(gen)
    result["syntax"] = {"ok": not errors(issues), "issues": [i.to_dict() for i in issues]}
    if errors(issues):
        result.update(points=0.0, slots=0, base=0.0, final=0.0, passed=False, penalties=_penalty_totals({}, rules),
                      steps=[], extra=[], variables=None, sequence=None, blocks=None,
                      critical_missing=[], mapping=None)
        return _round(result)

    # Step 2: mapping + code checks
    mapping: Mapping = mapper(gt, gen)
    var = pair_variables(gt, gen, mapping)
    oos = set(out_of_sequence(mapping))
    blocks = check_blocks(gt, gen, mapping, var.pairs)

    # Step 3: step points
    w = rules.weights
    by_gt = {p.gt: p for p in mapping.pairs}
    steps: List[dict] = []
    total = 0.0
    for a in gt.actions:
        p = by_gt.get(a.num)
        row: Dict = {"gt": a.num, "gt_text": a.text, "critical": a.num in critical_steps}
        if p is None:
            row.update(gen=None, keyword=0.0, element=0.0, variables=0.0, intent=0.0, points=0.0, status="missing")
        else:
            n = gen.action(p.gen)
            var_ok, var_reason = step_variables_ok(a, n, gt, var.pairs)
            pts = {
                "keyword": w["keyword"] if a.keyword == n.keyword else 0.0,
                "element": w["element"] if p.same_element else 0.0,
                "variables": w["variables"] if var_ok else 0.0,
                "intent": w["intent"] if p.same_intent else 0.0,
            }
            row.update(gen=p.gen, gen_text=n.text, **pts, points=round(sum(pts.values()), 6),
                       status="out_of_sequence" if a.num in oos else "mapped")
            if var_reason:
                row["variables_reason"] = var_reason
        total += row["points"]
        steps.append(row)

    # Step 4: Base Score
    slots = len(gt.actions) + len(mapping.extra_gen)
    total = round(total, 6)
    base = total / slots * 100 if slots else 0.0

    # Step 5: penalties
    critical_missing = [c for c in critical_steps if c not in by_gt]
    counts = {
        "out_of_sequence": len(oos),
        "missing_variable": len(var.missing),
        "logic_block": sum(1 for b in blocks if not b.ok),
        "critical_step": len(critical_missing),
    }
    penalties = _penalty_totals(counts, rules)
    final = max(0.0, base - sum(p["points"] for p in penalties.values()))

    result.update(
        points=total, slots=slots, base=base, final=final, passed=final >= rules.pass_mark,
        penalties=penalties,
        steps=steps,
        extra=[{"gen": n, "gen_text": gen.action(n).text} for n in mapping.extra_gen],
        variables={"pairs": var.pairs, "missing": var.missing, "unpaired_gen": var.unpaired_gen},
        sequence={"out_of_sequence_gt": sorted(oos)},
        blocks=[b.__dict__ for b in blocks],
        critical_missing=critical_missing,
        mapping=mapping.to_dict(),
    )
    return _round(result)


def _penalty_totals(counts: Dict[str, int], rules: Rules) -> Dict[str, dict]:
    return {k: {"count": counts.get(k, 0), "points": counts.get(k, 0) * v} for k, v in rules.penalties.items()}


def _round(result: dict) -> dict:
    """Keep exact values for aggregation and add 1-decimal display values."""
    for k in ("base", "final"):
        result[f"{k}_display"] = round(result[k] + 1e-9, 1)
    return result


def task_score(finals: Sequence[float]) -> Optional[dict]:
    """Step 6: mean of the runs' Final Scores, plus the lowest run (stability)."""
    if not finals:
        return None
    mean = sum(finals) / len(finals)
    return {"task_score": mean, "lowest": min(finals), "n_runs": len(finals),
            "task_score_display": round(mean + 1e-9, 1), "lowest_display": round(min(finals) + 1e-9, 1)}
