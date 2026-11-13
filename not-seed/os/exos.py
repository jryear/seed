"""exos -- say what you need; the machine is rebuilt to be able to do it.

  exos "<what you need>"   ask
  exos                     what this machine is, and why
  exos undo                go back to before the last ask
  exos check               re-run every check that earlier asks left behind
"""
import json, os, subprocess, sys

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

def ask(sentence):
    before = load()
    r = subprocess.run([MODEL], input=json.dumps({"ask": sentence, "asked": before}),
                       stdout=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit(f"the model ({MODEL}) failed; nothing changed")
    try:
        reply = json.loads(r.stdout)
    except ValueError:
        sys.exit(f"the model ({MODEL}) did not answer in the agreed form; nothing changed")
    if reply.get("say"):
        print(reply["say"])
    if not (reply.get("packages") or reply.get("tool")):
        return
    entry = {"ask": sentence, **{k: reply[k] for k in ("packages", "tool", "check") if k in reply}}
    save(before + [entry])
    print("rebuilding the machine...")
    ok, out = rebuild()
    if not ok:
        save(before)
        print(out[-1500:])
        sys.exit("the rebuild failed; the machine is unchanged")
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
