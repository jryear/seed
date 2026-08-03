#!/usr/bin/env python3
"""probe v0.2 — perturbation tripwire via local Ollama, with real exit codes.

Input:  [probe] <claim> || <perturbed variant>

Exit codes (enforced by seedd):
  0  TRANSFERS — conclusion survives perturbation
  2  FRAGILE   — conclusion diverges under perturbation
  3  ERROR     — malformed probe line or Ollama unreachable

Honest scope: flags fragile claims, not provenance. A 7B is a
tripwire, not an oracle.
"""
import json, os, sys, urllib.request

MODEL = os.environ.get("SEED_PROBE_MODEL", "reason:latest")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/generate"


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
    if not sep or not original.strip() or not perturbed.strip():
        print("[probe:error] malformed — need '[probe] claim || perturbed variant'")
        sys.exit(3)
    try:
        a = ask(f"Answer concisely: {original.strip()}")
        b = ask(f"Answer concisely: {perturbed.strip()}")
        verdict = ask(
            "One claim was tested under a changed variable.\n"
            f"Original: {original.strip()}\nAnswer 1: {a}\n\n"
            f"Perturbed: {perturbed.strip()}\nAnswer 2: {b}\n\n"
            "Does the underlying conclusion transfer coherently? "
            "Reply TRANSFERS or FRAGILE, then one line of reasoning."
        )
    except Exception as e:
        print(f"[probe:error] Ollama unreachable ({e}) — is ai-on running?")
        sys.exit(3)

    first = verdict.strip().splitlines()[0] if verdict.strip() else "(empty)"
    if "FRAGILE" in verdict.upper():
        print(f"[probe:FRAGILE] {original.strip()}\n  {first}")
        sys.exit(2)
    print(f"[probe:transfers] {original.strip()}\n  {first}")
    sys.exit(0)


if __name__ == "__main__":
    main()
