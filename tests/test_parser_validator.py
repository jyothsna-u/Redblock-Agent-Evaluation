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
    s = parse('STEPS\n    - IF $x != "a"\n        - CLICK ON "A" INTENT "a"\n    - ELSE\n'
              '        - CLICK ON "B" INTENT "b"\n$x = "a"\n')
    b = s.blocks[0]
    assert b.op == "NOT_EQUALS"
    assert [a.path for a in s.actions] == [(("B1", "then"),), (("B1", "else"),)]


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
])
def test_invalid_action_scripts(steps, vars_, code):
    issues = validate(BASE.format(steps=steps, vars=vars_))
    assert code in {i.code for i in errors(issues)}, [i.to_dict() for i in issues]


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
