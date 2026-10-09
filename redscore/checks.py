"""RedScore step 2 code checks: variables, sequence, logic blocks."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .mapping import Mapping
from .parser import RUNTIME_KINDS, Action, Block, Script, vars_in


# ---------------------------------------------------------------- variables

@dataclass
class VariableResult:
    pairs: Dict[str, str]          # GT name -> GEN name (defined vars, GRAB targets, FOR_EACH loop vars)
    missing: List[str]             # GT defined vars with no GEN partner of the same value (GRAB/loop vars excluded)
    unpaired_gen: List[str]        # GEN defined vars with no GT partner (informational)
    mismatched: Dict[str, str] = field(default_factory=dict)   # missing GT var -> GEN var paired through steps


def pair_variables(gt: Script, gen: Script, mapping: Mapping) -> VariableResult:
    """Pair GEN and GT variables by identical default value, then through the steps that use them.

    Value pairing: ties (several variables with the same value) are broken by how often the two
    variables appear together in mapped step pairs, then by name similarity. A GT variable without a
    same-value partner is a missing variable (-5).
    Step pairing (decision 2026-10-06): a variable whose sample value was transcribed differently is still
    paired through the mapped steps and loops that use it, so it costs only the missing-variable penalty
    and does not also fail every step and logic block that uses it. It is reported in `mismatched`.
    """
    cooccur: Dict[Tuple[str, str], int] = {}
    for p in mapping.pairs:
        for g in gt.action(p.gt).all_vars():
            for n in gen.action(p.gen).all_vars():
                cooccur[(g, n)] = cooccur.get((g, n), 0) + 1

    candidates = []
    for g, gv in gt.variables.items():
        for n, nv in gen.variables.items():
            if _norm_value(gv.value) == _norm_value(nv.value):
                sim = difflib.SequenceMatcher(None, g, n).ratio()
                candidates.append((cooccur.get((g, n), 0), sim, g, n))
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2], c[3]))

    pairs: Dict[str, str] = {}
    taken: Set[str] = set()
    for _, _, g, n in candidates:
        if g not in pairs and n not in taken:
            pairs[g] = n
            taken.add(n)

    same_value = set(pairs)

    # GRAB targets have no default value; they pair through their mapped GRAB steps.
    ordered = sorted(mapping.pairs, key=lambda p: p.gt)
    for p in ordered:
        g, n = gt.action(p.gt).grab_var, gen.action(p.gen).grab_var
        if g and n and g not in pairs and n not in taken:
            pairs[g] = n
            taken.add(n)

    def link(g: str, n: str) -> bool:
        if g in pairs or n in taken or not _same_kind(gt, g, gen, n):
            return False
        pairs[g] = n
        taken.add(n)
        return True

    gen_loops = [nb for nb in gen.blocks if nb.kind == "FOR_EACH"]
    changed = True
    while changed:
        changed = False
        # FOR_EACH loop variables (and a map loop's $key) pair through their paired list / map variables.
        # Document order, so an outer map loop's $value is paired before a nested loop over it.
        for gb in (b for b in gt.blocks if b.kind == "FOR_EACH"):
            if gb.list_var in pairs and gb.item_var not in pairs:
                for nb in gen_loops:
                    if nb.list_var == pairs[gb.list_var] and bool(nb.key_var) == bool(gb.key_var) and link(gb.item_var, nb.item_var):
                        if gb.key_var:
                            link(gb.key_var, nb.key_var)
                        changed = True
                        break
            # ...and the other way round: loops whose items pair have paired lists.
            if gb.item_var in pairs and gb.list_var not in pairs:
                for nb in gen_loops:
                    if nb.item_var == pairs[gb.item_var] and link(gb.list_var, nb.list_var):
                        changed = True
                        break
        # A mapped step pair whose only unpaired variables are one on each side pairs them.
        for p in ordered:
            g_free = [v for v in gt.action(p.gt).action_vars() if v not in pairs]
            n_free = [v for v in gen.action(p.gen).action_vars() if v not in taken]
            if len(g_free) == 1 and len(n_free) == 1 and link(g_free[0], n_free[0]):
                changed = True

    # A GT variable no GT step uses is a GT mistake (flagged in gt_issues), not something the GEN can miss.
    used = _used_vars(gt)
    missing = [g for g in gt.variables if g not in same_value and g in used]
    mismatched = {g: pairs[g] for g in missing if g in pairs}
    unpaired_gen = [n for n in gen.variables if n not in taken]
    return VariableResult(pairs, missing, unpaired_gen, mismatched)


def _used_vars(script: Script) -> Set[str]:
    used: Set[str] = set()
    for a in script.actions:
        used.update(a.all_vars())
    for b in script.blocks:
        used.update(v for v in (b.var, b.rhs_var, b.list_var) if v)
        used.update(vars_in(b.condition) + vars_in(b.text if b.malformed else ""))
    return used


def _same_kind(gt: Script, g: str, gen: Script, n: str) -> bool:
    """Input variables pair only with input variables of the same kind; loop and GRAB variables with each other."""
    gk = gt.variables[g].kind if g in gt.variables else "local"
    nk = gen.variables[n].kind if n in gen.variables else "local"
    return gk == nk or ("empty" in (gk, nk) and "local" not in (gk, nk))


def _norm_value(v):
    if isinstance(v, dict):
        return tuple(sorted((k.strip(), _norm_value(x)) for k, x in v.items()))
    if isinstance(v, list):
        return tuple(x.strip() for x in v)
    return v.strip() if isinstance(v, str) else v


def step_variables_ok(gt_step: Action, gen_step: Action, gt: Script, var_pairs: Dict[str, str]) -> Tuple[bool, str]:
    """0.2 parameter: same variables after mapping, nothing hard-coded.

    Compares the variables used by the action itself (value + element). A step that
    uses no variables on either side passes.
    """
    gt_vars = gt_step.action_vars()
    gen_vars = set(gen_step.action_vars())
    unmapped = [v for v in gt_vars if v not in var_pairs]
    if unmapped:
        reason = "GT variable(s) with no GEN partner: " + ", ".join("$" + v for v in unmapped)
        hc = _hard_coded(gt_step, gen_step, gt)
        return False, reason + (f"; hard-coded {hc}" if hc else "")
    expected = {var_pairs[v] for v in gt_vars}
    if expected != gen_vars:
        hc = _hard_coded(gt_step, gen_step, gt)
        return False, (f"expected {sorted('$' + v for v in expected)}, "
                       f"GEN uses {sorted('$' + v for v in gen_vars)}" + (f"; hard-coded {hc}" if hc else ""))
    # GEN uses exactly the mapped variables, so nothing is hard-coded: a GT value such as "User" that also
    # appears as an ordinary word in the GEN element text is not a hard-coded value.
    return True, ""


def _hard_coded(gt_step: Action, gen_step: Action, gt: Script) -> Optional[str]:
    """A GT variable's default value written literally into the GEN step."""
    gen_text = " ".join(x for x in (gen_step.value_literal, gen_step.element) if x)
    for v in gt_step.action_vars():
        var = gt.variables.get(v)
        if var is None or not isinstance(var.value, str) or not var.value.strip():
            continue
        if re.search(r"(?<![\w])" + re.escape(var.value.strip()) + r"(?![\w])", gen_text, re.IGNORECASE):
            return f'"{var.value}" (GT ${v})'
    return None


# ---------------------------------------------------------------- sequence

def out_of_sequence(mapping: Mapping) -> List[int]:
    """GT step numbers that are out of sequence.

    Pairs are read in GT order; the longest run whose GEN numbers keep rising is in
    sequence, every other pair is out of sequence (minimum number of steps out of
    place). Among equally long runs, the one keeping the earliest GT steps wins, so a
    step pulled forward flags the step it jumped ahead of (spec example: GT5).
    """
    pairs = sorted(mapping.pairs, key=lambda p: p.gt)
    gens = [p.gen for p in pairs]
    n = len(gens)
    best = [1] * n                       # longest rising run starting at i
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n):
            if gens[j] > gens[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
    keep: Set[int] = set()
    need = max(best, default=0)
    last = 0
    for i in range(n):
        if need and best[i] == need and gens[i] > last:
            keep.add(i)
            last = gens[i]
            need -= 1
    return [pairs[i].gt for i in range(n) if i not in keep]


# ---------------------------------------------------------------- logic blocks

@dataclass
class BlockResult:
    gt_block: str
    kind: str
    condition: str
    gen_block: Optional[str]
    ok: bool
    reason: str = ""


def _branch_steps(script: Script, block_id: str, branch: str) -> Set[int]:
    return {a.num for a in script.actions if (block_id, branch) in a.path}


def _condition_same(gb: Block, nb: Block, var_pairs: Dict[str, str], runtime: Dict[Tuple[str, str], bool]) -> bool:
    if gb.kind == "IF":
        return (var_pairs.get(gb.var) == nb.var and gb.op == nb.op
                and (gb.literal or "") == (nb.literal or "")
                and (var_pairs.get(gb.rhs_var) == nb.rhs_var if gb.rhs_var else nb.rhs_var is None))
    if gb.kind == "FOR_EACH":
        # EXECUTE_PARALLEL only changes how the iterations are batched, not which steps run for which values.
        return var_pairs.get(gb.list_var) == nb.list_var
    return runtime.get((gb.id, nb.id), False)


def _containment(gt: Script, gen: Script, gb: Block, nb: Block, mapping: Mapping) -> List[str]:
    g2n = {p.gt: p.gen for p in mapping.pairs}
    n2g = {p.gen: p.gt for p in mapping.pairs}
    problems = []
    for branch in ("then", "else"):
        gt_in = _branch_steps(gt, gb.id, branch)
        gen_in = _branch_steps(gen, nb.id, branch)
        for g in sorted(gt_in):
            if g in g2n and g2n[g] not in gen_in:
                problems.append(f"GT{g} ({branch}) is paired with GEN{g2n[g]}, which is outside the GEN {branch} branch")
        for n in sorted(gen_in):
            if n in n2g and n2g[n] not in gt_in:
                problems.append(f"GEN{n} is inside the GEN {branch} branch but its GT partner GT{n2g[n]} is not")
    return problems


def check_blocks(gt: Script, gen: Script, mapping: Mapping, var_pairs: Dict[str, str]) -> List[BlockResult]:
    """Every GT logic block must exist in GEN with the same condition and contain its steps."""
    runtime = {(r.gt_block, r.gen_block): r.same_condition for r in mapping.runtime_blocks}
    used: Set[str] = set()
    results = []
    for gb in gt.blocks:
        if gb.malformed:     # the GT block itself is not valid redflow: flagged in gt_issues, not charged to the GEN
            results.append(BlockResult(gb.id, gb.kind, gb.condition_text(), None, True,
                                       "not checked: this GT block is not valid redflow (GT flagged)"))
            continue
        cands = [nb for nb in gen.blocks if nb.kind == gb.kind and nb.id not in used]
        same_cond = [nb for nb in cands if _condition_same(gb, nb, var_pairs, runtime)]
        if not cands:
            results.append(BlockResult(gb.id, gb.kind, gb.condition_text(), None, False,
                                       f"no {gb.kind} block in GEN"))
            continue
        if not same_cond:
            results.append(BlockResult(gb.id, gb.kind, gb.condition_text(), None, False,
                                       f"no GEN {gb.kind} block with the same condition"))
            continue
        scored = sorted(((len(_containment(gt, gen, gb, nb, mapping)), i, nb) for i, nb in enumerate(same_cond)),
                        key=lambda x: (x[0], x[1]))
        _, _, nb = scored[0]
        used.add(nb.id)
        problems = _containment(gt, gen, gb, nb, mapping)
        results.append(BlockResult(gb.id, gb.kind, gb.condition_text(), nb.id, not problems,
                                   "; ".join(problems)))
    return results
