# AGENTS.md

Rules for any agent operating in this repository. They encode lessons already paid for; follow them or document why reality disagrees.

## State

- Flat files are canonical. `seed.md`, `history/`, `evidence.jsonl`, and git are the system of record. Everything else is a derived view.
- Never edit `seed.md` directly. Propose changes as field-level deltas in `inbox/`. The daemon is the only writer of carry state.
- Deltas touch only fields that already exist in `seed.md`, one heading each. Schema changes are a deliberate manual edit by the operator, never a delta side effect.
- Attach a `[probe] claim || perturbed variant` line to any load-bearing claim you introduce. Untested claims do not enter durable state.
- Never delete or rewrite `history/` or `evidence.jsonl`. Append only. Provenance outranks tidiness.

## Truthfulness

- Never report success you did not verify. Check return codes, re-read the tree, confirm the commit exists. "Committed", "ready", and "passing" are claims about reality, not intentions.
- Distinguish observed, inferred, and assumed in every report. Failures are reported verbatim, not summarized into optimism.
- If your context and the working tree disagree, the tree wins. Re-read before you write.

## Concurrency

- One writer to kernel code at a time. Everyone else works on a branch or a copy. State deltas already have a serialization point (`inbox/` → daemon); code changes get the same discipline.
- Repository commits require explicit operator approval. Proactivity does not waive approval gates.

## Construction discipline

- Choose the simplest implementation that fully meets the current requirement. No speculative abstraction, configuration, or indirection.
- Grow in layers: smallest end-to-end working version first; each capability lands on a product that already works. Never trade a working product for unfinished complexity.
- New infrastructure (databases, services, ontologies, panes) is promoted only by repeated, ledger-documented demand that existing files cannot serve. Elegance is not demand.
- Derived views must visibly distinguish file evidence from inference. No inferred relationship quietly becomes truth.
- Do not preserve backward-compatibility shims inside the kernel. Remove obsolete paths; git holds the past.

## Verification

- Test suites prove what their author imagined, not what an adversary finds. Substrate changes get independent review before release.
- A regression test must fail when its fix is reverted. If you can't demonstrate that, you haven't pinned the bug.
- Run the full suite strict (`PYTHONWARNINGS=error`) before calling anything release-ready.

## Judgment

- Do not manufacture motion. Work counts when it returns evidence, artifacts, or a changed decision — not activity.
- A change that alters no decision, assumption, position, or observed result does not need a delta.
- Naming persistent things belongs to the operator. Use plain functional labels for anything transient.
- Challenge load-bearing uncertainty; do not perform skepticism on everything. Reflexive opposition destroys signal.

## The standing test

Any tool, view, or agent in this environment must pass the vanish test: if it disappeared tonight, nothing canonical is lost. If your contribution fails that test, it belongs in `inbox/` or a branch — not in the kernel.
