"""Exercises the agent's bookkeeping against a fake Nix (no VM, no model).
Each "ask" sentence is the JSON reply the fake model should give.
Run: python3 test_agent.py
"""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE_REBUILD = r'''#!/usr/bin/env python3
import hashlib, json, os, subprocess, sys, time
from pathlib import Path
R = os.environ["EXOS_ROOT"]
asked = json.loads(Path(R + "/var/lib/exos/asked.json").read_text())
if os.path.exists(R + "/slow"): time.sleep(30)
if any("nope" in a.get("packages", []) for a in asked): sys.exit("error: attribute 'nope' missing")
d = R + "/systems/" + hashlib.sha1(json.dumps(asked).encode()).hexdigest()[:12]
os.makedirs(d + "/bin", exist_ok=True); os.makedirs(d + "/sw/bin", exist_ok=True)
Path(d + "/asked.json").write_text(json.dumps(asked))
for n in ["bash", "nixos-rebuild"] + [p for a in asked for p in a.get("packages", [])] \
        + [a["tool"]["name"] for a in asked if "tool" in a]:
    Path(f"{d}/sw/bin/{n}").touch()
Path(d + "/bin/switch-to-configuration").write_text(f"""#!/bin/sh
ln -sfn {d} {R}/run/current-system; cp {d}/asked.json {R}/etc/exos-asked.json
""")
os.chmod(d + "/bin/switch-to-configuration", 0o755)
subprocess.run(["nix-env", "-p", R + "/nix/var/nix/profiles/system", "--set", d])
subprocess.run([d + "/bin/switch-to-configuration", "switch"])
'''
FAKE_NIXENV = '#!/bin/sh\n[ "$3" = --set ] && ln -sfn "$4" "$2"\n'
FAKE_MODEL = r'''#!/usr/bin/env python3
import json, sys
q = json.load(sys.stdin); r = json.loads(q["ask"])
if isinstance(r, dict) and "then" in r: r = r["then"] if "error" in q else r["first"]
print(json.dumps(r))
'''

class World:
    def __init__(self):
        self.r = tempfile.mkdtemp(prefix="exos-test-")
        for d in ("var/lib/exos", "run", "etc", "nix/var/nix/profiles", "systems", "fakebin"):
            os.makedirs(f"{self.r}/{d}")
        for name, src in (("nixos-rebuild", FAKE_REBUILD), ("nix-env", FAKE_NIXENV), ("model", FAKE_MODEL)):
            Path(f"{self.r}/fakebin/{name}").write_text(src); os.chmod(f"{self.r}/fakebin/{name}", 0o755)
        self.env = {**os.environ, "EXOS_ROOT": self.r, "EXOS_MODEL": f"{self.r}/fakebin/model",
                    "EXOS_CHECK_SECONDS": "2", "PATH": f"{self.r}/fakebin:" + os.environ["PATH"]}
        Path(f"{self.r}/var/lib/exos/asked.json").write_text("[]")
        subprocess.run(["nixos-rebuild"], env=self.env)          # the base system, as booted
        os.remove(f"{self.r}/nix/var/nix/profiles/system")       # a fresh boot has no profile yet
        self.base = os.path.realpath(f"{self.r}/run/current-system")
    def exos(self, *args):
        p = subprocess.run([sys.executable, f"{HERE}/exos.py", *args], env=self.env,
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    def ask(self, **reply): return self.exos(json.dumps(reply))
    def pkg(self, name): return self.ask(packages=[name], check=f"test -e {self.r}/run/current-system/sw/bin/{name}")
    def brk(self): return self.ask(packages=["x"], check="false")
    def names(self):
        """Packages in the list; asserts the list is what the running machine was built from."""
        asked = json.loads(Path(f"{self.r}/var/lib/exos/asked.json").read_text())
        built = json.loads(Path(f"{self.r}/run/current-system/asked.json").read_text())
        assert asked == built, f"list {asked} but machine built from {built}"
        return [p for a in asked for p in a.get("packages", [])] + [a["tool"]["name"] for a in asked if "tool" in a]

def t_undo_then_rejected():
    w = World(); w.pkg("a"); w.pkg("b"); w.exos("undo"); rc, out = w.brk()
    assert rc and "as it was" in out, out; assert w.names() == ["a"]
def t_rejected_then_undo():
    w = World(); w.pkg("a"); w.brk(); w.pkg("b"); w.exos("undo")
    assert w.names() == ["a"]; assert w.exos("check")[0] == 0
def t_undo_does_not_resurrect():
    w = World(); w.pkg("a"); w.pkg("b"); w.exos("undo"); w.pkg("c"); w.exos("undo")
    assert w.names() == ["a"]
def t_first_ask_rejected():
    w = World(); rc, out = w.brk()
    assert rc and "as it was" in out, out; assert w.names() == []
    assert os.path.realpath(f"{w.r}/run/current-system") == w.base
def t_undo_all_the_way():
    w = World(); w.pkg("a"); w.exos("undo"); assert w.names() == []
    rc, out = w.exos("undo"); assert rc and "nothing to undo" in out
def t_build_fails_twice():
    w = World(); w.pkg("a"); rc, out = w.pkg("nope")
    assert rc and "failed twice" in out, out; assert w.names() == ["a"]
def t_retry_corrects():
    w = World(); ok = {"packages": ["good"], "check": "true #"}
    rc, out = w.ask(first={"packages": ["nope"], "check": "true #"}, then=ok)
    assert rc == 0, out; assert w.names() == ["good"]
def t_interrupted():
    w = World(); w.pkg("a"); Path(f"{w.r}/slow").touch()
    p = subprocess.Popen([sys.executable, f"{HERE}/exos.py", json.dumps({"packages": ["b"], "check": "true #"})],
                         env=w.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5); p.send_signal(signal.SIGINT); p.wait(); os.remove(f"{w.r}/slow")
    assert w.names() == ["a"]
def t_killed_then_reconciled():
    w = World(); w.pkg("a"); Path(f"{w.r}/slow").touch()
    p = subprocess.Popen([sys.executable, f"{HERE}/exos.py", json.dumps({"packages": ["b"], "check": "true #"})],
                         env=w.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5); p.kill(); p.wait(); os.remove(f"{w.r}/slow")
    subprocess.run(["pkill", "-f", f"{w.r}/fakebin/nixos-rebuild"])
    rc, out = w.exos(); assert "did not match" in out, out; assert w.names() == ["a"]
def t_bad_replies():
    w = World()
    for reply in ([], "x", {"packages": "ffmpeg"}, {"packages": ["a;b"], "check": "x"},
                  {"packages": ["a"]}, {"packages": ["a"], "check": " "}, {"packages": ["a"], "check": ":"},
                  {"tool": {"name": "nixos-rebuild", "source": "#!/bin/sh"}, "check": "x"},
                  {"tool": {"name": "Bad Name", "source": ""}, "check": "x"},
                  {"tool": {"name": "t"}, "check": "x"}, {"packages": ["a"], "check": "x", "open": "a; rm -rf /"}):
        rc, out = w.exos(json.dumps(reply))
        assert rc and "agreed form" in out and "Traceback" not in out, (reply, out)
        assert w.names() == []
def t_null_tool_is_no_tool():
    w = World(); rc, out = w.ask(packages=["a"], tool=None, check="true #")
    assert rc == 0, out; assert w.names() == ["a"]
def t_tool_name_taken_by_earlier_tool():
    w = World(); t = {"name": "big", "source": "#!/bin/sh"}
    assert w.ask(tool=t, check="true #")[0] == 0
    rc, out = w.ask(tool=t, check="true #"); assert rc and "agreed form" in out; assert w.names() == ["big"]
def t_hanging_check():
    w = World(); t0 = time.time(); rc, out = w.ask(packages=["a"], check="sleep 60")
    assert rc and time.time() - t0 < 20, out; assert w.names() == []
def t_check_reading_stdin_does_not_hang():
    w = World(); rc, out = w.ask(packages=["a"], check="cat"); assert rc == 0 and time.time(), out
def t_old_failure_not_blamed_on_new_ask():
    w = World(); flag = f"{w.r}/flag"; Path(flag).touch()
    w.ask(packages=["a"], check=f"test -e {flag}"); os.remove(flag)
    rc, out = w.pkg("b"); assert rc == 0 and "failing before this ask" in out, out
    assert w.names() == ["a", "b"]

if __name__ == "__main__":
    fails = 0
    for name, f in sorted(globals().items()):
        if name.startswith("t_"):
            try: f(); print("pass", name)
            except AssertionError as e: fails += 1; print("FAIL", name, "--", str(e)[:300])
    sys.exit(1 if fails else 0)
