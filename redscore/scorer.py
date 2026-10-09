"""RedScore steps 1-6: syntax gate, step points, Base Score, penalties, Final, Task Score.

A GEN that fails the syntax gate gets Final 0, but steps 2-5 still run so its diagnostic scores are kept.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .checks import check_blocks, out_of_sequence, pair_variables, step_variables_ok
from .mapping import Mapper, Mapping, MappingError
from .parser import Script, parse
from .rules import Rules
from .validator import errors, validate


def load_gt(source: str) -> Script:
    """Parse a ground truth leniently: GT files are never edited and GT errors never stop scoring.

    An invalid GT step line is kept as the step its author meant, so the GEN is still scored against it;
    every GT problem is reported by gt_issues() with the GT step it is on, and travels with each score.
    """
    return parse(source, lenient=True)


def gt_issues(gt: Script) -> List[dict]:
    """Errors in the GT, plus GT variables no step uses (which are not charged to the GEN), each with its step."""
    where: Dict[int, str] = {b.else_line: f"{b.id} ELSE" for b in gt.blocks if b.else_line}
    where.update({b.line: b.id for b in gt.blocks})        # an ELIF line is its own block, not an ELSE
    where.update({a.line: f"GT{a.num}" for a in gt.actions})
    return [dict(i.to_dict(), step=where.get(i.line)) for i in validate(gt)
            if i.severity == "error" or i.code == "W_VAR_UNUSED"]


def score_run(gt: Script, gen_source: str, rules: Rules, mapper: Mapper) -> dict:
    """Score one generated redflow against the GT. Returns a JSON-serialisable result.

    Critical steps are the GT action lines marked `# critical`; an unmarked GT gets no
    critical-step penalty.
    """
    critical_steps = gt.critical_steps
    flagged = gt_issues(gt)
    result = {
        "rules_version": rules.version,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "partial": gt.is_extraction,
        "n_gt": len(gt.actions),
        "critical_steps": critical_steps,
        "gt_valid": not any(i["severity"] == "error" for i in flagged),
        "gt_issues": flagged,
    }
    if gt.is_extraction:
        result["partial_reason"] = ("extraction script: only STEPS are scored; field-level scoring "
                                    "is not defined yet")

    # Step 1: syntax gate. A GEN that fails it cannot run, so its Final is 0 - but steps 2-5 still run on it
    # (decided 2026-10-06), so what the generator got right and wrong is kept for improving it: step points,
    # Base, penalties and `final_if_runnable`. Invalid GEN lines are kept leniently, like GT lines, so a typo
    # costs that step's points instead of the whole step.
    issues = validate(parse(gen_source))
    syntax_ok = not errors(issues)
    result["syntax"] = {"ok": syntax_ok, "issues": [i.to_dict() for i in issues]}
    gen = parse(gen_source, lenient=not syntax_ok)

    # Step 2: mapping + code checks
    try:
        mapping: Mapping = mapper(gt, gen)
    except (MappingError, RuntimeError, OSError) as e:
        if syntax_ok:
            raise
        # The Final is 0 either way; only the diagnostic scores are unavailable.
        result.update(points=0.0, slots=0, base=0.0, final=0.0, final_if_runnable=None, passed=False,
                      penalties=_penalty_totals({}, rules), steps=[], extra=[], variables=None, sequence=None,
                      blocks=None, critical_missing=[], mapping=None,
                      diagnostics_error=f"{type(e).__name__}: {e}")
        return _round(result)
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
    # Rounded so binary floating point cannot put an exact score on the wrong side of the pass mark
    # (8.1 / 9 * 100 is 89.99999999999999 unrounded).
    base = round(total / slots * 100, 9) if slots else 0.0

    # Step 5: penalties
    critical_missing = [c for c in critical_steps if c not in by_gt]
    counts = {
        "out_of_sequence": len(oos),
        "missing_variable": len(var.missing),
        "logic_block": sum(1 for b in blocks if not b.ok),
        "critical_step": len(critical_missing),
    }
    penalties = _penalty_totals(counts, rules)
    final_if_runnable = max(0.0, round(base - sum(p["points"] for p in penalties.values()), 9))
    final = final_if_runnable if syntax_ok else 0.0

    result.update(
        points=total, slots=slots, base=base, final=final, final_if_runnable=final_if_runnable,
        passed=final >= rules.pass_mark,
        penalties=penalties,
        steps=steps,
        extra=[{"gen": n, "gen_text": gen.action(n).text} for n in mapping.extra_gen],
        variables={"pairs": var.pairs, "missing": var.missing, "mismatched": var.mismatched,
                   "unpaired_gen": var.unpaired_gen},
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
    for k in ("base", "final", "final_if_runnable"):
        if result.get(k) is not None:
            result[f"{k}_display"] = round(result[k] + 1e-9, 1)
    return result


def task_score(finals: Sequence[float]) -> Optional[dict]:
    """Step 6: mean of the runs' Final Scores, plus the lowest run (stability)."""
    if not finals:
        return None
    mean = sum(finals) / len(finals)
    return {"task_score": mean, "lowest": min(finals), "n_runs": len(finals),
            "task_score_display": round(mean + 1e-9, 1), "lowest_display": round(min(finals) + 1e-9, 1)}
