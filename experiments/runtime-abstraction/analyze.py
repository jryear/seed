#!/usr/bin/env python3
"""analyze.py RESULTS_DIR [RESULTS_DIR ...] -> markdown summary on stdout.

Every number is derived from files the supervisor wrote: results.jsonl
(grades, /proc and strace measurements, CLI accounting) and the runtime's
call logs. Nothing here is inferred from agent self-reports.
"""
import json
import random
import statistics as st
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ["shell", "shell_svc", "cap", "cap_svc"]


def interface_chars(arm):
    """Size of what the agent must read to know its interface: tool catalog
    (+ README for shell arms). A proxy for required implementation knowledge."""
    req = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
    p = subprocess.run([sys.executable, str(HERE / "runtime.py"), "--arm", arm, "--workspace", "/nonexistent",
                        "--store", "/tmp/rt-analyze-store", "--log", "/dev/null", "--deliver-to", "/dev/null"],
                       input=req, capture_output=True, text=True)
    n = len(json.dumps(json.loads(p.stdout)["result"]["tools"]))
    if arm.startswith("shell"):
        sys.path.insert(0, str(HERE))
        import supervisor
        n += len(supervisor.README)
    return n


def boot_diff(a, b, n=4000, seed=0):
    """95% bootstrap CI for mean(b) - mean(a)."""
    if not a or not b:
        return None
    r = random.Random(seed)
    ds = sorted(st.mean(r.choices(b, k=len(b))) - st.mean(r.choices(a, k=len(a))) for _ in range(n))
    return st.mean(b) - st.mean(a), ds[int(0.025 * n)], ds[int(0.975 * n)]


def load(dirs):
    recs = []
    for d in dirs:
        for line in (Path(d) / "results.jsonl").read_text().splitlines():
            recs.append(json.loads(line))
    return recs


def cell(recs, arm, cond):
    return [r for r in recs if r["arm"] == arm and r["condition"] == cond]


def metrics(r):
    s = r["sessions"]
    tok_exact = all(x["tokens"]["exact"] for x in s)
    tok = sum(x["tokens"]["in"] + x["tokens"]["cache_read"] + x["tokens"]["cache_write"] + x["tokens"]["out"]
              for x in s)
    return {
        "pass": 1.0 if r["passed"] else 0.0,
        "wall": r["wall"],
        "tool_cpu": r["worker_cpu"],
        "tree_cpu": sum(x["tree_cpu"] for x in s),
        "execve": sum(x["execve_total"] for x in s),
        "norm_procs": r["normalize_runs"],
        "calls": r["tool_calls"],
        "errors": r["tool_errors"],
        "tokens": tok, "tok_exact": tok_exact,
        "cost_final": s[-1]["cost_usd"],
        "out_tokens_final": s[-1]["tokens"]["out"],
        "used_workers": 1.0 if r["normalize_runs"] > 0 else 0.0,
        "cache_hits": r["cache_hits"],
        "s2_norm": s[1]["execve_workers"]["normalize"] if len(s) > 1 else None,
        "s2_tool_cpu": None,
        "killed": len(s) > 1,
        "used_services": 1.0 if set(r["tools_used"]) & {"cached_sh", "checkpoint_put", "checkpoint_get",
                                                          "checkpoint_list", "verify_report", "progress"} else 0.0,
    }


def fmt(xs, f="{:.1f}"):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "—"
    return f"{f.format(st.median(xs))} [{f.format(min(xs))}–{f.format(max(xs))}]"


def main(dirs):
    recs = load(dirs)
    models = sorted({(r["model"], r.get("task", 1)) for r in recs})
    out = [f"Trials: {len(recs)}  ·  cells show median [min–max]\n"]
    for model_id, tsk in models:
        model = f"{model_id} · task {tsk}"
        mr = [r for r in recs if r["model"] == model_id and r.get("task", 1) == tsk]
        for cond in ["clean", "interrupted"]:
            out.append(f"\n### {model} — {cond}\n")
            out.append("| arm | n | pass | wall s | tool-subtree CPU s | normalize procs (strace) | "
                       "all execve | tool calls | tool errors | final-session cost $ | used provided workers |")
            out.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for arm in ARMS:
                c = [metrics(r) for r in cell(mr, arm, cond)]
                if not c:
                    continue
                out.append(
                    f"| {arm} | {len(c)} | {sum(m['pass'] for m in c):.0f}/{len(c)} | "
                    f"{fmt([m['wall'] for m in c])} | {fmt([m['tool_cpu'] for m in c])} | "
                    f"{fmt([m['norm_procs'] for m in c], '{:.0f}')} | {fmt([m['execve'] for m in c], '{:.0f}')} | "
                    f"{fmt([m['calls'] for m in c], '{:.0f}')} | {fmt([m['errors'] for m in c], '{:.0f}')} | "
                    f"{fmt([m['cost_final'] for m in c], '{:.4f}')} | "
                    f"{sum(m['used_workers'] for m in c):.0f}/{len(c)} |")
        # recovery: work redone after the kill
        out.append(f"\n### {model} — recovery (interrupted trials, session 2 only)\n")
        out.append("| arm | killed | session-2 normalize procs | trials where session 2 re-ran ≥8 normalizes | "
                   "used a service tool |")
        out.append("|---|---|---|---|---|")
        for arm in ARMS:
            c = [metrics(r) for r in cell(mr, arm, "interrupted")]
            k = [m for m in c if m["killed"]]
            out.append(f"| {arm} | {len(k)}/{len(c)} | {fmt([m['s2_norm'] for m in k], '{:.0f}')} | "
                       f"{sum(1 for m in k if (m['s2_norm'] or 0) >= 8)}/{len(k)} | "
                       f"{sum(m['used_services'] for m in c):.0f}/{len(c)} |")
        if tsk == 2:
            out.append(f"\n### {model} — off-catalog work (escape hatch / own code)\n")
            out.append("| arm | condition | pass | escape-hatch calls | escape-hatch errors | "
                       "hatch programs touching OS | delivered via derive | shell own-code calls |")
            out.append("|---|---|---|---|---|---|---|---|")
            for arm in ARMS:
                for cond in ["clean", "interrupted"]:
                    c = cell(mr, arm, cond)
                    if not c:
                        continue
                    f = lambda k: fmt([r.get(k, 0) for r in c], "{:.0f}")  # noqa: E731
                    out.append(f"| {arm} | {cond} | {sum(r['passed'] for r in c)}/{len(c)} | "
                               f"{f('escape_hatch_calls')} | {f('escape_hatch_errors')} | "
                               f"{f('escape_hatch_os_reach')} | "
                               f"{sum(1 for r in c if r.get('delivered_from') == 'derive')}/{len(c)} | "
                               f"{f('shell_own_code_calls')} |")
        # 2x2 contrasts
        out.append(f"\n### {model} — contrasts (mean difference, 95% bootstrap CI)\n")
        out.append("| contrast | condition | wall s | tool CPU s | tool calls | pass rate |")
        out.append("|---|---|---|---|---|---|")
        contrasts = [("hide processes | services on", "shell_svc", "cap_svc"),
                     ("hide processes | services off", "shell", "cap"),
                     ("add services | processes hidden", "cap", "cap_svc"),
                     ("add services | processes visible", "shell", "shell_svc")]
        for name, a, b in contrasts:
            for cond in ["clean", "interrupted"]:
                ca = [metrics(r) for r in cell(mr, a, cond)]
                cb = [metrics(r) for r in cell(mr, b, cond)]
                row = [name, cond]
                for k in ["wall", "tool_cpu", "calls", "pass"]:
                    d = boot_diff([m[k] for m in ca], [m[k] for m in cb])
                    row.append("—" if d is None else f"{d[0]:+.1f} [{d[1]:+.1f}, {d[2]:+.1f}]")
                out.append("| " + " | ".join(row) + " |")
    out.append("\n### Interface size (chars the agent must read to learn its interface)\n")
    out.append("| arm | chars |\n|---|---|")
    for arm in ARMS:
        out.append(f"| {arm} | {interface_chars(arm)} |")
    fails = [r for r in recs if not r["passed"]]
    out.append(f"\n### Failures ({len(fails)})\n")
    for r in fails:
        out.append(f"- {r['model']} {r['arm']} {r['condition']} rep{r['rep']}: {'; '.join(r['fail_reasons'][:3])}")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:])
