---
id: kb-design-automation
title: "Goal-Driven Design, Constraints and Interactive Optimisation"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [optimization, constraints, pareto, surrogate, design-space, interaction]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
  - { to: kb-cfd-estimation-methods, rel: depends-on }
review-by: 2026-12-05
summary: >-
  Evidence for turning a stated design goal and a set of constraints into a proposed wing — the
  distinction between constraints and objectives, interactive multi-objective optimisation with a
  low-fidelity solver in the loop, Pareto-front interaction patterns, and why the estimation chain
  is what makes any of it feasible.
---

# Goal-driven design, constraints and interactive optimisation

**The requirement:** state a goal — *"a racing wing for wingfoil racing, target wind 10–20 kn"* —
plus constraints — *"span no more than one metre"* — then move sliders for rider weight, speed
range, water type, take-off and stall speed, and converge on a proposed shape including section and
geometry.

## 1. The distinction that makes this tractable

**Constraints and objectives are different things and must not share a widget.**

- A **constraint** partitions the design space into feasible and infeasible. *Span ≤ 1 m* is a
  constraint. Violating it makes a design *invalid*, not *worse*.
- An **objective** orders the feasible designs. *Maximise L/D at cruise* is an objective.
- A **requirement** is an objective with a threshold — *take-off by 8 kn* — which behaves as a
  constraint until met and an objective afterwards.

Conflating them is the classic failure: a solver that treats span as an objective will happily
propose a 1.4 m wing that is 3% more efficient and useless.

**Consequence for the UI:** constraint sliders should show **how much feasible space remains**, and
objective sliders should show **what it costs to move**. They are different affordances.

## 2. The key precedent — interactive MOPSO over a low-fidelity solver

An interactive optimisation framework combining **a low-fidelity flow solver (Athena Vortex
Lattice)** with **interactive Multi-Objective Particle Swarm Optimisation** was demonstrated for
aerodynamic shape design, where *the decision maker periodically supplies preference information
during optimisation iterations to direct the search toward the region of interest and accelerate
it*. *(Verified — Aegis UAV study)*

**This is almost exactly the proposed architecture, and it validates two choices at once:**

1. **Low-fidelity solver in the loop.** AVL is a vortex-lattice code — the same tier as this
   project's Option 2. The optimisation is only tractable *because* evaluation is milliseconds. Our
   estimator at ~10 µs is faster still.
2. **Human preference injected during the run**, not specified up front. The designer does not know
   their utility function in advance; they recognise a good design when they see one. That is the
   argument against "enter your weights and press go".

## 3. Pareto fronts and how people actually interact with them

**PAVED** is an interactive parallel-coordinates visualisation for exploring multi-criteria
alternatives in engineering design, handling *about a dozen design parameters and up to ten
criteria*, and supporting **both formal constraints and informal preferences**. *(Verified)*

Two interaction patterns are directly reusable:

- **Brushing** — dragging over an axis range to select and highlight a subset. The standard gesture
  for filtering a design space.
- **The preference brush** — *a range brush locked at the high-quality end of an axis, so it always
  includes the best solutions while significantly reducing interaction complexity*. *(Verified)*
  This is a genuinely clever affordance: the user expresses "better is better on this axis" without
  having to pick a threshold.

**MIT Digital Structures' Design Space Exploration** (Grasshopper) samples a parametric space *made
from sliders*, iterates automatically capturing images and numeric properties, reconstructs previous
designs, and finds Pareto fronts. *(Verified)* The "reconstruct a previous design" capability is
worth stealing — **design exploration is non-linear and users need to go back.**

**ARCADE** demonstrates real-time topology optimisation where *pinching and dragging sliders adjusts
optimisation settings and the design re-renders in real time with objective values shown alongside*.
*(Verified)* Confirms that live slider-to-result is achievable when evaluation is cheap.

## 4. Why our estimation chain is the enabling asset

The estimator (`kb-cfd-estimation-methods`) evaluates a candidate in **~10 µs**. That number decides
what interaction is possible:

| Evaluation cost | Candidates per 100 ms frame | What the UI can do |
|---|---|---|
| ~10 µs (estimator) | ~10,000 | **Optimise while the slider moves.** Show the Pareto front updating live |
| ~10–100 ms (VLM) | 1–10 | Re-evaluate the current design on release; optimise in a background job |
| minutes (OpenFOAM) | — | Verify a chosen design. Never in a loop |

**This is the strongest argument for the layered architecture.** Goal-driven design is only
interactive because the cheapest tier exists. A tool built directly on CFD cannot offer this
experience at all.

## 5. Search strategy

The design vector is small — the generative layer is ~6–8 numbers per surface plus CST section
coefficients (`kb-cfd-parametric-geometry`). For that dimensionality:

- **Multi-objective evolutionary / particle swarm** (NSGA-II, MOPSO) is the established choice and
  is what the Aegis study used. Population-based, no gradients, handles constraints by
  feasibility-first ranking.
- **Bayesian optimisation** suits expensive evaluations, which is the *wrong* regime for the
  estimator tier but the right one for a VLM or CFD tier. A **human-in-the-loop Bayesian framework
  for constraint-aware development** exists in the literature. *(Verified)*
- **Surrogate models** mitigate cost when high-fidelity simulations drive objectives. *(Verified)*
  Not needed at the estimator tier — the estimator *is* the cheap model. A surrogate becomes
  relevant only over CFD output.

**Recommendation:** NSGA-II or MOPSO over the estimator, with feasibility-first constraint handling.
Not because it is sophisticated but because at 10 µs per evaluation, a population of 200 over 100
generations is 20,000 evaluations — **0.2 seconds**. The search is free; the interaction design is
the hard part.

## 6. Inverse design — the frontier, and why to avoid it for now

**3DID** navigates the 3D design space by coupling a continuous latent representation with
physics-aware optimisation, explicitly to avoid simplified parameterisations. *(Verified)* Related
work covers optimisation and generation in aerodynamics inverse design.

**This is genuinely the frontier and genuinely not ready for this project.** It requires a trained
generative model over a corpus that does not exist for hydrofoils, and it trades the interpretable
parametric model — which the user also wants to hand-edit in CAD — for a latent vector. **Record it
as a direction, not a plan.**

## 7. Open questions

1. **Is the estimator accurate enough to optimise against?** *(Flagged, load-bearing.)* Optimisation
   amplifies model error: it will find the corner of the design space where the model is most
   wrong. **Mitigation:** verify optima at the VLM tier, and treat estimator-only optima as
   *candidates*, never answers.
2. **How should infeasible regions be shown?** Sliders that silently clamp are confusing; sliders
   that allow infeasible values need a visible feasibility indicator. No source found settles this.
3. **What is the objective set for a foil?** L/D at cruise, take-off speed, stall margin, cavitation
   margin, structural depth — these are not independent and some are constraints in disguise.
   Requires the user's own priorities.
4. **Does a Pareto front over 5+ objectives help or overwhelm?** PAVED handles up to ten criteria,
   but "handles" is not "is useful". Unverified for this audience.

## Sources

| Source | Type | URL |
|---|---|---|
| Interactive Design Approach for Aerodynamic Shape Optimisation of the Aegis UAV (AVL + MOPSO) | primary (peer-reviewed) | https://doi.org/10.3390/aerospace6040042 |
| PAVED: Pareto Front Visualization for Engineering Design | primary (peer-reviewed) | https://onlinelibrary.wiley.com/doi/10.1111/cgf.13990 |
| Interactive Optimization With Parallel Coordinates | primary (peer-reviewed) | https://www.frontiersin.org/journals/ict/articles/10.3389/fict.2018.00032/full |
| Design Space Exploration (MIT Digital Structures) | primary | https://www.food4rhino.com/en/app/design-space-exploration |
| ARCADE: real-time immersed topology optimization | primary (arXiv) | https://arxiv.org/pdf/2501.13564 |
| 3DID: Direct 3D Inverse Design for Aerodynamics | primary (arXiv) | https://arxiv.org/html/2512.08987 |
| Human-in-the-Loop Bayesian Optimization, constraint-aware | primary (arXiv) | https://arxiv.org/pdf/2606.19230 |

All accessed 2026-09-06.
