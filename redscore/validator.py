"""Syntax validation for redflow scripts (RedScore step 1).

Rules come from docs/reference/redflow-syntax-reference.md, sections 2, 4, 5 and 7.10.
Any issue with severity "error" fails the syntax gate (Final Score 0).
"""
from __future__ import annotations

import re
from typing import List, Optional, Set

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
        used.update(x for x in (b.var, b.list_var) if x)
        used.update(vars_in(b.condition))
    for name in sorted(set(s.variables) - used):
        out.append(Issue(s.variables[name].line, "W_VAR_UNUSED", f"${name} is defined but never used", "warning"))
    return out


def _check_steps(s: Script) -> List[Issue]:
    out: List[Issue] = []

    def check_name(name: str, line: int):
        if not SNAKE.match(name):
            out.append(Issue(line, "E_VAR_NAME", f"${name} must be snake_case"))

    def check_defined(name: str, line: int, loop_vars: Set[str]):
        if name not in s.variables and name not in loop_vars:
            out.append(Issue(line, "E_VAR_UNDEFINED", f"${name} is used but never defined"))

    def walk(nodes: List[Node], loop_vars: Set[str]):
        for n in nodes:
            if isinstance(n, Action):
                for v in n.all_vars():
                    check_name(v, n.line)
                    check_defined(v, n.line, loop_vars)
                if n.intent is not None:
                    # Enforced for the FILL/FILL_AND_ENTER/SELECT value only: proven GTs (tc2, tc4) put
                    # variables in the element text without repeating them in the INTENT.
                    intent_vars = set(vars_in(n.intent))
                    if n.value_var and n.value_var not in intent_vars:
                        out.append(Issue(n.line, "E_INTENT_BINDING",
                                         f"${n.value_var} is used in the action but not referenced in its INTENT"))
                    for v in dict.fromkeys(vars_in(n.element)):
                        if v != n.value_var and v not in intent_vars:
                            out.append(Issue(n.line, "W_INTENT_BINDING_ELEMENT",
                                             f"${v} is in the element but not in the INTENT", "warning"))
                continue
            _check_block(n, s, out, check_name, check_defined, loop_vars)
            inner = loop_vars | ({n.item_var} if n.kind == "FOR_EACH" else set())
            walk(n.then, inner)
            if n.else_ is not None:
                walk(n.else_, loop_vars)

    for steps in _all_steps_sections(s):
        walk(steps.steps, set())
    return out


def _check_block(b: Block, s: Script, out: List[Issue], check_name, check_defined, loop_vars) -> None:
    if b.kind == "WAIT_UNTIL":
        if b.then:
            out.append(Issue(b.line, "E_WAIT_UNTIL_BODY", "WAIT_UNTIL must not have a nested body"))
    elif not b.then:
        out.append(Issue(b.line, "E_EMPTY_BODY", f"{b.kind} must have at least one nested step"))
    if b.kind in ("WHEN", "UNTIL", "WAIT_UNTIL"):
        if not (b.condition or "").strip():
            out.append(Issue(b.line, "E_EMPTY_CONDITION", f"{b.kind} needs a non-empty quoted condition"))
        for v in vars_in(b.condition):
            check_name(v, b.line)
            check_defined(v, b.line, loop_vars)
    if b.kind == "IF":
        check_name(b.var, b.line)
        check_defined(b.var, b.line, loop_vars)
        var = s.variables.get(b.var)
        if var is not None and b.op == "EXISTS" and var.kind == "list":
            out.append(Issue(b.line, "E_EXISTS_ON_LIST", f"EXISTS cannot be used on list ${b.var}; use NOT_EMPTY / EMPTY"))
        if var is not None and b.op in ("EMPTY", "NOT_EMPTY") and var.kind == "scalar":
            out.append(Issue(b.line, "W_EMPTY_ON_SCALAR", f"{b.op} is meant for lists; ${b.var} is a scalar", "warning"))
    if b.kind == "FOR_EACH":
        check_name(b.item_var, b.line)
        check_name(b.list_var, b.line)
        check_defined(b.list_var, b.line, loop_vars)
        var = s.variables.get(b.list_var)
        if var is not None and var.kind == "scalar":
            out.append(Issue(b.line, "W_FOR_EACH_SCALAR", f"FOR_EACH over ${b.list_var}, which is not a list", "warning"))


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
