from pathlib import Path

import pytest

from redscore.parser import parse
from redscore.validator import errors, validate

ROOT = Path(__file__).resolve().parent.parent
SYNTAX_REF = sorted((ROOT / "tests" / "fixtures" / "syntax_ref").glob("*.redflow"))
VENUS_GT = (ROOT / "tasks" / "venus-jml-create-account" / "gt.redflow").read_text()


@pytest.mark.parametrize("path", SYNTAX_REF, ids=lambda p: p.stem)
def test_syntax_reference_examples_are_valid(path):
    assert errors(validate(path.read_text())) == []


def test_venus_gt_structure():
    s = parse(VENUS_GT)
    assert len(s.actions) == 9
    assert [b.id for b in s.blocks] == ["B1"]
    b = s.blocks[0]
    assert (b.kind, b.var, b.op, b.literal) == ("IF", "role", "EQUALS", "Custom")
    assert [a.num for a in s.actions if ("B1", "then") in a.path] == [8]
    assert s.action(6).action_vars() == ["role"]
    assert s.variables["role"].value == "Admin"
    assert s.critical_steps == [9]


@pytest.mark.parametrize("comment,critical", [
    ("# critical", True), ("#critical", True), ("# Critical: final submit", True),
    ("# not critical", False), ("# criticality", False), ("", False),
])
def test_critical_marker(comment, critical):
    s = parse(f'STEPS\n    - CLICK ON "Save" INTENT "Save the user"  {comment}\n')
    assert s.critical_steps == ([1] if critical else [])


def test_critical_marker_inside_quotes_is_not_a_comment():
    s = parse('STEPS\n    - CLICK ON "Save # critical" INTENT "Save"\n')
    assert s.critical_steps == [] and s.actions[0].element == "Save # critical"


def test_misplaced_critical_marker_warns():
    src = ('STEPS\n    # critical\n    - CLICK ON "Save" INTENT "Save"\n'
           '    - IF $x EQUALS "a"  # critical\n        - CLICK ON "B" INTENT "b"\n$x = "a"\n')
    s = parse(src)
    assert s.critical_steps == []
    warns = [i for i in validate(s) if i.code == "W_CRITICAL_PLACEMENT"]
    assert [w.line for w in warns] == [2, 4] and all(w.severity == "warning" for w in warns)


def test_else_and_operators():
    s = parse('STEPS\n    - IF $x NOT_EQUALS "a"\n        - CLICK ON "A" INTENT "a"\n    - ELSE\n'
              '        - CLICK ON "B" INTENT "b"\n$x = "a"\n')
    b = s.blocks[0]
    assert b.op == "NOT_EQUALS"
    assert [a.path for a in s.actions] == [(("B1", "then"),), (("B1", "else"),)]


def test_elif_is_an_if_inside_the_previous_else():
    s = parse((ROOT / "tests/fixtures/syntax_ref/g_elif.redflow").read_text())
    b1, b2 = s.blocks
    assert (b2.kind, b2.is_elif, b2.path) == ("IF", True, (("B1", "else"),))
    assert b2.condition_text() == 'ELIF $department EQUALS "Support"'
    assert [a.path for a in s.actions] == [(("B1", "then"),), (("B1", "else"), ("B2", "then")),
                                           (("B1", "else"), ("B2", "else"))]


def test_new_constructs_parse():
    s = parse((ROOT / "tests/fixtures/syntax_ref/l_map_loop.redflow").read_text())
    assert s.variables["access"].kind == "map"
    assert s.variables["access"].value["Operating"] == ["Send money"]
    assert s.variables["access"].value["Archive"] == []
    outer = s.blocks[0]
    assert (outer.key_var, outer.item_var, outer.list_var) == ("account", "permissions", "access")
    s = parse((ROOT / "tests/fixtures/syntax_ref/j_grab.redflow").read_text())
    grabs = [a for a in s.actions if a.grab_var]
    assert [(a.keyword, a.grab_var, a.grab_list) for a in grabs] == [
        ("GRAB", "confirm_kw", False), ("GRAB", "status", False), ("GRAB ALL", "subs", True)]
    assert grabs[1].possible_values == ["Active", "Suspended"] and grabs[0].action_vars() == []
    s = parse((ROOT / "tests/fixtures/syntax_ref/n_wait_goto_login.redflow").read_text())
    assert s.url == "CONTINUE_FROM_LOGIN"
    assert [a.keyword for a in s.actions][2:] == ["WAIT", "GOTO", "DOUBLE_CLICK", "RIGHT_CLICK", "UPLOAD"]
    assert s.actions[2].seconds == 30
    s = parse('STEPS\n    - BROWSER_FIND $email\n    - FOR_EACH $r IN $roles EXECUTE_PARALLEL\n'
              '        - CLICK ON "$r" INTENT "Tick $r"\n$email = "a"\n$roles = ["x"]\n')
    assert (s.actions[0].keyword, s.actions[0].value_var, s.actions[0].intent) == ("BROWSER_FIND", "email", None)
    assert s.blocks[0].parallel and s.blocks[0].condition_text() == "FOR_EACH $r IN $roles EXECUTE_PARALLEL"


def test_extraction_steps_are_numbered():
    s = parse((ROOT / "tests/fixtures/syntax_ref/x_d_multi_tab.redflow").read_text())
    assert s.is_extraction
    assert [a.element for a in s.actions][:3] == ["Filter by role dropdown", "Account Administrator", "name"]


BASE = 'URL "https://x"\nSTEPS\n{steps}\n{vars}\n'


@pytest.mark.parametrize("steps,vars_,code", [
    ('   - CLICK ON "A" INTENT "a"', "", "E_INDENT"),
    ('\t- CLICK ON "A" INTENT "a"', "", "E_INDENT_TAB"),
    ('    - CLICK ON "A"', "", "E_NO_INTENT"),
    ('    - FILL $name INTO "Name" INTENT "Type the name"', '$name = "a"', "E_INTENT_BINDING"),
    ('    - FILL $name INTO "Name" INTENT "Type $name"', "", "E_VAR_UNDEFINED"),
    ('    - FILL $userName INTO "Name" INTENT "Type $userName"', '$userName = "a"', "E_VAR_NAME"),
    ('    - WHEN "a popup is visible"', "", "E_EMPTY_BODY"),
    ('    - WAIT_UNTIL "ready"\n        - CLICK ON "A" INTENT "a"', "", "E_WAIT_UNTIL_BODY"),
    ('    - WHEN ""\n        - CLICK ON "A" INTENT "a"', "", "E_EMPTY_CONDITION"),
    ('    - IF $roles EXISTS\n        - CLICK ON "A" INTENT "a"', '$roles = ["a", "b"]', "E_EXISTS_ON_LIST"),
    ('    - CLICK ON "A" INTENT "a"\n    - ELSE\n        - CLICK ON "B" INTENT "b"', "", "E_ELSE_ORPHAN"),
    ('    - UNTIL "busy"\n        - CLICK ON "A" INTENT "a"\n    - ELSE\n        - CLICK ON "B" INTENT "b"', "", "E_ELSE_ORPHAN"),
    ('    - TYPE $x INTO "A" INTENT "$x"', '$x = "a"', "E_UNKNOWN_STEP"),
    ('    - CLICK "A" INTENT "a"', "", "E_ACTION_SYNTAX"),
    ('    - IF $x LIKE "a"\n        - CLICK ON "A" INTENT "a"', '$x = "a"', "E_CONDITION_SYNTAX"),
    ('    - CLICK ON "A" INTENT "a"', '$x = "a"\n$x = "b"', "E_VAR_DUPLICATE"),
    ('    - CLICK ON "A" INTENT "a"', "$x = a", "E_VAR_VALUE"),
    # comparisons, IN, ELIF
    ('    - IF $x == "a"\n        - CLICK ON "A" INTENT "a"', '$x = "a"', "E_OPERATOR_SYMBOL"),
    ('    - IF $x != "a"\n        - CLICK ON "A" INTENT "a"', '$x = "a"', "E_OPERATOR_SYMBOL"),
    ('    - IF $x IN ["a", "b"]\n        - CLICK ON "A" INTENT "a"', '$x = "a"', "E_IN_LITERAL"),
    ('    - IF $x IN $y\n        - CLICK ON "A" INTENT "a"', '$x = "a"\n$y = "b"', "E_IN_NOT_LIST"),
    ('    - CLICK ON "A" INTENT "a"\n    - ELIF $x EQUALS "a"\n        - CLICK ON "B" INTENT "b"', '$x = "a"',
     "E_ELIF_ORPHAN"),
    ('    - WHEN "a popup"\n        - CLICK ON "A" INTENT "a"\n    - ELIF $x EQUALS "a"\n'
     '        - CLICK ON "B" INTENT "b"', '$x = "a"', "E_ELIF_AFTER_WHEN"),
    ('    - IF $x EQUALS "a"\n        - CLICK ON "A" INTENT "a"\n    - ELSE\n        - CLICK ON "B" INTENT "b"\n'
     '    - ELIF $x EQUALS "b"\n        - CLICK ON "C" INTENT "c"', '$x = "a"', "E_ELIF_ORPHAN"),
    ('    - IF $x EQUALS "a"\n        - CLICK ON "A" INTENT "a"\n    - ELIF $x EQUALS "b"', '$x = "a"', "E_EMPTY_BODY"),
    # FOR_EACH, EXECUTE_PARALLEL
    ('    - FOR_EACH $r IN $x\n        - CLICK ON "$r" INTENT "$r"', '$x = "a"', "E_FOR_EACH_SCALAR"),
    ('    - FOR_EACH $r IN $roles PARALLEL\n        - CLICK ON "$r" INTENT "$r"', '$roles = ["a"]', "E_FOR_EACH_SUFFIX"),
    ('    - EXECUTE_PARALLEL', "", "E_PARALLEL_STANDALONE"),
    # maps
    ('    - FOR_EACH $v IN $m\n        - CLICK ON "$v" INTENT "$v"', '$m["a"] = "x"', "E_FOR_EACH_MAP"),
    ('    - FOR_EACH $k, $v IN $m EXECUTE_PARALLEL\n        - CLICK ON "$v" INTENT "$v"', '$m["a"] = "x"',
     "E_PARALLEL_MAP"),
    ('    - FOR_EACH $k, $vs IN $m\n        - FOR_EACH $v IN $vs EXECUTE_PARALLEL\n'
     '            - CLICK ON "$v" INTENT "$v"', '$m["a"] = ["x"]', "E_PARALLEL_MAP"),
    ('    - FOR_EACH $k, $k IN $m\n        - CLICK ON "$k" INTENT "$k"', '$m["a"] = "x"', "E_MAP_LOOP_NAMES"),
    ('    - FOR_EACH $x, $v IN $m\n        - CLICK ON "$v" INTENT "$v $x"', '$m["a"] = "x"\n$x = "a"',
     "E_LOOP_VAR_DEFINED"),
    ('    - FOR_EACH $k, $v IN $roles\n        - CLICK ON "$v" INTENT "$v $k"', '$roles = ["a"]', "E_MAP_LOOP_NOT_MAP"),
    ('    - CLICK ON "Grant $m" INTENT "Grant $m"', '$m["a"] = "x"', "E_MAP_USAGE"),
    ('    - CLICK ON "Grant $m[Reserve]" INTENT "Grant"', '$m["Reserve"] = "x"', "E_MAP_KEY_READ"),
    ('    - FOR_EACH $k, $vs IN $m\n        - CLICK ON "$vs" INTENT "$vs $k"', '$m["a"] = ["x"]\n$m["b"] = "y"',
     "E_MAP_VALUE_TEXT"),
    ('    - FOR_EACH $k, $v IN $m\n        - IF $k EXISTS\n            - CLICK ON "$v" INTENT "$v"', '$m["a"] = "x"',
     "E_MAP_LOOP_TEST"),
    ('    - CLICK ON "A" INTENT "a"', '$m[$r] = ["x"]', "E_MAP_KEY_VAR"),
    ('    - CLICK ON "A" INTENT "a"', '$m[Petty cash] = ["x"]', "E_MAP_KEY_QUOTES"),
    ('    - CLICK ON "A" INTENT "a"', '$m["a"]["b"] = "x"', "E_MAP_NESTED"),
    ('    - CLICK ON "A" INTENT "a"', '$m["a"] = EMPTY', "E_MAP_EMPTY"),
    ('    - CLICK ON "A" INTENT "a"', '$m = {"a": ["x"]}', "E_MAP_OBJECT"),
    ('    - CLICK ON "A" INTENT "a"', '$m["a"] = "x"\n$m[a] = "y"', "E_MAP_DUP_KEY"),
    ('    - CLICK ON "A" INTENT "a"', '$m = "x"\n$m["a"] = "y"', "E_MAP_CONFLICT"),
    ('    - CLICK ON "A" INTENT "a"', '$m["a"] = "x"\n$m = "y"', "E_MAP_CONFLICT"),
    ('    - CLICK ON "A" INTENT "a"', '$m?["a"] = "x"\n$m["b"] = "y"', "E_MAP_OPTIONAL"),
    # GRAB
    ('    - GRAB ALL "rows" INTO $rows INTENT "Read rows"', "", "E_GRAB_ALL_LIST"),
    ('    - GRAB "row" INTO $rows[] INTENT "Read rows"', "", "E_GRAB_LIST"),
    ('    - GRAB ALL "rows" INTO $rows[] INTENT "Read" POSSIBLE_VALUES ["a"]', "", "E_GRAB_ALL_VALUES"),
    ('    - GRAB "status" INTO $s INTENT "Read" POSSIBLE_VALUES []', "", "E_GRAB_VALUES"),
    ('    - GRAB "status" INTO $s INTENT "Read" POSSIBLE_VALUES [""]', "", "E_GRAB_VALUES"),
    ('    - GRAB "status" INTO $s', "", "E_NO_INTENT"),
    ('    - GRAB "status" INTO $x INTENT "Read"', '$x = "a"', "E_GRAB_TARGET"),
    ('    - WHEN "a dialog"\n        - GRAB "word" INTO $w INTENT "Read"\n    - FILL $w INTO "Box" INTENT "Type $w"', "",
     "E_VAR_UNDEFINED"),
    ('    - GRAB "status" INTO $s INTENT "Read"\n    - IF $s EXISTS\n        - CLICK ON "A" INTENT "a"', "",
     "E_GRAB_EXISTS"),
    # BROWSER_FIND, WAIT, GOTO, URL, SELECT, new clicks
    ('    - BROWSER_FIND "rico@x.com"', "", "E_BROWSER_FIND_VALUE"),
    ('    - BROWSER_FIND $e INTENT "Find $e"', '$e = "a"', "E_INTENT_NOT_ALLOWED"),
    ('    - BROWSER_FIND $e\n        - CLICK ON "A" INTENT "a"', '$e = "a"', "E_UNEXPECTED_NESTING"),
    ('    - BROWSER_FIND $e', "", "E_VAR_UNDEFINED"),
    ('    - WAIT 0', "", "E_WAIT_SECONDS"),
    ('    - WAIT 2.5', "", "E_WAIT_SECONDS"),
    ('    - WAIT "30"', "", "E_WAIT_SECONDS"),
    ('    - WAIT 30 INTENT "slow page"', "", "E_INTENT_NOT_ALLOWED"),
    ('    - GOTO "https://x" INTENT "go"', "", "E_INTENT_NOT_ALLOWED"),
    ('    - GOTO CONTINUE_FROM_LOGIN', "", "E_GOTO_LOGIN"),
    ('    - SELECT "Sales Rep" FROM "Role dropdown" INTENT "Assign the role"', "", "E_SELECT_LITERAL"),
    ('    - SELECT "$role" FROM "Role dropdown" INTENT "Assign the role $role"', '$role = "a"', "E_SELECT_LITERAL"),
    ('    - DOUBLE_CLICK ON "Row"', "", "E_NO_INTENT"),
    ('    - UPLOAD $file INTO "Upload area" INTENT "Upload the file"', '$file = "v://a"', "E_INTENT_BINDING"),
])
def test_invalid_action_scripts(steps, vars_, code):
    issues = validate(BASE.format(steps=steps, vars=vars_))
    assert code in {i.code for i in errors(issues)}, [i.to_dict() for i in issues]


@pytest.mark.parametrize("src,code", [
    ('URL CONTINUE_FROM_LOGIN "https://x"\nSTEPS\n    - CLICK ON "A" INTENT "a"\n', "E_URL_SYNTAX"),
    ('URL https://x\nSTEPS\n    - CLICK ON "A" INTENT "a"\n', "E_URL_SYNTAX"),
])
def test_invalid_url_lines(src, code):
    assert code in {i.code for i in errors(validate(src))}


def test_grab_value_is_usable_later_at_same_level_or_deeper():
    src = ('STEPS\n    - GRAB "the word" INTO $w INTENT "Read the word"\n'
           '    - IF $w IN $allowed\n        - FILL $w INTO "Box" INTENT "Type $w"\n'
           '    - FILL $w INTO "Box" INTENT "Type $w"\n$allowed = ["a"]\n')
    assert errors(validate(src)) == []


def test_element_variable_missing_from_intent_is_only_a_warning():
    # Proven GTs do this (tc4): the variable is in the element text, not repeated in the INTENT.
    issues = validate('STEPS\n    - CLICK ON "View button of $email" INTENT "to open user details"\n'
                      '$email = "a"\n')
    assert errors(issues) == []
    assert "W_INTENT_BINDING_ELEMENT" in {i.code for i in issues}


@pytest.mark.parametrize("src,code", [
    ('URL "u"\nRESOURCE: "Users"\nEXTRACT\n    FROM LIST\n        - "email" INSTRUCT "col"\n', "E_RESOURCE_ID"),
    ('URL "u"\nRESOURCE: "Users" IDENTIFIED_BY "email"\nEXTRACT\n    FROM LIST\n        - "email"\n', "E_FIELD_INSTRUCT"),
    ('URL "u"\nEXTRACT\n    FROM LIST\n        - "email" INSTRUCT "col"\n', "E_RESOURCE_MISSING"),
    ('URL "u"\nRESOURCE: "G" IDENTIFIED_BY "n"\nEXTRACT\n    FROM LIST\n        - "n" INSTRUCT "c"\n'
     '        STEPS\n            - CLICK ON "n" INTENT "open"\n        EXTRACT\n            FROM LIST\n'
     '                - "m" INSTRUCT "c"\n', "E_NESTED_RESOURCE"),
    ('URL "u"\nRESOURCE: "A" IDENTIFIED_BY "n"\nEXTRACT\n    FROM LIST\n        - "n" INSTRUCT "c"\n'
     'STEPS\n    - GOTO "https://b"\nRESOURCE: "B" JOIN ON "employee_id"\nEXTRACT\n    FROM LIST\n'
     '        - "s" INSTRUCT "c"\n', "E_JOIN_KEY"),
    ('URL "u"\nRESOURCE: "A" IDENTIFIED_BY "n"\nEXTRACT\n    FROM DETAILS\n        - "n" INSTRUCT "c"\n'
     '        STEPS\n            - CLICK ON "x" INTENT "x"\n', "E_STEPS_IN_DETAILS"),
])
def test_invalid_extraction_scripts(src, code):
    issues = validate(src)
    assert code in {i.code for i in errors(issues)}, [i.to_dict() for i in issues]


def test_comments_and_hash_inside_quotes():
    src = 'STEPS\n    # note\n    - CLICK ON "Item #3" INTENT "Open item #3"  # trailing\n'
    s = parse(src)
    assert errors(validate(s)) == []
    assert s.actions[0].element == "Item #3"


def test_hard_coded_fill_value_parses():
    s = parse('STEPS\n    - FILL "john" INTO "Name" INTENT "Type john"\n')
    assert errors(validate(s)) == []
    assert s.actions[0].value_literal == "john" and s.actions[0].value_var is None
