"""exos -- say what you need; the machine is rebuilt to be able to do it.

  exos "<what you need>"   ask
  exos                     what this machine is, and why
  exos undo                go back to before the last ask
  exos check               re-run every check that earlier asks left behind
"""
import json, os, re, subprocess, sys

ROOT = os.environ.get("EXOS_ROOT", "")            # the tests point this at a scratch tree
ASKED = ROOT + "/var/lib/exos/asked.json"         # what the next build is made from
BACK = ROOT + "/var/lib/exos/back.json"           # systems `undo` returns to, oldest first
MODEL_FILE = ROOT + "/var/lib/exos/model"
RUNNING = ROOT + "/run/current-system"
BUILT_FROM = ROOT + "/etc/exos-asked.json"        # the list the running system was built from
PROFILE = ROOT + "/nix/var/nix/profiles/system"

def text(path):
    with open(path) as f:
        return f.read()

MODEL = os.environ.get("EXOS_MODEL") or (
    text(MODEL_FILE).strip() if os.path.exists(MODEL_FILE) else "exos-model-standin")
CHECK_SECONDS = int(os.environ.get("EXOS_CHECK_SECONDS", 60))

def read(path, default):
    return json.loads(text(path)) if os.path.exists(path) else default

def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".new", "w") as f:
        json.dump(value, f, indent=1)
    os.replace(path + ".new", path)

def load():
    return read(ASKED, [])

def running():
    return os.path.realpath(RUNNING)

def reconcile():
    """The running machine is the truth. If the list disagrees with it (an ask
    was cut short, or the machine restarted into another system), follow the machine."""
    built = read(BUILT_FROM, None)
    if built is not None and built != load():
        write(ASKED, built)
        write(BACK, [])
        print("note: the list did not match the running machine; it now does, and undo history was cleared")

def build():
    r = subprocess.run(["nixos-rebuild", "switch"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return r.returncode == 0, r.stdout

def go_to(system):
    """Make exactly this system the running one. True only if it now is."""
    if running() != system:
        subprocess.run([system + "/bin/switch-to-configuration", "switch"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.realpath(PROFILE) != system:
        subprocess.run(["nix-env", "-p", PROFILE, "--set", system],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return running() == system

def passes(check):
    try:
        return subprocess.run(["bash", "-lc", check], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=CHECK_SECONDS).returncode == 0
    except subprocess.TimeoutExpired:
        return False

def failing(asked):
    return [a for a in asked if a.get("check") and not passes(a["check"])]

def report(bad):
    for a in bad:
        print(f"check failed: `{a['check']}`  (from \"{a['ask']}\")")

def show(asked):
    gen = os.path.basename(os.readlink(PROFILE)) if os.path.islink(PROFILE) else "as booted"
    print(f"this machine ({gen}) is the base plus {len(asked)} thing(s) asked of it:")
    for i, a in enumerate(asked, 1):
        what = ", ".join(a.get("packages", [])) + (f" + tool `{a['tool']['name']}`" if "tool" in a else "")
        print(f"  {i}. \"{a['ask']}\" -> {what}   [check: {a.get('check', 'none')}]")

def consult(sentence, before, error=None):
    """Ask the model; return a validated reply or exit with nothing changed."""
    q = {"ask": sentence, "asked": before, **({"error": error} if error else {})}
    r = subprocess.run([MODEL], input=json.dumps(q), stdout=subprocess.PIPE, text=True)
    if r.returncode != 0:
        print(f"the model ({MODEL}) failed"); sys.exit(1)
    try:
        reply = json.loads(r.stdout)
        assert isinstance(reply, dict)
        reply = {k: v for k, v in reply.items() if v is not None}
        pk, tool = reply.get("packages", []), reply.get("tool")
        assert isinstance(pk, list)
        assert all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.+-]+", x) for x in pk)
        if tool is not None:
            assert isinstance(tool, dict) and isinstance(tool["source"], str)
            assert isinstance(tool["name"], str) and re.fullmatch(r"[a-z][a-z0-9-]*", tool["name"])
            # a tool may not take the name of anything the machine already has
            assert not os.path.lexists(f"{RUNNING}/sw/bin/{tool['name']}"), "name taken"
        check = reply.get("check", "")
        assert isinstance(check, str)
        if pk or tool:              # a change must come with a check that could fail
            assert check.strip() not in ("", ":", "true"), "no real check"
        # "open" is one program with plain arguments, no shell syntax
        assert re.fullmatch(r"[A-Za-z0-9_./][A-Za-z0-9 _./:=+@%-]*", reply.get("open", "x"))
    except (ValueError, AssertionError, KeyError, TypeError):
        print(f"the model ({MODEL}) did not answer in the agreed form"); sys.exit(1)
    return reply

def open_window(cmd):
    if os.environ.get("SWAYSOCK"):      # on the desktop: the session starts it, as the person
        subprocess.run(["swaymsg", "-q", "exec", cmd])
    else:
        print(f"no desktop here; to see it: {cmd}")

def ask(sentence):
    before, was = load(), running()
    broken = failing(before)        # already failing before this ask: not this ask's fault
    if broken:
        print("note: failing before this ask:"); report(broken)
    kept = False
    try:
        error = None
        for attempt in (1, 2):      # one chance to correct a failed build
            reply = consult(sentence, before, error)
            if reply.get("say"):
                print(reply["say"])
            if not (reply.get("packages") or reply.get("tool")):
                kept = True         # nothing to change
                if reply.get("open"):
                    open_window(reply["open"])
                return
            entry = {"ask": sentence,
                     **{k: reply[k] for k in ("packages", "tool", "check", "open") if k in reply}}
            write(ASKED, before + [entry])
            print("rebuilding the machine...")
            ok, out = build()
            if ok:
                break
            error = out[-3000:]
            if attempt == 2:
                print(out[-1500:])
                print("the build failed twice")
                return
            print("that did not build; asking the model to correct it...")
        bad = [a for a in failing(before + [entry]) if a not in broken]
        if bad:
            report(bad)
            return
        write(BACK, read(BACK, []) + [was])
        kept = True
        print("done; every check passes" if not broken else "done; this ask's check passes")
        if entry.get("open"):
            open_window(entry["open"])
    finally:
        if not kept:                # failed, rejected or interrupted: put everything back
            write(ASKED, before)
            if go_to(was):
                sys.exit("the machine is as it was before this ask")
            sys.exit(f"COULD NOT RETURN to the previous system.\n  running now: {running()}\n"
                     f"  wanted:      {was}\nthe list was restored but does not describe this machine")

def undo():
    back = read(BACK, [])
    if not back:
        sys.exit("nothing to undo")
    if not go_to(back[-1]):
        sys.exit(f"could not go back; the machine is running {running()}")
    write(BACK, back[:-1])
    write(ASKED, read(BUILT_FROM, []))
    show(load())
    report(failing(load()))

a = sys.argv[1:]
if a and a[0] in ("-h", "--help", "help"):
    print(__doc__); sys.exit()
reconcile()
if not a: show(load())
elif a == ["undo"]: undo()
elif a == ["check"]:
    bad = failing(load())
    report(bad)
    sys.exit(1 if bad else print("every check passes"))
else: ask(" ".join(a))
