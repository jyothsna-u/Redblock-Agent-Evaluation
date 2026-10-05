import json
from pathlib import Path

import pytest

from redscore.checks import check_blocks, out_of_sequence, pair_variables
from redscore.mapping import Mapping, MappingError, Pair, fixture_mapper, validate_mapping
from redscore.parser import parse
from redscore.rules import load_rules
from redscore.scorer import InvalidGroundTruth, load_gt, score_run, task_score

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "tasks" / "venus-jml-create-account"
RULES = load_rules()


def venus_run(run: int) -> dict:
    gt = load_gt((TASK / "gt.redflow").read_text())
    gen = (TASK / "gen" / f"run_{run}.redflow").read_text()
    return score_run(gt, gen, RULES, fixture_mapper(ROOT / "tests/fixtures/venus" / f"mapping_run_{run}.json"))


# ---------------------------------------------------------------- golden: docs/redscore-spec.md worked example

@pytest.mark.parametrize("run,points,slots,base,final,penalties", [
    (1, 7.5, 10, 75.0, 55.0, {"out_of_sequence": 5, "missing_variable": 5, "logic_block": 10, "critical_step": 0}),
    (2, 9.0, 10, 90.0, 90.0, {"out_of_sequence": 0, "missing_variable": 0, "logic_block": 0, "critical_step": 0}),
    (3, 7.0, 9, 77.8, 37.8, {"out_of_sequence": 0, "missing_variable": 0, "logic_block": 10, "critical_step": 30}),
])
def test_venus_runs(run, points, slots, base, final, penalties):
    r = venus_run(run)
    assert r["points"] == pytest.approx(points)
    assert r["slots"] == slots
    assert r["base_display"] == base
    assert r["final_display"] == final
    assert {k: v["points"] for k, v in r["penalties"].items()} == penalties


def test_venus_run1_details():
    r = venus_run(1)
    pts = {s["gt"]: s["points"] for s in r["steps"]}
    assert pts == {1: 1.0, 2: 1.0, 3: 0.7, 4: 1.0, 5: 1.0, 6: 0.8, 7: 1.0, 8: 0.0, 9: 1.0}
    assert r["sequence"]["out_of_sequence_gt"] == [5]
    assert r["variables"]["missing"] == ["role"]
    assert r["variables"]["pairs"] == {"email": "user_email", "legal_first_name": "first_name",
                                       "legal_last_name": "last_name"}
    assert [e["gen"] for e in r["extra"]] == [9]
    assert r["critical_missing"] == []


def test_venus_task_score():
    finals = [venus_run(i)["final"] for i in (1, 2, 3)]
    t = task_score(finals)
    assert t["task_score_display"] == 60.9
    assert t["lowest_display"] == 37.8
    assert venus_run(3)["critical_missing"] == [9]


def test_unmarked_gt_has_no_critical_penalty():
    gt = load_gt((TASK / "gt.redflow").read_text().replace("  # critical", ""))
    assert gt.critical_steps == []
    gen = (TASK / "gen/run_3.redflow").read_text()
    r = score_run(gt, gen, RULES, fixture_mapper(ROOT / "tests/fixtures/venus/mapping_run_3.json"))
    assert r["final_display"] == 67.8
    assert r["critical_missing"] == [] and r["critical_steps"] == []


# ---------------------------------------------------------------- sequence

def _m(pairs):
    return Mapping([Pair(g, n, True, True) for g, n in pairs], [], [], [])


def test_sequence_minimum_steps_out_of_place():
    # GT1's step done last: only GT1 is out of sequence, not every later step.
    assert out_of_sequence(_m([(1, 9)] + [(i, i - 1) for i in range(2, 10)])) == [1]


def test_sequence_swap_flags_the_later_gt_step():
    assert out_of_sequence(_m([(1, 1), (2, 2), (3, 3), (4, 5), (5, 4)])) == [5]


def test_sequence_in_order_and_empty():
    assert out_of_sequence(_m([(1, 2), (2, 5), (3, 7)])) == []
    assert out_of_sequence(_m([])) == []


# ---------------------------------------------------------------- syntax gate + validation of inputs

def test_syntax_error_scores_zero():
    gt = load_gt((TASK / "gt.redflow").read_text())
    r = score_run(gt, 'STEPS\n    - CLICK ON "Invite"\n', RULES, lambda *_: pytest.fail("mapper called"))
    assert r["final"] == 0 and not r["syntax"]["ok"] and r["mapping"] is None


def test_invalid_gt_rejected():
    with pytest.raises(InvalidGroundTruth):
        load_gt('STEPS\n    - CLICK ON "A"\n')


def test_mapping_validation():
    gt = parse((TASK / "gt.redflow").read_text())
    gen = parse((TASK / "gen/run_1.redflow").read_text())
    bad = [
        {"pairs": [{"gt": 1, "gen": 1, "same_element": True, "same_intent": True},
                   {"gt": 2, "gen": 1, "same_element": True, "same_intent": True}]},
        {"pairs": [{"gt": 10, "gen": 1, "same_element": True, "same_intent": True}]},
        {"pairs": [{"gt": 1, "gen": 1, "same_element": "maybe", "same_intent": True}]},
        {"pairs": [], "runtime_blocks": [{"gt_block": "B1", "gen_block": "B1", "same_condition": True}]},
        {},
    ]
    for data in bad:
        with pytest.raises(MappingError):
            validate_mapping(gt, gen, data)
    m = validate_mapping(gt, gen, {"pairs": [{"gt": 1, "gen": 1, "same_element": "yes", "same_intent": "no"}],
                                   "missing_gt": [2]})
    assert m.missing_gt == [2, 3, 4, 5, 6, 7, 8, 9] and m.extra_gen == list(range(2, 10))
    assert m.pairs[0].same_element is True and m.pairs[0].same_intent is False
    assert m.notes  # LLM missing_gt disagreed with pairs


# ---------------------------------------------------------------- variables

def test_variable_tie_broken_by_cooccurrence():
    gt = parse('STEPS\n    - FILL $first INTO "First" INTENT "$first"\n    - FILL $alias INTO "Alias" INTENT "$alias"\n'
               '$first = "john"\n$alias = "john"\n')
    gen = parse('STEPS\n    - FILL $b INTO "First" INTENT "$b"\n    - FILL $a INTO "Alias" INTENT "$a"\n'
                '$a = "john"\n$b = "john"\n')
    v = pair_variables(gt, gen, _m([(1, 1), (2, 2)]))
    assert v.pairs == {"first": "b", "alias": "a"} and v.missing == []


def test_hard_coded_fill_loses_variable_points():
    gt_src = 'STEPS\n    - FILL $name INTO "Name" INTENT "Type $name"\n$name = "john"\n'
    gen_src = 'STEPS\n    - FILL "john" INTO "Name" INTENT "Type john"\n'
    data = {"pairs": [{"gt": 1, "gen": 1, "same_element": True, "same_intent": True}]}
    r = score_run(load_gt(gt_src), gen_src, RULES, lambda gt, gen: validate_mapping(gt, gen, data))
    assert r["steps"][0]["variables"] == 0.0
    assert r["variables"]["missing"] == ["name"]
    assert r["final"] == pytest.approx(80 - 5)


def test_for_each_loop_variables_pair_through_list():
    gt = parse('STEPS\n    - FOR_EACH $role IN $roles\n        - CLICK ON "$role box" INTENT "Pick $role"\n'
               '$roles = ["a", "b"]\n')
    gen = parse('STEPS\n    - FOR_EACH $r IN $role_list\n        - CLICK ON "$r checkbox" INTENT "Pick $r"\n'
                '$role_list = ["a", "b"]\n')
    m = _m([(1, 1)])
    v = pair_variables(gt, gen, m)
    assert v.pairs == {"roles": "role_list", "role": "r"}
    assert all(b.ok for b in check_blocks(gt, gen, m, v.pairs))


# ---------------------------------------------------------------- logic blocks

GT_IF = ('STEPS\n    - CLICK ON "A" INTENT "a"\n    - IF $t EQUALS "x"\n        - CLICK ON "B" INTENT "b"\n'
         '    - ELSE\n        - CLICK ON "C" INTENT "c"\n$t = "x"\n')


def _blocks(gen_src, pairs, runtime=None, gt_src=GT_IF):
    gt, gen = parse(gt_src), parse(gen_src)
    m = Mapping([Pair(g, n, True, True) for g, n in pairs], runtime or [], [], [])
    return check_blocks(gt, gen, m, pair_variables(gt, gen, m).pairs)


def test_block_matches_with_renamed_variable():
    gen = ('STEPS\n    - CLICK ON "A" INTENT "a"\n    - IF $type EQUALS "x"\n        - CLICK ON "B" INTENT "b"\n'
           '    - ELSE\n        - CLICK ON "C" INTENT "c"\n$type = "x"\n')
    assert [b.ok for b in _blocks(gen, [(1, 1), (2, 2), (3, 3)])] == [True]


GT_ELIF = ('STEPS\n    - IF $d EQUALS "Sales"\n        - CLICK ON "A" INTENT "a"\n'
           '    - ELIF $d EQUALS "Support"\n        - CLICK ON "B" INTENT "b"\n'
           '    - ELSE\n        - CLICK ON "C" INTENT "c"\n$d = "Support"\n')


def test_elif_matches_the_same_chain_and_an_explicit_nested_if():
    nested = ('STEPS\n    - IF $dept EQUALS "Sales"\n        - CLICK ON "A" INTENT "a"\n    - ELSE\n'
              '        - IF $dept EQUALS "Support"\n            - CLICK ON "B" INTENT "b"\n'
              '        - ELSE\n            - CLICK ON "C" INTENT "c"\n$dept = "Support"\n')
    for gen in (GT_ELIF, nested):
        assert [b.ok for b in _blocks(gen, [(1, 1), (2, 2), (3, 3)], gt_src=GT_ELIF)] == [True, True]


def test_elif_with_wrong_condition_costs_one_block():
    gen = GT_ELIF.replace('ELIF $d EQUALS "Support"', 'ELIF $d EQUALS "Help"')
    assert [b.ok for b in _blocks(gen, [(1, 1), (2, 2), (3, 3)], gt_src=GT_ELIF)] == [True, False]


def test_in_condition_compares_both_variables():
    gt = ('STEPS\n    - IF $region IN $eu\n        - CLICK ON "A" INTENT "a"\n'
          '$region = "Germany"\n$eu = ["Germany", "France"]\n')
    same = gt.replace("$region", "$country").replace("$eu", "$eu_list")
    other = gt + '$apac = ["Japan"]\n'
    other = other.replace("IF $region IN $eu", "IF $region IN $apac")
    assert [b.ok for b in _blocks(same, [(1, 1)], gt_src=gt)] == [True]
    assert [b.ok for b in _blocks(other, [(1, 1)], gt_src=gt)] == [False]


def test_grab_targets_pair_through_their_steps():
    gt = ('STEPS\n    - GRAB "the keyword" INTO $kw INTENT "Read the keyword"\n'
          '    - FILL $kw INTO "Confirm box" INTENT "Type $kw"\n')
    gen = ('STEPS\n    - GRAB "the confirmation word" INTO $word INTENT "Read it"\n'
           '    - FILL $word INTO "Confirm input" INTENT "Type $word"\n')
    g, n = parse(gt), parse(gen)
    m = Mapping([Pair(1, 1, True, True), Pair(2, 2, True, True)], [], [], [])
    v = pair_variables(g, n, m)
    assert v.pairs == {"kw": "word"} and v.missing == []
    r = score_run(load_gt(gt), gen, RULES, lambda a, b: m)
    assert r["final"] == 100.0


def test_map_loop_variables_pair_through_the_map():
    gt = (ROOT / "tests/fixtures/syntax_ref/l_map_loop.redflow").read_text()
    gen = (gt.replace("$account", "$acct").replace("$permissions", "$perms")
           .replace("$permission ", "$perm ").replace("$permission\"", "$perm\"").replace("$access", "$grants"))
    g, n = parse(gt), parse(gen)
    m = Mapping([Pair(1, 1, True, True)], [], [], [])
    v = pair_variables(g, n, m)
    assert v.pairs == {"access": "grants", "permissions": "perms", "account": "acct", "permission": "perm"}
    assert all(b.ok for b in check_blocks(g, n, m, v.pairs))


def test_execute_parallel_does_not_change_the_block_match():
    gt = 'STEPS\n    - FOR_EACH $r IN $roles EXECUTE_PARALLEL\n        - CLICK ON "$r" INTENT "Tick $r"\n$roles = ["a"]\n'
    gen = gt.replace(" EXECUTE_PARALLEL", "")
    assert [b.ok for b in _blocks(gen, [(1, 1)], gt_src=gt)] == [True]


def test_block_wrong_condition():
    gen = ('STEPS\n    - CLICK ON "A" INTENT "a"\n    - IF $t EQUALS "y"\n        - CLICK ON "B" INTENT "b"\n'
           '    - ELSE\n        - CLICK ON "C" INTENT "c"\n$t = "x"\n')
    r = _blocks(gen, [(1, 1), (2, 2), (3, 3)])
    assert not r[0].ok and "same condition" in r[0].reason


def test_block_step_outside_and_missing_else():
    gen = ('STEPS\n    - CLICK ON "A" INTENT "a"\n    - IF $t EQUALS "x"\n        - CLICK ON "B" INTENT "b"\n'
           '    - CLICK ON "C" INTENT "c"\n$t = "x"\n')
    r = _blocks(gen, [(1, 1), (2, 2), (3, 3)])
    assert not r[0].ok and "GT3 (else)" in r[0].reason


def test_runtime_blocks_use_llm_verdict():
    from redscore.mapping import RuntimeBlockPair
    gt = 'STEPS\n    - WHEN "a cookie banner is visible"\n        - CLICK ON "Accept" INTENT "a"\n'
    gen = 'STEPS\n    - WHEN "the cookie consent popup shows"\n        - CLICK ON "Accept all" INTENT "a"\n'
    ok = _blocks(gen, [(1, 1)], [RuntimeBlockPair("B1", "B1", True)], gt_src=gt)
    bad = _blocks(gen, [(1, 1)], [RuntimeBlockPair("B1", "B1", False)], gt_src=gt)
    none = _blocks(gen, [(1, 1)], [], gt_src=gt)
    assert [ok[0].ok, bad[0].ok, none[0].ok] == [True, False, False]


# ---------------------------------------------------------------- extraction

def test_extraction_is_scored_as_partial():
    src = (ROOT / "tests/fixtures/syntax_ref/x_b_pre_steps.redflow").read_text()
    data = {"pairs": [{"gt": 1, "gen": 1, "same_element": True, "same_intent": True}]}
    r = score_run(load_gt(src), src, RULES, lambda gt, gen: validate_mapping(gt, gen, data))
    assert r["partial"] and r["final"] == 100.0
