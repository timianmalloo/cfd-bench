---
id: domain-experts
title: "Domain Experts — the CFD-Bench Subject-Matter Roster"
type: knowledge
status: accepted
owner: "@timianmalloo"
tags: [personas, domain-experts, roster, cfd, structures, gpu, geometry]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: depends-on }
  - { to: knowledge-gap-register, rel: depends-on }
  - { to: kb-cfd-orchestration, rel: depends-on }
  - { to: kb-cad-ux-geometry, rel: depends-on }
review-by: 2027-03-06
summary: >-
  The seven subject-matter lenses added to this repo's persona roster — what each catches that no
  general lens can, the seam that keeps them distinct from each other and from the Domain Researcher,
  their vetoes, and the candidates that were considered and rejected.
---

# Domain experts — the CFD-Bench roster

Added **2026-09-06** by `/adddomainexperts`. The roster is now **23 general lenses + 7 domain
experts = 30**.

## The domain, from the repo's own evidence

**Design and analysis of a single water-sports hydrofoil wing** — front wing or rear wing, not the
assembly — across surf, SUP/downwind, wing and windsurf disciplines, in salt and fresh water, on a
single Windows/NVIDIA machine. Established across 24 graph artifacts in `docs/knowledge/` and
`docs/proposals/`, not assumed.

**The user is an engineer who understands fluid mechanics and must be able to think in rider
requirements.** That answer (2026-09-06) shapes the roster: the experts can speak in full technical
register, and the translation burden sits with the AI vocabulary capability rather than with a
persona.

### The domain failure map — where an error is expensive, silent, or irreversible

| Failure | Why it is dangerous here |
|---|---|
| **A solver converges to a physically wrong answer** | Silent. CFD always produces a colourful field; nothing about convergence indicates physical correctness |
| **A validation comparison proves less than claimed** | Silent, and it launders confidence into every downstream number |
| **A section is ranked at the wrong Reynolds number** | Measured in Phase 0: the ranking **flips** between Re 6e5 and 1e6 |
| **A geometry carries an invisible curvature defect** | Hydrodynamically real, visually undetectable |
| **A GPU kernel returns a different number on the second run** | Destroys reproducibility, which the tool's whole trustworthiness rests on |
| **A foil is optimised thinner than it can survive** | **Irreversible and unsafe.** Phase 0 proved hydrodynamics always prefers thinner; a failure at 25 kn injures someone |
| **A units or sign convention error** | Silent factor errors — the defect class already flagged in v1 and still open (GAP-04) |

## The seven experts

| Expert | Owns | Veto | Convene when |
|---|---|---|---|
| **Computational Fluid Dynamicist** | Physical and numerical validity — turbulence model vs regime, mesh independence, CFL, validity envelopes | **Hard** (narrow) | A hydrodynamic quantity is computed, reported or relied on |
| **Experimental Fluid Dynamics Expert** | Whether a validation comparison actually proves the claim — condition matching, facility effects, uncertainty | **Hard** (narrow) | Any claim of validation, accuracy or agreement with experiment |
| **GPU & CUDA Compute Expert** | Kernel correctness, reproducibility, precision error budgets, bandwidth reality | **Hard** (narrow) | Any CUDA kernel, precision choice, or GPU performance claim |
| **Composite Structures & Hydroelasticity Expert** | Whether it survives its loads, and what shape it holds under them | **Hard** (narrow) | Any thickness decision or buildability claim |
| **OpenFOAM & SU2 Case Specialist** | Toolchain-specific case correctness — schemes, dictionaries, `checkMesh` | **Soft** | Any generated case or meshing configuration |
| **Parametric Geometry & Design-Space Expert** | Representation quality, validity by construction, continuity, derived-not-stored | **Soft** | Any change to the geometry model or design vector |
| **CAD/CAM Interop & Manufacturability Expert** | Keeping the fabrication door open; flagging unbuildable geometry | **Advisory** | A decision could foreclose future export or manufacture |

## Why each earned a seat — the Simplifier test

Each must catch a class of **domain** error no existing lens catches.

**Computational Fluid Dynamicist.** The Test Architect owns *software-test verifiability* — the code
computes what was specified. This lens owns *physical validity* — **a solver can pass every unit
test and still be physically wrong**. No general lens can make that call; it requires the governing
equations and the regime. Hard veto is proportional: the project's entire value is that its numbers
are right.

**Experimental Fluid Dynamics Expert.** Distinct from the above and the distinction matters. The CFD
lens owns the computation; this one owns **whether the comparison to reality is valid** — Reynolds
and Froude matching, blockage, facility effects, uncertainty bands, and whether validating lift
licenses a claim about drag. GAP-01 is precisely this gap, and the review that found the DTNSRDC
dataset also showed how easily a comparison can look conclusive and prove little.

**GPU & CUDA Compute Expert.** The SRE owns runtime behaviour; this lens owns whether the kernel is
**numerically right and reproducible**. Its single highest-value catch is one no other lens would
think to make: **GPU floating-point reductions are order-dependent, so the same input can produce a
different number on the next run** — which would silently undermine every downstream claim in a tool
whose credibility rests on reproducibility.

**Composite Structures & Hydroelasticity Expert.** *Not requested; recommended and confirmed.* This
is the lens `knowledge-gap-register.md` identified as the largest hole (GAP-02). Phase 0 established
that **thickness has no hydrodynamic optimum and is therefore set entirely by structure** — leaving
the tool with a variable decided by physics it cannot see. It also owns the **rigid-foil
assumption**: under load the wing deflects *and twists*, changing its own angle of attack, and at
AR 9–12 that coupling is not second-order. Hard veto is proportional because the failure mode is
physical injury.

**OpenFOAM & SU2 Case Specialist.** *Deliberately narrow, after the overlap was surfaced and the
split confirmed.* The CFD lens owns whether the physics is right; this one owns whether **this
toolchain is configured to do what that physics requires** — `fvSchemes`, `snappyHexMesh` behaviour,
dictionary semantics, `checkMesh` thresholds. Thin seam, but real: SPIKE-03 (auto-meshing) is the
load-bearing assumption of the whole orchestration story and needs exactly this knowledge. Soft veto
— it escalates physics concerns rather than owning them.

**Parametric Geometry & Design-Space Expert.** The Data & Persistence Architect owns storage and
migration; this lens owns whether the **model can express the right shapes and only valid ones**.
It carries the CST validity-by-construction argument, the curvature-comb requirement, and the
derive-don't-store rule that the market's own inconsistent aspect ratios justify.

**CAD/CAM Interop & Manufacturability Expert.** *Scope-adapted.* Fabrication is **out of scope by
decision (2026-09-06)**, but the architecture must not foreclose it. So this lens's convene-when
flipped from *"when we export"* to **"when a decision could make future fabrication hard"** — it
guards the internal representation's ability to emit an exact surface, keeps the export boundary an
interface, and flags geometry that is **unbuildable as drawn** (our measured sections carry
trailing-edge gaps of 0–0.08 mm at an 80 mm chord). Advisory, because it cannot block work on a
capability that is out of scope.

## Seams — how they stay distinct

```
Domain Researcher  ── research METHOD: establishes an unfamiliar SDK's contract by reading and running it
                      (establishes the OpenFOAM API; does not judge the physics)

CFD Dynamicist     ── is the COMPUTATION right?        │
EFD Expert         ── does the COMPARISON prove it?    │ all three can pass
Test Architect     ── does the CODE do what was specified? │ while the tool is still wrong

GPU Expert         ── does the KERNEL compute it reproducibly?
OpenFOAM/SU2       ── is THIS TOOLCHAIN configured to do it?

Parametric Geometry ── can the MODEL express it, and only validly?
CAD/CAM Interop     ── can it LEAVE the tool and be made?
Composite Structures ── will it SURVIVE, and what shape does it hold?
```

## Backing Claude skills — checked, and there are none

Stage 3 of `/adddomainexperts` requires discovering existing Claude domain skills and **wiring them
in rather than reinventing**. Searched 2026-09-06: **no CFD, structures, CAD or GPU domain skill
pack exists in this environment.** The `finance:*`-style packs the skill's worked examples reference
have no engineering equivalent here.

So every expert is recorded as *"None — capability is hand-built here"*. That is a finding, not an
omission: where a domain contract must be established rather than judged, these experts hand to the
**Domain Researcher** for a spike instead of asserting.

## Candidates considered and rejected

| Candidate | Rejected because |
|---|---|
| **Marine Hydrodynamics / Naval Architect** as a separate seat | Free-surface, cavitation and ventilation physics is genuinely distinct knowledge — but scoping the **Computational Fluid Dynamicist** to include it (with ITTC and the cavitation-bucket construction in its standards) is the smaller change. Revisit if free-surface work grows past one lens |
| **Water-Sports Rider Experience** lens | The user is an engineer who needs to *think* in rider terms — that is a **capability** (the AI vocabulary bridge, and the UX Researcher/IA lens already on the roster), not a subject-matter judgment seat. Adding a persona for it would be roster sprawl |
| **Numerical Methods** as separate from the CFD lens | The CFD Dynamicist's interrogation already carries mesh independence, CFL and discretisation. A separate seat would split one judgment across two cards |
| **Materials Science** separate from Composite Structures | Layup, fibre orientation and failure criteria are inside the structures lens's standards. A separate materials seat has nothing left to own |
| **Optimisation / OR** lens | The design-automation knowledge base already fixes the method (NSGA-II/MOPSO over the estimator, feasibility-first). The real risk there is *model error amplification*, which the **CFD Dynamicist** and **EFD Expert** already own via COMMIT-01 |

## How they join the workflows

These seven join `/specify`, `/define-architecture`, `/design-slice`, `/implement` and
`/investigate` **by their own convene-when predicates**, in peer and adversary modes — the casting
sheet in `collaborative-personas.md` §5 already provides for this. In practice, for the phases in
`docs/proposals/build-phasing-plan.html`:

| Phase | Experts convened |
|---|---|
| P0 conventions & spine | Parametric Geometry (schema, grain), CAD/CAM (representation foreclosure) |
| P1 estimator, validated | **CFD Dynamicist**, **EFD Expert** (the validation case) |
| P2 read a wing | CFD Dynamicist (what the charts may claim) |
| P3 draw a wing | **Parametric Geometry**, CAD/CAM |
| P4 trust the numbers | **CFD Dynamicist**, **EFD Expert**, **Composite Structures** |
| De-risking slice (~wk 15) | **CFD Dynamicist**, **OpenFOAM/SU2**, EFD Expert |
| P5 state a goal | CFD Dynamicist (envelope enforcement), Composite Structures (thickness is not a free variable) |
| P6 build the wing *(out of scope)* | CAD/CAM — advisory only |
| P7 explain it | — (AI Systems Engineer, already on the roster) |
| P8 prove it | **CFD Dynamicist**, **GPU Expert**, **OpenFOAM/SU2**, **EFD Expert** |

## Files

| Expert | Claude Code | Copilot |
|---|---|---|
| Computational Fluid Dynamicist | `.claude/agents/computational-fluid-dynamicist.md` | `.github/agents/computational-fluid-dynamicist.agent.md` |
| Experimental Fluid Dynamics Expert | `.claude/agents/experimental-fluid-dynamics-expert.md` | `.github/agents/experimental-fluid-dynamics-expert.agent.md` |
| GPU & CUDA Compute Expert | `.claude/agents/gpu-compute-expert.md` | `.github/agents/gpu-compute-expert.agent.md` |
| Composite Structures & Hydroelasticity Expert | `.claude/agents/composite-structures-expert.md` | `.github/agents/composite-structures-expert.agent.md` |
| OpenFOAM & SU2 Case Specialist | `.claude/agents/openfoam-su2-specialist.md` | `.github/agents/openfoam-su2-specialist.agent.md` |
| Parametric Geometry & Design-Space Expert | `.claude/agents/parametric-geometry-expert.md` | `.github/agents/parametric-geometry-expert.agent.md` |
| CAD/CAM Interop & Manufacturability Expert | `.claude/agents/cad-cam-interop-expert.md` | `.github/agents/cad-cam-interop-expert.agent.md` |

## Domain anti-patterns owned (extends `persona-audit.md` §8.8)

| Anti-pattern | Owner |
|---|---|
| **Converged-But-Physically-Wrong** | Computational Fluid Dynamicist |
| **Validity-Envelope-Exceeded** | Computational Fluid Dynamicist |
| **Validation-By-Resemblance** | Experimental Fluid Dynamics Expert |
| **Uncertainty-Free-Claim** | Experimental Fluid Dynamics Expert |
| **Non-Deterministic-Result** | GPU & CUDA Compute Expert |
| **Unjustified-Precision** | GPU & CUDA Compute Expert |
| **Roofline-Free-Claim** | GPU & CUDA Compute Expert |
| **Aero-Optimal-Structurally-Impossible** | Composite Structures Expert |
| **Rigid-Foil-Assumption** | Composite Structures Expert |
| **Solved-On-A-Bad-Mesh** | OpenFOAM & SU2 Case Specialist |
| **Scheme-Physics-Mismatch** | OpenFOAM & SU2 Case Specialist |
| **Invisible-Curvature-Defect** | Parametric Geometry Expert |
| **Two-Definitions-Of-One-Quantity** | Parametric Geometry Expert |
| **Two-Way-Parametric-Sync** | Parametric Geometry Expert |
| **Mesh-Only-Lock-In** | CAD/CAM Interop Expert |
| **Unbuildable-As-Drawn** | CAD/CAM Interop Expert |

## Gate record

- **Domain** derived from repo evidence (24 graph artifacts), not assumed.
- **Simplifier gate** run on all seven; five candidates rejected with reasons recorded above.
- **Overlap surfaced, not hidden:** the OpenFOAM/SU2 seat's overlap with the CFD lens was put to the
  maintainer, who confirmed a separate seat with narrow scope.
- **One expert recommended rather than requested** (Composite Structures) and confirmed before writing.
- **Maintainer confirmed the roster** before any file was written.
- **Backing skills searched**; none exist in this environment; recorded as such.
