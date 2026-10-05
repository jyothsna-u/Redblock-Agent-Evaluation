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


def version_summary(store: Store, gen_version: str, rules_version: str) -> Dict:
    tasks = store.tasks(gen_version, rules_version)
    runs = store.runs(gen_version, rules_version)
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return {
        "gen_version": gen_version,
        "n_tasks": len(tasks),
        "n_runs": len(runs),
        "mean_task_score": mean([t["task_score"] for t in tasks]),
        "mean_base_score": mean([r["base"] for r in runs]),
        "penalties": {k: sum(r[f"pen_{k}"] for r in runs)
                      for k in ("out_of_sequence", "missing_variable", "logic_block", "critical_step")},
        "syntax_failures": sum(1 for r in runs if not r["syntax_ok"]),
        "critical_step_misses": sum(1 for r in runs if r["critical_missing"] not in ("[]", None)),
        "partial_runs": sum(1 for r in runs if r["partial"]),
    }


MIN_TASKS_FOR_CI = 5   # below this the bootstrap interval is not meaningful


def compare(store: Store, old: str, new: str, rules_version: str) -> Dict:
    a = {t["task_id"]: t for t in store.tasks(old, rules_version)}
    b = {t["task_id"]: t for t in store.tasks(new, rules_version)}
    common = sorted(set(a) & set(b))
    per_task = [{"task_id": t, "old": a[t]["task_score"], "new": b[t]["task_score"],
                 "diff": b[t]["task_score"] - a[t]["task_score"],
                 "old_lowest": a[t]["lowest"], "new_lowest": b[t]["lowest"]} for t in common]
    diffs = [p["diff"] for p in per_task]
    ci = bootstrap_ci(diffs) if len(diffs) >= MIN_TASKS_FOR_CI else None
    sa, sb = version_summary(store, old, rules_version), version_summary(store, new, rules_version)
    return {
        "rules_version": rules_version,
        "old": sa, "new": sb,
        "common_tasks": len(common),
        "only_old": sorted(set(a) - set(b)), "only_new": sorted(set(b) - set(a)),
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
    lines = [f"RedScore comparison  {o['gen_version']} → {n['gen_version']}   (rules {r['rules_version']})", ""]
    rows = [
        ("Tasks / runs", f"{o['n_tasks']} / {o['n_runs']}", f"{n['n_tasks']} / {n['n_runs']}"),
        ("Mean Task Score", f(o["mean_task_score"]), f(n["mean_task_score"])),
        ("Mean Base Score", f(o["mean_base_score"]), f(n["mean_base_score"])),
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
    return "\n".join(lines)
