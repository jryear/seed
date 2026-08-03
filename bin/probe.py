#!/usr/bin/env python3
"""probe v0.3 — perturbation tripwire with a durable evidence ledger.

Input:  [probe] <claim> || <perturbed variant>

Exit codes (enforced by seedd):
  0  TRANSFERS — conclusion survives perturbation
  2  FRAGILE   — conclusion diverges under perturbation
  3  ERROR     — malformed probe line or Ollama unreachable

Every run — pass, fail, or error — appends a structured record to
evidence.jsonl: model, claim, perturbation, both answers, verdict,
timestamp. Nothing about a probe is stdout-only anymore.

Honest scope: flags fragile claims, not provenance. A 7B is a
tripwire, not an oracle.
"""
import json, os, sys, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence.jsonl"
MODEL = os.environ.get("SEED_PROBE_MODEL", "reason:latest")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/generate"


def record(rec):
    rec = {"ts": datetime.now().isoformat(timespec="seconds"),
           "model": MODEL, **rec}
    with open(EVIDENCE, "a") as f:
        f.write(json.dumps(rec) + "\n")


def ask(prompt):
    req = urllib.request.Request(
        OLLAMA,
        json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode(),
        {"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["response"]


def main():
    line = " ".join(sys.argv[1:]).removeprefix("[probe]").strip()
    original, sep, perturbed = line.partition("||")
    original, perturbed = original.strip(), perturbed.strip()
    if not sep or not original or not perturbed:
        record({"outcome": "malformed", "line": line})
        print("[probe:error] malformed — need '[probe] claim || perturbed variant'")
        sys.exit(3)
    try:
        a = ask(f"Answer concisely: {original}")
        b = ask(f"Answer concisely: {perturbed}")
        verdict = ask(
            "One claim was tested under a changed variable.\n"
            f"Original: {original}\nAnswer 1: {a}\n\n"
            f"Perturbed: {perturbed}\nAnswer 2: {b}\n\n"
            "Does the underlying conclusion transfer coherently? "
            "Reply TRANSFERS or FRAGILE, then one line of reasoning."
        )
    except Exception as e:
        record({"outcome": "error", "claim": original, "perturbed": perturbed,
                "error": str(e)})
        print(f"[probe:error] Ollama unreachable ({e}) — is ai-on running?")
        sys.exit(3)

    outcome = "fragile" if "FRAGILE" in verdict.upper() else "transfers"
    record({"outcome": outcome, "claim": original, "perturbed": perturbed,
            "answer_original": a, "answer_perturbed": b, "verdict": verdict.strip()})

    first = verdict.strip().splitlines()[0] if verdict.strip() else "(empty)"
    if outcome == "fragile":
        print(f"[probe:FRAGILE] {original}\n  {first}")
        sys.exit(2)
    print(f"[probe:transfers] {original}\n  {first}")
    sys.exit(0)


if __name__ == "__main__":
    main()
