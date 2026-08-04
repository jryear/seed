# Seed

A bounded, auditable state kernel for human–AI work. Flat files, git-backed, engine-agnostic.

Seed solves one problem: sessions with AI are stateless, and every tool that offers to fix that traps your state inside itself. Seed makes working state a **page of markdown under git** — readable by any model, writable by any agent, owned by no tool.

## The loop

```
Session reads bounded seed.md
  ↓
Work changes a decision, assumption, position, or observed result
  ↓
A field-level delta lands in inbox/
  ↓
[probe] claims are perturbation-tested through a local model
  ↓
seedd validates, merges changed fields, archives the delta
  ↓
Git commits the new durable state
  ↓
Next session starts from earned state instead of a cold open
```

## The continuity contract

`seed.md` carries five fields, bounded at 300 words total:

| Field | Carries |
|---|---|
| `L4 Position & Trajectory` | Where you stand; what compounding move is active |
| `L2 Pending Decision` | The high-stakes choice current work serves |
| `L1 Problem Class & Mode` | Named problem class; constructive or limiting |
| `Assumptions Most Likely Wrong` | Ranked; these are the perturbation targets |
| `Last Delta & Observed Result` | What shifted last cycle; what reality said |

The bound is load-bearing: a page that fits in one paste works from any surface, including a phone. If merged state would exceed it, the delta is **held**, not truncated — compression is a deliberate act, never a side effect.

## Guarantees (enforced, regression-tested)

Each guarantee below names the evolved-suite regression tests that pin it.

- Probe outcomes gate deltas: transferring probes may proceed; fragile, unreachable, malformed, or ambiguous outcomes hold. Indentation cannot bypass probing. (`test_03a_probe_transfers`–`test_03d_malformed_probe_blocks`, `test_16d_ambiguous_verdict_holds`–`test_16i_probe_exit_code_contract`, `test_19b_indented_probe_is_executed_and_stripped`)
- Probe directives do not enter the carry projection; the original delta is archived verbatim, and structured evidence is retained for transferring, fragile, malformed, and error outcomes. (`test_05_history`, `test_11_probe_lines_stripped`, `test_12_evidence_retained`, `test_16a_malformed_probe_evidence_schema`–`test_16c_partial_answers_survive_verdict_error`)
- The schema is the seed itself: unknown field headings are held rather than silently extending it. (`test_13_unknown_field_held`)
- Duplicate headings in one delta are held as a conflict rather than silently collapsing to the last value. (`test_14_duplicate_field_held`)
- A failed Git commit reports `MERGED BUT NOT COMMITTED`; restarting after disk state advances but before inbox cleanup replays idempotently. (`test_06_git_truth`, `test_07_crash_recovery`)
- Multiple queued deltas are processed in filename order, with both archived and the later field value winning. (`test_08_concurrent`)
- A delta that would exceed the carry bound is held without changing `seed.md`. (`test_09_carry_bound`)
- `setup.sh` fails loudly and cannot claim readiness over a broken initialization. (`test_15_setup_truthful`, `test_17e_setup_rejects_non_regular_allowlist_path`)
- Automated Git commits and initialization use explicit path allowlists; unrelated staged, untracked, or hook-added files are not swept into Seed commits. (`test_17_commit_is_allowlisted`, `test_17b_setup_is_allowlisted`, `test_17c_seedd_disables_commit_hooks`)
- The evidence ledger must be a regular file; an invalid allowlisted path holds ingestion or fails setup. (`test_17d_evidence_path_must_be_a_regular_file`, `test_17e_setup_rejects_non_regular_allowlist_path`)
- Held and archived moves do not clobber existing evidence; if the source disappears after its destination link is created, the destination payload survives. (`test_18a_held_collision_preserves_both`–`test_18e_destination_survives_source_unlink_race`)
- A delta with no Seed field is held, and an indented probe is still executed and stripped from carry. (`test_19a_no_field_delta_holds`, `test_19b_indented_probe_is_executed_and_stripped`)

## Layout

```
seed/
├── seed.md            # bounded carry state — the only file a session needs
├── inbox/             # candidate deltas; *.held.md = blocked, with reason
├── history/           # append-only delta archive, verbatim
├── evidence.jsonl     # append-only probe ledger: model, claim, answers, verdict
├── bin/seedd.py       # the commit loop (stdlib only)
├── bin/probe.py       # perturbation tripwire via local Ollama
├── tests/             # the reality audit
└── setup.sh
```

## Quickstart

```bash
bash setup.sh                 # init repo, fail loudly on error
python3 bin/seedd.py          # watch loop  (or --once for a single pass)
python3 tests/test_seed.py    # run the audit
```

Fill the five fields in `seed.md`. Open your next AI session by handing it the file. End the session by asking for "the delta, in seed field format" and dropping it in `inbox/`. That is the entire workflow.

## Design principles

1. **Flat files are canonical.** Databases, graphs, and UIs are derived views, promoted only by repeated, documented query demand that flat files cannot serve.
2. **State is not doctrine.** Seed carries state. How you reason lives in your runtime documents; which tools execute lives in your harness. No layer owns another.
3. **Probes block; evidence persists.** Untested load-bearing claims do not enter durable state. Every probe run — pass, fail, or error — is a permanent record.
4. **Truthful reporting is a kernel property.** No component may claim success it did not verify. This is enforced by tests, not by intention.
5. **The vanish test.** Any tool in the stack — UI, harness, engine, this daemon — must be deletable with no loss beyond convenience. State survives everything.

## What Seed is not

Not an agent framework. Not a memory ontology. Not an orchestrator. Not a harness. It is deliberately the smallest thing that closes the loop between sessions — and it stays that way until reality, in the form of recurring demand recorded in its own ledger, argues otherwise.

## Lineage

Seed was designed in conversation between a human operator and frontier models, then hardened by adversarial review: its first ledger entry records a hypothesis dying against evidence, and its first real use exposed and repaired a defect in the substrate itself. Both are preserved in `history/`. The project treats that as the standard: claims are proven by contact, and the proof is committed.
