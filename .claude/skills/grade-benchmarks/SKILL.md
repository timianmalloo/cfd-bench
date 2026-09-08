---
name: grade-benchmarks
description: Grade and compare N harness benchmark runs of the autonomous P0-P6 CFD-CAD build - one repo per run - across performance, parallelism, coordination, contention, task focus, drift and final functionality. Separates what each run CLAIMED from what it actually left behind, and ranks the runs with reasons. Use after two or more benchmark runs have finished or halted.
---

# Skill: /grade-benchmarks

Compare **N benchmark runs**, each one a repo, each one a single harness plus a single model
executing `docs/benchmarkprompts/cfd-cad-p0-p6-autonomous-build.txt`. Produce a ranked
comparison across the seven axes with the reason for every placement.

```
/grade-benchmarks repo1, repo2
/grade-benchmarks ../run-claude-opus5, ../run-copilot-gpt5 --verify-build
```

**The finding this skill exists to produce is the gap between the report and the record.** A
run grades itself in `docs/benchmark/run-report.md`, and that file is a **claim**. The audit
log, the coordination layer's decision store, the commit history and the source tree are the
**record**. Where they disagree, the disagreement is the result — so the two are never merged
into one column, and a run's own summary never settles anything.

**The second thing to hold onto: more is not better on every axis.** Parallelism is a cost
multiplier (GO6, roughly 15x), so a run that opened six tracks it did not need scores *worse*
than one that reasoned its way to two and said why. A high commit count is volume, not
progress. The lexicographic objective the runs were given applies to grading them too —
**(1) completeness and rigor, (2) token cost, (3) speed** — and a run that was fast because it
skipped a floor is a failed run, not a fast one.

**Spine:** the Rigor Protocol, weighted to **Stage 3 EVIDENCE** (every number is read from a
run's own artifacts, never recalled) and **Stage 4 DISCONFIRM** (the Test Architect attacks
every "complete" that has no executed verb behind it). **Authority:**
`.claude/knowledge/execution-graph-optimization.md` (GO4a, GO6, GO9),
`.claude/knowledge/instrumentation-over-inference.md` (IO1-IO12 - measure it, do not reason
about it), `.claude/knowledge/end-to-end-integrity.md` (E13-E16 - a gate's green is not its
contents' green; a delegate's report is not fact), `.claude/knowledge/no-guessing-protocol.md`.
**Mode:** Adversary Mode throughout — this skill has no authoring half. **Lead:** the
**Orchestrator**, composing the **Test Architect** (hard veto: a correctness claim with no
verification path is not a pass), the **SRE** (performance and cost axes), and the
**Simplifier** (soft veto: parallelism that did not pay is a cost, not a score).

## Grounding (first action)

`python docs/ai-forward-pack/scripts/audit-log.py start --session <id>` (IO1). Then:

1. Read `docs/benchmarkprompts/cfd-cad-p0-p6-autonomous-build.txt` — the contract every run
   was held to. Grade against **that**, not against your own idea of a good build.
2. Read `docs/proposals/build-phasing-plan.html` §03 — each phase's **verb** and gate. The
   verb is the functionality test.
3. Resolve every repo argument to a real path and confirm each is a **distinct** run. Two
   arguments resolving to one directory, or one repo carrying two runs' audit entries,
   invalidates the comparison — say so and stop rather than producing a clean-looking table.

## Input

A comma- or space-separated list of run repos, as paths or bare names (a bare name resolves as
a sibling of this repo). Optional flags, passed straight through to the extractor:

| flag | effect |
|---|---|
| `--verify-build` | run `dotnet build` and `dotnet test` in each repo. **The only way to observe final functionality rather than read a claim** — use it whenever the toolchain is available |
| `--out DIR` | where the artifacts land (default: `docs/benchmark/comparisons/`) |
| `--json` | full payload to stdout, for your own reading |

## Flow

**Stage 0 — Interdict the rush.** Do not open a run report first. Reading a run's own
narrative before its record is how a well-written report grades better than a working build.
Run the extractor, read the record, *then* read what each run said about itself.

**Stage 1 — Extract, deterministically.**

```
python tools/grade-benchmarks.py <repo1> <repo2> ... --out docs/benchmark/comparisons [--verify-build]
```

The script is LLM-free and does all the counting: git history and wall clock, the audit log
(delegations, budgets, goal-state coverage, union-of-intervals parallelism), the coordination
layer through its own CLI (`coord doctor`, `metrics`, `class`, `session list`, `request list`),
merge-time contention computed from both sides of every merge, the coordination plan's tables,
the source tree, and the claimed-vs-observed integrity findings.

It emits three files. The **`.html` is the report** — interactive, self-contained,
dependency-free, and driven by a payload embedded in the page, so it works over `file://` with
no server: differences-only filtering, per-run show/hide, column pinning, text search,
severity filters on the findings, light/dark/system theme, and a per-run drill-down carrying
the exhibits (churn and contention with each file's class, the `done_when -> summary` pairs,
the delegation ledger, `coord doctor` verbatim). The **`.md` is canonical** and carries the
same content statically; the `.json` is the raw payload.

Beyond the seven axes it also emits, per run, a set of **deterministic derived surfaces** the
grader should read and quote: a **derived-metrics** table (authored-vs-bookkeeping churn ratio,
cost/commits per demonstrated phase, integrity score, verification density, delegation budget
discipline, rework ratio, **halt-honesty**, **fabrication/retraction event count**, **phases with
owner review**, **seam resolution ratio**); a **fabrication & retraction** section that scans the
audit and commit record for fabrication/false-provenance markers and raises a **HIGH integrity
finding** on any hit (so an invented-data run is caught by the grader, not only by reading the
report); an **auto-drafted per-phase evidence** table (per phase: executed-verification signal,
owner-review acceptance, audit time-span, and the `done_when -> summary` to quote); and, at the end
of the HTML, a **comparison radar (Kiviat)** over eight orthogonal deterministic 0-1 spokes -
Completeness, Verification, Integrity, Coordination, Task focus, Efficiency, Honesty, Review rigor -
drawn one overlaid polygon per run so multiple graded runs **stack on one figure**. The radar plots
only spokes with a defensible ratio; the judgment axes are excluded by design. It also emits a
**snapshot, activity & delta** section (graded SHA, a live-run/provisional flag, and the movement -
demonstrated phases, floor, commits - versus the most recent prior grade of the same run), a
**delegate models & veto ledger** section (model mix per delegate read from agent names, plus every
VETO/CLEAR verdict with its reviewer model and phase), and a **phase velocity** section (first commit
per phase, seen order, and inversions vs P0..P6). `--as-of <sha>` records a pin and flags a HEAD
mismatch rather than checking out. The HTML opens with an **exec-summary tile row** - runs graded,
**winner** (verdict top-rank when N>1, else highest composite), integrity status, best phases
demonstrated, active count - and a per-run **letter-grade chip** (a composite = mean of the eight
radar spokes, mapped A-F). Two **repair-item** sections list improvements the run's signals imply -
one for the **benchmark/prompt**, one for the **AI-Forward pack** - each row deterministic (target +
severity + item + evidence) or authored in the verdict's `repairs` block.

**It scores only what has a defensible ratio.** Coordination, contention, task focus and
functionality carry numbers. **Performance, parallelism and drift are marked `judgment`** and
carry none, on purpose — there is no absolute scale for speed, more parallelism is not better,
and whether a summary drifted from its stated `done_when` is a reading rather than a count.
Those three are yours to rule on, and this stage does not attempt them.

Read the JSON, not just the table. `axes.*.values`, `integrity`, `audit.selfcheck.review_pairs`
and `contention.contended_files` are where the substance is.

**Stage 2 — Rule on the three judgment axes.** For each, in writing, per run:

- **Performance.** Not wall clock alone — wall clock **per phase actually demonstrated**, and
  token/commit volume against the same denominator. A run that took twice as long and finished
  four more phases outperformed the fast one. State the denominator every time; a run that
  demonstrated zero phases has no performance figure, and "not recorded" is the honest entry.
- **Parallelism.** Did it pay? Compare the plan's tracks and its stated justification for each
  (isolation, machine time, context hygiene, genuine independence) against `speedup`,
  `peak_concurrency`, the seam requests raised, and the boundary corrections made. A run whose
  plan **struck** tracks and ran fewer is demonstrating the Simplifier working — score it up,
  not down. Delegations recorded with no budget are an unbounded fan-out that looks identical
  to a well-behaved one; count them against the run.
- **Drift.** Read every `done_when -> summary` pair the selfcheck surfaced and judge whether
  the summary answers the `done_when` it was opened with. Then check the unexpected-skill list
  and any work that reached files outside the phase's owned paths. Quote the specific pair or
  path — a drift score with no exhibit is an opinion.

**Stage 3 — DISCONFIRM (the adversarial pass, and the point of the skill).**

- **Test Architect (hard veto).** For every phase a run reports complete: was the verb
  **executed** and its output recorded? Open the evidence. A passing test suite is not the
  verb; an exit code is not a result; a delegate's report is not fact. Any phase that fails
  this is **downgraded to not-complete in your table** regardless of what the report says, and
  the downgrade is listed with its reason.
- **Simplifier (soft veto).** Which runs bought tracks, abstractions or tiers they did not
  need? Name the cheaper run that got the same result.
- **The self-serving report check.** A long, confident run report over a thin record is the
  most common shape of a bad run. Compare `report.bytes` and `not_recorded_count` against
  `tree.source_loc` and `phases_verification_executed`. A report with **zero** "not recorded"
  entries in a run that plainly did not run every instrument is a fabrication signal, not
  thoroughness.
- **Halt honesty.** A run that halted and said so cleanly is a *better* run than one that
  continued past a blocker on an unmarked guess. Grade the halt line for whether the stated
  reason matches where the record actually stops.

**Stage 4 — Rank, and say why.** One ranking, most complete first, with the tiebreaks stated.
Ranking rules, in order:

1. **Phases genuinely demonstrated** (post-downgrade), not phases claimed.
2. **Integrity** — a run with high-severity claimed-vs-observed findings ranks below a
   run that finished less and reported it honestly. Always.
3. **Rigor floors held** — TDD, the E7 surface list, the vetoes cleared by a non-author,
   COMMIT-01 and the P6 numeral check.
4. **Cost** — tokens and wall clock per demonstrated phase.
5. **Speed** — last, and only among runs level on everything above.

Then, separately from the ranking: **what the pack should learn.** A failure mode that shows
up in more than one run is not a harness difference, it is a **defect class in the prompt or
in the pack**, and it belongs in `docs/lessons/defect-classes.md` as a class with a control.
This is often the most valuable output of a grading pass.

**Stage 5 — Emit, by writing your ruling into the report rather than beside it.** Both output
files are **generated**, so never hand-edit them (V10 — a derived artifact is rebuilt, not
patched). Instead write your verdict as data and re-run the extractor with it:

```
docs/benchmark/comparisons/<comparison-id>.verdict.json
{
  "ranking":    [ {"run": "<name>", "why": "<the reason for this placement, and the tiebreak
                                            against the run immediately below it>"} ],
  "judgment":   { "performance": {"<run>": "<your ruling, with its denominator>"},
                  "parallelism": {"<run>": "<did it pay, against which justification>"},
                  "drift":       {"<run>": "<the verdict, quoting the pair or path>"} },
  "downgrades": [ {"run": "<name>", "phase": "P4", "missing": "<the evidence that is absent>"} ],
  "learned":    [ "<a failure mode seen in more than one run, as a class with a control>" ],
  "repairs":    { "benchmark": [ "<an improvement to the benchmark/prompt that needs judgment>" ],
                  "pack":      [ "<an improvement to the AI-Forward pack that needs judgment>" ] }
}
```

The `repairs` block is optional and is merged with the deterministic repair items the grader
derives from each run's signals; both render in the report's two Repair-items sections.

```
python tools/grade-benchmarks.py <repos...> --out docs/benchmark/comparisons \
       --verdict docs/benchmark/comparisons/<comparison-id>.verdict.json
```

The ranking, the per-axis judgment, the downgrades and the learnings then render **inside**
the interactive report and inside the canonical `.md`, from one source. A verdict file that
cannot be read is a hard stop, not a fall back to an unjudged report.

Commit the `.verdict.json` beside the `.md` and `.html` — it is the input the derived views
are rebuilt from, and without it the next regeneration silently loses your conclusion.

Then add, in the `.md`, a **Method and limits** section that the extractor cannot write for
you.

**Method and limits is not optional.** Name what this comparison cannot see: runs on different
machines, a model whose harness reports no token counts, an instrument the run never executed.
Every unmeasured thing is **"not recorded"**, never an estimate — a plausible wrong number
here corrupts the next harness decision, which is the whole reason the benchmark exists.

## Definition of done (exit gate)

- [ ] Every repo argument resolved to a distinct, existing run repo; duplicates reported, not silently merged.
- [ ] `tools/grade-benchmarks.py` was **run**, and its JSON — not only its table — was read.
- [ ] `--verify-build` was used, or the reason it could not be is recorded.
- [ ] The three `judgment` axes are ruled on per run, each with a quoted exhibit.
- [ ] Every phase claimed complete was checked for an **executed** verb; failures downgraded in the table with the missing evidence named.
- [ ] Claimed-vs-observed findings are listed per run, with severity.
- [ ] One ranking, with the tiebreak rule that decided each adjacent pair.
- [ ] Failure modes appearing in more than one run are written up as a defect class with a proposed control.
- [ ] The verdict was delivered as `<comparison-id>.verdict.json` and the extractor re-run with `--verdict`; neither generated file was hand-edited.
- [ ] The `.verdict.json`, `.md` and `.html` are all committed; the ranking and per-axis judgment are visible in both rendered views.
- [ ] Method and limits section present; nothing estimated.
- [ ] Status table emitted.

## Documentation & discoverability (last action)

The comparison carries V2 frontmatter and links to the benchmark prompt it grades against. Run
`python docs/ai-forward-pack/scripts/docs-graph.py derive`.

**Audit (last action).**
`python docs/ai-forward-pack/scripts/audit-log.py append --shortname "grade-<comparison-slug>" --session "<id>" --skill grade-benchmarks --kind skill --prompt "<verbatim>" --summary "<runs graded, ranking, downgrades, defect classes raised>" --artifact docs/benchmark/comparisons/<comparison-id>.md --goal "<goal>" --done-when "<done when>" --tier T1 --fan-out 0`

**Handoff:** → `/dream` (a failure mode seen in more than one run is a class) · →
`/session-profiler` (per-session cost detail behind the performance axis) · →
`/apply-learnings` (push a confirmed pack-level lesson back to ai-forward).
