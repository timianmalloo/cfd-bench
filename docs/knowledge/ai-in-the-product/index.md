---
id: kb-ai-in-the-product
title: "LLMs Inside an Engineering Tool"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [llm, claude-api, ai-ux, evals, structured-outputs, prompt-caching, csharp]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
  - { to: kb-design-automation, rel: refines }
  - { to: knowledge-gap-register, rel: refines }
review-by: 2026-12-06
summary: >-
  Where a language model belongs in a deterministic engineering tool and where it must not go — the
  language/numbers boundary that keeps non-determinism out of the solver path, the capability
  inventory ranked by value over risk, the eval each capability needs before it ships, and the
  measured Claude API cost and C# integration surface.
---

# LLMs inside an engineering tool

## 1. The governing rule

> **The model reads and writes *language*. The solver reads and writes *numbers*.
> Numbers flow into the model as context; they never flow out of it as results.**

Every capability below is judged against that one sentence. It exists because the pack's
**AI Systems Engineer holds a hard veto on non-determinism leaking into a deterministic path**, and
a CFD tool is about as deterministic a path as software gets. A user who cannot reproduce a number
cannot trust the tool, and a number that came from a language model is not reproducible.

**The practical form of the rule is mechanically checkable:** every numeral appearing in
model-generated text must also appear in the structured input given to that call. That check is a
unit test, not a guideline — see §4.

## 2. Where an LLM genuinely earns its place

Ranked by value ÷ risk. The first two are the user's own proposals and they are the two best ideas
on the list.

### (a) Brief → structured design intent

Natural language in — *"a racing wing for wingfoil racing, target wind 10–20 kn, span under a
metre"* — typed constraints, objectives and context out.

- **Why it fits.** This is *translation*, the task class LLMs are strongest at, and the output is a
  small typed object the user can read and correct before anything acts on it.
- **What contains the risk.** Two things. **Structured outputs** (`output_config.format` with a JSON
  schema) guarantee the shape is valid, so the failure mode is a wrong *value*, never a malformed
  object. And **the user confirms before the optimiser runs** — the model proposes, a human accepts.
- **What it must not do.** Invent a constraint the user did not state. An unstated span limit that
  appears in the extracted intent is worse than no extraction at all, because it silently narrows
  the design space. **Every extracted field carries a provenance flag: stated, inferred, or
  defaulted** — and inferred fields are visually distinct.

### (b) Explain the design against the goals

Take the brief, the constraints, the chosen candidate and its computed numbers; explain the fit and
the trade-offs.

- **Why it fits.** All the facts are supplied. The model is doing *exposition*, not computation.
- **The hard constraint.** Every number in the explanation must be one that was passed in. The
  moment the model writes "L/D is around 19" instead of reading 19.8 from the solver, it has
  fabricated engineering data with total confidence. This is the single biggest risk in the whole
  proposal and it is why the numeral check in §4 is non-negotiable.
- **Grounding.** The repo holds a sourced, confidence-labelled knowledge base. Explanations should
  cite it — the API's **citations** feature attaches `cited_text` and a document location to text
  blocks, which turns "high aspect ratio glides better" into a claim with a source behind it.
- **The genuinely valuable version** is not a summary of the numbers — the user can read numbers.
  It is *why this design and not the neighbouring one*: which constraint bound, what was given up,
  and what would change if a constraint moved.

### (c) Diagnose a failed solver run

Read `checkMesh` output, diverging residuals, a `snappyHexMesh` failure — say what went wrong and
what to change.

- **Why it fits.** Log interpretation is a classic LLM strength, and the answer is
  **self-verifying**: the suggestion either fixes the run or it does not.
- **Why it matters here specifically.** It directly serves the stated requirement — *"I don't want
  to have to worry about input files"* — and it attacks `SPIKE-03`, the load-bearing assumption that
  meshing can be automated. When automation fails, this is what stops the user being stranded.

### (d) Knowledge-base question answering

An in-app assistant grounded in `docs/knowledge/` with citations.

- **Why it fits.** We have ~25 artifacts of sourced domain knowledge with confidence labels. This is
  retrieval and synthesis over vetted text — the lowest-risk LLM application there is.
- **Cheap by construction.** The knowledge prefix is stable, so **prompt caching** applies: a 15k
  prefix costs ~10× less on a cache read than fresh, and breaks even after ~1.4 calls.

### (e) Vocabulary bridging — rider language to engineering

*"It feels sticky on take-off"* → insufficient CL at low speed. *"The tip breaches in turns"* →
tip ventilation, and here is the submergence relationship.

- **Why it matters more than it looks.** `GAP-03` in the gap register says we have not established
  who the user is, and that the proposals lean engineer. **This capability is what would let the
  tool serve a rider at all**, and it is cheap. It may be the difference between a tool for the
  person who built it and a tool for the sport.

### (f) Design report generation

A shareable summary — the brief, what was built, why, the caveats. Same machinery as (b) at longer
form, and the natural artifact to hand a shaper or a builder.

### (g) Section-selection rationale

*Why E818 rather than NACA 4412 for this case* — grounded in the measured catalog rather than
generated. We already have the numbers (E818 reaching 42.1 kn cavitation-free against 4412's
31.4 kn); the model supplies the sentence, not the figure.

## 3. Where an LLM must not go

| Never | Why |
|---|---|
| **Compute or estimate any physical quantity** | The estimator, VLM and CFD tiers exist. A model-generated number is unreproducible and indistinguishable from a real one on screen |
| **Choose the design** | The optimiser is deterministic, inspectable and verifiable at a higher tier. Replacing it with a model forfeits all three |
| **Generate geometry directly** | A wing from a language model is unvalidated and un-auditable. Geometry comes from the parametric model |
| **Judge structural safety** | We have no structural model at all (`GAP-02`). A model asked whether a foil is strong enough will answer, and the answer will be worthless and confident |
| **Silently alter a user's constraint** | The tool's trustworthiness rests on never moving what the user set |
| **Be required for core function** | The tool must be fully usable offline. AI is additive; if the network is down the wing still gets designed |

## 4. The eval each capability needs

The AI Systems Engineer's veto is on **an AI capability with no eval harness**. So each capability
ships with one or does not ship.

| Capability | Eval | Grading |
|---|---|---|
| **Brief → intent** | A corpus of briefs with hand-written expected intents, including adversarial ones (vague, contradictory, over-constrained) | Field-level: exact match on numeric constraints; semantic match on objectives. **Plus a precision check — did it invent a field?** |
| **Explain** | Design/result pairs with known correct readings | **(1) Numeral check — mechanical, every number in the output must appear in the input. Automatic fail otherwise.** (2) No unsupported claims (each assertion traces to input or a cited doc). (3) Human usefulness rating |
| **Diagnose** | A corpus of genuinely failed runs with known root causes | Did it name the actual cause? Did the suggested fix work when applied? |
| **KB Q&A** | Questions with known answers in the base, plus **questions whose answers are *not* in the base** | Correctness on the first set; **refusal-to-answer on the second**. Confident answers to unanswerable questions are the failure mode |
| **Vocabulary bridge** | Rider phrases with expert-labelled engineering meanings | Agreement with the expert label |

**The numeral check deserves emphasis.** It is a deterministic guard on a non-deterministic
component, it is about twenty lines of code, and it catches the single most damaging failure this
feature set can produce.

## 5. Cost — measured, not guessed

Claude Opus 5 at **$5 / $25 per MTok** (input/output). Cache reads at the standard 0.1× multiplier
(**Inferred** — the pricing table gives the base rates; the 0.1× cache-read and 1.25× cache-write
multipliers are the standard Anthropic ratios and were not separately verified for Opus 5).

| Capability | Fresh in | Cached in | Out | $/call | Calls per $1 |
|---|---|---|---|---|---|
| Brief → design intent | 1,500 | — | 300 | **$0.0150** | 67 |
| Explain the design | 2,000 | 15,000 | 1,200 | **$0.0475** | 21 |
| Diagnose a solver failure | 8,000 | 4,000 | 800 | **$0.0620** | 16 |
| Knowledge-base Q&A | 400 | 15,000 | 700 | **$0.0270** | 37 |
| Vocabulary bridge | 600 | 4,000 | 250 | **$0.0112** | 89 |
| Design report | 3,000 | 15,000 | 2,500 | **$0.0850** | 12 |

**A heavy 74-interaction session costs about $2.57.** A hundred such sessions is ~$257.

**Caching the knowledge prefix pays for itself after 1.4 calls** — 15k tokens cost $0.075 fresh
versus $0.0075 on a cache read, a 10× difference, against a one-time write of $0.094.

*Cost tuning is the user's decision.* A cheaper model on the bounded capabilities (vocabulary
bridge, intent extraction) is a legitimate option, but it should be measured against the eval rather
than assumed — and the default stays `claude-opus-5`.

## 6. The API key problem — state it plainly

**A key shipped inside a desktop binary is extractable.** Obfuscation does not change this; the key
is present at runtime and can be recovered. Three honest options:

| Approach | Fit |
|---|---|
| **BYOK — the user supplies their own key** | **Right for this project.** Non-commercial, single user, no distribution problem. Key lives in the OS credential store or an env var, never in the repo or the binary |
| **A proxy service** holding the key server-side | The only correct answer for distributed commercial software. Adds infrastructure, auth and a bill |
| **Key embedded in the app** | Not an option. It leaks, and the leak bills the owner |

For a tool the user runs on their own machine, **BYOK is not a compromise — it is the correct
design**, and it also makes the offline-degradation requirement natural: no key, no AI features,
everything else works.

## 7. The C# integration surface

The official SDK is `Anthropic` on NuGet (`dotnet add package Anthropic`), which suits a WPF
application directly. *(Verified from the SDK reference.)*

- **Client:** `AnthropicClient client = new();` — reads `ANTHROPIC_API_KEY` by default, or set
  `ApiKey` explicitly from the credential store.
- **Structured outputs** (the brief→intent feature): `OutputConfig.Format = new JsonOutputFormat
  { Schema = ... }`, where `Schema` is a `Dictionary<string, JsonElement>`. `Type` is auto-set to
  `"json_schema"`.
- **Prompt caching** (the knowledge prefix): `System` takes `List<TextBlockParam>` with
  `CacheControl = new CacheControlEphemeral()`. Verify hits via `response.Usage.CacheReadInputTokens`
  — if it is zero across repeated calls, something in the prefix is varying.
- **Thinking:** on Opus 5 thinking is on by default; `Thinking = new ThinkingConfigAdaptive()`.
  `Effort` nests under `OutputConfig`, not top level.
- **Streaming** for anything long-form (explain, report) so the UI shows progress rather than a
  pause.
- **Errors:** catch a most-specific-first chain from `Anthropic.Exceptions` rather than one broad
  class, so retryable (429, 5xx) and non-retryable (400, 404) are distinguishable.
- **Assistant prefill is not supported** on Opus 5 — use structured outputs to control format.

## 8. Risks specific to putting an LLM in this tool

1. **Fabricated numbers presented with total confidence.** The dominant risk. Mitigated by the
   numeral check, and by rendering model-generated text in a visually distinct way from computed
   values.
2. **Authority laundering.** A model explaining a result makes the result *feel* more validated than
   it is. An eloquent explanation of an estimator-tier number can read as an engineering
   endorsement. **Explanations must inherit and display the confidence of the tier they describe.**
3. **Prompt injection through solver logs and user files.** The diagnosis feature reads machine
   output; the import feature reads files. Neither is fully trusted input. Keep model output
   confined to *advice* and never let it trigger an action directly.
4. **Silent scope creep into computation.** The pressure to let the model "just estimate" something
   when a tier is slow will be constant. The rule in §1 exists to be enforced, not admired.
5. **Non-reproducibility of the explanation itself.** The same design may be explained differently
   on two runs. That is acceptable for prose and unacceptable for numbers — which is exactly the
   line §1 draws.

## 9. Open questions

1. **Does the numeral check have false positives that make it unusable?** Rounding ("about 20" from
   19.8), units conversion and derived quantities all produce numerals not literally in the input.
   **Needs a real implementation and a tuning pass** — the check may need to allow rounding of
   supplied values while rejecting unsupplied ones.
2. **Is Opus 5 necessary for the bounded capabilities?** Unmeasured. Build the eval first, then test.
3. **What is the right refusal behaviour for KB Q&A?** A model that says "I don't know" too often is
   useless; one that never does is dangerous. The threshold needs setting against the eval.
4. **Does citation-grounded explanation actually increase trust, or just length?** Unverified with
   users, and it interacts with `GAP-03`.

## Sources

| Source | Type | Notes |
|---|---|---|
| Anthropic Claude API reference (bundled `claude-api` skill) | primary (vendor) | Model IDs and pricing (cached 2026-06-24), structured outputs, prompt caching, thinking/effort, citations, C# SDK surface |
| `csharp/claude-api/README.md`, `tool-use.md` | primary (vendor) | `AnthropicClient`, `OutputConfig.Format` / `JsonOutputFormat`, `CacheControlEphemeral`, `ThinkingConfigAdaptive`, exception namespaces |
| `.claude/agents/ai-systems-engineer.md` | project | The hard veto on an AI capability with no eval harness, and on non-determinism in a deterministic path |
| Local computation, this session | primary | Per-capability cost table and cache breakeven |

Accessed 2026-09-06.
