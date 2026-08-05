#!/usr/bin/env python3
"""seedd v0.3.1 — hardened commit loop.

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
  5. The headings already present in seed.md are the schema. Unknown
     or duplicate delta headings HOLD instead of mutating state.
  6. Probe directives never enter seed.md. Probe outcomes are appended
     to evidence.jsonl while the original delta remains in history/.
  7. Git commits are path-allowlisted; unrelated staged or untracked work
     cannot be swept into Seed history.
  8. Held and archived evidence names never overwrite an existing file.

Usage:
  python3 bin/seedd.py          # watch loop
  python3 bin/seedd.py --once   # single pass (tests, cron)

Held deltas: fix the file (or delete the probe line), rename back
to .md, and seedd will retry it.
"""
import os, re, stat, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED, HISTORY, INBOX = ROOT / "seed.md", ROOT / "history", ROOT / "inbox"
EVIDENCE = ROOT / "evidence.jsonl"
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


def is_regular_file(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def move_no_clobber(source, destination_for):
    counter = 0
    while True:
        destination = destination_for(counter)
        try:
            os.link(source, destination, follow_symlinks=False)
        except FileExistsError:
            counter += 1
            continue
        try:
            source.unlink()
        except FileNotFoundError:
            # A concurrent source-side unlink leaves the new hard link as the
            # only surviving copy. Preserve it; rollback would destroy evidence.
            pass
        return destination


def move_to_held(delta_path):
    return move_no_clobber(
        delta_path,
        lambda counter: delta_path.parent / (
            f"{delta_path.stem}.held.md" if counter == 0
            else f"{delta_path.stem}.{counter}.held.md"
        ),
    )


def move_to_history(delta_path, stamp):
    return move_no_clobber(
        delta_path,
        lambda counter: HISTORY / (
            f"{stamp}-{delta_path.name}" if counter == 0
            else f"{stamp}-{counter}-{delta_path.name}"
        ),
    )


def hold(delta_path, reason):
    held = move_to_held(delta_path)
    with open(held, "a") as f:
        f.write(f"\n\n<!-- HELD: {reason} -->\n")
    print(f"HELD {delta_path.name} as {held.name} — {reason}")
    print("  fix the file, rename back to .md to retry")


def run_probes(delta_text):
    """Returns None if all probes transfer, else a hold reason."""
    for line in delta_text.splitlines():
        if line.lstrip().startswith("[probe]"):
            r = subprocess.run(
                [sys.executable, str(ROOT / "bin" / "probe.py"), line.lstrip()],
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


def commit_paths(paths, message):
    invalid = [path for path in paths if not is_regular_file(path)]
    if invalid:
        failure = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr=f"refusing non-regular path: {invalid[0]}",
        )
        return failure, None
    relative = [str(path.relative_to(ROOT)) for path in paths]
    add = git("add", "--", *relative)
    if add.returncode != 0:
        return add, None
    commit_result = git("-c", "core.hooksPath=/dev/null", "commit",
                        "--only", "-m", message, "--", *relative)
    return add, commit_result


def commit(delta_path):
    if not is_regular_file(delta_path):
        print(f"REFUSED {delta_path.name} — delta must be a regular file")
        return
    if not is_regular_file(SEED):
        print("REFUSED — seed.md must be a regular file")
        return
    if os.path.lexists(EVIDENCE) and not is_regular_file(EVIDENCE):
        hold(delta_path, "evidence.jsonl must be a regular file")
        return
    delta = delta_path.read_text()

    # Schema checks (cheap, before any model call)
    names = FIELD.findall(delta)
    if not names:
        hold(delta_path, "no field headings — a delta must update the existing Seed schema")
        return
    if len(names) != len(set(names)):
        hold(delta_path, "duplicate field headings in one delta — resolve the conflict explicitly")
        return
    known = set(parse(SEED.read_text())[1].keys())
    unknown = set(names) - known
    if unknown:
        hold(delta_path,
             f"unknown field(s): {', '.join(sorted(unknown))} — schema changes are manual: edit seed.md deliberately, then commit")
        return

    reason = run_probes(delta)
    if reason:
        hold(delta_path, reason)
        return

    # Probe lines are directives, not carry text: strip from the projection,
    # keep verbatim in history/; structured evidence lands in evidence.jsonl.
    content = "\n".join(
        line for line in delta.splitlines()
        if not line.lstrip().startswith("[probe]")
    )
    merged = merge(SEED.read_text(), content)
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
    archived = move_to_history(delta_path, stamp)

    paths = [SEED, archived]
    if EVIDENCE.exists():
        paths.append(EVIDENCE)
    add, com = commit_paths(paths, f"delta {stamp}")
    if add.returncode == 0 and com is not None and com.returncode == 0:
        print(f"committed {stamp} — seed regenerated ({words} words)")
    else:
        err = ((com.stderr or com.stdout) if com is not None else add.stderr).strip()[:200]
        print(f"MERGED BUT NOT COMMITTED — disk state is current; git failed: {err}")
        print("  fix git; Seed will stage only its explicit state and evidence paths.")


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
        print(f"seedd v0.3.1 watching {INBOX}")
        while True:
            single_pass()
            time.sleep(2)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
