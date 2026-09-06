---
id: kb-cfd-orchestration
title: "Orchestrating OpenFOAM and SU2 from a C# Application"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [openfoam, su2, orchestration, interop, docker, wsl, cloud, csharp]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
review-by: 2026-12-05
summary: >-
  How a C# desktop application can drive OpenFOAM and SU2 without the user ever seeing a dictionary
  file — the case-generation layer, the four candidate execution substrates on Windows, the
  interop boundary that keeps solvers replaceable, and what cloud execution costs.
---

# Orchestrating OpenFOAM and SU2 from C#

**The requirement, stated as the user did:** *"I don't want to have to worry about input files."*
That is the whole problem. OpenFOAM is not a library you call — it is **a directory tree of
dictionary files and a family of command-line executables**. Everything below follows from that.

## 1. The shape of the problem

An OpenFOAM case is a directory: `0/` (initial and boundary conditions), `constant/` (mesh,
physical properties), `system/` (`controlDict`, `fvSchemes`, `fvSolution`, `blockMeshDict`,
`snappyHexMeshDict`). A run is a *sequence of executables* over that directory — `blockMesh`,
`snappyHexMesh`, `checkMesh`, the solver, `postProcess`.

**The traditional workflow is "copy a tutorial directory and edit by hand"**, which is exactly what
the user is refusing. *(Verified)*

**The consequence for architecture is a good one:** because the interface is files-and-processes
rather than a linked library, **there is no FFI problem to solve**. There is a *generation* problem
and an *orchestration* problem, both of which are ordinary software.

## 2. Case generation — prior art, and what it tells us

| Tool | Approach | What to take from it |
|---|---|---|
| **PyFoam** | Loads OpenFOAM dictionary files and represents them as Python dictionaries | The dictionary format is **parseable and round-trippable**. This is the foundational fact |
| **PyFoamCaseBuilder** | Each boundary condition has a *type tag* (the OpenFOAM boundary type name) plus a parameter dictionary | The right data model for boundary conditions: **a discriminated union keyed by type**, not free-form text |
| **CaseFOAM** | Sits on PyFoam; generates case *structures* for parameter studies, flat or tree hierarchy | Parameter sweeps are a first-class concern, not an afterthought. Our angle-of-attack and speed sweeps are exactly this shape |
| **fluidsimfoam** | A "workflow manager for OpenFOAM" — a wrapper that only issues OpenFOAM commands underneath, generating parametrised input including `blockMeshDict` | **This is the closest analogue to what we want**, and it validates the approach: generate, invoke, parse |

*(All Verified from project documentation.)*

**The lesson:** every serious attempt at this problem converges on the same three-layer shape —
a **typed case model**, a **serialiser** to dictionary format, and a **process runner**. Nobody has
found a way around generating the files; they have found ways to never hand-edit them. That is what
the user is asking for and it is a solved shape.

**SU2 is a different and easier story.** It has a **Python wrapper (`pysu2`)** built with SWIG that
wraps the `CDriver` structure, so any SU2 driver can be instantiated and used as a Python object.
*(Verified)* Its config is a single flat `.cfg` file rather than a directory tree. **SU2 is the
better first target for programmatic control**; OpenFOAM is the one that needs the generation layer.

## 3. Execution substrate on Windows — four options

OpenFOAM is a Linux application. Current release is **OpenFOAM-v2606** (26 June 2026). *(Verified)*

| Substrate | How it works | For | Against |
|---|---|---|---|
| **Docker Desktop** | OpenCFD distributes official images on Docker Hub with an installer wizard; user files appear on the host under `C:\user\<username>` | Officially supported and documented by OpenCFD. Reproducible. Same binary as Linux | Docker Desktop is a heavyweight dependency and a licensing question for commercial use |
| **WSL2 directly** | Install OpenFOAM inside a WSL2 distro; invoke via `wsl.exe -d <distro> -- <command>` | No Docker layer. Fast filesystem within the distro. Trivial to invoke from C# | Per-machine setup; version drift between users |
| **WSL Containers (WSLC)** | Native container support in WSL2 via `wslc.exe`, public preview 29 June 2026 | Dramatic speed improvements and tight Windows integration | **Preview.** Missing orchestration features, network configuration and tooling gaps — not a Docker Desktop replacement yet *(Verified)* |
| **Cloud** | CFD Direct From the Cloud (CFDDFC) on AWS Marketplace; also Azure. Launch preconfigured instances in minutes, up to 48 processors, clusters of hundreds | No local setup. Elastic. Arm/Graviton instances save ~35% | Latency, data transfer, and a billing relationship the desktop app must manage |

*(All Verified.)*

**Prior art worth studying:** **FoilPilot** (`olaafrossi/FoamPilot`) is an OpenFOAM Docker control
UI that **handles the full WSL2 and Docker Desktop installation including a guided reboot**.
*(Verified)* That is precisely the onboarding problem a desktop app faces, and someone has already
solved it in public.

**Recommendation:** **WSL2 directly for v1**, Docker as the reproducible fallback, cloud as a later
scale-out. WSL2 is the shortest path from a C# process to a running solver, has no licensing
question, and `wsl.exe` is an ordinary child process. Treat the substrate as a **strategy behind one
interface** so the choice stays reversible.

## 4. The interop boundary

**There is no P/Invoke here, and that is the point.** The boundary is:

```
ICfdBackend
  ├─ Task<CaseHandle>  PrepareAsync(WingGeometry, OperatingPoint, Fidelity)
  ├─ IAsyncEnumerable<SolverProgress> RunAsync(CaseHandle, CancellationToken)
  └─ Task<CfdResult>   HarvestAsync(CaseHandle)
```

Everything OpenFOAM-specific — dictionary serialisation, `blockMesh`/`snappyHexMesh` sequencing,
residual parsing — lives behind that. Consequences:

- **The estimator, the VLM tier and OpenFOAM are all just `ICfdBackend` implementations at different
  fidelities.** That is the phased approach the user asked for, expressed as one interface rather
  than three code paths.
- **Solvers stay replaceable.** Swapping OpenFOAM for SU2, or local for cloud, changes one class.
- **Progress must stream.** A run is minutes to hours; the UI needs residuals and iteration counts as
  they appear, which is why `RunAsync` yields rather than returns. Parse the solver's stdout — that
  is where residuals are written.
- **Cancellation must be real.** Killing the process tree, not just abandoning the task.

## 5. Meshing is the hard part, and it is where the effort goes

The dictionaries are tedious but mechanical. **Meshing is the part that fails.** `snappyHexMesh`
needs a watertight surface (STL), a background `blockMesh`, refinement regions, and boundary-layer
settings, and it fails in ways that need judgement to diagnose.

**But our geometry is not arbitrary.** It is a single wing with a known parametric description — a
lofted surface from stations, always the same topology. That means the meshing setup can be
**generated from the parametric model rather than authored**: refinement boxes sized from the chord,
boundary-layer thickness from the target `y+` at the operating Reynolds number, domain extents as
multiples of span. **A general CFD GUI cannot do this; a single-purpose wing tool can.** This is the
strongest argument that the orchestration layer is tractable here and not in general.

**Always run `checkMesh` and refuse to solve on a mesh that fails it.** A bad mesh produces a
converged, plausible, wrong answer — the failure mode this whole domain is prone to.

## 6. Cloud economics

CFDDFC is available on the AWS Marketplace for x86 (Intel/AMD) and Arm (Graviton) instances,
launching preconfigured OpenFOAM in minutes with up to 48 processors and clusters of hundreds.
**Graviton C6g instances save ~35% on EC2 costs for batch CFD.** At 1008 cores, EFA networking
delivered **linear strong scaling**. *(Verified)*

*Design implication:* for a single-wing case at our scale, **one instance is enough** — this is not
a cluster problem. The cloud value here is elasticity for parameter sweeps (dozens of independent
angle-of-attack cases), which is embarrassingly parallel and therefore the ideal cloud workload.

## 7. Open questions

1. **How reliably can `snappyHexMesh` settings be generated for our geometry family?** *(Flagged,
   load-bearing.)* The claim that a single-purpose tool can auto-mesh reliably is plausible and
   unproven. **Settle by** meshing three wings across the geometry range and checking `checkMesh`.
2. **Does the WSL2 filesystem boundary cost enough to matter?** Windows-to-WSL file access across
   `/mnt/c` is slow; cases should live inside the distro. Unmeasured here.
3. **What is the licensing position of Docker Desktop for a commercial product?** A commercial
   question, not technical, but it decides the substrate.
4. **Is `pysu2` buildable on Windows?** It requires compiling SU2 with the Python wrapper enabled;
   the documentation is Linux-centric. Unverified.

## Sources

| Source | Type | URL |
|---|---|---|
| PyFoam / pyFoamCaseBuilder | primary | https://openfoamwiki.net/index.php/Contrib_pyFoamCaseBuilder |
| CaseFOAM documentation | primary | https://casefoam.readthedocs.io/en/latest/ |
| fluidsimfoam | primary | https://pypi.org/project/fluidsimfoam/ |
| OpenFOAM current release (v2606) | primary | https://www.openfoam.com/current-release |
| OpenFOAM Docker installation on Windows | primary | https://www.openfoam.com/download/openfoam-installation-on-windows-docker |
| FoamPilot | primary | https://github.com/olaafrossi/FoamPilot |
| SU2 Python wrapper build | primary | https://su2code.github.io/docs/Python-Wrapper-Build/ |
| CFD Direct From the Cloud — cost | primary | https://cfd.direct/cloud/cost/ |
| WSL Containers preview (June 2026) | secondary | https://windowsnews.ai/article/microsofts-wsl-containers-preview-landsbut-should-developers-ditch-docker-desktop-yet.432315 |

All accessed 2026-09-06.
