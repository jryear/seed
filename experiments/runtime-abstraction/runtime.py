#!/usr/bin/env python3
"""MCP stdio server exposing one experimental arm's interface to the agent.

Arms (2x2):
  shell       processes visible, services off   -> sh
  shell_svc   processes visible, services on    -> sh + cached_sh, checkpoints, verify_report
  cap         processes hidden,  services off   -> capability/state-transition API, process-local state
  cap_svc     processes hidden,  services on    -> same API + persistent states, semantic cache,
                                                   progress(), runtime-verified delivery

Every tool call is appended to --log (owned by the supervisor). The agent
never sees the log, the store, or any host path in the cap arms.
"""
import argparse
import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--arm", required=True, choices=["shell", "shell_svc", "cap", "cap_svc"])
ap.add_argument("--workspace", required=True)   # shell arms: agent's cwd. cap arms: hidden data root
ap.add_argument("--store", required=True)       # service store; survives agent interruption
ap.add_argument("--log", required=True)
ap.add_argument("--deliver-to", required=True)  # where the graded report lands
A = ap.parse_args()
WS, STORE, LOG, OUT = Path(A.workspace), Path(A.store), Path(A.log), Path(A.deliver_to)
STORE.mkdir(parents=True, exist_ok=True)
SESSION = os.environ.get("RT_SESSION", "?")


def log(rec):
    rec.update(t=round(time.time(), 3), arm=A.arm, session=SESSION)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
        h.update(b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------- shell arms
def t_sh(command):
    p = subprocess.run(["bash", "-c", command], cwd=WS, capture_output=True, text=True, timeout=180)
    out = (p.stdout + p.stderr)[-8000:]
    meta = {"spawns": 1, "normalize_ok": p.returncode == 0 and "normalize" in command}
    return {"exit_code": p.returncode, "output": out}, meta


def t_cached_sh(command, inputs, outputs):
    try:
        key = sha("sh", command, *[(WS / i).read_bytes() for i in inputs])
    except OSError as e:
        return {"error": f"input unreadable: {e}"}, {}
    entry = STORE / "shcache" / key
    if (entry / "meta.json").exists():
        meta = json.loads((entry / "meta.json").read_text())
        for i, o in enumerate(meta["outputs"]):
            dst = WS / o
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(entry / f"out{i}", dst)
        return {"exit_code": 0, "output": meta["output"], "cache": "hit"}, {"cache": "hit"}
    res, m = t_sh(command)
    if res["exit_code"] == 0:
        entry.mkdir(parents=True, exist_ok=True)
        for i, o in enumerate(outputs):
            if (WS / o).is_file():
                shutil.copy(WS / o, entry / f"out{i}")
        (entry / "meta.json").write_text(json.dumps({"outputs": outputs, "output": res["output"]}))
    res["cache"] = "miss"
    m["cache"] = "miss"
    return res, m


def _ckpt():
    f = STORE / "checkpoints.json"
    return f, (json.loads(f.read_text()) if f.exists() else {})


def t_checkpoint_put(key, value):
    f, d = _ckpt()
    d[key] = value
    f.write_text(json.dumps(d))
    return {"ok": True}, {}


def t_checkpoint_get(key):
    return {"value": _ckpt()[1].get(key)}, {}


def t_checkpoint_list():
    return {"checkpoints": _ckpt()[1]}, {}


def _ledger_regions(root):
    return sorted(p.read_text().splitlines()[0].split("=", 1)[1]
                  for p in (root / "data").glob("ledger_*.csv"))


def _verify(report, regions):
    problems = []
    if not isinstance(report, dict) or not isinstance(report.get("regions"), dict):
        return ["report must be an object with a 'regions' object"]
    missing = sorted(set(regions) - set(report["regions"]))
    if missing:
        problems.append(f"regions missing: {missing}")
    try:
        s = round(sum(v for r in report["regions"].values() for v in r.values()), 2)
        if abs(s - report.get("grand_total_usd", float("nan"))) > 0.05:
            problems.append("grand_total_usd does not equal the sum of region totals")
    except Exception:  # noqa: BLE001
        problems.append("region totals are not numeric")
    return problems


def t_verify_report(path):
    try:
        report = json.loads((WS / path).read_text())
    except Exception as e:  # noqa: BLE001
        return {"verified": False, "problems": [f"unreadable: {e}"]}, {}
    probs = _verify(report, _ledger_regions(WS))
    return {"verified": not probs, "problems": probs}, {}


# ------------------------------------------------------------------ cap arms
WORK = Path(tempfile.mkdtemp(prefix="rt-work-"))       # runtime-private scratch
if A.arm == "cap_svc":
    SDIR = STORE / "states"
else:
    SDIR = WORK / "states"                              # dies with this process
SDIR.mkdir(parents=True, exist_ok=True)
INDEX = SDIR / "index.json"
WORKERS = WS / "tools"


def _index():
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def _save_index(ix):
    INDEX.write_text(json.dumps(ix))


def _resources():
    res = []
    for p in sorted((WS / "data").glob("ledger_*.csv")):
        lines = p.read_text().splitlines()
        res.append({"id": f"ledger:{lines[0].split('=', 1)[1]}", "kind": "ledger",
                    "records": len(lines) - 2})
    for p in sorted((WS / "data").glob("rates_*.csv")):
        res.append({"id": f"rates:{p.stem.split('_', 1)[1]}", "kind": "rates",
                    "as_of": p.stem.split("_", 1)[1]})
    return res


def _resolve(ref):
    """resource id or state id -> (kind, file)"""
    if ref.startswith("ledger:"):
        f = WS / "data" / f"ledger_{ref[7:]}.csv"
        return ("ledger", f) if f.exists() else (None, None)
    if ref.startswith("rates:"):
        f = WS / "data" / f"rates_{ref[6:]}.csv"
        return ("rates", f) if f.exists() else (None, None)
    st = _index().get(ref)
    return (st["kind"], SDIR / st["file"]) if st else (None, None)


CAPS = {
    "normalize": {"inputs": {"ledger": "ledger"}, "produces": "normalized_ledger",
                  "contract": "Validates every record, drops records whose fingerprint does not "
                              "verify (tampered), then drops duplicate transaction ids (first "
                              "wins). Precondition: every record well-formed. Expensive."},
    "repair": {"inputs": {"ledger": "ledger"}, "produces": "ledger",
               "contract": "Produces a ledger with malformed records dropped."},
    "aggregate": {"inputs": {"rates": "rates", "ledgers": "list of normalized_ledger"},
                  "produces": "report",
                  "contract": "Converts to USD with the given rates; USD revenue per region per "
                              "product plus grand_total_usd. Each region at most once."},
}


def t_capabilities():
    return {"capabilities": CAPS}, {}


def t_resources():
    return {"resources": _resources()}, {}


def _scrub(text, mapping):
    for k, v in mapping.items():
        text = text.replace(k, v)
    text = re.sub(r"Remedy: tools/repair\.py[^.]*\.", "Remedy: capability 'repair'.", text)
    return text.strip()


def t_transition(capability, inputs):
    if capability not in CAPS:
        return {"ok": False, "failure": "unknown_capability"}, {}
    spec = CAPS[capability]["inputs"]
    if set(inputs) != set(spec):
        return {"ok": False, "failure": "bad_inputs", "expected": spec}, {}
    files, keyparts, names = {}, [capability], {}
    for name, want in spec.items():
        refs = inputs[name] if want.startswith("list") else [inputs[name]]
        if not isinstance(refs, list):
            return {"ok": False, "failure": "bad_inputs", "detail": f"{name} must be a list"}, {}
        want_kind = want.split()[-1]
        got = []
        for r in refs:
            kind, f = _resolve(str(r))
            if kind is None:
                return {"ok": False, "failure": "no_such_state", "detail": str(r)}, {}
            if kind != want_kind:
                return {"ok": False, "failure": "type_mismatch",
                        "detail": f"{r} is {kind}, {name} needs {want_kind}"}, {}
            got.append(f)
            names[str(f)] = str(r)
            body = f.read_bytes()
            if A.arm == "cap_svc" and capability == "normalize":
                body = body.split(b"\n", 1)[1]          # region label is metadata, not input
            keyparts.append(body)
        files[name] = got
    meta = {}
    ix = _index()
    key = sha(*keyparts)
    if A.arm == "cap_svc":
        hit = next((sid for sid, s in ix.items() if s.get("key") == key), None)
        if hit and capability != "normalize":
            meta["cache"] = "hit"
            return {"ok": True, "state": hit, "kind": ix[hit]["kind"], "executed": False,
                    "summary": ix[hit]["summary"]}, meta
        src = files["ledger"][0].read_text().splitlines()[0] if capability == "normalize" else ""
        if hit and capability == "normalize" and ix[hit].get("label") == src:
            meta["cache"] = "hit"
            return {"ok": True, "state": hit, "kind": "normalized_ledger", "executed": False,
                    "summary": ix[hit]["summary"]}, meta
        if hit and capability == "normalize":
            cached = (SDIR / ix[hit]["file"]).read_text().split("\n", 1)[1]
            sid = "st_" + sha(key, src)[:10]
            if sid not in ix:
                (SDIR / f"{sid}.dat").write_text(src + "\n" + cached)
                ix[sid] = {"kind": "normalized_ledger", "file": f"{sid}.dat", "key": key + src,
                           "from": {"capability": capability, "inputs": inputs},
                           "summary": ix[hit]["summary"], "session": SESSION}
                _save_index(ix)
            meta["cache"] = "hit"
            return {"ok": True, "state": sid, "kind": "normalized_ledger", "executed": False,
                    "summary": ix[sid]["summary"]}, meta
    sid = "st_" + sha(key, time.time())[:10]
    out = SDIR / f"{sid}.dat"
    if capability == "aggregate":
        argv = ["aggregate.py", str(files["rates"][0]), str(out)] + [str(f) for f in files["ledgers"]]
    else:
        argv = [f"{capability}.py", str(files["ledger"][0]), str(out)]
    p = subprocess.run([sys.executable, str(WORKERS / argv[0])] + argv[1:], cwd=WORK,
                       capture_output=True, text=True, timeout=180)
    meta.update(spawns=1, normalize_ok=(capability == "normalize" and p.returncode == 0))
    if p.returncode != 0:
        return {"ok": False, "failure": "precondition_violated",
                "detail": _scrub(p.stderr, names)}, meta
    if capability == "aggregate":
        summary = {"regions": sorted(json.loads(out.read_text())["regions"])}
    else:
        summary = {"note": _scrub(p.stdout, {**names, str(out): sid})}
    ix[sid] = {"kind": CAPS[capability]["produces"], "file": out.name,
               "key": key if A.arm == "cap_svc" else None,
               "from": {"capability": capability, "inputs": inputs},
               "summary": summary, "session": SESSION,
               "label": files["ledger"][0].read_text().splitlines()[0] if "ledger" in files else ""}
    _save_index(ix)
    return {"ok": True, "state": sid, "kind": ix[sid]["kind"], "executed": True,
            "summary": summary}, meta


def t_inspect(state):
    ix = _index()
    if state.startswith(("ledger:", "rates:")):
        kind, f = _resolve(state)
        if kind is None:
            return {"ok": False, "failure": "no_such_resource"}, {}
        lines = f.read_text().splitlines()
        if kind == "rates":
            return {"resource": state, "kind": kind,
                    "usd_per_unit": {c: float(v) for c, v in (x.split(",") for x in lines[1:])}}, {}
        return {"resource": state, "kind": kind, "records": len(lines) - 2,
                "fields": lines[1].split(","), "first_records": lines[2:7]}, {}
    if state not in ix:
        return {"ok": False, "failure": "no_such_state"}, {}
    s = ix[state]
    res = {"state": state, "kind": s["kind"], "derived_from": s["from"], "summary": s["summary"]}
    if s["kind"] == "report":
        res["content"] = json.loads((SDIR / s["file"]).read_text())
    return res, {}


def t_progress():
    ix = _index()
    return {"states": [{"state": k, "kind": v["kind"], "derived_from": v["from"],
                        "earlier_session": v["session"] != SESSION} for k, v in ix.items()]}, {}


def t_deliver(state):
    kind, f = _resolve(state)
    if kind != "report":
        return {"accepted": False, "failure": "type_mismatch",
                "detail": "the objective's result must be a report state"}, {}
    report = json.loads(f.read_text())
    if A.arm == "cap_svc":
        probs = _verify(report, [r["id"][7:] for r in _resources() if r["kind"] == "ledger"])
        if probs:
            return {"accepted": False, "failure": "postcondition_violated", "problems": probs}, {}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report))
    return {"accepted": True, "verified": A.arm == "cap_svc"}, {"delivered": True}


# ------------------------------------------------------------------ catalog
S = lambda **p: {"type": "object", "properties": p, "required": list(p)}  # noqa: E731
STR, LST = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
TOOLS = {
    "shell": {"sh": (t_sh, "Run a bash command in the workspace; returns exit code and output.",
                     S(command=STR))},
    "cap": {
        "capabilities": (t_capabilities, "List capabilities and their contracts.", S()),
        "resources": (t_resources, "List the resources available to this objective.", S()),
        "transition": (t_transition, "Request a state transition: apply a capability to inputs "
                       "(resource ids or state ids). Returns a new state or a structured failure.",
                       S(capability=STR, inputs={"type": "object"})),
        "inspect": (t_inspect, "Describe a state: kind, provenance, summary (and content for reports).",
                    S(state=STR)),
        "deliver": (t_deliver, "Deliver a state as the result of the objective.", S(state=STR)),
    },
}
TOOLS["shell_svc"] = dict(TOOLS["shell"], **{
    "cached_sh": (t_cached_sh, "Like sh, but memoized on (command, bytes of declared inputs). On a "
                  "hit, declared outputs are restored without running. Cache persists across sessions.",
                  S(command=STR, inputs=LST, outputs=LST)),
    "checkpoint_put": (t_checkpoint_put, "Persist a named checkpoint value (survives interruption).",
                       S(key=STR, value=STR)),
    "checkpoint_get": (t_checkpoint_get, "Read a named checkpoint.", S(key=STR)),
    "checkpoint_list": (t_checkpoint_list, "List all checkpoints.", S()),
    "verify_report": (t_verify_report, "Check a report file covers every ledger region and its "
                      "grand total is consistent.", S(path=STR)),
})
TOOLS["cap_svc"] = dict(TOOLS["cap"], progress=(
    t_progress, "List states that exist for this objective, including from earlier sessions, "
    "with provenance. Transitions are cached on their real inputs; repeats may not execute.", S()))
ACTIVE = TOOLS[A.arm]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        req = json.loads(line)
    except ValueError:
        continue
    mid, method = req.get("id"), req.get("method")
    if mid is None:
        continue  # notification
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": req["params"].get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}}, "serverInfo": {"name": "env", "version": "1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in ACTIVE.items()]}})
    elif method == "tools/call":
        name, args = req["params"]["name"], req["params"].get("arguments") or {}
        t0, c0 = time.time(), child_cpu()
        if name not in ACTIVE:
            res, meta = {"error": f"unknown tool {name}"}, {}
        else:
            try:
                res, meta = ACTIVE[name][0](**args)
            except Exception as e:  # noqa: BLE001
                res, meta = {"error": f"{type(e).__name__}: {e}"}, {"exception": True}
        err = bool(res.get("error")) or res.get("ok") is False or res.get("accepted") is False \
            or (isinstance(res.get("exit_code"), int) and res["exit_code"] != 0)
        log({"tool": name, "args": json.dumps(args)[:300], "is_error": err,
             "dur": round(time.time() - t0, 3), "worker_cpu": round(child_cpu() - c0, 3), **meta})
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(res)}], "isError": False}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})

shutil.rmtree(WORK, ignore_errors=True)
