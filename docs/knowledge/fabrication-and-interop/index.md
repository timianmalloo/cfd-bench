---
id: kb-fabrication-interop
title: "Fabrication, Export Formats and CAD Interoperability"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [export, step, stl, 3mf, cam, gcode, mcp, cad-interop, molds]
links:
  - { to: kb-cad-ux-geometry, rel: refines }
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
review-by: 2026-12-05
summary: >-
  What format a foil should leave the tool in for each destination — STEP for machining, STL/3MF for
  printing — why STL is the wrong answer for a mold, where CAM and G-code generation sit, and an
  honest ranking of what CAD MCP servers can and cannot model today.
---

# Fabrication, export and CAD interoperability

## 1. Export formats — the decision is not close

| Format | Representation | Right for | Wrong for |
|---|---|---|---|
| **STEP (AP242)** | Mathematically defined solids — planes, cylinders, cones, **splines** — as exact B-Rep | **CNC machining, molds, FEA, injection molding.** Enables feature-based machining, datum setup and tolerance control | Nothing in our path |
| **STL** | Triangular facet mesh | 3D printing, rapid prototyping, visualisation | **Machining.** Carries no accurate dimensional geometry |
| **3MF** | Mesh plus metadata | 3D printing (modern replacement for STL) | Machining |
| **IGES** | Older surface exchange | Legacy interop only | Anything new |

*(All Verified.)*

**The finding that settles the user's question:** *STL does not carry accurate dimensional geometry
and is not appropriate for CNC machining submissions.* Tessellation **discards parametric features,
sketch constraints, feature history, threads, fillet definitions, and all tolerance and material
information**. For CNC it *requires manual surface machining and increases programming time and
risk*. *(Verified)*

The industry rule is explicit: **STEP AP242 for CNC machining; watertight STL or 3MF for 3D
printing.** *(Verified)*

**So for a foil mold: STEP, not STL.** A hydrofoil is a smooth, curvature-critical surface — exactly
the case where faceting hurts most, because a coarse tessellation puts visible flats on the very
surface whose curvature determines the pressure distribution.

**If STL must be sent anyway**, set deviation tolerance to **≤ 0.01 mm** in the export settings;
coarse STLs with visible facets produce inaccurate results. *(Verified)* Treat that as the floor,
not a target.

### What this means for the architecture

**STEP export requires a B-Rep kernel.** Our station-and-loft model can trivially emit a mesh, but
emitting an *exact spline surface* in STEP means either OCCT (see `kb-cad-ux-geometry`) or writing a
STEP writer, and the latter is not a reasonable undertaking. **This is the strongest single argument
for taking the OCCT dependency**, and it should be weighed as such rather than as a general
"we might want a kernel someday".

**Recommended export set:**

| Destination | Format | Notes |
|---|---|---|
| CNC / mold | **STEP AP242** | The deliverable that matters |
| 3D print | **3MF**, STL fallback | Watertight; ≤0.01 mm deviation |
| CAD handoff | **STEP** | Universally readable |
| Analysis / meshing | **STL** | `snappyHexMesh` wants STL; tolerance is a solver concern, not a fabrication one |
| Section exchange | **Selig `.dat`** | Round-trips with XFOIL/XFLR5 and the catalog |
| Whole-model archive | **native JSON/DSL** | The station model itself; the only lossless form |

Note **STL appears twice for different reasons** — as a poor fabrication format and as a perfectly
good meshing input. Same format, different fitness. Worth keeping distinct in the code.

## 2. Molds, and the step everyone forgets

A foil mold is **the negative of the foil, in two halves**, and the geometry the CAM system needs is
not the wing — it is the mold block with the wing cavity subtracted, plus a parting surface, draft
where needed, and location features.

**That subtraction is a boolean operation on solids**, which a mesh model cannot do robustly and a
B-Rep kernel does natively. It reinforces the OCCT case.

Also unaddressed by any source found: **shrinkage and layup allowance**. A composite foil laid up in
a mold is not the same size as the mold cavity. **Flagged as a real gap** — if the tool exports mold
geometry it must state whether any allowance is applied, and the honest v1 answer is "none, and here
is the number you must apply yourself".

## 3. CAM and G-code

| Tool | Language | Notes |
|---|---|---|
| **Generic CAM** | C++ | Open-source toolpath generator; **starts from STL or GTS** and emits G-code |
| **PathCAM** | **C#/.NET** | 2.5D toolpaths, connects to some CNC machines, exports `.gcode`; uses **STLdotNET** |
| **OneManLabs CAM** | Browser | Imports DXF/SVG; contour, pocket, drill; GRBL G-code |
| **CamBam** | — | 3D meshes profiled with **multi-pass roughing or finishing**; explicitly supports **molds** |

*(All Verified.)*

**Assessment: do not build CAM.** The honest reading is that these tools are either 2.5D
(PathCAM) or mesh-based (Generic CAM), and **a foil mold needs true 3D surface finishing with
ball-nose scallop control** — which is what commercial CAM (Fusion, Mastercam, HyperMill) does well
and open source does not.

**The right scope is to export STEP and stop.** Emitting G-code directly would mean owning tool
libraries, machine post-processors, collision checking and workholding — an entire second product,
and one where a mistake breaks a machine. If a G-code path is ever wanted, **PathCAM is the only
C#/.NET starting point found**, and it is 2.5D.

*Design implication:* the tool's fabrication story is **"exports STEP that any CAM system can
machine"**, not "generates G-code". That is a smaller and much more defensible claim.

## 4. CAD MCP servers — an honest ranking

The user asked specifically about *ranking ability to create a true high-fidelity model*. Servers
exist for AutoCAD, Fusion 360 (several independent implementations), FreeCAD and Onshape.
*(Verified)*

| Platform | What the MCP server actually exposes | High-fidelity foil surface? |
|---|---|---|
| **Onshape (FeatureScript)** | **Text-to-code-to-CAD** — generates, tests and refines custom **FeatureScript** features from natural language | **Best of the four.** It generates *code in a real CAD language*, so the ceiling is FeatureScript's, not the protocol's |
| **FreeCAD** | Create complex geometries, parametric design, multi-part assemblies, execute modelling workflows **through scripting** | **Second.** Full Python scripting access means the ceiling is FreeCAD's own kernel (OCCT) |
| **Fusion 360** | Sketch shapes, extrude to 3D, apply **fillets and chamfers**; access design, components, parameters; create sketches, add parameters | **Third.** Feature-primitive vocabulary — sketch/extrude/fillet is a *mechanical* modelling idiom |
| **AutoCAD** | Drafting-oriented | **Lowest** for freeform surfaces |

**The ranking conclusion, stated plainly:** MCP servers that expose a **scripting or code-generation
surface** (Onshape FeatureScript, FreeCAD Python) can in principle produce high-fidelity freeform
geometry, because the protocol is not the limit — the CAD system's own API is. Servers that expose a
**fixed tool vocabulary** (sketch, extrude, fillet) cannot produce a lofted foil surface at
acceptable fidelity, because a foil is not expressible in that vocabulary at all.

**But the deeper point matters more:** *none of these is the right way to build the foil.* A foil is
defined by its station geometry, which this tool owns. Round-tripping it through an MCP server to a
CAD system is a lossy translation of a model we already have exactly. **The realistic use of a CAD
MCP is the reverse direction** — taking our STEP output into a CAD system for *downstream* work
(mold blocks, fixtures, assembly context) where the CAD system is genuinely better. That is a
worthwhile integration and a modest one.

*(Confidence: the capability inventory is **Verified** from the server documentation; the fidelity
ranking is **Inferred** from the exposed tool vocabularies and was not tested by generating a foil
through any of them.)*

## 5. Open questions

1. **OCCT licensing.** *(Flagged, load-bearing.)* Blocks the STEP path if it fails.
2. **What surface tolerance does a foil mold actually need?** No source found gives a hydrofoil
   figure. Machining tolerance interacts with layup thickness and post-finishing. **Unresolved and
   consequential** — it sets the export precision requirement.
3. **Shrinkage/layup allowance.** Whether the tool should model it at all. Currently unaddressed.
4. **Has anyone driven a foil through a CAD MCP end to end?** No evidence found. The fidelity
   ranking above is reasoned, not tested.
5. **Does `snappyHexMesh` want a different STL tolerance than printing?** Almost certainly — meshing
   wants a clean watertight surface at the mesh scale, not sub-0.01 mm. Unquantified.

## Sources

| Source | Type | URL |
|---|---|---|
| STL vs STEP for CNC — key differences | secondary | https://bravofabs.com/stl-vs-stp-format-drawings/ |
| Choosing the right CAD file format for manufacturing | secondary | https://xometry.pro/en/articles/file-formats-manufacturing/ |
| CAD file prep for CNC machining | secondary | https://www.plastfabworks.com/post/how-to-prepare-a-cad-file-for-cnc-plastic-machining |
| STEP vs STL — GDS | secondary | https://www.globaldesignsolutions.com/resources/step-vs-stl/ |
| Generic CAM | primary | https://genericcam.sourceforge.net/about.html |
| PathCAM (C#/.NET) | primary | https://github.com/xenovacivus/PathCAM |
| OneManLabs CAM | primary | https://github.com/OneManLabs/cam |
| CamBam toolpaths and G-code | primary | http://www.cambam.info/doc/1.0/toolpaths-and-gcode.html |
| 9 MCP servers for CAD (Snyk) | secondary | https://snyk.io/articles/9-mcp-servers-for-computer-aided-drafting-cad-with-ai/ |
| Onshape FeatureScript MCP Server | primary (vendor) | https://www.onshape.com/en/blog/featurescript-mcp-server-enables-text-code-cad |
| FreeCAD MCP server | primary | https://github.com/contextform/freecad-mcp |
| Fusion 360 MCP server | primary | https://github.com/faust-machines/fusion360-mcp-server |

All accessed 2026-09-06.
