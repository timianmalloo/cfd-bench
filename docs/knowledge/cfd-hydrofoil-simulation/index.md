---
id: kb-cfd-hydrofoil-simulation
title: "Small-Footprint CFD for Water-Sports Hydrofoils"
type: knowledge
status: draft
owner: "@timianmalloo"
phase: pre-specification
tags: [cfd, hydrofoil, lbm, gpu, cuda, marine-hydrodynamics, water-sports]
links:
  - { to: kb-cfd-state-of-the-art, rel: refines }
  - { to: kb-cfd-comparables, rel: refines }
  - { to: kb-cfd-references, rel: refines }
  - { to: kb-cfd-data-and-constants, rel: refines }
  - { to: kb-cfd-foil-sections, rel: refines }
  - { to: kb-cfd-estimation-methods, rel: refines }
  - { to: kb-cfd-watersports-practice, rel: refines }
  - { to: kb-cfd-parametric-geometry, rel: refines }
  - { to: kb-cfd-open-questions, rel: refines }
  - { to: kb-cfd-sources, rel: refines }
  - { to: glossary-cfd-hydrofoil, rel: uses-term }
review-by: 2026-12-04
summary: >-
  Evidence base for a small, local design and simulation tool for water-sports hydrofoils — surf,
  SUP/downwind, wing and windsurf foiling — on a single Windows/NVIDIA machine. Establishes the
  closed-form estimation chain that answers most design questions in microseconds, the section and
  geometry catalogs, a four-concept parametric grammar, and the narrow band where simulation is
  actually required.
---

# Small-footprint CFD for water-sports hydrofoils — domain knowledge

**Version 2** · compiled 2026-09-05 · Lead: Domain Researcher

**Domain & problem.** Predicting hydrodynamic forces, efficiency (L/D) and cavitation margin for
water-sports hydrofoils — surf, SUP/downwind, wing and windsurf/race foiling — in salt and fresh
water, on a single Windows/NVIDIA machine, without deploying a general-purpose CFD package.

> ### Scope change from v1 — recorded, not silent
> **v1 covered hydrofoils *and* surfboards. v2 drops the surfboard/planing scenario entirely** at
> the user's direction. Retired with it: the Savitsky empirical planing method, RANS+VOF with 6-DOF
> trim and sinkage, and the whole free-surface-craft cost rung. Those passages remain in
> `state-of-the-art.md` and `comparables.md` marked **RETIRED** rather than deleted, because the
> reasoning that led to the two-tier architecture depended on them and a future reader needs to see
> why the shape survived the scope cut.
>
> **This cut has a consequence that must not be glossed:** planing was one of the three gaps that
> justified building anything at all. The case-against was re-tested on the narrower scope — see
> `open-questions.md`. It still holds, but on **two** gaps rather than three, and the surviving
> justification is narrower and more dependent on the free-surface argument.

## Headline findings

1. **Most of the design question is answerable in closed form, in microseconds.** A chain of
   published formulae — XFOIL section polars, Helmbold lift slope, lifting-line induced drag, ITTC
   1957 skin friction with a Hoerner form factor, and the incipient-cavitation critical speed —
   produces L/D, Cl/Cd, required angle of attack and cavitation margin with no simulation.
   **It was executed against real water-sports geometry and the numbers are physically right.**
   — *(Verified for each formula; the assembled chain is Inferred)*
2. **Cavitation is not a water-sports problem except at race speed.** The cavitation number stays
   above 3 until 22 kn and only reaches 1.0 at 28 kn. Below roughly 25 kn it does not bind, so it is
   a **check**, not a design driver. — *(Inferred, from Verified formulae and constants)*
3. **The induced/friction crossover is the whole story of discipline differences.** Induced drag is
   **77%** of total for a surf foil at 7 kn and **3%** for a race foil at 28 kn. That is why aspect
   ratio governs take-off and section drag governs top speed. — *(Inferred, computed)*
4. **Take-off demands more of the section than the design point does.** A surf foil needs
   `CL ≈ 0.78` at 7 kn, above the `0–0.6` band the International Hydrofoil Society quotes as typical.
   This explains high-camber low-speed sections directly. — *(Verified band; Inferred comparison)*
5. **A complete foil assembly needs exactly four concepts** — assembly, surface, station, loft rule.
   A strut is a surface with a vertical span axis; decalage is a difference between station
   incidences. No special cases. — *(Inferred, corroborated by OpenVSP's own structure)*
6. **CST, PARSEC, NACA 4-digit and Bézier are the same object.** All are exactly equivalent to
   Bézier curves, so the parameterisation question is a choice of clothing, not of system. CST's
   class/shape split makes invalid airfoils unrepresentable. — *(Verified)*
7. **Published aspect ratios are not comparable across manufacturers** — calculation conventions
   differ. The tool must compute AR from its own geometry under a stated definition. — *(Verified)*
8. **Span is nearly constant across the whole domain** (95–107 cm) while area varies 2.5× and aspect
   ratio 3×. Area and AR are the real design variables; span is a consequence.
   — *(Inferred, computed)*
9. **The practitioner section ranking is explicit and citable:** NACA **66-series ahead of
   16-series** for subcavitating hydrofoils, on separation grounds — the 16-series' convex pressure
   recovery invites trailing-edge separation, and **separation is the trigger condition for
   ventilation**. — *(Verified — IHS/Tom Speer)*
10. **Salt vs fresh remains a two-parameter change, not a physics change** (+2.69% density, +4.44%
    kinematic viscosity at 15 °C). — *(Verified — ITTC 7.5-02-01-03)*
11. **The GPU is still not the constraint.** A 43 M-cell foil box runs at an estimated ~220 steps/s
    on this laptop. — *(Inferred — bandwidth-scaled, never measured)*

## Confidence summary

- **Verified: 24** · **Inferred: 11** · **Flagged: 9**
- **Load-bearing Flagged claims:**
  - *Thickness-ratio guidance (10–12%)* — the only quantitative source is a retailer blog whose
    adjacent tables were demonstrably garbled. **This is the largest evidence gap in the base** and
    it is load-bearing for a design tool.
  - *ILGPU Blackwell/sm_120 support* — v1.5.3 (July 2024) predates Blackwell.
  - *LBM accuracy at Re > 10⁶* — published validation clusters below our envelope.
  - *The ~9,570 MLUPs/s throughput estimate* — scaled from a desktop benchmark, never measured here.
  - *Stabiliser sizing at 20–30% of front wing* — single secondary source.
- **One source was found internally inconsistent and corrected:** the IHS gives
  `V_crit = 14/sqrt(sigma_i)` and separately advises `pv = 17000 Pa`. Deriving the constant shows it
  requires `pv ≈ 1671 Pa` — the ITTC value. The formula is right; the quoted vapour pressure is not
  a physical property. Details in `estimation-methods.md`.

## Design implications

- **The estimator is the product's inner loop, not a preliminary step.** It answers most of what a
  foil designer asks, fast enough for a dragged slider. Simulation exists for the narrow band it
  cannot reach: free-surface proximity, separation, ventilation onset, and 3D stall.
- **Build the geometry model as two layers** — a small generative design vector that *emits*
  explicit stations, with generation strictly one-way. Everything downstream reads stations only.
- **Derive area, aspect ratio, span and chord from stations. Never store them.** The market's own
  inconsistency is the argument.
- **Model salt vs fresh as a two-field fluid property record** from the ITTC tables.
- **Enforce the validity envelope in the tool, not the documentation.** Linear methods return
  confident numbers at 30° angle of attack and they are meaningless. The surf-foil take-off case at
  α_eff = 10.5° is already near the edge.
- **Section polars must record `Ncrit` and `Cp_min`.** Without `Ncrit` a polar is not reproducible;
  without `Cp_min` there is no cavitation check.
- **Quote wing-only L/D as wing-only.** The strut is a large fraction of real drag; the estimate
  overstates whole-craft L/D and must say so where it is displayed.

## How to use this base

Personas and the design skills cite these files as evidence. Next step is `/adddomainexperts` (a
marine-hydrodynamics lens and a GPU-computing lens), then `/specify`. Refresh the ILGPU and CUDA
facts first — they are the most dated and fastest-moving claims here.
