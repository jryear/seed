# Runtime abstraction experiment

Does an agent do better when its interface is **requests for state transitions**
(capabilities, typed states, runtime-managed caching/checkpoints) instead of
**a shell over processes and files**? And if it does, is that because processes
are hidden, or because the runtime adds services?

This lives outside the Seed kernel. Deleting this directory loses nothing canonical.

## Design (2×2, one task family)

| | services off | services on |
|---|---|---|
| **processes visible** | `shell`: `sh` | `shell_svc`: `sh` + `cached_sh`, checkpoints, `verify_report` |
| **processes hidden** | `cap`: `capabilities`, `resources`, `transition`, `inspect`, `deliver`; state dies with the runtime process | `cap_svc`: same + persistent states, semantic cache, `progress`, runtime-verified delivery |

- **Interface removal is real, not prompted.** The agent is headless `claude -p` with `--tools ""` (no built-in Bash/Read/Edit), `--strict-mcp-config` (only this arm's MCP server), and a replaced system prompt. The init event of every trial lists only the arm's tools.
- **Task.** Produce a revenue report across 8 regional ledgers. The ledgers include duplicates, one ledger with malformed rows (normalize fails; repair is the remedy), two rate tables (only the latest is "current"), and two regions whose transaction bodies are identical. Each record also carries a fingerprint, and a few records were tampered with. Only the expensive check (~1.5 CPU-s per ledger) catches the tampering, so an agent that skips it gets a wrong answer. The same worker programs execute in every arm.
- **Independent supervisor** (`supervisor.py`). It owns the OS and the agent does not.
  - Traces every `execve` with strace.
  - Measures tool-subtree CPU from `/proc`.
  - In the interrupted condition, `SIGKILL`s the whole process group once the tool subtree has burned 4.5 CPU-s. That is about 3 ledgers of work, observed at host level and independent of the interface.
  - Starts a fresh session after the kill, and grades the delivered report against an independent reference implementation.
- **Shell containment.** Each shell command runs in a private mount namespace. `/home/user` and `/root` are empty, `/tmp` is a per-trial directory that persists, and only the workspace is visible at its own path.

Run: `python3 supervisor.py --out DIR --model M --reps N` then `python3 analyze.py DIR`.

## Results (final configuration: 112 trials, Haiku 5.5 ×8 and Sonnet 5.5 ×6 per cell)

Full tables: `results/final/summary.md`. Raw data: `results/final/results.jsonl`, plus per-call logs in `calls.tgz`.

**Observed:**

1. **Completion reliability did not discriminate.** 112/112 trials passed. This task sits at the ceiling for both models, so it is not evidence that either interface is more reliable.
2. **Recovery is where the arms separate, and it comes from services plus hidden processes together.**

   | trials where the resumed session redid all normalization (≥8 runs) | Haiku | Sonnet |
   |---|---|---|
   | shell | 6/8 | 6/6 |
   | shell_svc | 5/8 | 6/6 |
   | cap | 8/8 | 6/6 |
   | cap_svc | **0/8** | **0/6** |

   - Shell agents called `checkpoint_list` in every `shell_svc` trial, but almost never wrapped work in `cached_sh` before the kill. Offering services alongside a shell did not change behaviour.
   - Sonnet shell agents ran normalization in parallel, so the kill landed with all 8 runs in flight and none finished. The `cap` runtime serializes, so 3–4 runs completed before the kill.
3. **The latency gain from hiding processes depends on the condition and the model.**
   - With services on, the interrupted condition was faster: Sonnet −11.8 s [−20.8, −2.3], Haiku −3.5 s (CI spans 0).
   - On clean runs there was no reliable difference.
   - With services off, Haiku was faster (−6 to −14 s) and Sonnet showed no difference.
4. **Model cost** (final-session USD; killed sessions report no cost and are excluded):
   - `cap` was the cheapest clean arm for both models: Haiku $0.0031 vs $0.0050 for shell; Sonnet $0.036 vs $0.060.
   - `cap_svc` was the cheapest interrupted arm for Sonnet: $0.029 vs $0.039–0.054.
5. **Host work.**
   - Process spawns fell 5–12×: 18–37 execve vs 89–365. Almost all of the shell spawns were exploration (`ls`, `cat`, `find`), not task work.
   - Tool CPU moved little. The exception is `cap_svc`, about 2 CPU-s lower on clean runs, which came from the semantic cache reusing the mirrored ledger. A byte-keyed `cached_sh` cannot see that, because the region label differs.
6. **Round-trips doubled.** Capability arms made 14–34 tool calls vs 5–16. Each call is cheaper, but the count is higher.
7. **Implementation knowledge.** The interface catalogs are similar in size (956 vs 1039 characters for the services-off arms). But shell agents read the worker source code in 49 of 56 trials. Capability agents cannot do that; they worked from contracts alone and passed every trial.
8. **Containment.**
   - Without the sandbox, 6 of 32 shell trials searched the host filesystem after getting confused by a scratch path the CLI injects into the agent's context. Two of them found the harness's cached task data and failed (`results/haiku-unsandboxed/`).
   - With the sandbox, 3 of 32 Haiku shell trials still tried this; it was contained.
   - Capability arms: 0 of 56. They have no tool that can reach a path.

**What this does not show:**
- Anything beyond one task family I designed. The semantic-cache win exploits a structure I planted (the mirrored ledger).
- Reliability differences, because the task is at ceiling.
- Session-1 cost for interrupted trials; those sessions emit no final accounting.
- Interrupted-condition tool CPU from the call log. It undercounts the call in flight when the kill lands, so use the strace process counts instead.

**Assumption most likely wrong:** that these effects survive a task where the capability catalog does *not* fit the job. Here every needed operation existed as a capability. An open-ended task would force an escape hatch, and that is where the abstraction is predicted to leak.

## Task 2: incomplete catalog (112 trials, same models and cells)

The objective asks for USD revenue per region **per month**, with each transaction converted at
the rate table for its own month. No capability does this. The capability arms get `derive`, an
escape hatch: the agent writes a Python `run(inputs)` over the decoded contents of states and
resources. It runs in the same mount jail as the shell and sees only its inputs. Its results are
marked unverified, and errors return only the line number in the agent's program. Shell arms
already have general compute. Full tables are in `results/task2/summary.md`.

**Observed:**

1. **The escape hatch became the main path.** Every capability-arm trial that delivered a report
   delivered one built by `derive`: 55 of 56. The other trial refused to deliver.
   - Hatch errors were rare: median 0, maximum 1.
   - No hatch program tried to reach the OS: 0 of 56.
   - The prediction that the abstraction would leak through errors on the failure path was **not
     borne out**.
2. **The leak showed up as cost instead.** On task 1 the capability arms were cheapest; on task 2
   that advantage shrank or reversed.
   - Sonnet, clean runs: cap $0.060 vs shell $0.061, and cap_svc was the most expensive at
     $0.079.
   - Haiku, clean runs: cap $0.0061 vs shell $0.0080.
   - Tool calls were about 3× the shell's: 20–34 vs 6–14.
   - Implementation knowledge came back. Capability agents had to learn the decoded data format
     and write the same aggregation code a shell agent writes.
3. **The recovery advantage survived.**

   | trials where the resumed session redid all normalization (≥8 runs) | Haiku | Sonnet |
   |---|---|---|
   | shell | 3/8 | 6/6 |
   | shell_svc | 4/8 | 6/6 |
   | cap | 8/8 | 6/6 |
   | cap_svc | **0/8** | **0/6** |

4. **Reliability: 108 of 112 passed, and the 4 failures were small and mixed.**
   - **cap_svc, interrupted (Haiku):** refused to deliver. The agent judged the mirrored `coastal`
     ledger to be corrupt data.
   - **cap, clean (Haiku):** delivered `coastal` as empty, on the same suspicion.
   - **cap, interrupted (Haiku):** delivered correct numbers wrapped in an extra `{"report": ...}`
     layer. This arm has no delivery verification. cap_svc's coverage check would have rejected
     the wrapper.
   - **shell, interrupted (Haiku):** the 900 s session timeout fired.

   Two of the four come from the mirror I planted for the cache test. That makes it a
   task-ambiguity defect: an identical ledger under a second region is a reasonable thing for an
   agent to flag.
5. **Containment.** 11 of 56 sandboxed shell trials probed outside the workspace, and all were
   contained. Capability arms, hatch included: 0.

**Revised position:**
- The benefit of hiding processes depends on the catalog fitting the work. When it doesn't, the
  agent writes code anyway and pays extra round-trips to do it.
- The durable benefit is runtime-owned persistent state, which recovery depends on, together
  with containment by construction.
- A capability layer with an escape hatch kept both properties here.

## Artifacts kept as evidence of harness defects

- `results/haiku-unsandboxed/`: no shell containment; workspace escapes.
- `results/haiku-shell-sandbox-v1-tmpfs/` and `results/sonnet-sandbox-v1-tmpfs/`: the first sandbox wiped `/tmp` between commands, which inflated shell rework (16–36 normalize runs). The shell-arm numbers in these runs are not valid; the cap-arm numbers are reused in `final/`.

## Next layer

- A second agent family: Codex, via `supervisor.py --agent codex` (built, not yet run; needs OpenAI network access and a login).
- Experiment 3 (agent-invented primitives) is only worth building after that. What would carry over is the matched search budget on the baseline and held-out tasks.
