"""exos -- say what you need; the machine is rebuilt to be able to do it.

  exos "<what you need>"   ask
  exos                     what this machine is, and why
  exos undo                go back to before the last ask
  exos check               re-run every check that earlier asks left behind
"""
import json, os, re, subprocess, sys

ASKED = "/var/lib/exos/asked.json"
MODEL = os.environ.get("EXOS_MODEL") or (
    open("/var/lib/exos/model").read().strip() if os.path.exists("/var/lib/exos/model")
    else "exos-model-standin")

def load():
    return json.load(open(ASKED)) if os.path.exists(ASKED) else []

def save(asked):
    os.makedirs(os.path.dirname(ASKED), exist_ok=True)
    with open(ASKED + ".new", "w") as f:
        json.dump(asked, f, indent=1)
    os.replace(ASKED + ".new", ASKED)

PROFILE = "/nix/var/nix/profiles/system"

def generation():
    return os.readlink(PROFILE) if os.path.islink(PROFILE) else None

def rebuild(*extra):
    was = generation()
    r = subprocess.run(["nixos-rebuild", "switch", *extra],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 and was and generation() != was:
        # the new system was registered but never took effect: unregister it
        subprocess.run(["nix-env", "-p", PROFILE, "--rollback"], capture_output=True)
    return r.returncode == 0, r.stdout

def failing(asked):
    bad = []
    for a in asked:
        c = a.get("check")
        if c and subprocess.run(["bash", "-lc", c], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL).returncode != 0:
            bad.append(a)
    return bad

def show(asked):
    gen = generation() or "as booted"
    print(f"this machine ({gen}) is the base plus {len(asked)} thing(s) asked of it:")
    for i, a in enumerate(asked, 1):
        what = ", ".join(a.get("packages", [])) + (f" + tool `{a['tool']['name']}`" if "tool" in a else "")
        print(f"  {i}. \"{a['ask']}\" -> {what}   [check: {a.get('check', 'none')}]")

def consult(sentence, before, error=None):
    """Ask the model; return a validated reply or exit with nothing changed."""
    q = {"ask": sentence, "asked": before, **({"error": error} if error else {})}
    r = subprocess.run([MODEL], input=json.dumps(q), stdout=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit(f"the model ({MODEL}) failed; nothing changed")
    try:
        reply = json.loads(r.stdout)
        pk, tool = reply.get("packages", []), reply.get("tool")
        assert isinstance(reply, dict) and isinstance(pk, list)
        assert all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.+-]+", x) for x in pk)
        assert tool is None or (re.fullmatch(r"[a-z][a-z0-9-]*", tool["name"])
                                and isinstance(tool["source"], str))
        assert isinstance(reply.get("check", ""), str)
        assert reply.get("check") or not (pk or tool), "a change must come with a check"
    except (ValueError, AssertionError, KeyError, TypeError):
        sys.exit(f"the model ({MODEL}) did not answer in the agreed form; nothing changed")
    return reply

def ask(sentence):
    before = load()
    error = None
    for attempt in (1, 2):          # one chance to correct a failed rebuild
        reply = consult(sentence, before, error)
        if reply.get("say"):
            print(reply["say"])
        if not (reply.get("packages") or reply.get("tool")):
            return
        entry = {"ask": sentence, **{k: reply[k] for k in ("packages", "tool", "check") if k in reply}}
        save(before + [entry])
        print("rebuilding the machine...")
        ok, out = rebuild()
        if ok:
            break
        save(before)
        error = out[-3000:]
        if attempt == 2:
            print(out[-1500:])
            sys.exit("the rebuild failed twice; the machine is unchanged")
        print("that did not build; asking the model to correct it...")
    bad = failing(before + [entry])
    if bad:
        rebuild("--rollback")
        save(before)
        for a in bad:
            print(f"check failed: `{a['check']}`  (from \"{a['ask']}\")")
        sys.exit("went back to the machine as it was")
    print("done; every check passes")

def undo():
    asked = load()
    if not asked:
        sys.exit("nothing to undo")
    ok, out = rebuild("--rollback")
    if not ok:
        print(out[-1500:]); sys.exit("could not go back")
    save(json.load(open("/etc/exos-asked.json")))
    show(load())

a = sys.argv[1:]
if not a: show(load())
elif a == ["undo"]: undo()
elif a == ["check"]:
    bad = failing(load())
    for x in bad: print(f"check failed: `{x['check']}`  (from \"{x['ask']}\")")
    sys.exit(1 if bad else print("every check passes"))
elif a[0] in ("-h", "--help", "help"): print(__doc__)
else: ask(" ".join(a))
