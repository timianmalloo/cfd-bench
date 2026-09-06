---
id: glossary-cfd-hydrofoil
title: "Glossary — Hydrofoil and CFD Ubiquitous Language"
type: glossary
status: draft
owner: "@timianmalloo"
tags: [glossary, ubiquitous-language, cfd, hydrofoil]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
review-by: 2026-12-04
summary: >-
  The domain's ubiquitous language for hydrofoil and planing-craft simulation — the exact terms to
  use in code, specs and UI, each with its near-miss disambiguation so the vocabulary resolves
  identically across artifacts and sessions.
---

# Glossary — ubiquitous language

Use these exact terms in code, specs and UI. The "not to be confused with" line is the point of
each entry — most defects in this domain are vocabulary collisions.

## Fluid & flow

- **Chord** — the straight-line distance from a foil section's leading edge to its trailing edge.
  *Not* the span, and *not* the arc length of the surface.
- **Span** — tip-to-tip width of the lifting surface. **Aspect ratio** = span^2 / planform area.
- **Angle of attack (alpha)** — angle between the chord line and the oncoming flow. *Not* the same
  as **trim**, which is the craft's attitude relative to the water surface. A foil has both.
- **Reynolds number (Re)** — `V*c/nu`. Inertial over viscous forces. Chord-based here unless
  explicitly stated otherwise.
- **Froude number (Fn)** — `V/sqrt(g*L)`. Inertial over gravitational forces. **The free-surface
  governing parameter.** Depth-based (`Fn_h`) for submerged-foil surface interaction.
- **Cavitation number (sigma)** — `(p - p_v)/(0.5*rho*V^2)`. Onset of vapour cavities.
- **Kinematic viscosity (nu)** — `mu/rho`, m^2/s. *Not* dynamic viscosity (mu, Pa*s). Confusing the
  two is a factor-of-1000 error class; always carry units in the type.
- **Absolute salinity (S_A)** — g/kg. Standard seawater is **35.16504 g/kg** under TEOS-10. *Not*
  "practical salinity" (PSU), which is a different, dimensionless scale.

## Foil-specific regimes

- **Submergence depth** — distance from the free surface to the foil. Lift falls as this decreases.
- **Ventilation** — **air drawn from the free surface into a low-pressure region on the foil**,
  collapsing lift. Requires air ingress into separated flow at sub-atmospheric pressure from a
  continuously available air source. *Not* cavitation.
- **Cavitation** — **vapour** cavities formed when local pressure drops below vapour pressure. The
  fluid boils; no external air source involved. *Not* ventilation.
- **Ventilation washout** — the re-establishment of wetted flow, driven by upstream motion of the
  re-entrant jet. Ventilation onset and washout occur at different conditions — the regime has
  **hysteresis**, so it cannot be modelled as a single-valued function of angle and speed.
- **Flow regimes (surface-piercing foils)** — **fully wetted (FW)**, **partially ventilated (PV)**,
  **fully ventilated (FV)**. Each has its own stability region in parameter space.
- **Surface-piercing** — the foil crosses the water surface. *Not* the same as **shallowly
  submerged**, where it stays under the surface but interacts with it.

## Planing

- **Planing** — the regime where a hull is supported chiefly by **dynamic** pressure rather than
  buoyancy. A surfboard at speed is planing; the same board at rest is floating.
- **Deadrise angle** — the transverse V-angle of the hull bottom. A primary Savitsky input.
- **Trim** — running attitude (bow-up angle) at speed. A *solved output*, not an input.
- **Sinkage** — vertical displacement of the craft from its static floating position at speed. Also
  a solved output. **Trim and sinkage together are the equilibrium** a planing solver must find.
- **Porpoising** — coupled pitch-heave instability of a planing craft. Savitsky's correlations
  include stability limits for it.
- **Wetted area** — the instantaneously wetted portion of the hull. Varies with speed and trim,
  which is what makes planing a coupled problem rather than a lookup.

## Numerical methods

- **Potential flow** — inviscid, irrotational flow model. Basis of panel, VLM and lifting-line
  methods. Cannot represent stall.
- **Panel method** — surface-discretised potential flow; singularity elements on the body surface.
- **Vortex lattice method (VLM)** — lifting surfaces discretised into a lattice of vortex rings.
  Meshes surfaces only, so it is orders of magnitude cheaper than volume methods.
- **Lifting line** — the simplest 3D model; a single bound vortex line with trailing vorticity.
- **RANS** — Reynolds-averaged Navier-Stokes; turbulence is modelled, not resolved.
- **LES** — large-eddy simulation; large scales resolved, small scales modelled (e.g.
  Smagorinsky-Lilly).
- **LBM (lattice Boltzmann method)** — evolves particle distribution functions on a uniform lattice
  via stream-and-collide. Local and explicit, hence GPU-friendly.
- **MLUPs** — **mega lattice updates per second**; the LBM throughput unit. `cells * steps/s / 1e6`.
- **VOF (volume of fluid)** — interface capture by tracking a phase-fraction field.
- **PLIC** — piecewise-linear interface calculation; a sharper VOF interface reconstruction.
- **Level set** — interface tracking via the zero contour of a signed distance function. SU2's
  free-surface approach. An alternative to VOF, not a synonym.
- **Bounce-back** — the standard LBM no-slip wall condition. **Its inaccuracy on coarse grids at
  high Re is the method's principal weakness for foil drag.**
- **AMR (adaptive mesh refinement)** — locally varying cell size. **Absent from FluidX3D**, which is
  the main reason a uniform-grid budget governs the estimates in this base.
- **Savitsky method** — the 1964 empirical planing correlation set. Algebraic, prismatic hulls,
  calm water, steady state.
- **Surrogate model** — a learned approximation of a solver's input-output map. Fast online, but
  bounded by its training distribution.
