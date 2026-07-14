import sys
import itertools
from parser import parse, execute_all


template = sys.argv[1]
rule = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""
outfile = sys.argv[3] if len(sys.argv) > 3 else ""

vars_ = []
seen = set()
for ch in template:
    if ch.isupper() and ch not in seen:
        seen.add(ch)
        vars_.append(ch)

conditions = parse(rule) if rule else []

results = []
if conditions:
    for combo in itertools.product("0123456789", repeat=len(vars_)):
        ctx = dict(zip(vars_, combo))
        if all(execute_all(conditions, ctx)):
            s = template
            for var, val in ctx.items():
                s = s.replace(var, val)
            results.append(s)
else:
    if rule:
        sys.exit(0)
    for combo in itertools.product("0123456789", repeat=len(vars_)):
        ctx = dict(zip(vars_, combo))
        s = template
        for var, val in ctx.items():
            s = s.replace(var, val)
        results.append(s)

lines = [str(len(results))] + results
output = "\n".join(lines)

if outfile:
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(output)
        f.write("\n")
    print(f"Saved {len(results)} combos to {outfile}")
else:
    print("Usage: python save_combos.py <template> [<rule>] [<outfile>]")
    print("  If <outfile> omitted, prints to stdout")
    print("  If <rule> omitted, generates all 10^n combos")
