"""Parse redflow scripts (action and extraction) into a small AST.

The parser is tolerant: it records problems as `Issue`s instead of raising, so the
validator can report every error in one pass. Grammar follows
docs/reference/redflow-syntax-reference.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

ACTION_KEYWORDS = ("CLICK", "HOVER", "FILL", "FILL_AND_ENTER", "SELECT", "GOTO")
BLOCK_KINDS = ("IF", "FOR_EACH", "WHEN", "UNTIL", "WAIT_UNTIL")
RUNTIME_KINDS = ("WHEN", "UNTIL", "WAIT_UNTIL")
INDENT = 4

VAR_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_Q = r'"((?:[^"\\]|\\.)*)"'          # a double-quoted string, group = contents
_VAL = r'(?:\$([A-Za-z_][A-Za-z0-9_]*)|' + _Q + r')'   # $var or "literal"
_INTENT = r'(?:\s+INTENT\s+' + _Q + r')?'

_ACTION_PATTERNS = [
    ("CLICK", re.compile(r'^CLICK\s+ON\s+' + _Q + _INTENT + r'$')),
    ("HOVER", re.compile(r'^HOVER\s+ON\s+' + _Q + _INTENT + r'$')),
    ("FILL_AND_ENTER", re.compile(r'^FILL_AND_ENTER\s+' + _VAL + r'\s+INTO\s+' + _Q + _INTENT + r'$')),
    ("FILL", re.compile(r'^FILL\s+' + _VAL + r'\s+INTO\s+' + _Q + _INTENT + r'$')),
    ("SELECT", re.compile(r'^SELECT\s+' + _VAL + r'\s+FROM\s+' + _Q + _INTENT + r'$')),
    ("GOTO", re.compile(r'^GOTO\s+' + _Q + r'$')),
]
_IF_CMP = re.compile(r'^IF\s+\$([A-Za-z_][A-Za-z0-9_]*)\s+(EQUALS|==|NOT_EQUALS|!=)\s+' + _Q + r'$')
_IF_UNARY = re.compile(r'^IF\s+\$([A-Za-z_][A-Za-z0-9_]*)\s+(EXISTS|NOT_EMPTY|EMPTY)$')
_FOR_EACH = re.compile(r'^FOR_EACH\s+\$([A-Za-z_][A-Za-z0-9_]*)\s+IN\s+\$([A-Za-z_][A-Za-z0-9_]*)$')
_RUNTIME = re.compile(r'^(WHEN|UNTIL|WAIT_UNTIL)\s+' + _Q + r'$')
_URL = re.compile(r'^URL\s+' + _Q + r'$')
_VAR_DEF = re.compile(r'^\$([A-Za-z_][A-Za-z0-9_]*)(\?)?\s*=\s*(.+)$')
_RES_TOP = re.compile(r'^RESOURCE:\s*' + _Q + r'\s+(IDENTIFIED_BY|JOIN\s+ON)\s+' + _Q + r'$')
_RES_SHORT = re.compile(r'^RESOURCE:?\s*' + _Q + r'$')
_FIELD = re.compile(r'^-\s*' + _Q + r'(\[\])?(?:\s+INSTRUCT\s+' + _Q + r')?(?:\s+POSSIBLE_VALUES\s+(\[.*\]))?$')

_OP_NORMAL = {"==": "EQUALS", "!=": "NOT_EQUALS"}

# `# critical` at the end of a GT action line marks the step that commits the change.
CRITICAL_RE = re.compile(r"^#\s*critical\b", re.IGNORECASE)


@dataclass
class Issue:
    line: int
    code: str
    message: str
    severity: str = "error"   # "error" fails the syntax gate; "warning" is informational

    def to_dict(self) -> dict:
        return {"line": self.line, "code": self.code, "message": self.message, "severity": self.severity}


def vars_in(text: Optional[str]) -> List[str]:
    return VAR_RE.findall(text or "")


@dataclass
class Action:
    keyword: str
    line: int
    text: str
    value_var: Optional[str] = None       # FILL $x / SELECT $x
    value_literal: Optional[str] = None   # FILL "john" (hard-coded)
    element: Optional[str] = None         # quoted target; URL for GOTO
    intent: Optional[str] = None
    num: int = 0                          # 1-based step number, document order
    path: Tuple[Tuple[str, str], ...] = ()  # ((block_id, "then"|"else"), ...) outermost first
    critical: bool = False                # line ends with `# critical`

    def action_vars(self) -> List[str]:
        """Variables used by the action itself (value + element), excluding the intent."""
        out = [self.value_var] if self.value_var else []
        out += [v for v in vars_in(self.element) if v not in out]
        return out

    def all_vars(self) -> List[str]:
        out = self.action_vars()
        out += [v for v in vars_in(self.intent) if v not in out]
        return out


@dataclass
class Block:
    kind: str                       # IF | FOR_EACH | WHEN | UNTIL | WAIT_UNTIL
    line: int
    text: str
    var: Optional[str] = None       # IF variable
    op: Optional[str] = None        # EQUALS | NOT_EQUALS | EXISTS | EMPTY | NOT_EMPTY
    literal: Optional[str] = None   # IF comparison literal
    item_var: Optional[str] = None  # FOR_EACH $item
    list_var: Optional[str] = None  # FOR_EACH ... IN $list
    condition: Optional[str] = None  # WHEN/UNTIL/WAIT_UNTIL natural-language condition
    then: List["Node"] = field(default_factory=list)
    else_: Optional[List["Node"]] = None
    else_line: Optional[int] = None
    id: str = ""
    path: Tuple[Tuple[str, str], ...] = ()

    def condition_text(self) -> str:
        if self.kind == "IF":
            lit = f' "{self.literal}"' if self.literal is not None else ""
            return f"IF ${self.var} {self.op}{lit}"
        if self.kind == "FOR_EACH":
            return f"FOR_EACH ${self.item_var} IN ${self.list_var}"
        return f'{self.kind} "{self.condition}"'


Node = Union[Action, Block]


@dataclass
class StepsSection:
    line: int
    steps: List[Node] = field(default_factory=list)


@dataclass
class Field:
    name: str
    line: int
    is_array: bool = False
    instruct: Optional[str] = None
    possible_values: Optional[List[str]] = None


@dataclass
class Resource:
    name: str
    line: int
    identified_by: Optional[str] = None
    join_on: Optional[str] = None
    short_form: bool = False


@dataclass
class FromBlock:
    mode: str                       # LIST | DETAILS
    line: int
    items: List[Union[Field, StepsSection, Resource, "Extract"]] = field(default_factory=list)


@dataclass
class Extract:
    line: int
    froms: List[FromBlock] = field(default_factory=list)


@dataclass
class Variable:
    name: str
    line: int
    value: Union[str, List[str], None]   # None = EMPTY
    optional: bool = False

    @property
    def kind(self) -> str:
        if self.value is None:
            return "empty"
        return "list" if isinstance(self.value, list) else "scalar"


@dataclass
class Script:
    source: str
    url: Optional[str] = None
    sections: List[Union[StepsSection, Resource, Extract]] = field(default_factory=list)
    variables: Dict[str, Variable] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    duplicate_vars: List[Variable] = field(default_factory=list)

    @property
    def is_extraction(self) -> bool:
        return any(isinstance(s, (Resource, Extract)) for s in self.sections)

    @property
    def critical_steps(self) -> List[int]:
        return [a.num for a in self.actions if a.critical]

    def action(self, num: int) -> Action:
        return self.actions[num - 1]

    def block(self, block_id: str) -> Block:
        return next(b for b in self.blocks if b.id == block_id)


# ---------------------------------------------------------------- line tree

@dataclass
class _Line:
    no: int
    indent: int
    text: str
    comment: str = ""
    children: List["_Line"] = field(default_factory=list)


def strip_comment(line: str) -> str:
    in_q = False
    prev = ""
    for i, ch in enumerate(line):
        if ch == '"' and prev != "\\":
            in_q = not in_q
        elif ch == "#" and not in_q:
            return line[:i]
        prev = ch
    return line


def _line_tree(source: str, issues: List[Issue]) -> _Line:
    root = _Line(0, -INDENT, "")
    stack = [root]
    for no, raw in enumerate(source.splitlines(), start=1):
        text = strip_comment(raw).rstrip()
        comment = raw[len(strip_comment(raw)):].strip()
        if not text.strip():
            if CRITICAL_RE.match(comment):
                issues.append(Issue(no, "W_CRITICAL_PLACEMENT",
                                    "`# critical` must be at the end of the step line it marks", "warning"))
            continue
        if "\t" in text[: len(text) - len(text.lstrip())]:
            issues.append(Issue(no, "E_INDENT_TAB", "indentation must use spaces, not tabs"))
            text = text.replace("\t", " " * INDENT)
        indent = len(text) - len(text.lstrip(" "))
        while stack[-1].indent >= indent:
            stack.pop()
        parent = stack[-1]
        if indent != parent.indent + INDENT:
            issues.append(Issue(no, "E_INDENT",
                                f"expected indentation of {parent.indent + INDENT} spaces, found {indent}"))
        node = _Line(no, indent, text.strip(), comment)
        parent.children.append(node)
        stack.append(node)
    return root


# ---------------------------------------------------------------- parser

def parse(source: str) -> Script:
    script = Script(source=source)
    root = _line_tree(source, script.issues)
    for node in root.children:
        _parse_top(node, script)
    _number(script)
    _check_critical_marks(root, script)
    return script


def _check_critical_marks(root: _Line, s: Script) -> None:
    action_lines = {a.line for a in s.actions}
    stack = list(root.children)
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if CRITICAL_RE.match(node.comment) and node.no not in action_lines:
            s.issues.append(Issue(node.no, "W_CRITICAL_PLACEMENT",
                                  "`# critical` only applies to action steps (CLICK, FILL, SELECT, ...)", "warning"))


def _parse_top(node: _Line, s: Script) -> None:
    t = node.text
    m = _URL.match(t)
    if m:
        if s.url is not None:
            s.issues.append(Issue(node.no, "E_URL_DUP", "more than one URL line"))
        s.url = m.group(1)
        _no_children(node, s)
        return
    if t == "STEPS":
        s.sections.append(StepsSection(node.no, _parse_steps(node.children, s)))
        return
    if t == "EXTRACT":
        s.sections.append(_parse_extract(node, s))
        return
    if t.startswith("RESOURCE"):
        s.sections.append(_parse_resource(node, s))
        _no_children(node, s)
        return
    m = _VAR_DEF.match(t)
    if m:
        var = Variable(m.group(1), node.no, None, optional=bool(m.group(2)))
        ok, value = _parse_value(m.group(3).strip())
        if not ok:
            s.issues.append(Issue(node.no, "E_VAR_VALUE",
                                  f"${var.name}: value must be \"text\", [\"a\", \"b\"] or EMPTY"))
        var.value = value
        if var.name in s.variables:
            s.duplicate_vars.append(var)
        else:
            s.variables[var.name] = var
        _no_children(node, s)
        return
    if t.startswith("-"):
        s.issues.append(Issue(node.no, "E_STEP_OUTSIDE_STEPS", "step is not inside a STEPS block"))
        return
    s.issues.append(Issue(node.no, "E_UNKNOWN_LINE", f"unrecognised line: {t!r}"))


def _parse_value(text: str):
    if text == "EMPTY":
        return True, None
    m = re.fullmatch(_Q, text)
    if m:
        return True, m.group(1)
    if text.startswith("["):
        try:
            val = json.loads(text)
        except ValueError:
            return False, None
        if isinstance(val, list) and all(isinstance(v, str) for v in val):
            return True, val
    return False, None


def _no_children(node: _Line, s: Script) -> None:
    for c in node.children:
        s.issues.append(Issue(c.no, "E_UNEXPECTED_NESTING", f"line cannot be nested here: {c.text!r}"))


def _parse_steps(lines: List[_Line], s: Script) -> List[Node]:
    out: List[Node] = []
    for node in lines:
        t = node.text
        if not t.startswith("-"):
            s.issues.append(Issue(node.no, "E_STEP_DASH", f"step must start with '- ': {t!r}"))
            continue
        stmt = t[1:].strip()
        if stmt == "ELSE":
            prev = out[-1] if out else None
            if isinstance(prev, Block) and prev.kind in ("IF", "WHEN") and prev.else_ is None:
                prev.else_ = _parse_steps(node.children, s)
                prev.else_line = node.no
                if not node.children:
                    s.issues.append(Issue(node.no, "E_EMPTY_BODY", "ELSE must have at least one nested step"))
            else:
                s.issues.append(Issue(node.no, "E_ELSE_ORPHAN", "ELSE must directly follow an IF or WHEN block"))
            continue
        block = _parse_block_header(stmt, node.no)
        if block is not None:
            block.then = _parse_steps(node.children, s)
            out.append(block)
            continue
        action = _parse_action(stmt, node.no, s)
        if action is not None:
            action.critical = bool(CRITICAL_RE.match(node.comment))
            out.append(action)
            _no_children(node, s)
    return out


def _parse_block_header(stmt: str, no: int) -> Optional[Block]:
    m = _IF_CMP.match(stmt)
    if m:
        return Block("IF", no, stmt, var=m.group(1), op=_OP_NORMAL.get(m.group(2), m.group(2)), literal=m.group(3))
    m = _IF_UNARY.match(stmt)
    if m:
        return Block("IF", no, stmt, var=m.group(1), op=m.group(2))
    m = _FOR_EACH.match(stmt)
    if m:
        return Block("FOR_EACH", no, stmt, item_var=m.group(1), list_var=m.group(2))
    m = _RUNTIME.match(stmt)
    if m:
        return Block(m.group(1), no, stmt, condition=m.group(2))
    return None


def _parse_action(stmt: str, no: int, s: Script) -> Optional[Action]:
    for kw, pat in _ACTION_PATTERNS:
        m = pat.match(stmt)
        if not m:
            continue
        if kw == "GOTO":
            return Action(kw, no, stmt, element=m.group(1))
        if kw in ("CLICK", "HOVER"):
            a = Action(kw, no, stmt, element=m.group(1), intent=m.group(2))
        else:
            a = Action(kw, no, stmt, value_var=m.group(1), value_literal=m.group(2),
                       element=m.group(3), intent=m.group(4))
        if a.intent is None:
            s.issues.append(Issue(no, "E_NO_INTENT", f"{kw} requires an INTENT"))
        return a
    word = stmt.split()[0] if stmt.split() else ""
    if word in ACTION_KEYWORDS:
        s.issues.append(Issue(no, "E_ACTION_SYNTAX", f"malformed {word} statement: {stmt!r}"))
    elif word in BLOCK_KINDS:
        s.issues.append(Issue(no, "E_CONDITION_SYNTAX", f"malformed {word} condition: {stmt!r}"))
    else:
        s.issues.append(Issue(no, "E_UNKNOWN_STEP", f"unknown step keyword: {stmt!r}"))
    return None


def _parse_resource(node: _Line, s: Script) -> Resource:
    m = _RES_TOP.match(node.text)
    if m:
        r = Resource(m.group(1), node.no)
        if m.group(2) == "IDENTIFIED_BY":
            r.identified_by = m.group(3)
        else:
            r.join_on = m.group(3)
        return r
    m = _RES_SHORT.match(node.text)
    if m:
        return Resource(m.group(1), node.no, short_form=True)
    s.issues.append(Issue(node.no, "E_RESOURCE_SYNTAX", f"malformed RESOURCE line: {node.text!r}"))
    return Resource("", node.no, short_form=True)


def _parse_extract(node: _Line, s: Script) -> Extract:
    ex = Extract(node.no)
    for c in node.children:
        if c.text in ("FROM LIST", "FROM DETAILS"):
            ex.froms.append(_parse_from(c, s))
        else:
            s.issues.append(Issue(c.no, "E_EXTRACT_CHILD", f"EXTRACT may only contain FROM LIST / FROM DETAILS, found {c.text!r}"))
    if not ex.froms:
        s.issues.append(Issue(node.no, "E_EMPTY_BODY", "EXTRACT must contain FROM LIST or FROM DETAILS"))
    return ex


def _parse_from(node: _Line, s: Script) -> FromBlock:
    fb = FromBlock(node.text.split()[1], node.no)
    for c in node.children:
        t = c.text
        if t.startswith("-"):
            m = _FIELD.match(t)
            if not m:
                s.issues.append(Issue(c.no, "E_FIELD_SYNTAX", f"malformed field: {t!r}"))
                continue
            f = Field(m.group(1), c.no, is_array=bool(m.group(2)), instruct=m.group(3))
            if m.group(4):
                ok, vals = _parse_value(m.group(4))
                if not ok or not isinstance(vals, list):
                    s.issues.append(Issue(c.no, "E_FIELD_SYNTAX", "POSSIBLE_VALUES must be a list of strings"))
                f.possible_values = vals if isinstance(vals, list) else None
            fb.items.append(f)
            _no_children(c, s)
        elif t == "STEPS":
            fb.items.append(StepsSection(c.no, _parse_steps(c.children, s)))
        elif t == "EXTRACT":
            fb.items.append(_parse_extract(c, s))
        elif t.startswith("RESOURCE"):
            fb.items.append(_parse_resource(c, s))
            _no_children(c, s)
        else:
            s.issues.append(Issue(c.no, "E_UNKNOWN_LINE", f"unrecognised line inside FROM {fb.mode}: {t!r}"))
    return fb


# ---------------------------------------------------------------- numbering

def _number(s: Script) -> None:
    """Assign step numbers (actions only) and block ids in document order."""

    def walk_steps(nodes: List[Node], path):
        for n in nodes:
            if isinstance(n, Action):
                n.num = len(s.actions) + 1
                n.path = path
                s.actions.append(n)
            else:
                n.id = f"B{len(s.blocks) + 1}"
                n.path = path
                s.blocks.append(n)
                walk_steps(n.then, path + ((n.id, "then"),))
                if n.else_ is not None:
                    walk_steps(n.else_, path + ((n.id, "else"),))

    def walk_extract(ex: Extract):
        for fb in ex.froms:
            for item in fb.items:
                if isinstance(item, StepsSection):
                    walk_steps(item.steps, ())
                elif isinstance(item, Extract):
                    walk_extract(item)

    for sec in s.sections:
        if isinstance(sec, StepsSection):
            walk_steps(sec.steps, ())
        elif isinstance(sec, Extract):
            walk_extract(sec)


def iter_fields(s: Script):
    """Yield (field, from_block) for every extraction field, document order."""

    def walk(ex: Extract):
        for fb in ex.froms:
            for item in fb.items:
                if isinstance(item, Field):
                    yield item, fb
                elif isinstance(item, Extract):
                    yield from walk(item)

    for sec in s.sections:
        if isinstance(sec, Extract):
            yield from walk(sec)
