# Roadmap

No timelines. Phases advance when their success signals are observed, not when time passes. Signals are checkpoints: if a phase's signals aren't appearing, the phase is wrong or premature — stop and re-read the evidence.

Standing rule inherited from the kernel: **infrastructure is promoted by demonstrated demand, recorded in the ledger — never by anticipation.**

---

## Phase 0 — Kernel stabilization

- Stable repository at a permanent path (out of any session-scoped tree).
- [x] Version labels consistent across daemon, probe, and suite.
- Socket hygiene in tests; strict-warnings run stays clean.
- Tag the release; independent reviewer reproduces the suite from a fresh clone.

**Success signals:**
- Full suite passes under `PYTHONWARNINGS=error` from a fresh clone.
- An independent reviewer (human or agent with no authorship stake) reproduces all results.
- Zero uncommitted state after any test run.

## Phase 1 — Production carry (the phase that matters)

- Daily use: sessions open from `seed.md`, close with a delta.
- Deltas recording decisions, assumptions, positions, observed results — about work, not about Seed.
- First real `[probe]` holds exercised against live claims.

**Success signals:**
- ≥10 committed deltas whose subject is the world, not the substrate.
- ≥1 FRAGILE hold on a real claim that changed what entered carry.
- ≥1 decision made differently, with an attributable outcome, traceable to carried state (the original five-cycle contract).
- Carry-bound pressure observed and resolved by deliberate compression at least once.

## Phase 2 — Minimal provenance

- `evidence_id` + `delta_id` on every evidence record; stable link to the history artifact.
- No heuristic correlation anywhere: every probe record resolvable to its delta by identity.

**Success signals:**
- A claim's full test history retrievable with `grep` alone.
- No consumer of `evidence.jsonl` needs timestamps or text-matching to join records.

## Phase 3 — Seed Studio (derived views only)

Panes earn existence individually, in demand order — not as a suite:

- **Delta queue** first: pending / held / applied, hold reasons, retry controls.
- **Evidence browser** second: claims, perturbations, answers, verdicts, repeat-probe comparison.
- **Current-seed + health pane** when operating blind on files demonstrably costs something.
- **Timeline** when history is long enough that `git log` stops being sufficient.
- **Derived graph canvas** only after the first real need to trace a claim across deltas — and it must visibly distinguish file evidence from inferred relationships. No inferred edge quietly becomes truth.

**Success signals:**
- An operating decision (retry, reject, compress, investigate) made from the Studio that would have been missed in raw files.
- The Studio holds zero canonical state: killing it loses nothing (the vanish test, verified by actually killing it).
- Each shipped pane traceable to a logged instance of need.

## Phase 4 — Multi-runtime adoption

- Other surfaces and agents read `seed.md` and produce deltas: terminal agents, mobile capture, Hermes gateway, side agents.
- One-writer discipline for kernel code; branches for everything else.
- Conflict and hold paths exercised by real concurrent use, not just tests.

**Success signals:**
- Deltas committed from ≥3 distinct runtimes.
- ≥1 concurrent-writer conflict caught by policy rather than by luck.
- A session on a phone that opens from carry and produces a valid delta.

## Phase 5 — Graph promotion (conditional; may never trigger)

Promotion to a canonical event store (SQLite first; never a graph DB before meaning stabilizes) occurs only on repeated, ledger-documented instances of:

- tracing one claim across many deltas and probes;
- multi-hop provenance queries;
- temporal-validity or authority-path queries;
- unresolved identity collisions;
- repeated bespoke joins across markdown, JSONL, and git;
- material performance or maintenance failures of flat files.

**Success signals (that the promotion was right, after the fact):**
- The event store is a projection *backing*, with flat files still exported as the audit surface.
- Every pre-promotion record migrated with provenance intact.
- Query demand continues after promotion (it wasn't a one-time itch).

## Phase 6 — Derivative substrates

- Second seed for a genuinely separate project lane, only when one repo demonstrably can't serve both.
- Client-facing derivative: stripped shell + seed kernel + PR-gated automation as a deliverable product pattern.
- Possible public extraction: the kernel is small enough to be legible open source.

**Success signals:**
- A second seed justified in writing by a real collision, not by tidiness.
- A client system shipped on the pattern with the client able to operate it unassisted.
- An outside adopter runs the loop without the authors present.

---

## Anti-goals (permanent)

- Seed never becomes an agent harness, an orchestrator, or a scheduler.
- No UI, database, or service ever owns canonical state.
- No component is added because it would be elegant. The ledger decides.
