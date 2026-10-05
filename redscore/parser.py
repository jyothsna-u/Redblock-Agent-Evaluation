"""Parse redflow scripts (action and extraction) into a small AST.

The parser is tolerant: it records problems as `Issue`s instead of raising, so the
validator can report every error in one pass. Grammar follows
docs/reference/redflow-syntax-reference.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

ACTION_KEYWORDS = ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "HOVER", "FILL", "FILL_AND_ENTER", "SELECT", "UPLOAD",
                   "GOTO", "WAIT", "BROWSER_FIND", "GRAB")
NO_INTENT_KEYWORDS = ("GOTO", "WAIT", "BROWSER_FIND")
BLOCK_KINDS = ("IF", "ELIF", "FOR_EACH", "WHEN", "UNTIL", "WAIT_UNTIL")
RUNTIME_KINDS = ("WHEN", "UNTIL", "WAIT_UNTIL")
INDENT = 4

_NAME = r'([A-Za-z_][A-Za-z0-9_]*)'
VAR_RE = re.compile(r"\$" + _NAME)
_Q = r'"((?:[^"\\]|\\.)*)"'          # a double-quoted string, group = contents
_VAL = r'(?:\$' + _NAME + '|' + _Q + r')'   # $var or "literal"
_INTENT = r'(?:\s+INTENT\s+' + _Q + r')?'

_ACTION_PATTERNS = [
    ("CLICK", re.compile(r'^CLICK\s+ON\s+' + _Q + _INTENT + r'$')),
    ("DOUBLE_CLICK", re.compile(r'^DOUBLE_CLICK\s+ON\s+' + _Q + _INTENT + r'$')),
    ("RIGHT_CLICK", re.compile(r'^RIGHT_CLICK\s+ON\s+' + _Q + _INTENT + r'$')),
    ("HOVER", re.compile(r'^HOVER\s+ON\s+' + _Q + _INTENT + r'$')),
    ("FILL_AND_ENTER", re.compile(r'^FILL_AND_ENTER\s+' + _VAL + r'\s+INTO\s+' + _Q + _INTENT + r'$')),
    ("FILL", re.compile(r'^FILL\s+' + _VAL + r'\s+INTO\s+' + _Q + _INTENT + r'$')),
    ("SELECT", re.compile(r'^SELECT\s+' + _VAL + r'\s+FROM\s+' + _Q + _INTENT + r'$')),
    ("UPLOAD", re.compile(r'^UPLOAD\s+' + _VAL + r'\s+INTO\s+' + _Q + _INTENT + r'$')),
    ("GOTO", re.compile(r'^GOTO\s+' + _Q + r'$')),
    ("WAIT", re.compile(r'^WAIT\s+([1-9][0-9]*)$')),
    ("BROWSER_FIND", re.compile(r'^BROWSER_FIND\s+\$' + _NAME + r'$')),
    ("GRAB", re.compile(r'^GRAB\s+(ALL\s+)?' + _Q + r'\s+INTO\s+\$' + _NAME + r'(\[\])?' + _INTENT
                        + r'(?:\s+POSSIBLE_VALUES\s+(\[.*\]))?$')),
]
_COND_CMP = re.compile(r'^\$' + _NAME + r'\s+(EQUALS|NOT_EQUALS)\s+' + _Q + r'$')
_COND_UNARY = re.compile(r'^\$' + _NAME + r'\s+(EXISTS|NOT_EMPTY|EMPTY)$')
_COND_IN = re.compile(r'^\$' + _NAME + r'\s+IN\s+\$' + _NAME + r'$')
_FOR_EACH = re.compile(r'^FOR_EACH\s+\$' + _NAME + r'\s+IN\s+\$' + _NAME + r'(\s+EXECUTE_PARALLEL)?$')
_FOR_EACH_MAP = re.compile(r'^FOR_EACH\s+\$' + _NAME + r'\s*,\s*\$' + _NAME + r'\s+IN\s+\$' + _NAME
                           + r'(\s+EXECUTE_PARALLEL)?$')
_RUNTIME = re.compile(r'^(WHEN|UNTIL|WAIT_UNTIL)\s+' + _Q + r'$')
_URL = re.compile(r'^URL\s+(?:' + _Q + r'|(CONTINUE_FROM_LOGIN))$')
_VAR_DEF = re.compile(r'^\$' + _NAME + r'(\?)?\s*=\s*(.+)$')
_MAP_DEF = re.compile(r'^\$' + _NAME + r'(\?)?\[(.*)\]\s*=\s*(.+)$')
_RES_TOP = re.compile(r'^RESOURCE:\s*' + _Q + r'\s+(IDENTIFIED_BY|JOIN\s+ON)\s+' + _Q + r'$')
_RES_SHORT = re.compile(r'^RESOURCE:?\s*' + _Q + r'$')
_FIELD = re.compile(r'^-\s*' + _Q + r'(\[\])?(?:\s+INSTRUCT\s+' + _Q + r')?(?:\s+POSSIBLE_VALUES\s+(\[.*\]))?$')

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
    value_var: Optional[str] = None       # FILL $x / SELECT $x / UPLOAD $x / BROWSER_FIND $x
    value_literal: Optional[str] = None   # FILL "john" (hard-coded)
    element: Optional[str] = None         # quoted target; URL for GOTO; what to read for GRAB
    intent: Optional[str] = None
    num: int = 0                          # 1-based step number, document order
    path: Tuple[Tuple[str, str], ...] = ()  # ((block_id, "then"|"else"), ...) outermost first
    critical: bool = False                # line ends with `# critical`
    grab_var: Optional[str] = None        # GRAB ... INTO $x: the variable the step defines
    grab_list: bool = False               # GRAB ALL ... INTO $x[]
    possible_values: Optional[List[str]] = None   # GRAB ... POSSIBLE_VALUES [...]
    seconds: Optional[int] = None         # WAIT <seconds>

    def action_vars(self) -> List[str]:
        """Variables used by the action itself (value + element), excluding the intent.

        A GRAB target is defined by the step, not used by it, so it is not included."""
        out = [self.value_var] if self.value_var else []
        out += [v for v in vars_in(self.element) if v not in out]
        return out

    def all_vars(self) -> List[str]:
        out = self.action_vars()
        out += [v for v in vars_in(self.intent) if v not in out]
        return out


@dataclass
class Block:
    """A logic block. ELIF is stored as an IF (is_elif=True) that is the only step of the previous
    IF's ELSE branch, so `IF a / ELIF b / ELSE c` has the same tree as `IF a / ELSE (IF b / ELSE c)`."""
    kind: str                       # IF | FOR_EACH | WHEN | UNTIL | WAIT_UNTIL
    line: int
    text: str
    var: Optional[str] = None       # IF variable
    op: Optional[str] = None        # EQUALS | NOT_EQUALS | EXISTS | EMPTY | NOT_EMPTY | IN
    literal: Optional[str] = None   # IF comparison literal
    rhs_var: Optional[str] = None   # IF $x IN $list
    is_elif: bool = False
    item_var: Optional[str] = None  # FOR_EACH $item (or $value of a map loop)
    key_var: Optional[str] = None   # FOR_EACH $key, $value IN $map
    list_var: Optional[str] = None  # FOR_EACH ... IN $list (or $map)
    parallel: bool = False          # FOR_EACH ... EXECUTE_PARALLEL
    condition: Optional[str] = None  # WHEN/UNTIL/WAIT_UNTIL natural-language condition
    then: List["Node"] = field(default_factory=list)
    else_: Optional[List["Node"]] = None
    else_line: Optional[int] = None
    id: str = ""
    path: Tuple[Tuple[str, str], ...] = ()

    def condition_text(self) -> str:
        if self.kind == "IF":
            rhs = f' "{self.literal}"' if self.literal is not None else f" ${self.rhs_var}" if self.rhs_var else ""
            return f"{'ELIF' if self.is_elif else 'IF'} ${self.var} {self.op}{rhs}"
        if self.kind == "FOR_EACH":
            loop = f"${self.key_var}, ${self.item_var}" if self.key_var else f"${self.item_var}"
            return f"FOR_EACH {loop} IN ${self.list_var}" + (" EXECUTE_PARALLEL" if self.parallel else "")
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
    value: Union[str, List[str], Dict[str, Union[str, List[str]]], None]   # None = EMPTY; dict = map
    optional: bool = False

    @property
    def kind(self) -> str:
        if self.value is None:
            return "empty"
        if isinstance(self.value, dict):
            return "map"
        return "list" if isinstance(self.value, list) else "scalar"


@dataclass
class Script:
    source: str
    url: Optional[str] = None             # the URL, or CONTINUE_FROM_LOGIN
    sections: List[Union[StepsSection, Resource, Extract]] = field(default_factory=list)
    variables: Dict[str, Variable] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    duplicate_vars: List[Variable] = field(default_factory=list)
    map_optional: Dict[str, Set[bool]] = field(default_factory=dict)   # map name -> `?` flags seen

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
        s.url = m.group(1) if m.group(1) is not None else m.group(2)
        _no_children(node, s)
        return
    if t == "URL" or t.startswith("URL "):
        s.issues.append(Issue(node.no, "E_URL_SYNTAX",
                              "URL takes a quoted URL or CONTINUE_FROM_LOGIN, and nothing else"))
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
    m = _MAP_DEF.match(t)
    if m:
        _parse_map_entry(node, m, s)
        _no_children(node, s)
        return
    m = _VAR_DEF.match(t)
    if m:
        var = Variable(m.group(1), node.no, None, optional=bool(m.group(2)))
        text = m.group(3).strip()
        ok, value = _parse_value(text)
        if text.startswith("{"):
            s.issues.append(Issue(node.no, "E_MAP_OBJECT",
                                  f"${var.name}: declare a map one entry per line, e.g. ${var.name}[\"key\"] = [...]"))
        elif not ok:
            s.issues.append(Issue(node.no, "E_VAR_VALUE",
                                  f"${var.name}: value must be \"text\", [\"a\", \"b\"] or EMPTY"))
        var.value = value
        prev = s.variables.get(var.name)
        if prev is not None and prev.kind == "map":
            s.issues.append(Issue(node.no, "E_MAP_CONFLICT", f"${var.name} cannot be both a map and a single value"))
        elif prev is not None:
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


_MAP_KEY_QUOTED = re.compile(_Q)
_MAP_KEY_BARE = re.compile(r'[^"\[\]$\s]+')


def _parse_map_entry(node: _Line, m: "re.Match", s: Script) -> None:
    """One `$name["key"] = value` line of a map variable (syntax reference 2.2)."""
    name, optional, raw_key, text = m.group(1), bool(m.group(2)), m.group(3).strip(), m.group(4).strip()
    no = node.no
    if "][" in raw_key:
        s.issues.append(Issue(no, "E_MAP_NESTED", f"${name}: maps are one level deep"))
        return
    if "$" in raw_key:
        s.issues.append(Issue(no, "E_MAP_KEY_VAR", f"${name}: map keys are plain text; variables are not substituted"))
        return
    km = _MAP_KEY_QUOTED.fullmatch(raw_key)
    if km:
        key = km.group(1)
    elif _MAP_KEY_BARE.fullmatch(raw_key):
        key = raw_key
    elif re.fullmatch(r'[^"\[\]$]+', raw_key):
        s.issues.append(Issue(no, "E_MAP_KEY_QUOTES", f"${name}: a key with spaces needs quotes: [\"{raw_key}\"]"))
        return
    else:
        s.issues.append(Issue(no, "E_MAP_KEY", f"${name}: malformed map key [{raw_key}]"))
        return
    ok, value = _parse_value(text)
    if ok and value is None:
        s.issues.append(Issue(no, "E_MAP_EMPTY", f"${name}[\"{key}\"]: use [] for a key with no values; "
                                                 "EMPTY is not allowed as a map entry"))
        return
    if not ok:
        s.issues.append(Issue(no, "E_VAR_VALUE", f"${name}[\"{key}\"]: value must be \"text\" or [\"a\", \"b\"]"))
        return
    var = s.variables.get(name)
    if var is None:
        var = s.variables[name] = Variable(name, no, {}, optional=optional)
        s.map_optional[name] = set()
    elif var.kind != "map":
        s.issues.append(Issue(no, "E_MAP_CONFLICT", f"${name} cannot be both a map and a single value"))
        return
    if key in var.value:
        s.issues.append(Issue(no, "E_MAP_DUP_KEY", f"${name}: key \"{key}\" is declared more than once"))
        return
    flags = s.map_optional[name]
    if flags and optional not in flags:      # reported once, where the entries start to mix
        s.issues.append(Issue(no, "E_MAP_OPTIONAL", f"${name}: mark every map entry with ? or none of them"))
    flags.add(optional)
    var.value[key] = value


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
        word = stmt.split()[0] if stmt.split() else ""
        if word in ("ELSE", "ELIF"):
            _parse_else(node, stmt, word, out, s)
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


def _chain_tail(prev: Optional[Node]) -> Optional[Block]:
    """The last block of an IF / ELIF ... chain (or the block itself), which an ELIF / ELSE attaches to."""
    while (isinstance(prev, Block) and prev.else_ is not None and len(prev.else_) == 1
           and isinstance(prev.else_[0], Block) and prev.else_[0].is_elif):
        prev = prev.else_[0]
    return prev if isinstance(prev, Block) else None


def _parse_else(node: _Line, stmt: str, word: str, out: List[Node], s: Script) -> None:
    tail = _chain_tail(out[-1] if out else None)
    open_tail = tail is not None and tail.else_ is None
    if word == "ELSE":
        if stmt != "ELSE":
            s.issues.append(Issue(node.no, "E_ELSE_SYNTAX", "ELSE takes no condition"))
            return
        if not (open_tail and tail.kind in ("IF", "WHEN")):
            s.issues.append(Issue(node.no, "E_ELSE_ORPHAN", "ELSE must directly follow an IF, ELIF or WHEN block"))
            return
        tail.else_ = _parse_steps(node.children, s)
        tail.else_line = node.no
        if not node.children:
            s.issues.append(Issue(node.no, "E_EMPTY_BODY", "ELSE must have at least one nested step"))
        return
    if open_tail and tail.kind == "WHEN":
        s.issues.append(Issue(node.no, "E_ELIF_AFTER_WHEN", "WHEN supports ELSE but not ELIF"))
        return
    if not (open_tail and tail.kind == "IF"):
        s.issues.append(Issue(node.no, "E_ELIF_ORPHAN", "ELIF must directly follow an IF or another ELIF"))
        return
    block = _parse_block_header("IF" + stmt[len("ELIF"):], node.no)
    if block is None or block.kind != "IF":
        _step_error(stmt, node.no, s)
        return
    block.text, block.is_elif = stmt, True
    block.then = _parse_steps(node.children, s)
    tail.else_ = [block]
    tail.else_line = node.no


def _parse_block_header(stmt: str, no: int) -> Optional[Block]:
    if stmt.startswith("IF "):
        cond = stmt[3:].strip()
        m = _COND_CMP.match(cond)
        if m:
            return Block("IF", no, stmt, var=m.group(1), op=m.group(2), literal=m.group(3))
        m = _COND_UNARY.match(cond)
        if m:
            return Block("IF", no, stmt, var=m.group(1), op=m.group(2))
        m = _COND_IN.match(cond)
        if m:
            return Block("IF", no, stmt, var=m.group(1), op="IN", rhs_var=m.group(2))
        return None
    m = _FOR_EACH.match(stmt)
    if m:
        return Block("FOR_EACH", no, stmt, item_var=m.group(1), list_var=m.group(2), parallel=bool(m.group(3)))
    m = _FOR_EACH_MAP.match(stmt)
    if m:
        return Block("FOR_EACH", no, stmt, key_var=m.group(1), item_var=m.group(2), list_var=m.group(3),
                     parallel=bool(m.group(4)))
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
        if kw == "WAIT":
            return Action(kw, no, stmt, seconds=int(m.group(1)))
        if kw == "BROWSER_FIND":
            return Action(kw, no, stmt, value_var=m.group(1))
        if kw == "GRAB":
            a = _grab(m, stmt, no, s)
        elif kw in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "HOVER"):
            a = Action(kw, no, stmt, element=m.group(1), intent=m.group(2))
        else:
            a = Action(kw, no, stmt, value_var=m.group(1), value_literal=m.group(2),
                       element=m.group(3), intent=m.group(4))
            if kw == "SELECT" and a.value_literal is not None:
                s.issues.append(Issue(no, "E_SELECT_LITERAL",
                                      "SELECT takes a $variable written without quotes, not a quoted value"))
        if a.intent is None:
            s.issues.append(Issue(no, "E_NO_INTENT", f"{a.keyword} requires an INTENT"))
        return a
    _step_error(stmt, no, s)
    return None


def _grab(m: "re.Match", stmt: str, no: int, s: Script) -> Action:
    is_all, target, as_list, pv = bool(m.group(1)), m.group(3), bool(m.group(4)), m.group(6)
    a = Action("GRAB ALL" if is_all else "GRAB", no, stmt, element=m.group(2), intent=m.group(5),
               grab_var=target, grab_list=as_list)
    if is_all and not as_list:
        s.issues.append(Issue(no, "E_GRAB_ALL_LIST", f"GRAB ALL must write into a list: INTO ${target}[]"))
    if as_list and not is_all:
        s.issues.append(Issue(no, "E_GRAB_LIST", f"only GRAB ALL may write into a list (${target}[])"))
    if pv is not None:
        if is_all:
            s.issues.append(Issue(no, "E_GRAB_ALL_VALUES", "POSSIBLE_VALUES cannot be used with GRAB ALL"))
        ok, vals = _parse_value(pv)
        if not ok or not isinstance(vals, list) or not vals or not all(v.strip() for v in vals):
            s.issues.append(Issue(no, "E_GRAB_VALUES",
                                  "POSSIBLE_VALUES must be a list with at least one non-empty quoted value"))
        else:
            a.possible_values = vals
    return a


def _step_error(stmt: str, no: int, s: Script) -> None:
    """Report a step line that matched no action or block, as specifically as possible."""
    word = stmt.split()[0] if stmt.split() else ""
    rest = stmt[len(word):].strip()
    if word in NO_INTENT_KEYWORDS and re.search(r'\sINTENT\s+"', stmt):
        s.issues.append(Issue(no, "E_INTENT_NOT_ALLOWED", f"{word} takes no INTENT"))
    elif word == "WAIT":
        s.issues.append(Issue(no, "E_WAIT_SECONDS", "WAIT takes a whole number of seconds above 0, e.g. WAIT 30"))
    elif word == "BROWSER_FIND":
        s.issues.append(Issue(no, "E_BROWSER_FIND_VALUE",
                              "BROWSER_FIND must be followed by a $variable only, not a quoted literal"))
    elif word == "GOTO" and "CONTINUE_FROM_LOGIN" in rest:
        s.issues.append(Issue(no, "E_GOTO_LOGIN", "CONTINUE_FROM_LOGIN only works on the URL line, not with GOTO"))
    elif word in ("IF", "ELIF") and re.match(r'\$\w+\s+(==|!=)', rest):
        s.issues.append(Issue(no, "E_OPERATOR_SYMBOL", "use EQUALS / NOT_EQUALS; == and != are not supported"))
    elif word in ("IF", "ELIF") and re.match(r'\$\w+\s+IN\s+\[', rest):
        s.issues.append(Issue(no, "E_IN_LITERAL", "the right-hand side of IN must be a list variable, not a literal list"))
    elif word == "FOR_EACH" and re.match(r'\$\w+\s+IN\s+\$\w+\s+\S', rest):
        s.issues.append(Issue(no, "E_FOR_EACH_SUFFIX", "only EXECUTE_PARALLEL may follow FOR_EACH $item IN $list"))
    elif word == "EXECUTE_PARALLEL":
        s.issues.append(Issue(no, "E_PARALLEL_STANDALONE",
                              "EXECUTE_PARALLEL goes at the end of a FOR_EACH line, not as its own step"))
    elif word in ACTION_KEYWORDS:
        s.issues.append(Issue(no, "E_ACTION_SYNTAX", f"malformed {word} statement: {stmt!r}"))
    elif word in BLOCK_KINDS:
        s.issues.append(Issue(no, "E_CONDITION_SYNTAX", f"malformed {word} condition: {stmt!r}"))
    else:
        s.issues.append(Issue(no, "E_UNKNOWN_STEP", f"unknown step keyword: {stmt!r}"))


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
