---
id: kb-cad-ux-geometry
title: "CAD UX Paradigms and the .NET Geometry Stack"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [cad, ux, wpf, nurbs, helixtoolkit, rhino3dm, stepcode, licensing, splines, shape3d]
links:
  - { to: kb-cfd-parametric-geometry, rel: refines }
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
  - { to: decision-0001-geometry-kernel, rel: depends-on }
review-by: 2026-12-05
summary: >-
  The three CAD interaction paradigms and which fits a foil editor, what Shape3d and Rhino actually
  do at the control-point level, the continuity and curvature-comb vocabulary a surface editor must
  speak, and the concrete .NET stack — HelixToolkit for the viewport and a fully permissive
  geometry path (rhino3dm MIT, STEPcode BSD) that removes the need for a B-Rep kernel entirely.
---

# CAD UX paradigms and the .NET geometry stack

## 1. Three paradigms, and the one this project needs

| Paradigm | Exemplar | Mental model | Fit here |
|---|---|---|---|
| **Direct manipulation of NURBS** | Rhino | No history tree. Curves, surfaces and solids are first-class entities; you manipulate control points and surface continuity (G0/G1/G2/G3). Rhino is *non-history* and cannot construct from a feature tree | **The primary paradigm.** A foil is a freeform surface, not a feature stack |
| **Visual programming / explicit history** | Grasshopper | Components on a canvas, outputs wired to inputs. Grew from David Rutten's 2008 question *"what if you could have more explicit control over this history?"* | **Not for v1.** Powerful and a large surface. The generative layer already covers the parametric need |
| **Relational geometry** | MultiSurf / SurfaceWorks | A hierarchy of dependencies among surface elements; changing a parameter auto-updates dependents. Notably **not a NURBS model** — a relational model of interrelated points, curves and surface types, which most CAD systems do not recognise | **The idea, not the implementation.** Our station model *is* relational. But its non-NURBS representation is an interoperability trap |

*(All Verified.)*

**The MultiSurf lesson is the important one.** It is the closest existing analogue to what this
project wants — parametric relational surfaces for marine design — and its recorded weakness is that
**its native model is not NURBS, so it does not round-trip to other CAD**. Since this project must
export to CAM and CAD (see `kb-fabrication-interop`), the internal model may be relational but
**the exported model must be NURBS/B-Rep.**

## 2. Shape3d — the closest UX analogue, and it is a marine design tool

Shape3d designs surfboards from concept to CNC. Its curve editing is worth copying almost directly:

- **Left-click a control point** to select it (turns red); move with mouse **or arrow keys**.
- **Double-left-click** on the curve to *add* a control point at that position.
- **Delete / right-click** to remove one.
- **Multi-point selection and alignment**, and **accurate keyboard displacement steps**.
- **Flow visualisation:** holding left-click in the outline, profile or thickness view shows the
  slice flow with width/rocker/thickness **and the distance from tail and nose simultaneously**.
- Ability to **display thickness between any two curves**.

*(All Verified from the Shape3d documentation.)*

**Three transferable principles:**

1. **Keyboard nudge with a defined step is not optional.** Precision work needs it; mouse-only
   editing is for sketching.
2. **Show the derived quantity while editing the curve.** Shape3d shows width and rocker *as you
   drag*. Our equivalent is showing chord, thickness, area and aspect ratio live — and, uniquely,
   **L/D from the estimator**.
3. **Multi-view editing of orthogonal curves** — outline, profile, thickness — is the established
   paradigm for a lofted marine surface. A foil maps onto exactly this: **planform outline,
   anhedral/dihedral curve, chord distribution, thickness distribution, twist distribution.**

**AkuShaper** is the other surfboard-to-CNC tool in this space and confirms the category.

## 3. The continuity vocabulary a surface editor must speak

| Level | Meaning |
|---|---|
| **G0** | Position — curves share the junction point |
| **G1** | Tangent — matched end tangent *directions* |
| **G2** | Curvature — matched radius/curvature values. Also called **fairness** |
| **G3** | Matched rate of change of curvature |

*(Verified — Autodesk Alias.)* Note the distinction: **geometric continuity G1 matches tangent
directions but not length; analytic C1 matches both.** *(Verified)*

**Curvature combs** illustrate connection smoothness — *at G1 the combs are parallel where they meet
but of different lengths*. *(Verified)* **A curvature comb is the single most valuable diagnostic in
a foil editor**, because a curvature discontinuity is hydrodynamically real and visually invisible —
the exact risk flagged in `kb-cfd-parametric-geometry`.

**Degree matters:** *degree-5 splines ensure G4 continuity internally; degree-3 only G2.*
*(Verified)* For a foil section where pressure distribution is a derivative of curvature, **degree 5
is the right default.**

**Handles:** *the tangent arrow grip changes the magnitude of the tangent at the base point,
creating a sharper or flatter curvature.* *(Verified)* — the standard Bézier handle affordance.

## 4. The .NET stack — what exists

### Viewport: HelixToolkit

Helix Toolkit is a collection of 3D components for .NET. **`HelixToolkit.Wpf.SharpDX` (3.1.2 on
NuGet)** provides a custom 3D engine and scene graph on **SharpDX / DirectX 11**, with XAML/MVVM
compatibility, `Viewport3DX`, and an `EffectsManager` for graphics resources. It supports WPF,
Avalonia and WinUI. **Manipulator/gizmo support exists** — there is a `ManipulatorDemo` in the
repository, and `ManipulationBinding` maps manipulation gestures, with the binding target relaxed to
`Element` rather than `GeometryModel3D`. *(Verified)*

**Assessment: use it.** It is the only mature open-source WPF 3D viewport with a gizmo story. The
plain `HelixToolkit.Wpf` (WPF 3D) package exists but SharpDX is the performant path.

### Geometry kernel: NOT REQUIRED — see `decision-0001-geometry-kernel`

> **DECIDED 2026-09-06.** OCCT is **deferred indefinitely** on licensing grounds, and the review that
> produced that decision found we do not need a B-Rep kernel at all on this scope. The permissive
> stack below replaces it. The OCCT assessment is retained for the record.

**The permissive alternatives:**

| Need | Library | Licence | Notes |
|---|---|---|---|
| NURBS curves/surfaces, B-Reps, meshes, extrusions, SubDs | **rhino3dm** (`mcneel/rhino3dm`) | **MIT** | .NET bindings via NuGet, Windows/macOS/Linux. openNURBS grant is MIT verbatim; McNeel state commercial use is encouraged. **Reads/writes 3DM only — no STEP or IGES** *(Verified)* |
| STEP AP203/AP242 read and write | **STEPcode** | **BSD** | EXPRESS parser, SDAI classes, Part 21 I/O. Used by BRL-CAD, SCView and **OpenVSP** *(Verified)* |

**The decisive precedent:** *OpenVSP uses STEPcode to write AP203 files that currently contain only
`B_SPLINE_SURFACE_WITH_KNOTS` entities.* *(Verified)* That is exactly our case — a lofted B-spline
surface reaching STEP with no B-Rep kernel involved.

**Why no kernel is needed.** A kernel earns its keep on booleans, filleting and topological repair.
Lofting, evaluation, meshing and single-entity STEP export need none of those. The two requirements
that would have needed one — subtracting the wing from a mold block, and importing arbitrary
third-party B-Rep — are both out of scope on independent grounds (molds belong in CAM; import reads
our own format).

### The OCCT assessment, retained for the record

**OCC C# Wrapper** wraps OCCT C++ classes for .NET; the C# interface reuses the C++ DLLs and calls
C++ methods through C# calls, on Windows and Linux. Official C# samples exist
(`Open-Cascade-SAS/OCCT-samples-csharp`), including a Direct3D sample. *(Verified)*

**What OCCT gives that nothing else in .NET does:** a real B-Rep kernel — NURBS surfaces, booleans,
filleting, and **STEP/IGES import and export**. Since STEP is the required output for CNC
(`kb-fabrication-interop`), OCCT is close to unavoidable if we want proper B-Rep export rather than
a mesh.

**The cost, now verified:** OCCT 6.7.0+ is **LGPL-2.1 with the Open CASCADE Exception 1.0**. The
exception permits object code to incorporate material from Library *header files* under terms of
your choice — it does **not** lift the linking obligations. Under **LGPL section 6** an application
must carry the LGPL notice, **make the OCCT sources it used available to its users**, and **ensure
the user can run the application against a modified OCCT**. *(Verified)* That third obligation
shapes how the application is built and shipped, applies regardless of commercial intent, and is
the reason this dependency was declined.

### The build-versus-buy line

| Layer | Decision | Why |
|---|---|---|
| Station/loft model | **Build** | It is the domain model. Small, and no library has it |
| Section curves (CST, NACA, catalog) | **Build** | Already specified; a few hundred lines |
| Spline evaluation, curvature combs | **Build** | Standard maths, and we need exact control |
| 3D viewport, camera, picking, gizmos | **Buy — HelixToolkit** | Months of work, solved |
| NURBS surface maths, if it gets hard | **Buy — rhino3dm (MIT)** | Permissive, .NET-native, drop-in |
| STEP AP203 export | **Build, or STEPcode (BSD)** | One entity type; OpenVSP proves the approach |
| B-Rep kernel | **Not required** | Deferred indefinitely — see `decision-0001-geometry-kernel` |
| Mesh/STL generation | **Either** | Trivial from our own loft; OCCT does it too |
| 2D charts | **Buy — ScottPlot** | See `kb-flow-visualization` |

## 5. The paradigm decision for this tool

**Direct manipulation of a constrained parametric model** — a hybrid, and the constraint is what
makes it work.

The user does not want free-form NURBS editing (that is Rhino, and it would let them build a
non-foil). They want to *edit the outline, anhedral, chord, thickness and twist*. Those are
**exactly the curves in the station model**. So:

- **The editable objects are the distribution curves**, not the surface. Editing "the outline" means
  editing the chord-versus-span curve. The surface is always derived.
- **The surface is never edited directly.** That preserves the invariant that geometry is always a
  valid foil, and it keeps the estimator connected — every edit maps to parameters it understands.
- **Direct manipulation applies to the curves**: control points, handles, keyboard nudge, curvature
  combs.

This is Shape3d's model rather than Rhino's, and Shape3d is the tool built for exactly this class of
object. There is a patent-recorded concept for *enforcing parametric constraints in a direct
modeling interface*, so the hybrid is a recognised approach. *(Verified — exists as prior art;
patent implications not assessed.)*

## 6. Open questions

1. ~~OCCT licensing.~~ **CLOSED 2026-09-06** — LGPL-2.1 §6 obligations verified, dependency
   declined, permissive path adopted. See `decision-0001-geometry-kernel`.
2. **Does HelixToolkit's gizmo generalise to control-point dragging on a curve?** The demos show
   object transforms. Dragging one control point in a 3D view against a plane is a different
   interaction. **Settle by spike.**
3. **Do we need OCCT at all for v1?** If v1 exports STL and defers STEP, the whole kernel dependency
   is deferrable. Depends on whether CAM is a v1 requirement.
4. ~~How is an imported arbitrary file reconciled to stations?~~ **CLOSED by scope decision
   2026-09-06** — import reads **our own format only**, so it is deserialisation rather than surface
   fitting. Arbitrary third-party B-Rep import is out of scope, which is also what removes the last
   requirement for a geometry kernel.
5. **Is our own STEP writer correct?** Unverified until a CAM system opens the output. The
   acceptance test is not "it writes a file" but "Fusion or Mastercam opens it and the surface is
   smooth". Tracked as `SPIKE-02`.

## Sources

| Source | Type | URL |
|---|---|---|
| HelixToolkit — Getting Started / Viewport3DX | primary | https://helix-toolkit.github.io/helix-toolkit/develop3/articles/intro.html |
| HelixToolkit.Wpf.SharpDX 3.1.2 | primary | https://www.nuget.org/packages/HelixToolkit.Wpf.SharpDX/ |
| HelixToolkit ManipulatorDemo | primary | https://github.com/helix-toolkit/helix-toolkit/blob/main-v2/Source/Examples/WPF.SharpDX/ManipulatorDemo/MainViewModel.cs |
| OCC C# Wrapper | primary | https://occt3d.com/components/occ-csharp-wrapper/ |
| OCCT licensing (LGPL-2.1 + exception, §6 obligations) | primary (vendor) | https://dev.opencascade.org/resources/licensing |
| Open CASCADE Exception 1.0 (SPDX) | standard | https://spdx.org/licenses/OCCT-exception-1.0.html |
| rhino3dm (MIT) | primary | https://github.com/mcneel/rhino3dm |
| What is Rhino3dm? | primary (vendor) | https://developer.rhino3d.com/en/guides/opennurbs/what-is-rhino3dmio/ |
| STEPcode (BSD); OpenVSP writes AP203 B_SPLINE_SURFACE_WITH_KNOTS | primary | https://stepcode.github.io/docs/home/ |
| OCCT C# samples | primary | https://github.com/Open-Cascade-SAS/OCCT-samples-csharp |
| Shape3d user manual v8 | primary | https://www.shape3d.com/Manuals/User_Manual_V8.pdf |
| Shape3d X — what's new | primary | https://www.shape3d.com/products/FromV8toVX.aspx |
| Autodesk Alias — Continuity G0 G1 G2 G3 | primary | https://help.autodesk.com/cloudhelp/2026/ENU/Alias-Video-Tutorials/files/essential-concepts/continuity-g0-g1-g2-g3.html |
| Fusion — Control Point Splines FAQ | primary | https://www.autodesk.com/products/fusion-360/blog/sketch-control-point-splines-faq/ |
| Grasshopper 3D overview / history | secondary | https://en.wikipedia.org/wiki/Grasshopper_3D |
| MultiSurf relational geometry / NURBS discussion | secondary | http://www.kastenmarine.com/why_NURBS.htm |
| CAD modeling paradigms: NURBS, parametric, implicit, SubD | secondary | https://www.demystifyingplm.com/cad-modeling-paradigms-nurbs-parametric-implicit |

All accessed 2026-09-06.
