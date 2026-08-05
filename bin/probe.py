#!/usr/bin/env python3
"""probe v0.3.1 — perturbation tripwire with a durable evidence ledger.

Input:  [probe] <claim> || <perturbed variant>

Exit codes (enforced by seedd):
  0  TRANSFERS — conclusion survives perturbation
  2  FRAGILE   — conclusion diverges under perturbation
  3  ERROR     — malformed probe line or Ollama unreachable

Every run — transfers, fragile, malformed, or error — appends a structured record to
evidence.jsonl: model, claim, perturbation, both answers, verdict,
timestamp. Nothing about a probe is stdout-only anymore.

Honest scope: flags fragile claims, not provenance. A 7B is a
tripwire, not an oracle.
"""
import json, os, re, sys, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence.jsonl"
MODEL = os.environ.get("SEED_PROBE_MODEL", "reason:latest")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/generate"


def record(outcome, claim=None, perturbed=None, answer_original=None,
           answer_perturbed=None, verdict=None, **extra):
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "outcome": outcome,
        "claim": claim,
        "perturbed": perturbed,
        "answer_original": answer_original,
        "answer_perturbed": answer_perturbed,
        "verdict": verdict,
        **extra,
    }
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
        record("malformed", claim=original or None,
               perturbed=perturbed or None, line=line,
               error="missing claim or perturbation separator")
        print("[probe:error] malformed — need '[probe] claim || perturbed variant'")
        sys.exit(3)
    a = b = verdict = None
    try:
        a = ask(f"Answer concisely: {original}")
        if not isinstance(a, str) or not a.strip():
            record("malformed", claim=original, perturbed=perturbed,
                   answer_original=a, answer_perturbed=b, verdict=verdict,
                   error="original answer must be a non-empty string")
            print("[probe:error] malformed original answer")
            sys.exit(3)
        b = ask(f"Answer concisely: {perturbed}")
        if not isinstance(b, str) or not b.strip():
            record("malformed", claim=original, perturbed=perturbed,
                   answer_original=a, answer_perturbed=b, verdict=verdict,
                   error="perturbed answer must be a non-empty string")
            print("[probe:error] malformed perturbed answer")
            sys.exit(3)
        verdict = ask(
            "One claim was tested under a changed variable.\n"
            f"Original: {original}\nAnswer 1: {a}\n\n"
            f"Perturbed: {perturbed}\nAnswer 2: {b}\n\n"
            "Does the underlying conclusion transfer coherently? "
            "Reply TRANSFERS or FRAGILE, then one line of reasoning."
        )
    except Exception as e:
        record("error", claim=original, perturbed=perturbed,
               answer_original=a, answer_perturbed=b, verdict=verdict,
               error=str(e))
        print(f"[probe:error] Ollama unreachable ({e}) — is ai-on running?")
        sys.exit(3)

    if not isinstance(verdict, str):
        record("malformed", claim=original, perturbed=perturbed,
               answer_original=a, answer_perturbed=b, verdict=verdict,
               error="verdict must be a string")
        print(f"[probe:error] malformed verdict type — {type(verdict).__name__}")
        sys.exit(3)

    first = verdict.strip().splitlines()[0] if verdict.strip() else "(empty)"
    match = re.fullmatch(
        r"(TRANSFERS|FRAGILE)(?:\s*(?:—|-|:)\s*.*)?",
        first.strip(),
        flags=re.IGNORECASE,
    )
    verdict_tokens = {
        token.upper()
        for token in re.findall(r"\b(?:TRANSFERS|FRAGILE)\b", verdict,
                                flags=re.IGNORECASE)
    }
    if match is None or len(verdict_tokens) != 1:
        record("malformed", claim=original, perturbed=perturbed,
               answer_original=a, answer_perturbed=b, verdict=verdict.strip(),
               error="verdict must be an unambiguous TRANSFERS or FRAGILE result")
        print(f"[probe:error] malformed verdict — {first}")
        sys.exit(3)

    token = match.group(1).upper()
    outcome = "fragile" if token == "FRAGILE" else "transfers"
    record(outcome, claim=original, perturbed=perturbed,
           answer_original=a, answer_perturbed=b, verdict=verdict.strip())

    if outcome == "fragile":
        print(f"[probe:FRAGILE] {original}\n  {first}")
        sys.exit(2)
    print(f"[probe:transfers] {original}\n  {first}")
    sys.exit(0)


if __name__ == "__main__":
    main()
