---
id: kb-cfd-hydrofoil-simulation
title: "Small-Footprint CFD for Hydrofoils and Surfboards"
type: knowledge
status: draft
owner: "@timianmalloo"
phase: pre-specification
tags: [cfd, hydrofoil, surfboard, lbm, gpu, cuda, marine-hydrodynamics]
links:
  - { to: kb-cfd-state-of-the-art, rel: refines }
  - { to: kb-cfd-comparables, rel: refines }
  - { to: kb-cfd-references, rel: refines }
  - { to: kb-cfd-data-and-constants, rel: refines }
  - { to: kb-cfd-open-questions, rel: refines }
  - { to: kb-cfd-sources, rel: refines }
  - { to: glossary-cfd-hydrofoil, rel: uses-term }
review-by: 2026-12-04
summary: >-
  Evidence base for building a small, local CFD tool for hydrofoils and surfboards in salt and
  fresh water on a single Windows/NVIDIA machine. Establishes that salt vs fresh is a parameter
  change rather than a physics change, that the foiling Reynolds envelope is 5.5e5-1.6e6, that
  this laptop's GPU is not the binding constraint, and that hydrofoils and surfboards are two
  distinct physics problems requiring two different solver tiers.
---

# Small-footprint CFD for hydrofoils and surfboards — domain knowledge

**Domain & problem.** Predicting hydrodynamic forces (lift, drag, moment) and running attitude for
hydrofoils and surfboards operating in salt and fresh water, on a single Windows/NVIDIA machine,
without deploying a general-purpose CFD package such as OpenFOAM or SU2.

**Canonical framing.** The field does *not* treat this as one problem. Marine hydrodynamics splits
it in two, and the split is the single most important structural fact in this base:

- A **fully submerged lifting foil** is an attached-flow, high-Reynolds problem. The canonical
  cheap method is potential flow (lifting line / vortex lattice / panel) with a viscous correction
  from 2D sectional data. This is what XFLR5 and Typhoon do.
- A **planing surfboard** is a free-surface, partially-wetted, dynamically-trimming problem. Potential
  flow methods do not apply. The canonical cheap method is the **Savitsky (1964) empirical planing
  correlation**; the canonical expensive method is RANS + VOF with 6-DOF motion.

The user's framing ("one simpler, smaller solution") is therefore *idiosyncratic in scope but sound
in intent*: one **application** is reasonable, one **solver** is not. Divergence noted explicitly.

**Compiled:** 2026-09-05 · **Lead:** Domain Researcher · **Status:** fresh

## Headline findings

1. **Salt vs fresh water is a parameter change, not a physics change.** At 15 degC, standard seawater
   (S_A = 35.16504 g/kg) is **+2.69% denser** and **+4.44% more viscous kinematically** than fresh
   water. Both fluids are Newtonian and incompressible in this regime. One code path, two constants.
   — *(Verified, ITTC 7.5-02-01-03 Rev 02)*
2. **The foiling envelope is Re 5.5e5 to 1.6e6** (chord-based, seawater at 15 degC). This is the
   awkward band: too high to ignore turbulence, high enough that wall-resolved simulation is costly.
   — *(Verified for the property values; Inferred for the speed/chord envelope, from community
   sources rather than a standard)*
3. **This laptop's GPU is not the binding constraint.** A hydrofoil box at 60 cells/chord is only
   ~43 M cells; the estimated throughput is ~220 steps/s. The RTX 5090 Laptop GPU can hold ~396 M
   cells at FP32/FP16 LBM density. The constraint is *physical fidelity and scope*, not hardware.
   — *(Inferred — bandwidth-scaled from a published desktop benchmark; see the caveat below)*
4. **Strong prior art already exists** and must be beaten, not ignored: XFLR5, Typhoon (Ghent
   University), FoilBoard, and FluidX3D. Two of these are free, open source, and directly aimed at
   hydrofoils. — *(Verified)*
5. **FluidX3D is the performance ceiling to measure against, and it has three specific
   disqualifiers** for this project: it is **OpenCL not CUDA**, it has **no adaptive mesh
   refinement** (uniform cell size everywhere), and it is **free for non-commercial use only**.
   — *(Verified)*
6. **The pure-.NET GPU path carries real risk.** ILGPU's most recent release is **v1.5.3 (July
   2024)**, which predates Blackwell. sm_120 support is unconfirmed. — *(Flagged — load-bearing;
   see open-questions.md)*
7. **CUDA Toolkit 12.8 is the hard floor** for native sm_120 codegen. This machine's driver
   (591.91) advertises CUDA 13.1, so the driver side is satisfied; the toolkit is not installed.
   — *(Verified)*

## Confidence summary

- **Verified: 12** · **Inferred: 5** · **Flagged: 3**
- The **Flagged claims that are load-bearing**:
  - *ILGPU Blackwell/sm_120 support* — decides whether a pure-.NET GPU path is viable at all.
  - *LBM accuracy at Re > 1e6 for lift/drag on a foil* — most published LBM airfoil validation sits
    **below** 1e6, which is beneath our operating envelope.
  - *The ~9,570 MLUPs/s laptop throughput estimate* — bandwidth-scaled from the desktop RTX 5090
    figure, never measured on this machine. It must be measured before any plan depends on it.

## Design implications

- **Build two solver tiers, not one solver.** A fast potential-flow tier answers the hydrofoil
  design question in milliseconds and is what the user will actually use daily. A GPU LBM tier
  answers the questions the fast tier cannot (free surface, separation, planing) and is the
  validation reference. Attempting one solver for both is the primary design failure mode here.
- **Model salt vs fresh as a two-field fluid property record** (`density`, `kinematic_viscosity`),
  sourced from the ITTC tables, never as a solver branch or a code path.
- **Declare the grain early:** one row is exactly one *(geometry, speed, angle of attack, fluid,
  depth)* evaluation. Forces are derived, never stored twice.
- **The toolkit floor is CUDA 12.8+**; anything that compiles kernels must target `sm_120` or ship
  PTX for JIT. Verify before committing to a GPU binding.
- **Borrow the framing from XFLR5/Typhoon, not the code.** Their scope decisions are validated by
  a real user community; their known weakness (linear methods, no stall, no free surface) is
  precisely the gap a GPU tier would fill.
- **Do not build a general CFD package.** The Simplifier's position is recorded in
  open-questions.md and it is strong: if the answer is "a better XFLR5", that is a wrapper, not a
  solver.

## How to use this base

Personas and the design skills cite these files as evidence. The next step is `/adddomainexperts`
(a marine-hydrodynamics and a GPU-computing lens), then `/specify`. Refresh when the domain moves —
particularly the ILGPU and CUDA facts, which are dated and fast-moving.
