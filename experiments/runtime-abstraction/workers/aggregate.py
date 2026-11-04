#!/usr/bin/env python3
"""aggregate.py RATES.csv OUT.json NORMALIZED.csv [NORMALIZED.csv ...]
Converts to USD and sums per region per product; adds grand_total_usd.
Refuses ledgers that were not normalized (duplicates present)."""
import json, sys
if len(sys.argv) < 4:
    print("usage: aggregate.py RATES.csv OUT.json NORMALIZED.csv...", file=sys.stderr); sys.exit(1)
rates = {}
for line in open(sys.argv[1]).read().splitlines()[1:]:
    c, v = line.split(","); rates[c] = float(v)
regions = {}
for path in sys.argv[3:]:
    lines = open(path).read().splitlines()
    region = lines[0].split("=", 1)[1]
    ids, per = set(), {}
    for line in lines[2:]:
        t, p, a, c = line.split(",")[:4]
        if t in ids:
            print(f"{path}: duplicate txn {t}; input is not normalized", file=sys.stderr); sys.exit(2)
        ids.add(t); per[p] = per.get(p, 0.0) + float(a) * rates[c]
    if region in regions:
        print(f"{path}: region {region} given twice", file=sys.stderr); sys.exit(2)
    regions[region] = {p: round(v, 2) for p, v in sorted(per.items())}
out = {"regions": regions, "grand_total_usd": round(sum(v for r in regions.values() for v in r.values()), 2)}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(f"aggregated {len(regions)} regions -> {sys.argv[2]}")
