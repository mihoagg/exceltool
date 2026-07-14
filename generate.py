import sys
import itertools
from parser import parse, execute_all


template = sys.argv[1]
rule = sys.argv[2] if len(sys.argv) > 2 else ""

vars = []
seen = set()
for ch in template:
    if ch.isupper() and ch not in seen:
        seen.add(ch)
        vars.append(ch)

results = []
conditions = parse(rule) if rule else []

if not conditions:
    print(0)
    sys.exit(0)
else:
    for combo in itertools.product("0123456789", repeat=len(vars)):
        ctx = dict(zip(vars, combo))
        if all(execute_all(conditions, ctx)):
            s = template
            for var, val in ctx.items():
                s = s.replace(var, val)
            results.append(s)

for r in results:
    print(r)
print("total: " , len(results))
    
