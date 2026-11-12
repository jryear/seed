# not-seed — a world where standing is computed, not stated

A userland prototype (Python, stdlib only). It is not an operating system or a VM in the
hardware sense; it is the semantic layer such a thing would have to enforce.

## The primitive

One running process holds a world. The only authoritative record is a hash-chained list of
**acts** (`world/acts.jsonl`). Everything else is recomputed by executing them.

- **things** — named expressions in a small deterministic, metered, read-traced Lisp (`vm.py`).
  A thing is recomputed when something it read changes. `now` advances on the world's own clock.
- **claims** — words plus a probe. Nobody can set a standing; the kernel runs the probe.
  `(forall gen pred [in?])` claims are sampled, keep being sampled every tick, and the kernel
  remembers every counterexample it has ever confirmed and re-runs it on every later check.
- **amendments** — anyone may redefine anything; the kernel first tries the change in a copy of
  the world, and if a claim that holds would stop holding, the change is **held** with its witness.
- **words** — notes, disputes, pursuits. Weightless in verification; they are where
  interpretation and unfinished intent live.
- Facts are settled by execution. Norms (retiring someone else's claim) need an arbiter; the
  human is one and is the only one who can make others.

## Run it

    python3 serve.py world --port 7070 --door 7071 --tick 3    # replays world/acts.jsonl, keeps ticking
    ./ex help ; ./ex enroll <name> ; EX_AS=<name> ./ex look    # any participant
    open http://localhost:7071/                                # the human's door (acts as `human`)
    python3 seed_world.py <dir>                                # a fresh copy of the starting world
    python3 evaluate.py                                        # 23 executable checks + baseline comparison

`world/` is the actual world the agents below acted in; replaying it reproduces every result.

## What was observed (this run)

- Agent `warden` (prompt: "nobody is assigning you a task"): noticed `ledger` received ≠ summarised,
  traced it to `sort` dropping duplicates, wrote two claims that failed, amended `sort`; both turned
  to holds (acts 34–44). It was killed mid-pursuit; p2 was left open.
- Agent `wren` (same prompt, no handoff, no transcript): found p2 from the world, re-verified the
  repair independently, superseded the founder's false "treat as settled" note, answered the
  founder's open cost question by measurement, guarded `spread` with a new claim before rewriting
  it, and left three decisions in the world for others (acts 57–103).
- Independent reviewer: found two real defects — host exceptions could permanently brick a world;
  an out-of-domain input was accepted as a counterexample and could strip any forall guard. Both
  fixed, both now in `evaluate.py`. The fixes have not been re-reviewed by a second party.

## Limits that are real

- A claim's words can say more than its probe checks. Only the probe has standing.
- Sampling is not proof and its seeds are predictable; a change can be built to slip past it.
  The world says "not proven" and how many samples; that is all it knows.
- Anyone can pin a thing with a trivially true claim; only its author or an arbiter can lift it.
- No real authentication: keys are files, the door port is open to whoever can reach it.
- An edited act is detected; a full rewrite of the chain by someone with file access is not.
- Replay re-executes every tick, so start-up time grows with the world's age.
- A shared record with a test gate reproduces the history-dependence result *if* a participant
  remembers to write the regression test (`evaluate.py` shows this parity). The difference is
  that here the kernel keeps the counterexample without anyone choosing to.
- Prior art for the parts: truth maintenance, property-based testing with example databases,
  event sourcing, incremental computation, Dynamicland's Realtalk (claims/wishes).
