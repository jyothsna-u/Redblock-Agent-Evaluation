"""Generator version comparison (spec: "Comparing generator versions")."""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .store import Store


def bootstrap_ci(diffs: List[float], n: int = 10000, seed: int = 0, level: float = 0.95) -> Optional[Tuple[float, float]]:
    """Percentile bootstrap CI of the mean per-task difference."""
    if not diffs:
        return None
    rng = random.Random(seed)
    k = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(k)) / k for _ in range(n))
    lo = means[int((1 - level) / 2 * n)]
    hi = means[min(n - 1, int((1 + level) / 2 * n))]
    return lo, hi


class NotComparable(RuntimeError):
    pass


SCALE_FIELDS = ("rules_sha256", "judge", "scoring_code_sha256")


def _scale_of(rows, version: str):
    """The one scale every complete task of a version was measured on; refuses unknown or mixed scales."""
    unknown = [r["task_id"] for r in rows if any(r[f] is None for f in SCALE_FIELDS)]
    if unknown:
        raise NotComparable(f"{version}: {', '.join(unknown)} were scored before provenance was recorded; "
                            f"re-score them (`rescore --rules ... --adopt-live-gt`, or `task --force`)")
    groups: Dict[Tuple, List[str]] = {}
    for r in rows:
        groups.setdefault(tuple(r[f] for f in SCALE_FIELDS), []).append(r["task_id"])
    if len(groups) > 1:
        detail = "; ".join(f"{', '.join(ts)}: judge {s[1]}, rules {s[0][:10]}, code {s[2][:10]}"
                           for s, ts in groups.items())
        raise NotComparable(f"{version} mixes {len(groups)} scales, so it is not one benchmark ({detail}); "
                            f"re-score its tasks so one judge, rules file and scoring code measured all of them")
    return next(iter(groups), None)


def version_summary(store: Store, gen_version: str, rules_version: str) -> Dict:
    tasks = [t for t in store.tasks(gen_version, rules_version) if t["status"] == "complete"]
    done = {t["task_id"] for t in tasks}
    runs = [r for r in store.runs(gen_version, rules_version) if r["task_id"] in done]
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return {
        "gen_version": gen_version,
        "n_tasks": len(tasks),
        "n_runs": len(runs),
        "mean_task_score": mean([t["task_score"] for t in tasks]),
        "mean_base_score": mean([r["base"] for r in runs if r["base"] is not None]),
        # What the runs would score if none had a syntax error: the generator's quality apart from syntax cliffs.
        "mean_final_if_runnable": mean([r["final_if_runnable"] for r in runs if r["final_if_runnable"] is not None]),
        "penalties": {k: sum(r[f"pen_{k}"] for r in runs)
                      for k in ("out_of_sequence", "missing_variable", "logic_block", "critical_step")},
        "syntax_failures": sum(1 for r in runs if not r["syntax_ok"]),
        "critical_step_misses": sum(1 for r in runs if r["critical_missing"] not in ("[]", None)),
        "partial_runs": sum(1 for r in runs if r["partial"]),
    }


MIN_TASKS_FOR_CI = 5   # below this the bootstrap interval is not meaningful


def compare(store: Store, old: str, new: str, rules_version: str) -> Dict:
    """Compare two generator versions task by task. Only complete tasks measured on the same scale, against
    the same GT (same gt_sha256), are compared; everything else is refused or listed as not compared."""
    rows_a, rows_b = store.tasks(old, rules_version), store.tasks(new, rules_version)
    for version, rows in ((old, rows_a), (new, rows_b)):
        legacy = [t["task_id"] for t in rows if t["status"] is None]
        if legacy:
            raise NotComparable(f"{version}: {', '.join(legacy)} were scored before scales and GT snapshots were "
                                f"recorded, so it cannot be shown they were measured the same way; re-score them "
                                f"(`rescore --rules <file> --adopt-live-gt`, or `task --force` to re-map with the judge)")
    a = {t["task_id"]: t for t in rows_a if t["status"] == "complete"}
    b = {t["task_id"]: t for t in rows_b if t["status"] == "complete"}
    sa_scale, sb_scale = _scale_of(list(a.values()), old), _scale_of(list(b.values()), new)
    if sa_scale and sb_scale and sa_scale != sb_scale:
        detail = "; ".join(f"{f}: {old} {x} vs {new} {y}"
                           for f, x, y in zip(SCALE_FIELDS, sa_scale, sb_scale) if x != y)
        raise NotComparable(f"{old} and {new} were measured on different scales ({detail}); "
                            f"re-score the older one with `rescore` (same judge) or re-run it")
    gt_changed = sorted(t for t in set(a) & set(b) if a[t]["gt_sha256"] != b[t]["gt_sha256"])
    common = sorted(t for t in set(a) & set(b) if t not in gt_changed)
    per_task = [{"task_id": t, "old": a[t]["task_score"], "new": b[t]["task_score"],
                 "diff": b[t]["task_score"] - a[t]["task_score"],
                 "old_lowest": a[t]["lowest"], "new_lowest": b[t]["lowest"]} for t in common]
    diffs = [p["diff"] for p in per_task]
    ci = bootstrap_ci(diffs) if len(diffs) >= MIN_TASKS_FOR_CI else None
    sa, sb = version_summary(store, old, rules_version), version_summary(store, new, rules_version)
    return {
        "rules_version": rules_version,
        "old": sa, "new": sb,
        "scale": dict(zip(SCALE_FIELDS, sa_scale or sb_scale or (None,) * 3)),
        "common_tasks": len(common),
        "only_old": sorted(set(a) - set(b)), "only_new": sorted(set(b) - set(a)),
        "gt_changed": gt_changed,
        "gt_flagged": sorted(t for t in common if 0 in (a[t]["gt_valid"], b[t]["gt_valid"])),
        "incomplete": {old: sorted(t["task_id"] for t in rows_a if t["status"] != "complete"),
                       new: sorted(t["task_id"] for t in rows_b if t["status"] != "complete")},
        "mean_diff": sum(diffs) / len(diffs) if diffs else None,
        "ci95": ci,
        "real_change": bool(ci and (ci[0] > 0 or ci[1] < 0)),
        "critical_regression": sb["critical_step_misses"] > sa["critical_step_misses"],
        "improved": sorted((p for p in per_task if p["diff"] > 0), key=lambda p: -p["diff"]),
        "regressed": sorted((p for p in per_task if p["diff"] < 0), key=lambda p: p["diff"]),
        "per_task": per_task,
    }


def format_report(r: Dict) -> str:
    f = lambda x: "—" if x is None else f"{x:.1f}"  # noqa: E731
    o, n = r["old"], r["new"]
    sc = r["scale"]
    lines = [f"RedScore comparison  {o['gen_version']} → {n['gen_version']}   (rules {r['rules_version']})",
             f"Same scale on both sides: judge {sc['judge']}, rules {str(sc['rules_sha256'])[:10]}, "
             f"scoring code {str(sc['scoring_code_sha256'])[:10]}" if sc["judge"] else
             "Nothing to compare: no task is complete in both versions", ""]
    rows = [
        ("Tasks / runs", f"{o['n_tasks']} / {o['n_runs']}", f"{n['n_tasks']} / {n['n_runs']}"),
        ("Mean Task Score", f(o["mean_task_score"]), f(n["mean_task_score"])),
        ("Mean Base Score", f(o["mean_base_score"]), f(n["mean_base_score"])),
        ("Mean Final if runnable", f(o["mean_final_if_runnable"]), f(n["mean_final_if_runnable"])),
    ]
    rows += [(f"Penalty pts: {k.replace('_', ' ')}", f(o["penalties"][k]), f(n["penalties"][k])) for k in o["penalties"]]
    rows += [("Syntax failures (runs)", str(o["syntax_failures"]), str(n["syntax_failures"])),
             ("Critical-step misses (runs)", str(o["critical_step_misses"]), str(n["critical_step_misses"]))]
    lines += [f"  {a:<30}{b:>12}{c:>12}" for a, b, c in rows]
    lines.append("")
    if r["common_tasks"] and not r["ci95"]:
        lines.append(f"Mean per-task diff {r['mean_diff']:+.1f} over {r['common_tasks']} common task(s); "
                     f"too few tasks for a bootstrap CI (need {MIN_TASKS_FOR_CI})")
    if r["ci95"]:
        lo, hi = r["ci95"]
        verdict = "REAL change" if r["real_change"] else "not significant (CI includes 0)"
        lines.append(f"Mean per-task diff {r['mean_diff']:+.1f}  95% bootstrap CI [{lo:+.1f}, {hi:+.1f}]  → {verdict}"
                     f"  over {r['common_tasks']} common tasks")
    if r["critical_regression"]:
        lines.append("REGRESSION: critical-step misses increased")
    for title, key in (("Improved", "improved"), ("Regressed", "regressed")):
        lines.append(f"\n{title} ({len(r[key])}):")
        lines += [f"  {p['task_id']:<40}{p['old']:>7.1f} → {p['new']:>5.1f}  ({p['diff']:+.1f})" for p in r[key]] or ["  none"]
    if r["only_old"] or r["only_new"]:
        lines.append(f"\nNot compared — only in old: {r['only_old']}  only in new: {r['only_new']}")
    if r["gt_changed"]:
        lines.append(f"Not compared — GT changed between the versions: {r['gt_changed']}")
    if r["gt_flagged"]:
        lines.append(f"GT flagged (compared, but the GT has errors; see each run's gt_issues): {r['gt_flagged']}")
    for version, ts in r["incomplete"].items():
        if ts:
            lines.append(f"Not compared — incomplete in {version} (runs not scored): {ts}")
    return "\n".join(lines)
