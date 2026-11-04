#!/usr/bin/env python3
"""normalize.py LEDGER.csv OUT.csv
Validates every row, drops rows whose fingerprint does not verify (tampered;
CPU-expensive check), then drops duplicate txn_ids (first wins).
Exit 0 ok; exit 2 malformed input (nothing written); exit 1 usage."""
import hashlib, sys

def main():
    if len(sys.argv) != 3:
        print("usage: normalize.py LEDGER.csv OUT.csv", file=sys.stderr); return 1
    src, out = sys.argv[1], sys.argv[2]
    lines = open(src).read().splitlines()
    if not lines or not lines[0].startswith("#region="):
        print(f"{src}: first line must be '#region=<name>'", file=sys.stderr); return 2
    region, header, rows = lines[0], lines[1], lines[2:]
    bad, good = [], []
    for i, line in enumerate(rows, start=3):
        f = line.split(",")
        try:
            assert len(f) == 5 and f[3] in ("USD", "EUR", "GBP", "JPY")
            float(f[2])
            good.append(f)
        except (AssertionError, ValueError):
            bad.append(i)
    if bad:
        print(f"{src}: {len(bad)} malformed rows at lines {bad}; nothing written. "
              f"Remedy: tools/repair.py drops malformed rows into a new ledger.", file=sys.stderr)
        return 2
    seen, keep, tampered = set(), [], 0
    for f in good:
        h = f"{f[0]}|{f[2]}".encode()
        for _ in range(27000):           # fingerprint verification: real CPU work
            h = hashlib.sha256(h).digest()
        if h.hex()[:12] != f[4]:
            tampered += 1
            continue
        if f[0] not in seen:
            seen.add(f[0]); keep.append(f)
    with open(out, "w") as o:
        o.write(region + "\n" + header + "\n" + "".join(",".join(f) + "\n" for f in keep))
    print(f"normalized {len(keep)} rows ({tampered} failed fingerprint, "
          f"{len(good) - len(keep) - tampered} duplicates dropped) -> {out}")
    return 0

sys.exit(main())
