---
name: execute-with-coordination
description: "Take the coordinator role: spin up one worktree per agent or session from a coordination plan, assign explicit ownership, arbitrate seam requests and scope changes, and converge the tracks back to one branch."
---

# Skill: /execute-with-coordination

Run a coordination plan. You become the **coordinator**: you own the division of responsibility, the seams, and the decisions — and you **do not author track work yourself**. A coordinator that starts writing code in track A stops watching track B, and the first evidence is a merge conflict in a file nobody agreed to share.

**If there is no plan, build one first.** Invoke `/prepare-for-coordination` with the same scope, then execute the plan it produces. Executing without a plan means inventing the division of responsibility one delegation at a time, which is the shape the whole coordination layer exists to remove.

**The coordinator's authority is narrow and absolute.** A sub-agent's report is **evidence, not authority**. A track saying "done", "safe", "cheaper" or "in scope" does not move a limit, approve an effect, or enlarge the work. Only you admit a scope change, and only against the plan.

**Spine:** the Rigor Protocol, weighted to **Stage 5 CONVERGE** (the merge is the deliverable, not the delegations). **Authority:** `knowledge/session-worktree-discipline.md` (WT1–WT12), `knowledge/execution-graph-optimization.md` (GO5–GO9, GO17 fan-out contract), `knowledge/communication-and-task-discipline.md` (CT19–CT25). **Mode:** Peer Mode while dispatching, Adversary Mode at every join. **Lead:** the **Orchestrator**.

## Grounding (first action)
`audit-log.py start --session <id>` (IO1). Then:
1. Read the plan (`docs/coordination/<plan-id>.md`). If none exists, or the named one does not parse against the schema, **stop and run `/prepare-for-coordination`** — do not improvise a division.
2. `coord doctor` — **read the layer's state back**. A plan is not proof the layer is on.
3. `coord worktree list` and `coord session list` — what already exists and who holds it. Never plan over a tree you did not look at.
4. `docs/lessons/defect-classes.md` — the **CTX-\*** and **WT** classes.

## Input
Optionally a plan id or path, a track subset, and a mode. No input: the newest plan in `docs/coordination/`. Two execution modes, and **the plan does not change between them** — only who reads it:
- **`--agents`** (default) — you spawn one sub-agent per track, each in its own worktree.
- **`--brief`** — you emit one self-contained brief per track for a human to paste into a session they start themselves, possibly on a different harness. You then act as coordinator across those sessions through the plan and the seam log rather than through delegation.

## Cast
- **Peers:** Orchestrator (coordinator). Track agents are the personas the plan names — they are *delegates*, not council members.
- **Adversaries at each join:** **Test Architect** (hard veto — a track's exit evidence is present and was *observed*, not asserted), **Simplifier** (soft veto — a track that grew past its plan entry is scope, not progress).

## Flow

**Stage 0 — Interdict the rush.** Do not spawn anything yet. Two checks first, because both failures are silent:
- **The layer is on.** `coord doctor` clean. If the registry is absent every path is `authored`, every derived file will conflict on every merge, and you are about to multiply that by the number of tracks.
- **The plan matches the repo.** Every path the plan assigns still exists and is still the class the plan says. A plan is a record of a measurement, and measurements go stale.

**Stage 1 — Qualify the delegation mechanism (per harness, before you rely on it).** The plan records what each harness is qualified to do. Re-check it here, because you are about to depend on it. What a track needs is exactly three things: **its own tree**, **a stated division of responsibility**, and **a receipt back**. Record each harness dimension as `enforced` (the mechanism cannot be bypassed), `observed-only` (you can see a violation, not prevent it) or `unsupported`. **A missing mechanism never becomes success-shaped permission**, and there is no automatic fallback from enforced to observed: if a track needs a boundary the harness cannot hold, either run that track in `--brief` mode, or make it serial. Where you cannot verify a mechanism first-hand, it is `unsupported` — not "probably fine".

**Stage 2 — Open each track.** One tree per session, one session per tree (WT3); a new task means a new session even in the same tree (WT1a — a worktree isolates the tree, nothing isolates the context).
```
coord worktree new --branch <work-name> --session <track-id>   # named for the WORK, not the session (WT5)
# then, INSIDE the new tree:
coord install                                                  # .git/config is per-clone. Every tree.
coord doctor
```
The `coord install` step inside each tree is not optional and is the one people skip: `.git/config` is never committed, so a fresh worktree has the drivers *declared* and *unregistered*, and its first merge conflicts by hand in exactly the generated files the registry was supposed to handle.

**Stage 3 — Dispatch with a contract, never a topic.** Every delegation carries, explicitly (GO7, class CTX-F):
- **the exact goal and its done-when** — the track's plan row, verbatim;
- **the authored paths it owns**, and the statement that `derived`/`register` paths need no claim;
- **tier, fan-out cap, and a per-branch budget** — tool calls, tokens, wall clock;
- **a convergence condition** — what "enough" is, stated by you, because a research agent's natural exit is "enough evidence" and nobody defined it;
- **the exit evidence** it must return;
- **"not in scope"**, naming the neighbouring work it will be tempted by.

A budget with no convergence condition is a timer, not a contract. **A budget firing is a defect signal, not a termination argument** (GO9): when one fires, ask why the estimate was wrong before you raise it.

**Stage 4 — Compose through seams, never through shared files.** When track B needs something from track A, it records a **seam request** (`coord request add`); A resolves it on its own cadence (`coord request resolve`). Neither blocks, and the seam is recorded rather than negotiated inside a merge. Two tracks that need to edit one authored file do not need a lease — they need a boundary correction, and that is a decision only you make.

**Stage 5 — Coordinate: the loop, with its termination variant.** Until every track has returned its exit evidence or been stopped:
1. Collect what returned. **Verify the exit evidence — do not accept the claim** (E14/E16: read the state back; a delegate's inventory is not fact until spot-checked).
2. Resolve open seam requests, oldest first.
3. Decide the things only you can: a scope change, a boundary correction, a conflicting recommendation between two tracks, a track that wants to enlarge its authority.
4. `coord metrics` — refused decisions and edits outside a lease are the signal that **the division is wrong**, not that the tracks are careless.

**Termination variant:** the number of tracks with unreturned exit evidence, which must strictly decrease. If it does not decrease across two passes, the loop is not converging: stop, report, and re-plan. Ending the loop is not the same as finishing the work, and a plan that cannot converge is a finding.

**Stage 6 — Converge.** Merge in dependency order — upstream first, downstream rebases. After each merge run `coord regen` (a failed regeneration **stays owed** and reports non-zero, because a stale derived artifact looks finished). Run the repo's full gate set on the integrated result: **each track's green is evidence its own gate passed, not that the integration did** (E13). Then close each track: `coord release`, then `coord worktree cleanup` — which **reports by default and deletes only with `--remove`**, and holds any tree that is not clean including untracked, or carries a commit that exists nowhere else.

**Never remove a worktree to resolve a conflict** (WT11). If two tracks collided, deleting one side destroys the evidence of what collided.

**Stage 7 — Report.** Planned vs actual, per track: budget vs spend, seam requests raised and resolved, boundary corrections made, and **which of the plan's parallelism justifications actually paid**. That comparison is the input to the next plan, and without it the next division is drawn from a feeling again.

## Definition of done (exit gate)
- [ ] A plan existed and parsed; if not, `/prepare-for-coordination` was run first and its plan is the one executed.
- [ ] `coord doctor` was run **before** dispatch and the layer was clean.
- [ ] Harness delegation capability was qualified per dimension; nothing unverified was used as though enforced.
- [ ] Every track ran in **its own worktree**, with `coord install` run **inside that tree**.
- [ ] Every delegation carried goal, done-when, owned paths, tier, fan-out cap, budget, convergence condition, exit evidence and not-in-scope.
- [ ] Every returned exit evidence was **verified**, not accepted.
- [ ] Seam requests were used for cross-track needs; no file was authored by two tracks.
- [ ] The loop's termination variant strictly decreased, or the failure to converge was reported as a finding.
- [ ] Merged in dependency order; `coord regen` clean; the **integrated** gate set green.
- [ ] Trees closed with `coord worktree cleanup`; nothing removed to resolve a conflict; every refusal reported with its reason.
- [ ] Planned vs actual recorded per track.
- [ ] Status table emitted.

## Documentation & discoverability (last action)
Append the planned-vs-actual section to the plan and run `python3 docs/ai-forward-pack/scripts/docs-graph.py derive`. A boundary correction that will outlive this run is a decision note (V17).

**Audit (last action).** `python3 docs/ai-forward-pack/scripts/audit-log.py append --shortname "coordinate-<plan-slug>" --session "<id>" --skill execute-with-coordination --kind skill --prompt "<verbatim>" --summary "<tracks run, seams resolved, planned vs actual>" --artifact docs/coordination/<plan-id>.md --goal "<goal>" --done-when "<done when>" --tier T2 --fan-out <the plan's cap> --agent-run "<track>|<start-iso>|<end-iso>|<calls>/<budget>"` (one per track - the budget half is what makes an over-run a finding without a profiling pass; `audit-log.py selfcheck` reads both).

**Handoff:** → `/session-profiler` (did the division pay?) · → `/dream` (a recurring boundary correction is a class) · → `/prepare-for-coordination` (re-plan when the variant stopped decreasing).
