#!/usr/bin/env python3
"""seedd v0.2 — hardened commit loop.

Guarantees (v0 hazards closed):
  1. A delta enters the seed only if every [probe] line TRANSFERS.
     FRAGILE, unreachable-Ollama, or malformed probes HOLD the delta
     in inbox/ as <name>.held.md with the reason appended.
  2. Git results are reported truthfully. A failed commit prints
     "MERGED BUT NOT COMMITTED", never "committed".
  3. The 300-word carry bound BLOCKS: an over-bound merge holds the
     delta and leaves seed.md untouched.
  4. Atomicity/concurrency: seed.md is replaced via temp-file +
     os.replace (atomic on POSIX); a pidfile lock prevents two seedd
     instances; merge happens BEFORE the delta leaves inbox/ and the
     field-merge is idempotent, so replaying after a crash is safe.

Usage:
  python3 bin/seedd.py          # watch loop
  python3 bin/seedd.py --once   # single pass (tests, cron)

Held deltas: fix the file (or delete the probe line), rename back
to .md, and seedd will retry it.
"""
import os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED, HISTORY, INBOX = ROOT / "seed.md", ROOT / "history", ROOT / "inbox"
LOCK = ROOT / ".seedd.lock"
WORD_BOUND = 300

FIELD = re.compile(r"^## (.+?)\s*$", re.M)


def parse(text):
    parts = FIELD.split(text)
    return parts[0], dict(zip(parts[1::2], (p.strip() for p in parts[2::2])))


def merge(seed_text, delta_text):
    head, fields = parse(seed_text)
    _, updates = parse(delta_text)
    fields.update(updates)
    body = "\n\n".join(f"## {k}\n{v}" for k, v in fields.items())
    return f"{head.strip()}\n\n{body}\n"


def hold(delta_path, reason):
    held = delta_path.parent / (delta_path.stem + ".held.md")
    delta_path.rename(held)
    with open(held, "a") as f:
        f.write(f"\n\n<!-- HELD: {reason} -->\n")
    print(f"HELD {delta_path.name} — {reason}")
    print("  fix the file, rename back to .md to retry")


def run_probes(delta_text):
    """Returns None if all probes transfer, else a hold reason."""
    for line in delta_text.splitlines():
        if line.startswith("[probe]"):
            r = subprocess.run(
                [sys.executable, str(ROOT / "bin" / "probe.py"), line],
                capture_output=True, text=True,
            )
            if r.stdout:
                sys.stdout.write(r.stdout)
            if r.returncode == 2:
                return f"probe FRAGILE: {line[:80]}"
            if r.returncode != 0:
                detail = (r.stderr or r.stdout or "").strip()[:120]
                return f"probe did not complete (rc={r.returncode}): {detail}"
    return None


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True
    )


def commit(delta_path):
    delta = delta_path.read_text()

    reason = run_probes(delta)
    if reason:
        hold(delta_path, reason)
        return

    merged = merge(SEED.read_text(), delta)
    words = len(merged.split())
    if words > WORD_BOUND:
        hold(delta_path,
             f"carry bound: merged seed would be {words} words (bound {WORD_BOUND})")
        return

    # Atomic seed replace BEFORE the delta leaves inbox/.
    # Crash between these steps => delta re-runs; merge is idempotent.
    tmp = SEED.parent / (SEED.name + ".tmp")
    tmp.write_text(merged)
    os.replace(tmp, SEED)

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    delta_path.rename(HISTORY / f"{stamp}-{delta_path.name}")

    add = git("add", "-A")
    com = git("commit", "-m", f"delta {stamp}")
    if add.returncode == 0 and com.returncode == 0:
        print(f"committed {stamp} — seed regenerated ({words} words)")
    else:
        err = (com.stderr or com.stdout or add.stderr or "").strip()[:200]
        print(f"MERGED BUT NOT COMMITTED — disk state is current; git failed: {err}")
        print("  fix git; the next successful commit sweeps this state in (git add -A).")


def acquire_lock():
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        pid = LOCK.read_text().strip() or "0"
        try:
            os.kill(int(pid), 0)
            print(f"another seedd is running (pid {pid}); exiting")
            return False
        except (ProcessLookupError, ValueError, PermissionError):
            print(f"stale lock (pid {pid}) — taking over")
            LOCK.unlink(missing_ok=True)
            return acquire_lock()


def single_pass():
    for f in sorted(INBOX.glob("*.md")):
        if f.name.endswith(".held.md"):
            continue
        time.sleep(0.2)  # let in-flight writes settle
        commit(f)


def main():
    HISTORY.mkdir(exist_ok=True)
    INBOX.mkdir(exist_ok=True)
    if not acquire_lock():
        sys.exit(1)
    try:
        if "--once" in sys.argv:
            single_pass()
            return
        print(f"seedd v0.2 watching {INBOX}")
        while True:
            single_pass()
            time.sleep(2)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
