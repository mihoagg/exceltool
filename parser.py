import re


def split_conditions(rule_str: str) -> list[str]:
    parts = []
    depth = 0
    i = 0
    start = 0
    n = len(rule_str)
    while i < n:
        if rule_str[i] == "(":
            depth += 1
            i += 1
        elif rule_str[i] == ")":
            depth -= 1
            i += 1
        elif rule_str[i] in (",", ";") and depth == 0:
            if rule_str[i] == ";":
                parts.append(rule_str[start:i].strip())
                start = i + 1
            else:
                after = rule_str[i+1:]
                m = re.match(r'\s*([A-Za-z]+)\s*(?:,\s*[A-Za-z]+\s*)*(?:[=#]|>=|<=|>|<)', after)
                if not m:
                    m = re.match(r'\s*(\d+)\s*(?:[=#]|>=|<=|>|<)', after)
                if m:
                    parts.append(rule_str[start:i].strip())
                    start = i + 1
            i += 1
        elif rule_str[i] in (" ", "\t") and depth == 0:
            buf = rule_str[start:i].strip()
            if buf and any(op in buf for op in ("=", "#", ">", "<")):
                words = buf.rsplit(None, 1)
                if len(words) > 1 and words[-1].lower() in ("and", "or", "not"):
                    i += 1
                    continue
                j = i
                while j < n and rule_str[j] in (" ", "\t"):
                    j += 1
                if j < n:
                    rest = rule_str[j:]
                    m = re.match(r'([A-Za-z]+)\s*(?:[=#]|>=|<=|>|<)', rest)
                    if not m:
                        m = re.match(r'(\d+)\s*(?:[=#]|>=|<=|>|<)', rest)
                    if m:
                        parts.append(buf)
                        start = j
                        i = j
                        continue
            i += 1
        else:
            i += 1
    if start < n:
        tail = rule_str[start:].strip()
        if tail:
            parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


OP_RE = r"(?:>=|<=|>|<|=|#)"
_CHAIN_RE = r"([A-Za-z0-9]+)\s*(" + OP_RE + r")\s*"


def _find_matching_paren(s: str, start: int = 0) -> int:
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(s) - 1


def _split_on(expr: str, kw: str) -> list[str]:
    parts = []
    depth = 0
    i = 0
    start = 0
    n = len(expr)
    k = len(kw)
    while i < n:
        if expr[i] == "(":
            depth += 1
            i += 1
        elif expr[i] == ")":
            depth -= 1
            i += 1
        elif depth == 0 and expr[i:i+k].lower() == kw:
            before_ok = i == 0 or not expr[i-1].isalnum()
            after_ok = i+k >= n or not expr[i+k].isalnum()
            if before_ok and after_ok:
                parts.append(expr[start:i].strip())
                i += k
                start = i
                continue
            i += 1
        else:
            i += 1
    if start < n:
        tail = expr[start:].strip()
        if tail:
            parts.append(tail)
    return parts


def parse_condition(cond: str) -> dict:
    cond = cond.strip()
    if not cond:
        return None

    or_parts = _split_on(cond, "or")
    if len(or_parts) > 1:
        children = [parse_condition(p) for p in or_parts if parse_condition(p)]
        if len(children) == 1:
            return children[0]
        return {"type": "or", "children": children}

    and_parts = _split_on(cond, "and")
    if len(and_parts) > 1:
        children = [_parse_single(p) for p in and_parts if _parse_single(p)]
        if len(children) == 1:
            return children[0]
        return {"type": "and", "children": children}

    return _parse_single(cond)


def _parse_single(expr: str) -> dict:
    expr = expr.strip()
    if not expr:
        return None

    if expr.lower().startswith("not") and (len(expr) == 3 or not expr[3].isalpha()):
        inner_str = expr[3:].lstrip()
        if inner_str.startswith("("):
            end = _find_matching_paren(inner_str)
            inner_raw = inner_str[1:end].strip() if end > 0 else ""
        else:
            inner_raw = inner_str
        if inner_raw:
            inner = parse_condition(inner_raw)
            if inner:
                return {"type": "not", "children": [inner]}
        return {"type": "raw", "raw": expr}

    if expr.startswith("("):
        end = _find_matching_paren(expr)
        inner = expr[1:end].strip()
        if inner:
            inner_conds = split_conditions(inner)
            children = [parse_condition(c) for c in inner_conds if parse_condition(c)]
            if len(children) == 1:
                return children[0]
            return {"type": "and", "children": children}
        return {"type": "raw", "raw": expr}

    m = re.match(r'^([A-Za-z]+)\s*(' + OP_RE + r')\s*(.+)$', expr)
    if not m:
        m = re.match(r'^(\d+)\s*(' + OP_RE + r')\s*(.+)$', expr)
    if m:
        left = m.group(1).strip()
        op = m.group(2)
        right = m.group(3).strip()

        cm = re.match(_CHAIN_RE, right)
        if cm:
            if op == "#":
                parts = [left]
                rest_right = right
                while True:
                    c = re.match(_CHAIN_RE, rest_right)
                    if c:
                        parts.append(c.group(1))
                        rest_right = rest_right[len(c.group(0)):].strip()
                    else:
                        if rest_right:
                            parts.append(rest_right)
                        break
                children = []
                for i in range(len(parts)):
                    for j in range(i + 1, len(parts)):
                        children.append(_build_node(parts[i], "#", [parts[j]]))
                if len(children) == 1:
                    return children[0]
                return {"type": "and", "children": children}
            else:
                first = _build_node(left, op, [cm.group(1)])
                rest = _parse_single(cm.group(1) + " " + cm.group(2) + " " + right[len(cm.group(0)):].strip())
                if rest and rest.get("type") != "raw":
                    return {"type": "and", "children": [first, rest]}

        vals = [v.strip() for v in re.split(r",\s*", right) if v.strip()]
        return _build_node(left, op, vals)

    return {"type": "raw", "raw": expr}


_OP_MAP = {
    "=": "equals",
    "#": "not_equals",
    ">=": "gte",
    "<=": "lte",
    ">": "gt",
    "<": "lt",
}


def _build_node(field: str, op: str, vals: list[str]) -> dict:
    t = _OP_MAP.get(op)
    if not t:
        return {"type": "raw", "raw": f"{field}{op}{vals}"}

    if len(field) > 1 and field.isalpha():
        if op == "=":
            return _decompose_equals(field, vals)
        if op == "#":
            return _decompose_not_equals(field, vals)

    return {"type": t, "field": field, "values": vals}


def _dedup_children(nodes: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for n in nodes:
        key = (n.get("type"), n.get("field"), tuple(n.get("values", [])))
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def _pad_val(val: str, length: int) -> str:
    if len(val) == length:
        return val
    if len(val) < length:
        return ((val * (length // len(val) + 1))[:length])
    return val[:length]


def _decompose_equals(field: str, vals: list[str]) -> dict:
    letters = list(field)
    n = len(letters)

    if all(len(v) < n for v in vals):
        digits = sorted(set(''.join(vals)))
        if not digits:
            return {"type": "raw", "raw": f"{field}={','.join(vals)}"}
        children = [{"type": "equals", "field": var, "values": digits} for var in letters]
        children = _dedup_children(children)
        if len(children) == 1:
            return children[0]
        return {"type": "and", "children": children}

    branches = []
    for val in vals:
        v = _pad_val(val, n)
        if not v:
            continue
        children = _dedup_children([
            {"type": "equals", "field": var, "values": [ch]}
            for var, ch in zip(letters, v)
        ])
        if len(children) == 1:
            branches.append(children[0])
        else:
            branches.append({"type": "and", "children": children})
    if len(branches) == 1:
        return branches[0]
    return {"type": "or", "children": branches}


def _decompose_not_equals(field: str, vals: list[str]) -> dict:
    letters = list(field)
    n = len(letters)

    if all(len(v) < n for v in vals):
        digits = sorted(set(''.join(vals)))
        if not digits:
            return {"type": "raw", "raw": f"{field}#{','.join(vals)}"}
        children = [{"type": "not_equals", "field": var, "values": digits} for var in letters]
        children = _dedup_children(children)
        if len(children) == 1:
            return children[0]
        return {"type": "or", "children": children}

    groups = []
    for val in vals:
        v = _pad_val(val, n)
        if not v:
            continue
        children = _dedup_children([
            {"type": "not_equals", "field": var, "values": [ch]}
            for var, ch in zip(letters, v)
        ])
        if len(children) == 1:
            groups.append(children[0])
        else:
            groups.append({"type": "or", "children": children})
    if len(groups) == 1:
        return groups[0]
    return {"type": "and", "children": groups}


def _expand_multi_field_conditions(conditions: list[str]) -> list[str]:
    _SOLO_RE = re.compile(r'^[A-Za-z]+$')
    _OP_COND_RE = re.compile(r'^([A-Za-z]+)\s*([=#]|>=|<=|>|<)\s*(.+)$')
    result = []
    i = 0
    while i < len(conditions):
        chunk = conditions[i]
        op_m = _OP_COND_RE.match(chunk)
        if op_m:
            op = op_m.group(2)
            vals = op_m.group(3).strip()
            solo_fields = []
            j = len(result) - 1
            while j >= 0:
                if _SOLO_RE.match(result[j]):
                    solo_fields.insert(0, result[j])
                    j -= 1
                else:
                    break
            if solo_fields:
                result = result[:j + 1]
                for f in solo_fields:
                    result.append(f'{f}{op}{vals}')
            result.append(chunk)
            i += 1
            continue
        # Split comma-separated field names before adding
        for piece in chunk.split(','):
            p = piece.strip()
            if p:
                if _SOLO_RE.match(p):
                    result.append(p)
                else:
                    result.append(p)
        i += 1
    return result


def parse(rule_str: str) -> list[dict]:
    raw_conditions = split_conditions(rule_str)
    expanded = _expand_multi_field_conditions(raw_conditions)
    return [parse_condition(c) for c in expanded if parse_condition(c)]


def _resolve(v: str, context: dict) -> str:
    return str(context.get(v, v))


def execute_condition(cond: dict, context: dict) -> bool:
    if cond is None:
        return True
    t = cond.get("type")

    if t == "and":
        for child in cond.get("children", []):
            if not execute_condition(child, context):
                return False
        return True

    if t == "or":
        for child in cond.get("children", []):
            if execute_condition(child, context):
                return True
        return False

    if t == "equals":
        val = str(context.get(cond["field"], ""))
        return val in [_resolve(v, context) for v in cond["values"]]

    if t == "not_equals":
        val = str(context.get(cond["field"], ""))
        return val not in [_resolve(v, context) for v in cond["values"]]

    if t == "gte":
        return int(context.get(cond["field"], 0)) >= int(_resolve(cond["values"][0], context))
    if t == "lte":
        return int(context.get(cond["field"], 0)) <= int(_resolve(cond["values"][0], context))
    if t == "gt":
        return int(context.get(cond["field"], 0)) > int(_resolve(cond["values"][0], context))
    if t == "lt":
        return int(context.get(cond["field"], 0)) < int(_resolve(cond["values"][0], context))

    if t == "not":
        return not execute_condition(cond["children"][0], context)

    return True


def execute_all(conditions: list[dict], context: dict) -> list[bool]:
    return [execute_condition(c, context) for c in conditions]


def run(rule_str: str, context: dict) -> list[bool]:
    conditions = parse(rule_str)
    return execute_all(conditions, context)
