"""Fills the exos model contract with an OpenAI chat model.

Key:   file named by EXOS_KEY_FILE, else /run/exos-secrets/omarchy, else $OPENAI_API_KEY
Model: EXOS_OPENAI_MODEL (default gpt-5.4-mini)
"""
import json, os, sys, urllib.request, urllib.error

SYSTEM = """You administer a NixOS machine. The machine has nothing installed beyond a
minimal base; everything else exists only because someone asked for it. You are given
what the person just asked ("ask"), everything asked before ("asked"), and sometimes
"error": the output of a rebuild that failed on your previous answer, to correct.

Answer with one JSON object and nothing else. Keys, all optional:
  "say":      one short plain sentence to the person.
  "packages": nixpkgs attribute names to add (e.g. "ffmpeg", "python3", "python3Packages.requests").
              Only names you are confident exist in nixpkgs. As few as do the job.
  "tool":     {"name": lowercase-with-dashes, "source": full script text starting with a
              "#!/usr/bin/env <interpreter>" line}. Use when the person needs a program that
              does not exist. Put its interpreter and dependencies in "packages".
  "check":    REQUIRED whenever you give packages or a tool. One shell command that exits 0 only if the machine can now do what was asked.
              Quick, non-interactive, no network, no side effects.
  "open":     the machine has a graphical desktop (Wayland, sway) that is empty until something
              is asked for. If what was asked is something to look at or use in a window, give
              one command that opens that window: a program and plain arguments only, no shell
              syntax (no quotes, pipes, ;, &, $). For a terminal program or a tool you wrote,
              use "foot --hold <command>" (foot is installed). May be given without packages or
              a tool, to open something the machine already has. Omit for non-visual asks.
If nothing needs to change, or you cannot do it, return only "say"."""

def key():
    for p in (os.environ.get("EXOS_KEY_FILE"), "/run/exos-secrets/omarchy"):
        if p and os.path.exists(p):
            return open(p).read().strip()
    return os.environ.get("OPENAI_API_KEY", "").strip()

def main():
    k = key()
    if not k:
        sys.exit("exos: no OpenAI key found")
    body = {"model": os.environ.get("EXOS_OPENAI_MODEL", "gpt-5.4-mini"),
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": sys.stdin.read()}]}
    req = urllib.request.Request(
        os.environ.get("EXOS_OPENAI_URL", "https://api.openai.com/v1/chat/completions"),
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + k, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"exos: the model service answered {e.code}: {e.read()[:300].decode(errors='replace')}")
    except OSError as e:
        sys.exit(f"exos: could not reach the model service: {e}")
    print(reply["choices"][0]["message"]["content"])

main()
