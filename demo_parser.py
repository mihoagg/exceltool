import sys
from parser import parse


def cond_to_str(cond: dict) -> str:
    t = cond.get("type")
    if t == "and":
        children = cond.get("children", [])
        return "(" + " and ".join(cond_to_str(c) for c in children) + ")"
    if t == "or":
        children = cond.get("children", [])
        return "(" + " or ".join(cond_to_str(c) for c in children) + ")"
    if t == "not":
        return "not " + cond_to_str(cond["children"][0])
    field = cond.get("field", "?")
    op_map = {"equals": "=", "not_equals": "#", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}
    op = op_map.get(t, "?")
    values = cond.get("values", [])
    vals = ", ".join(values)
    return f"{field} {op} {vals}"


def rebuild(rule_str: str) -> str:
    conditions = parse(rule_str)
    return " -- ".join(cond_to_str(c) for c in conditions)


if len(sys.argv) > 1:
    rule_str = " ".join(sys.argv[1:])
    print(rebuild(rule_str))
else:
    print("Usage: python demo_parser.py <rule>")
    print("Example: python demo_parser.py \"A=5,8,9, A#B\"")
