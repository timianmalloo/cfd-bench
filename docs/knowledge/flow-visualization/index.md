---
id: kb-flow-visualization
title: "Analysis Charts and Flow Visualisation for Foil Design"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [visualization, charts, cp, polars, streamlines, lic, video, scottplot]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
  - { to: kb-cfd-estimation-methods, rel: depends-on }
review-by: 2026-12-05
summary: >-
  The chart set that actually diagnoses a foil, the quasi-3D coupling that makes a 2D section view
  at a spanwise station physically meaningful, streamline and LIC techniques for 2D and 3D flow,
  and the .NET libraries for plotting and video export — including the gap where VTK has no .NET
  binding.
---

# Analysis charts and flow visualisation

## 1. The chart set

Standard CFD post-processing for airfoils centres on a small, well-established set. *(Verified)*

### Tier 1 — the ones that diagnose

| Chart | Axes | What it tells you |
|---|---|---|
| **Cp distribution** | Cp vs x/c, **y-axis inverted** | The single most informative plot. Suction peak height (cavitation risk), pressure recovery shape (separation risk), and whether the section is achieving the **rooftop** distribution the IHS criterion demands |
| **Drag polar** | Cd vs Cl | The efficiency signature. The classic aerodynamic chart |
| **Cl vs α** | — | Lift-curve slope, zero-lift angle, **stall onset and its sharpness** |
| **Cd vs α** | — | Drag bucket location and width — where the laminar section actually pays off |
| **L/D vs α** (or vs speed) | — | Where the design point should sit |
| **Cm vs α** | — | Pitching moment. Directly the "negative pitching moment feels unstable at speed" effect from the design practice base |

### Tier 2 — foil-specific, and mostly missing from generic tools

| Chart | Why it matters here |
|---|---|
| **σᵢ (= −Cp_min) vs Cl** — the **cavitation bucket** | The IHS gives the exact recipe: analyse over the α range, record min Cp at each, plot σᵢ vs Cl. **Width** = tolerance to angle variation; **depth** = tolerance to low cavitation number |
| **V_crit vs Cl** | The same data in units a rider understands — knots, not a dimensionless number |
| **Transition location (x_tr) vs α** | Upper and lower. Where laminar flow ends; the mechanism behind the drag bucket |
| **Displacement thickness δ\* along the chord** | The standard boundary-layer plot; the precursor to separation *(Verified)* |
| **Separation onset vs α** | *Trailing-edge stall propagating forward along the chord is evident in the Cp distribution* *(Verified)* — so separation is best shown **on** the Cp plot, as a marked region, not as a separate chart |
| **Spanwise load distribution** | 3D only. Cl(y) against the elliptical ideal — shows where the planform is wasting span |

### Tier 3 — comparison and decision

- **Overlay mode on every chart.** Comparing two candidate sections is the actual task; a chart that
  cannot overlay is half a chart.
- **Reynolds sweep on one axis.** Phase 0 showed section ranking *flips* between Re 6e5 and 1e6, so
  any ranked view must be Reynolds-parameterised.
- **Pareto / parallel coordinates** for multi-criteria selection — see `kb-design-automation`.

## 2. The 2D-section-at-a-spanwise-station view — and why it is physically legitimate

The user asked for a 2D visualisation of a given section "expressed as distance from mid point".
This is not a display convenience; it has a proper method behind it.

**Quasi-3D / strip theory:** *the lift distribution on the wing is computed using a vortex lattice
method, then strip theory is applied to compute viscous drag at several spanwise positions.* The
wing is treated as *a sum of airfoil section strips where 2D theory applies*, and **the 3D effect is
the downwash induced by the trailing vortex sheet, producing a local induced angle of attack that
modifies the sectional lift**. *(Verified)*

**So the correct chain for a section view at station `y` is:**

1. VLM gives the spanwise circulation → local induced angle of attack `α_i(y)`.
2. Local **effective** angle `α_eff(y) = α_geometric(y) − α_i(y)`.
3. Run the 2D section at `α_eff(y)` and the local chord's Reynolds number.
4. Display *that* Cp distribution, boundary layer and separation.

**The critical correctness point:** displaying the section at the *geometric* angle of attack would
be wrong — it ignores downwash and would overstate loading, badly near the tips where downwash is
largest. **The station slider must drive `α_eff`, not `α`.** This is the kind of quiet error that
produces a plausible, wrong picture.

## 3. Flow visualisation techniques

| Technique | Character | Fit |
|---|---|---|
| **Streamlines** | Integral curves of the velocity field. Adjustable density, user-controlled placement and panning | **2D and 3D.** The default. Familiar to every user |
| **LIC (Line Integral Convolution)** | Introduced 1993; *one of the most popular methods for vector field visualisation*. Dense texture representation | **Best for 2D sections.** Dense — shows the whole field, not just seeded lines. **GPUFLIC** achieves interactive rates for unsteady flows |
| **Evenly-spaced illuminated streamlines** | Controlled spacing, lit as tubes | **3D.** Plain 3D streamlines occlude badly; illumination and even spacing are the established fixes |
| **Glyphs** | Arrows/vectors at sample points | Quick, but clutters. Secondary |
| **Surface Cp contours** | Scalar on the wing surface | **Essential in 3D** — pairs naturally with Cp curves in 2D |
| **Iso-surfaces (Q-criterion, λ₂)** | Vortex cores | For tip vortices and separated wakes. Later |

*(All Verified.)*

**GPU is the enabler:** *unlike most CFD where visualisation happens after computation, GPU-based
software allows real-time visualisation of flow fields while computation takes place.* *(Verified)*
Since layer 5 already puts the field in VRAM, **rendering from the same buffers avoids a readback**
— a real architectural advantage of doing the LBM in CUDA with D3D interop.

## 4. The .NET stack — and one gap

### 2D charts: ScottPlot

ScottPlot is free, open source, interactive, designed for **large datasets**, and supports WPF among
many targets. Comparisons put **ScottPlot ahead of OxyPlot and LiveCharts2 for large static
datasets**; LiveCharts2 is the most modern-feeling with MVVM binding and animation; OxyPlot has the
broadest cross-platform reach. *(Verified)*

**Recommendation: ScottPlot.** Our charts are scientific, dense (a Cp distribution is hundreds of
points; a polar sweep is thousands), and static-per-frame. Performance at scale is the deciding
axis, and animation polish is not.

### 3D rendering: HelixToolkit — because VTK is not available

**VTK/ParaView bindings exist for C++, Python, Tcl/Tk, Java and JavaScript. C# and .NET bindings are
not among them.** *(Verified — a real gap, not an oversight in the search.)*

This is a **significant architectural finding**. The default scientific-visualisation stack is
unavailable to a WPF application. The options are:

1. **Render it ourselves in HelixToolkit/SharpDX.** Full control, no interop, shares the viewport
   with the CAD editor. Streamline integration and LIC are both implementable as compute/pixel
   shaders. **Recommended** — and note that the CAD editor needs this viewport anyway, so it is not
   an extra dependency.
2. **Shell out to ParaView** for heavy post-processing, accepting a separate window. Pragmatic
   escape hatch for anything exotic; not an interactive experience.
3. **Python sidecar** with VTK, piping images back. Adds a Python runtime to a .NET product.

**Recommendation: (1), with (2) as an explicit escape hatch.** Do not build a general
visualisation toolkit — build the six views this domain needs.

### Video export: FFmpeg wrappers

| Library | Approach |
|---|---|
| **FFMpegCore** (5.4.0) | .NET FFmpeg/FFprobe wrapper. **Writes video frames directly from program memory** without saving PNGs first, via `IPipeSource` — `RawVideoPipeSource` for raw frames. Also `JoinImageSequence` with configurable frame rate |
| **FFMediaToolkit** | Cross-platform encoder/decoder using native FFmpeg; creates videos from bitmaps |
| **NReco VideoConverter** | Encodes live streams from `Bitmap` without temp files; animated GIF |

*(All Verified.)*

**Recommendation: FFMpegCore with `RawVideoPipeSource`.** The α/velocity sweep the user asked for is
exactly a frame generator — render each sweep step to an offscreen target and pipe it. **No
intermediate PNG files**, which matters when a sweep is hundreds of frames.

## 5. The sweep as a first-class concept

The user wants both 2D and 3D views to sweep α and velocity, and to export the result as video.
That makes **the sweep a domain object, not a UI loop**:

```
Sweep { Variable(alpha|velocity|station|Re), From, To, Steps, HoldOthers }
```

Consequences:
- Every view — charts, 2D section, 3D field — **binds to the same sweep**, so scrubbing moves all of
  them together.
- The sweep is the **video timeline**. Export is "render this sweep to frames", not a separate mode.
- Sweep results are **cacheable and re-orderable**; at estimator cost the whole sweep precomputes
  instantly, at CFD cost it is a job queue.
- A sweep is also exactly what a **polar** is. The polar chart and the animation are two views of one
  computation.

## 6. Open questions

1. **What does "separation" mean for the estimator tier?** *(Flagged.)* The closed-form chain has no
   separation model; NeuralFoil gives transition and boundary-layer parameters but not a separation
   point directly. Showing separation may require the VLM+strip tier at minimum. **Do not draw a
   separation marker the model cannot support.**
2. **Is LIC worth implementing versus streamlines?** LIC is denser and more informative but is a
   shader to write and tune. Streamlines are cheaper and familiar. Unresolved.
3. **How is a 3D field slice extracted for the 2D view when the source is LBM?** A uniform Cartesian
   lattice does not align with a swept, twisted station plane; interpolation is needed and its
   accuracy near the surface is exactly where it matters most.
4. **Colour maps.** No source consulted on perceptual uniformity here; the default rainbow map is
   known-bad for scalar fields and should not be the default.

## Sources

| Source | Type | URL |
|---|---|---|
| XFOIL analysis docs — polars, Cp, boundary layer, δ* | primary | https://v0xnihili.github.io/xfoil-docs/analysis/ |
| CFD post-processing (Verus Engineering) | secondary | https://www.verus-engineering.com/blog/cfd-cases-4/cfd-post-processing-74 |
| NASA CFD database for airfoils at post-stall α | primary | https://ntrs.nasa.gov/api/citations/20140000500/downloads/20140000500.pdf |
| Quasi-3D aerodynamic analysis / strip theory + VLM | primary (peer-reviewed) | https://link.springer.com/article/10.1007/s00158-016-1447-9 |
| Strip theory overview | secondary | https://www.sciencedirect.com/topics/engineering/strip-theory |
| Vector field visualization with streamlines | primary (arXiv) | https://arxiv.org/pdf/cs/0610088 |
| GPUFLIC: interactive dense visualization of unsteady flows | primary | https://www.researchgate.net/publication/220778331_GPUFLIC |
| Evenly-spaced illuminated streamlines | primary | https://www.academia.edu/14389007/ |
| ScottPlot | primary | https://scottplot.net/ |
| ScottPlot vs OxyPlot vs LiveCharts2 comparison | secondary (vendor blog) | https://lightningchart.com/blog/best-scottplot-alternative-in-2026-gpu-rendering-3d-charts-cross-language-support/ |
| ParaView Catalyst — language bindings | primary | https://docs.paraview.org/en/latest/Catalyst/background.html |
| FFMpegCore | primary | https://github.com/rosenbjerg/FFMpegCore |
| FFMediaToolkit | primary | https://github.com/radek-k/FFMediaToolkit |

All accessed 2026-09-06.
