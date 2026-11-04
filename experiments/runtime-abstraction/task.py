"""Task family: regional revenue report.

Builds one task instance (data + worker programs), computes ground truth with
an independent reference implementation, and grades a delivered report.

Designed difficulties, identical across arms:
  - duplicate txn_ids inside ledgers (normalize dedups)
  - one ledger with malformed rows (normalize fails; repair is the remedy)
  - two regions with byte-identical ledger bodies (cache opportunity)
  - two rate tables; the objective says "current", the latest is correct
  - every record carries a fingerprint; a few were tampered with after signing.
    Only the expensive fingerprint check (~1.5 s CPU per ledger) finds them, so
    an agent that skips the contract's verification step gets a wrong answer.
"""
import hashlib
import csv
import json
import random
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKERS = HERE / "workers"

REGIONS = ["north", "south", "east", "west", "central", "coastal", "highland", "metro"]
PRODUCTS = ["anvil", "bolt", "cable", "dynamo", "ember"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY"]
RATES_OLD = {"USD": 1.0, "EUR": 1.05, "GBP": 1.22, "JPY": 0.0068}
RATES_NEW = {"USD": 1.0, "EUR": 1.09, "GBP": 1.27, "JPY": 0.0065}
CORRUPT_REGION = "south"
MIRROR = ("coastal", "east")  # coastal's body is byte-identical to east's

FP_ROUNDS = 27000


def fingerprint(txn, amount):
    h = f"{txn}|{amount}".encode()
    for _ in range(FP_ROUNDS):
        h = hashlib.sha256(h).digest()
    return h.hex()[:12]


OBJECTIVE = (
    "Produce the regional revenue report. For every regional sales ledger: "
    "deduplicate and normalize its transactions, convert amounts to USD using "
    "the current exchange rates, and report USD revenue per region per product, "
    "plus a grand total. Deliver the report as the result of this objective. "
    "Every region must be included."
)


def _rows(rng, region):
    rows, n = [], 160
    for i in range(n):
        txn, amt = f"{region[:2].upper()}{i:04d}", f"{rng.uniform(5, 900):.2f}"
        rows.append([txn, rng.choice(PRODUCTS), amt, rng.choice(CURRENCIES), fingerprint(txn, amt)])
    for r in rng.sample(rows, 4):  # tampered after signing
        r[2] = f"{float(r[2]) * 3 + 50:.2f}"
    for _ in range(12):  # duplicates
        rows.append(list(rng.choice(rows)))
    rng.shuffle(rows)
    return rows


def build(dest: Path, seed: int = 7):
    """Create data/ under dest. Returns ground truth. Generation is memoized
    per seed because signing is deliberately expensive."""
    cache = HERE / ".taskcache" / str(seed)
    if not (cache / "truth.json").exists():
        tmp = cache.with_name(f"{seed}.tmp{random.random()}")
        t = _build(tmp, seed)
        (tmp / "truth.json").write_text(json.dumps(t))
        try:
            tmp.rename(cache)
        except OSError:
            shutil.rmtree(tmp)
    shutil.copytree(cache / "data", dest / "data", dirs_exist_ok=True)
    return json.loads((cache / "truth.json").read_text())


def _build(dest: Path, seed: int):
    rng = random.Random(seed)
    data = dest / "data"
    data.mkdir(parents=True, exist_ok=True)
    bodies = {}
    for region in REGIONS:
        if region == MIRROR[0]:
            continue
        bodies[region] = _rows(rng, region)
    bodies[MIRROR[0]] = bodies[MIRROR[1]]
    for region in REGIONS:
        lines = [f"#region={region}", "txn_id,product,amount,currency,fingerprint"]
        lines += [",".join(r) for r in bodies[region]]
        if region == CORRUPT_REGION:
            lines.insert(9, "SO9001,bolt,12..50,EUR,000000000000")
            lines.insert(40, "SO9002,cable")
            lines.insert(77, "SO9003,anvil,not-a-number,USD,000000000000")
        # The mirror shares its transaction body with east but not its region
        # line, so a byte-level cache misses it and only a cache keyed on the
        # operation's real input (the body) can skip the work.
        (data / f"ledger_{region}.csv").write_text("\n".join(lines) + "\n")
    for name, rates in (("rates_2026-10.csv", RATES_OLD), ("rates_2026-11.csv", RATES_NEW)):
        (data / name).write_text("currency,usd_per_unit\n" +
                                 "".join(f"{c},{v}\n" for c, v in rates.items()))
    return truth(bodies)


def truth(bodies):
    report = {}
    for region, rows in bodies.items():
        seen, per = set(), {}
        for txn, product, amount, cur, fp in rows:
            if fingerprint(txn, amount) != fp or txn in seen:
                continue
            seen.add(txn)
            per[product] = per.get(product, 0.0) + float(amount) * RATES_NEW[cur]
        report[region] = {p: round(v, 2) for p, v in sorted(per.items())}
    grand = round(sum(v for r in report.values() for v in r.values()), 2)
    return {"regions": report, "grand_total_usd": grand}


def install_workers(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for f in WORKERS.iterdir():
        if f.suffix == ".py":
            shutil.copy(f, dest / f.name)


def grade(report_path: Path, expected: dict):
    """Returns (passed: bool, reasons: list[str])."""
    if not report_path.is_file():
        return False, ["no report delivered"]
    try:
        got = json.loads(report_path.read_text())
    except Exception as e:  # noqa: BLE001
        return False, [f"report is not JSON: {e}"]
    reasons = []
    gr = got.get("regions") if isinstance(got, dict) else None
    if not isinstance(gr, dict):
        return False, ["report has no 'regions' object"]
    for region, prods in expected["regions"].items():
        if region not in gr:
            reasons.append(f"missing region {region}")
            continue
        for p, v in prods.items():
            gv = gr[region].get(p) if isinstance(gr[region], dict) else None
            if not isinstance(gv, (int, float)) or abs(gv - v) > 0.02:
                reasons.append(f"{region}/{p}: got {gv} want {v}")
    for region in gr:
        if region not in expected["regions"]:
            reasons.append(f"unexpected region {region}")
    gt = got.get("grand_total_usd")
    if not isinstance(gt, (int, float)) or abs(gt - expected["grand_total_usd"]) > 0.05:
        reasons.append(f"grand_total_usd: got {gt} want {expected['grand_total_usd']}")
    return not reasons, reasons[:10]
