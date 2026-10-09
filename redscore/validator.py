"""Syntax validation for redflow scripts (RedScore step 1).

Rules come from docs/reference/redflow-syntax-reference.md, sections 2 to 6 and 8.10.
Any issue with severity "error" fails the syntax gate (Final Score 0).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from .parser import (Action, Block, Extract, Field, FromBlock, Issue, Resource, Script,
                     StepsSection, Node, parse, vars_in)

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate(source_or_script) -> List[Issue]:
    s = source_or_script if isinstance(source_or_script, Script) else parse(source_or_script)
    issues = list(s.issues)
    issues += _check_structure(s)
    issues += _check_variables(s)
    issues += _check_steps(s)
    issues += _check_extraction(s)
    return sorted(issues, key=lambda i: (i.line, i.code))


def errors(issues: List[Issue]) -> List[Issue]:
    return [i for i in issues if i.severity == "error"]


def _check_structure(s: Script) -> List[Issue]:
    out = []
    if s.url is None:
        out.append(Issue(0, "W_NO_URL", "no URL line (not scored; supplied per run)", "warning"))
    if not any(isinstance(x, (StepsSection, Extract)) for x in s.sections):
        out.append(Issue(0, "E_NO_STEPS", "script has no STEPS or EXTRACT block"))
    for sec in s.sections:
        if isinstance(sec, StepsSection) and not sec.steps:
            out.append(Issue(sec.line, "E_EMPTY_BODY", "STEPS must contain at least one step"))
    return out


def _check_variables(s: Script) -> List[Issue]:
    out = []
    for v in s.duplicate_vars:
        out.append(Issue(v.line, "E_VAR_DUPLICATE", f"${v.name} is defined more than once"))
    for v in s.variables.values():
        if not SNAKE.match(v.name):
            out.append(Issue(v.line, "E_VAR_NAME", f"${v.name} must be snake_case"))
    used: Set[str] = set()
    for a in s.actions:
        used.update(a.all_vars())
    for b in s.blocks:
        used.update(x for x in (b.var, b.rhs_var, b.list_var) if x)
        used.update(vars_in(b.condition) + vars_in(b.text if b.malformed else ""))
    for name in sorted(set(s.variables) - used):
        out.append(Issue(s.variables[name].line, "W_VAR_UNUSED", f"${name} is defined but never used", "warning"))
    return out


# Kinds of variables that steps bring into scope (input variables come from s.variables):
#   loop       FOR_EACH $item IN $list          map_key    FOR_EACH $key, ... IN $map
#   grab       GRAB ... INTO $x                 map_value  ... $value IN $map, every value a string
#   grab_list  GRAB ALL ... INTO $x[]           map_list   ... $value IN $map, some value is a list
LIST_KINDS = ("list", "grab_list", "map_list")
MAP_LOOP_KINDS = ("map_key", "map_value", "map_list")


def _check_steps(s: Script) -> List[Issue]:
    out: List[Issue] = []
    grabbed: Set[str] = set()

    def kind_of(name: str, scope: Dict[str, str]) -> Optional[str]:
        if name in scope:
            return scope[name]
        var = s.variables.get(name)
        return var.kind if var is not None else None

    def use(name: str, line: int, scope: Dict[str, str], text: str = "", as_text: bool = True,
            loop: bool = False):
        """A variable used by a step: snake_case, defined in scope, and not a map / list-valued map $value
        (`loop`: the list of a FOR_EACH, which reports maps itself)."""
        if not SNAKE.match(name):
            out.append(Issue(line, "E_VAR_NAME", f"${name} must be snake_case"))
        kind = kind_of(name, scope)
        if kind is None:
            out.append(Issue(line, "E_VAR_UNDEFINED", f"${name} is used but never defined"))
        elif loop:
            pass
        elif kind == "map" and re.search(r"\$" + name + r"\??\[", text):
            out.append(Issue(line, "E_MAP_KEY_READ", f"map ${name} cannot be read by key in a step; "
                                                     f"loop over it with FOR_EACH $key, $value IN ${name}"))
        elif kind == "map":
            out.append(Issue(line, "E_MAP_USAGE", f"map ${name} can only be used in a map loop "
                                                  f"(FOR_EACH $key, $value IN ${name})"))
        elif kind == "map_list" and as_text:
            out.append(Issue(line, "E_MAP_VALUE_TEXT", f"${name} holds a list for some keys, so it cannot be used "
                                                       f"as text; loop over it with FOR_EACH $item IN ${name}"))

    def new_name(name: str, line: int, scope: Dict[str, str], code: str, what: str):
        if not SNAKE.match(name):
            out.append(Issue(line, "E_VAR_NAME", f"${name} must be snake_case"))
        if name in s.variables or name in scope or name in grabbed:
            out.append(Issue(line, code, f"{what} ${name} must be a new variable name, not one already defined"))

    def walk(nodes: List[Node], scope: Dict[str, str]):
        scope = dict(scope)    # GRAB results reach later steps at this level or deeper, not after the block
        for n in nodes:
            if isinstance(n, Action):
                for v in n.all_vars():
                    use(v, n.line, scope, n.text)
                if n.intent is not None:
                    # Enforced for the FILL/FILL_AND_ENTER/SELECT/UPLOAD value only: proven GTs (tc2, tc4) put
                    # variables in the element text without repeating them in the INTENT.
                    intent_vars = set(vars_in(n.intent))
                    if n.value_var and n.value_var not in intent_vars:
                        out.append(Issue(n.line, "E_INTENT_BINDING",
                                         f"${n.value_var} is used in the action but not referenced in its INTENT"))
                    for v in dict.fromkeys(vars_in(n.element)):
                        if v != n.value_var and v not in intent_vars:
                            out.append(Issue(n.line, "W_INTENT_BINDING_ELEMENT",
                                             f"${v} is in the element but not in the INTENT", "warning"))
                if n.grab_var:
                    new_name(n.grab_var, n.line, scope, "E_GRAB_TARGET", "the GRAB target")
                    grabbed.add(n.grab_var)
                    scope[n.grab_var] = "grab_list" if n.grab_list else "grab"
                continue
            _check_block(n, s, out, use, new_name, kind_of, scope)
            inner = dict(scope)
            if n.kind == "FOR_EACH" and n.key_var:
                values = (s.variables[n.list_var].value if kind_of(n.list_var, scope) == "map" else {}) or {}
                inner[n.key_var] = "map_key"
                inner[n.item_var] = "map_list" if any(isinstance(v, list) for v in values.values()) else "map_value"
            elif n.kind == "FOR_EACH":
                inner[n.item_var] = "loop"
            walk(n.then, inner)
            if n.else_ is not None:
                walk(n.else_, scope)

    for steps in _all_steps_sections(s):
        walk(steps.steps, {})
    return out


def _check_block(b: Block, s: Script, out: List[Issue], use, new_name, kind_of, scope) -> None:
    if b.kind == "WAIT_UNTIL":
        if b.then:
            out.append(Issue(b.line, "E_WAIT_UNTIL_BODY", "WAIT_UNTIL must not have a nested body"))
    elif not b.then:
        out.append(Issue(b.line, "E_EMPTY_BODY", f"{'ELIF' if b.is_elif else b.kind} must have at least one nested step"))
    if b.malformed:      # GT lenient parse: the header error is already reported; only the body is checked
        return
    if b.kind in ("WHEN", "UNTIL", "WAIT_UNTIL"):
        if not (b.condition or "").strip():
            out.append(Issue(b.line, "E_EMPTY_CONDITION", f"{b.kind} needs a non-empty quoted condition"))
        for v in vars_in(b.condition):
            use(v, b.line, scope, b.condition)
    if b.kind == "IF":
        use(b.var, b.line, scope, as_text=False)
        kind = kind_of(b.var, scope)
        if kind in MAP_LOOP_KINDS and b.op not in ("EQUALS", "NOT_EQUALS"):
            out.append(Issue(b.line, "E_MAP_LOOP_TEST",
                             f"inside a map loop, ${b.var} can only be tested with EQUALS / NOT_EQUALS"))
        elif kind in ("grab", "grab_list") and b.op in ("EXISTS", "EMPTY", "NOT_EMPTY"):
            out.append(Issue(b.line, "E_GRAB_EXISTS", f"${b.var} is read from the page while the script runs, so it "
                                                      f"cannot be tested with {b.op}; use EQUALS / NOT_EQUALS or IN"))
        elif b.op == "EXISTS" and kind in LIST_KINDS:
            out.append(Issue(b.line, "E_EXISTS_ON_LIST", f"EXISTS cannot be used on list ${b.var}; use NOT_EMPTY / EMPTY"))
        elif b.op in ("EMPTY", "NOT_EMPTY") and kind == "scalar":
            out.append(Issue(b.line, "W_EMPTY_ON_SCALAR", f"{b.op} is meant for lists; ${b.var} is a scalar", "warning"))
        if b.op == "IN":
            use(b.rhs_var, b.line, scope, as_text=False)
            rhs = kind_of(b.rhs_var, scope)
            if rhs is not None and rhs not in ("list", "grab_list", "empty"):
                out.append(Issue(b.line, "E_IN_NOT_LIST", f"the right-hand side of IN must be a list variable; "
                                                          f"${b.rhs_var} is not a list"))
    if b.kind == "FOR_EACH":
        use(b.list_var, b.line, scope, loop=True)
        kind = kind_of(b.list_var, scope)
        if b.key_var:
            if b.key_var == b.item_var:
                out.append(Issue(b.line, "E_MAP_LOOP_NAMES", "$key and $value of a map loop need different names"))
            for v in dict.fromkeys((b.key_var, b.item_var)):
                new_name(v, b.line, scope, "E_LOOP_VAR_DEFINED", "map loop variable")
            if kind is not None and kind != "map":
                out.append(Issue(b.line, "E_MAP_LOOP_NOT_MAP", f"FOR_EACH $key, $value IN needs a map; "
                                                               f"${b.list_var} is not a map"))
            if b.parallel:
                out.append(Issue(b.line, "E_PARALLEL_MAP", "EXECUTE_PARALLEL cannot be used on a map loop"))
        else:
            if not SNAKE.match(b.item_var):
                out.append(Issue(b.line, "E_VAR_NAME", f"${b.item_var} must be snake_case"))
            if kind == "map":
                out.append(Issue(b.line, "E_FOR_EACH_MAP", f"${b.list_var} is a map; loop over it with "
                                                           f"FOR_EACH $key, $value IN ${b.list_var}"))
            elif kind in ("scalar", "loop", "grab", "map_key", "map_value"):
                out.append(Issue(b.line, "E_FOR_EACH_SCALAR", f"FOR_EACH over ${b.list_var}, which is not a list"))
            if b.parallel and kind in MAP_LOOP_KINDS:
                out.append(Issue(b.line, "E_PARALLEL_MAP", "EXECUTE_PARALLEL cannot be used on a loop over a map value"))


def _all_steps_sections(s: Script):
    def walk_extract(ex: Extract):
        for fb in ex.froms:
            for item in fb.items:
                if isinstance(item, StepsSection):
                    yield item
                elif isinstance(item, Extract):
                    yield from walk_extract(item)

    for sec in s.sections:
        if isinstance(sec, StepsSection):
            yield sec
        elif isinstance(sec, Extract):
            yield from walk_extract(sec)


def _check_extraction(s: Script) -> List[Issue]:
    out: List[Issue] = []
    if not s.is_extraction:
        return out
    extracted: Set[str] = set()   # field names seen so far, for JOIN ON

    prev: Optional[object] = None
    for sec in s.sections:
        if isinstance(sec, Resource):
            if sec.short_form or not (sec.identified_by or sec.join_on):
                out.append(Issue(sec.line, "E_RESOURCE_ID",
                                 "top-level RESOURCE needs IDENTIFIED_BY (or JOIN ON for a cross-URL join)"))
            if sec.join_on and sec.join_on not in extracted:
                out.append(Issue(sec.line, "E_JOIN_KEY",
                                 f"JOIN ON \"{sec.join_on}\" must match a field already extracted"))
        elif isinstance(sec, Extract):
            if not isinstance(prev, Resource):
                out.append(Issue(sec.line, "E_RESOURCE_MISSING", "top-level EXTRACT must follow a RESOURCE declaration"))
            _check_extract(sec, out, extracted)
        prev = sec
    return out


def _check_extract(ex: Extract, out: List[Issue], extracted: Set[str]) -> None:
    list_fields: Set[str] = set()
    for fb in ex.froms:
        names = set()
        prev = None
        for item in fb.items:
            if isinstance(item, Field):
                if item.instruct is None:
                    out.append(Issue(item.line, "E_FIELD_INSTRUCT", f'field "{item.name}" needs an INSTRUCT clause'))
                if not re.match(r"^[a-z][a-z0-9_]*$", item.name):
                    out.append(Issue(item.line, "W_FIELD_NAME", f'field "{item.name}" should be snake_case', "warning"))
                if fb.mode == "DETAILS" and item.name in list_fields:
                    out.append(Issue(item.line, "W_DETAILS_DUPLICATE",
                                     f'"{item.name}" is already extracted in FROM LIST', "warning"))
                names.add(item.name)
                extracted.add(item.name)
            elif isinstance(item, StepsSection):
                if fb.mode == "DETAILS":
                    out.append(Issue(item.line, "E_STEPS_IN_DETAILS", "per-item STEPS belong inside FROM LIST, not FROM DETAILS"))
            elif isinstance(item, Extract):
                if fb.mode == "DETAILS":
                    out.append(Issue(item.line, "E_EXTRACT_IN_DETAILS", "nested EXTRACT belongs inside FROM LIST"))
                if any(f.mode == "LIST" for f in item.froms) and not isinstance(prev, Resource):
                    out.append(Issue(item.line, "E_NESTED_RESOURCE",
                                     "a nested FROM LIST needs a RESOURCE declaration directly above its EXTRACT"))
                _check_extract(item, out, extracted)
            elif isinstance(item, Resource):
                if fb.mode == "DETAILS":
                    out.append(Issue(item.line, "E_RESOURCE_IN_DETAILS", "RESOURCE cannot appear inside FROM DETAILS"))
            prev = item
        if fb.mode == "LIST":
            list_fields |= names
        if not any(isinstance(i, Field) for i in fb.items):
            out.append(Issue(fb.line, "E_EMPTY_BODY", f"FROM {fb.mode} must declare at least one field"))
