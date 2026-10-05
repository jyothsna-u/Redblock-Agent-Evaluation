"""RedScore v0.1 - compare a generated redflow (GEN) against a ground-truth redflow (GT).

Action scripts only (Create / Update / Activate / Deactivate / Remove / entitlement Skills).
Usage:  python redscore.py gt.redflow gt.params gen.redflow gen.params
"""
import re, sys, json
from dataclasses import dataclass, field

# ------------------------------------------------------------------ config (versioned with every score)
CONFIG = {
    "version": "redscore-0.1",
    "w_step": {"action": 0.30, "target": 0.40, "vars": 0.20, "block": 0.10},
    "w_total": {"step_f1": 0.55, "structure": 0.15, "params": 0.10, "order": 0.10, "url": 0.10},
    "match_threshold": 0.50,       # tau: min S(g,p) for two steps to be paired
    "order_threshold": 0.80,       # tau_o: missed+extra pair this similar = ORDER_ERROR
    "dice_sure_high": 0.80,        # >= : trust the text similarity, no judge
    "dice_sure_low": 0.30,         # <= : trust the text similarity, no judge
    "pass_score": 90.0,
    "action_partial": {frozenset({"FILL", "FILL_AND_ENTER"}): 0.7,
                       frozenset({"SELECT", "CLICK"}): 0.5,
                       frozenset({"HOVER", "CLICK"}): 0.3},
    "stopwords": {"the", "a", "an", "on", "in", "at", "of", "for", "to", "this", "that", "with"},
    "synonyms": {"box": "field", "input": "field", "textbox": "field", "textfield": "field", "btn": "button"},
}

# Cached LLM-judge answers: (normalised GT target, normalised GEN target) -> 0 / 0.5 / 1.
# In production this is filled by a pinned judge model at temperature 0 and stored, so re-scoring is identical.
JUDGE_CACHE = {}


# ------------------------------------------------------------------ parsing
@dataclass
class Step:
    idx: int
    action: str
    target: str
    vars: set
    block: tuple            # enclosing IF/FOR_EACH/WHEN chain, e.g. ('IF $role EQUALS "Custom"',)
    weight: float = 1.0
    raw: str = ""

@dataclass
class Redflow:
    url: str = ""
    steps: list = field(default_factory=list)
    blocks: list = field(default_factory=list)   # block headers
    params: dict = field(default_factory=dict)   # name -> (default, optional)

ACTION_RE = [
    ("CLICK", re.compile(r'CLICK ON "(?P<t>[^"]*)"')),
    ("HOVER", re.compile(r'HOVER ON "(?P<t>[^"]*)"')),
    ("FILL_AND_ENTER", re.compile(r'FILL_AND_ENTER (?P<v>\$\w+) INTO "(?P<t>[^"]*)"')),
    ("FILL", re.compile(r'FILL (?P<v>\$\w+) INTO "(?P<t>[^"]*)"')),
    ("SELECT", re.compile(r'SELECT (?P<v>\$\w+) FROM "(?P<t>[^"]*)"')),
    ("GOTO", re.compile(r'GOTO "(?P<t>[^"]*)"')),
]
BLOCK_RE = re.compile(r'^(IF|ELSE|FOR_EACH|WHEN|UNTIL)\b(.*)$')

def parse_redflow(text, params_text="", critical=()):
    rf = Redflow()
    stack = []  # (indent, header)
    n = 0
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        s = line.strip()
        if s.startswith("URL "):
            rf.url = s[4:].strip().strip('"'); continue
        if s == "STEPS":
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = s[1:].strip() if s.startswith("-") else s
        while stack and stack[-1][0] >= indent:
            stack.pop()
        m = BLOCK_RE.match(body)
        if m:
            header = " ".join(body.split())
            rf.blocks.append(header)
            stack.append((indent, header))
            continue
        for act, rx in ACTION_RE:
            mm = rx.search(body)
            if mm:
                n += 1
                v = set(re.findall(r"\$\w+", mm.group("t")))
                if "v" in mm.groupdict() and mm.group("v"):
                    v.add(mm.group("v"))
                rf.steps.append(Step(n, act, mm.group("t"), v, tuple(h for _, h in stack),
                                     2.0 if n in critical else 1.0, body))
                break
    for line in params_text.splitlines():
        mm = re.match(r'\s*(\$\w+)(\?)?\s*=\s*(.+)$', line)
        if mm:
            rf.params[mm.group(1)] = (mm.group(3).strip().strip('"'), bool(mm.group(2)))
    return rf


# ------------------------------------------------------------------ step 1: variable mapping
def map_variables(gt, gen):
    """GEN var -> GT var, by equal default value, then by name similarity."""
    mapping, used = {}, set()
    for gv, (gval, _) in gen.params.items():
        for tv, (tval, _) in gt.params.items():
            if tv not in used and gval == tval:
                mapping[gv] = tv; used.add(tv); break
    for gv in gen.params:
        if gv in mapping: continue
        best = max((t for t in gt.params if t not in used),
                   key=lambda t: dice(tokens(gv[1:].replace("_", " ")), tokens(t[1:].replace("_", " "))), default=None)
        if best and dice(tokens(gv[1:].replace("_", " ")), tokens(best[1:].replace("_", " "))) >= 0.5:
            mapping[gv] = best; used.add(best)
    return mapping

def rename(rf, mapping):
    for st in rf.steps:
        st.vars = {mapping.get(v, v) for v in st.vars}
        for a, b in mapping.items():
            st.target = st.target.replace(a, b)
    rf.blocks = [" ".join(mapping.get(w, w) for w in b.split()) for b in rf.blocks]
    for st in rf.steps:
        st.block = tuple(" ".join(mapping.get(w, w) for w in b.split()) for b in st.block)
    rf.params = {mapping.get(k, k): v for k, v in rf.params.items()}


# ------------------------------------------------------------------ step 2: similarity
def tokens(text, params=None):
    if params:  # substitute $var -> its default value so descriptions compare like the live page
        for k, (v, _) in params.items():
            text = text.replace(k, v)
    out = []
    for w in re.findall(r"[a-z0-9@._]+", text.lower()):
        w = CONFIG["synonyms"].get(w, w)
        if w not in CONFIG["stopwords"]:
            out.append(w)
    return set(out)

def dice(a, b):
    return 1.0 if not a and not b else 2 * len(a & b) / (len(a) + len(b))

def target_score(g, p, gt_params, trace):
    a, b = tokens(g.target, gt_params), tokens(p.target, gt_params)
    d = dice(a, b)
    if d >= CONFIG["dice_sure_high"] or d <= CONFIG["dice_sure_low"]:
        trace["target_src"] = "text"; return d
    key = (" ".join(sorted(a)), " ".join(sorted(b)))
    trace["target_src"] = "judge"; trace["dice"] = d
    return JUDGE_CACHE.get(key, d)

def action_score(a, b):
    return 1.0 if a == b else CONFIG["action_partial"].get(frozenset({a, b}), 0.0)

def vars_score(g, p):
    if not g.vars and not p.vars: return 1.0
    return len(g.vars & p.vars) / len(g.vars | p.vars)

def step_sim(g, p, gt_params):
    tr = {}
    A = action_score(g.action, p.action)
    T = target_score(g, p, gt_params, tr)
    V = vars_score(g, p)
    B = 1.0 if g.block == p.block else 0.0
    w = CONFIG["w_step"]
    S = w["action"] * A + w["target"] * T + w["vars"] * V + w["block"] * B
    return S, dict(A=A, T=T, V=V, B=B, **tr)


# ------------------------------------------------------------------ step 3: alignment (weighted LCS)
def align(gt_steps, gen_steps, gt_params):
    n, m, tau = len(gt_steps), len(gen_steps), CONFIG["match_threshold"]
    S = [[step_sim(g, p, gt_params) for p in gen_steps] for g in gt_steps]
    M = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(M[i - 1][j], M[i][j - 1])
            s = S[i - 1][j - 1][0]
            if s >= tau:
                best = max(best, M[i - 1][j - 1] + gt_steps[i - 1].weight * s)
            M[i][j] = best
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        s = S[i - 1][j - 1][0]
        if s >= tau and abs(M[i][j] - (M[i - 1][j - 1] + gt_steps[i - 1].weight * s)) < 1e-9:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif abs(M[i][j] - M[i - 1][j]) < 1e-9:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    matched_g = {a for a, _ in pairs}; matched_p = {b for _, b in pairs}
    missed = [i for i in range(n) if i not in matched_g]
    extra = [j for j in range(m) if j not in matched_p]
    order_err = []
    for i in list(missed):                       # post-pass: captured but in the wrong place
        for j in list(extra):
            if S[i][j][0] >= CONFIG["order_threshold"]:
                order_err.append((i, j)); missed.remove(i); extra.remove(j); break
    return S, M, pairs, missed, extra, order_err


# ------------------------------------------------------------------ step 4: score
def f1(p, r):
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)

def block_sig(b):
    return " ".join(b.split())

def score(gt_text, gt_params, gen_text, gen_params, critical=(), syntax_ok=True):
    gt = parse_redflow(gt_text, gt_params, critical)
    gen = parse_redflow(gen_text, gen_params)
    mapping = map_variables(gt, gen)
    rename(gen, mapping)
    S, M, pairs, missed, extra, order_err = align(gt.steps, gen.steps, gt.params)

    # GEN steps inherit the weight of the GT step they matched; unmatched GEN steps weigh 1
    gen_w = {j: 1.0 for j in range(len(gen.steps))}
    for i, j in pairs + order_err:
        gen_w[j] = gt.steps[i].weight
    credit = sum(gt.steps[i].weight * S[i][j][0] for i, j in pairs + order_err)
    W_gt = sum(s.weight for s in gt.steps)
    W_gen = sum(gen_w.values())
    coverage, precision = credit / W_gt, credit / W_gen if W_gen else 0.0
    step_f1 = f1(precision, coverage)

    gb, pb = [block_sig(b) for b in gt.blocks], [block_sig(b) for b in gen.blocks]
    mb = sum(1 for b in gb if b in pb)
    structure = 1.0 if not gb and not pb else f1(mb / len(pb) if pb else 0.0, mb / len(gb) if gb else 0.0)

    gv, pv = set(gt.params), set(gen.params)
    mv = len(gv & pv)
    params = 1.0 if not gv and not pv else f1(mv / len(pv) if pv else 0.0, mv / len(gv) if gv else 0.0)

    n_match = len(pairs) + len(order_err)
    order = 1.0 if n_match == 0 else 1 - len(order_err) / n_match

    gu, pu = gt.url.split("?")[0].split("#")[0].rstrip("/"), gen.url.split("?")[0].split("#")[0].rstrip("/")
    url = 1.0 if gu == pu else (0.5 if gu.split("/")[2:3] == pu.split("/")[2:3] else 0.0)

    w = CONFIG["w_total"]
    red = 100 * (1 if syntax_ok else 0) * (w["step_f1"] * step_f1 + w["structure"] * structure +
                                            w["params"] * params + w["order"] * order + w["url"] * url)
    critical_missed = [gt.steps[i].idx for i in missed if gt.steps[i].weight >= 2]
    hardcoded = []
    for i, j in pairs + order_err:
        for v in gt.steps[i].vars - gen.steps[j].vars:
            if gt.params.get(v, ("",))[0].lower() in gen.steps[j].target.lower():
                hardcoded.append((gt.steps[i].idx, v))
    verdict = "FAIL (critical step missed)" if critical_missed else ("PASS" if red >= CONFIG["pass_score"] else "FAIL")
    return dict(gt=gt, gen=gen, mapping=mapping, S=S, M=M, pairs=pairs, missed=missed, extra=extra,
                order_err=order_err, credit=credit, W_gt=W_gt, W_gen=W_gen, coverage=coverage,
                precision=precision, step_f1=step_f1, structure=structure, params=params, order=order,
                url=url, redscore=red, critical_missed=critical_missed, hardcoded=hardcoded, verdict=verdict)
