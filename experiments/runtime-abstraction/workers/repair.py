#!/usr/bin/env python3
"""repair.py LEDGER.csv OUT.csv  -- copy a ledger, dropping malformed rows."""
import sys
if len(sys.argv) != 3:
    print("usage: repair.py LEDGER.csv OUT.csv", file=sys.stderr); sys.exit(1)
lines = open(sys.argv[1]).read().splitlines()
keep, dropped = lines[:2], 0
ncols = len(lines[1].split(","))
for line in lines[2:]:
    f = line.split(",")
    try:
        assert len(f) == ncols and f[3] in ("USD", "EUR", "GBP", "JPY"); float(f[2]); keep.append(line)
    except (AssertionError, ValueError):
        dropped += 1
open(sys.argv[2], "w").write("\n".join(keep) + "\n")
print(f"repaired: dropped {dropped} malformed rows -> {sys.argv[2]}")
