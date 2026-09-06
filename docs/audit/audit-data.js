// Derived from docs/audit/*.jsonl by scripts/audit-log.py — DO NOT hand-edit (the JSONL logs are the source of truth; see audit-and-change-log.md).
window.AUDIT_DATA = {
  "project": "cfd-bench",
  "generated": "2026-09-06T15:44:51Z",
  "audit": [
    {
      "id": "al-01M1TD7004M7W7J08YZ74SF5BV",
      "shortname": "addpacktorepo-cfd-bench",
      "datetime": "2026-09-06T03:46:53Z",
      "session": "session_01A5LNAt2ocZqd1MbQcEQwer",
      "prompt": "create a new empty repo under my tim.ian.malloo@gmail.com account, repo name \"cfd-bench\", local location under c:\\projects, then apply the ai-forward pack to the repo",
      "summary": "AI-Forward Pack revision 61 (2026.09.05.2) installed into the fresh cfd-bench repo: 39 knowledge docs, 25 skills, 23 agents, Copilot instructions/prompts/agents, templates+scripts+hooks under docs/ai-forward-pack/, Docs Explorer at docs/index.html, CLAUDE.md/AGENTS.md managed blocks, .gitignore hygiene, and the optional docs-health CI workflow.",
      "kind": "command",
      "skill": "addpacktorepo",
      "tool": null,
      "actor": null,
      "artifacts": [],
      "tags": [],
      "outcome": "success"
    },
    {
      "id": "al-01M1TDJD1S9R0C2GF0JQSD3FGQ",
      "shortname": "cfd-bench-project-intent",
      "datetime": "2026-09-06T03:53:06Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "CFD-Bench will be a C# and WPF and CUDA based project for local CFD simulation on windows / nvidia machines",
      "summary": "First recorded statement of project intent: cfd-bench is a local CFD simulation app for Windows/NVIDIA machines, built on C# + WPF with CUDA compute. Closes the intent gap flagged at grounding (repo previously had no README/spec/architecture stating what the project is).",
      "kind": "prompt",
      "skill": null,
      "tool": null,
      "actor": null,
      "artifacts": [],
      "tags": [
        "intent",
        "cfd",
        "wpf",
        "cuda",
        "csharp"
      ],
      "outcome": "success"
    },
    {
      "id": "al-01M1TFBA3YRHVQ1RQEFN9DG824",
      "shortname": "collectknowledge-cfd-hydrofoil-simulation",
      "datetime": "2026-09-06T04:24:11Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "look at solutions for CFD like openfoam and stanford su2 also modern efficienct approaches for CFD analysis for hydrofoils, specifically i am interested in implementing a simpler, smaller solution instead of needing to use a full blown cfd package. Looking for simulation of hydrofoils and surfboards in salt and freshwater. acquire knowledge and think of pros and cons and optioins for such a solution assuming the hardware on this laptop as the baseline. create a proposal in html that i can review",
      "summary": "Built the repo's first domain knowledge base (8 docs, 24 sources) for small-footprint CFD of hydrofoils and surfboards. Key findings: hydrofoil (attached flow, potential-flow methods) and surfboard (planing, free surface) are two distinct physics problems, not one; salt vs fresh water is a two-parameter change (+2.69% density, +4.44% kinematic viscosity at 15C, ITTC 7.5-02-01-03) not a physics change; the foiling Reynolds envelope is 5.5e5-1.6e6; a 43M-cell 3D foil box fits comfortably on the RTX 5090 Laptop at ~220 steps/s est, so hardware is not the constraint. Strong free prior art exists (XFLR5, Typhoon, FluidX3D) and the disconfirming case against building anything substantially survives, narrowing the defensible project to an integrated application over established methods. Recommended Option B (two-tier: low-order interactive core + CUDA LBM) built in the order of Option A. Proposal published as HTML.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/index.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "cfd",
        "hydrofoil",
        "knowledge-base",
        "gpu"
      ],
      "outcome": "success",
      "goal": "Build a sourced domain knowledge base for small-footprint hydrofoil/surfboard CFD and a reviewable HTML proposal of options benchmarked against this laptop",
      "done_when": "docs/knowledge/cfd-hydrofoil-simulation/ exists with confidence-labelled cited findings; proposal HTML lays out options with pros/cons; graph index synced; audit and change log written",
      "tier": "T2",
      "fan_out": 0,
      "git": {
        "sha": "691174f7693b635ef8416286fb4e5af4956886b8",
        "short": "691174f76",
        "branch": "main",
        "pushed": true
      }
    },
    {
      "id": "al-01M1TH4AFVMR2WQKGV48BK84S3",
      "shortname": "collectknowledge-hydrofoil-v2",
      "datetime": "2026-09-06T04:55:19Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "lets simplify / continue with /collectknowledge / lets just focus on the hydrofoil scenario and not the surfboard scenario / further analyze and refine your proposal and do a deeper dive on algorithms, approach, architecture / also on the following: a catalog of hydrofoil foil section data (partial to Eppler but comprehensive across foil families); the ability to estimate L/D Cl/Cd pre-simulation; best practices in hydrofoil design for water sports (surf, sup, windsurf, wing, downwind foiling); catalog of optimal geometries (aspect ratios, plan forms, thicknesses); parametric design and description of 3D foils with multi-surface parametric design and a simple grammar. collect knowledge on these and related aspects, update the proposal with a v2",
      "summary": "v2 of the knowledge base: scope narrowed to hydrofoil only (surfboard/planing retired and marked RETIRED in place, not deleted). Four new docs: foil-sections (Eppler E817/818/836/837/838/874/904/908; NACA 66-series ranked ahead of 16-series by IHS on separation grounds; UIUC ~1650 sections; catalog grain and Cp_min/Ncrit requirements), estimation-methods (XFOIL + Helmbold + lifting line + ITTC 1957 + Hoerner form factor + cavitation critical speed, executed across four disciplines), watersports-design-practice (AR bands, area/AR per discipline, the low-speed-lift vs glide tradeoff, stabiliser sizing), parametric-geometry (CST/Kulfan sections; four-concept assembly/surface/station/loft grammar; two-layer generative-emits-explicit design). Key findings: most design questions are closed-form in microseconds; cavitation does not bind below ~25 kn; induced drag is 77% of drag at surf take-off and 3% at race speed; span is nearly fixed (95-107 cm) while area and AR vary widely; published aspect ratios are not comparable across manufacturers. Caught and corrected an internal inconsistency in the IHS source: V_crit=14/sqrt(sigma_i) derives from ITTC pv=1670.9 Pa, not the 17000 Pa the same document advises. Recommendation changed from v1: Option 2 (estimator + catalog + panel/VLM), sequenced so Option 1 ships first, GPU LBM gated on validation.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/index.md",
        "docs/knowledge/cfd-hydrofoil-simulation/estimation-methods.md",
        "docs/knowledge/cfd-hydrofoil-simulation/parametric-geometry.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "cfd",
        "hydrofoil",
        "sections",
        "estimation",
        "parametric",
        "v2"
      ],
      "outcome": "success",
      "goal": "v2 proposal: hydrofoil only, deeper algorithms/architecture, plus section catalog, pre-simulation estimation, water-sports design practice, geometry catalog and a parametric multi-surface grammar",
      "done_when": "New knowledge docs researched and confidence-labelled; existing base reconciled with surfboard scope explicitly retired; v2 proposal replaces v1 at the same artifact URL; graph, audit and change log updated",
      "tier": "T2",
      "fan_out": 0,
      "git": {
        "sha": "6e3dbdeda2156709800d31f7a0ec97345f4475ee",
        "short": "6e3dbdeda",
        "branch": "knowledge/cfd-hydrofoil-simulation",
        "pushed": null
      }
    },
    {
      "id": "al-01M1TJE84RRX29SEDW48Y189Y7",
      "shortname": "phase-0-evidence-pass",
      "datetime": "2026-09-06T05:18:13Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "merge now, then start phase-0 collecting evidence in knowledge and refining the proposal accordingly",
      "summary": "Merged the knowledge branch to main, then executed Phase 0. Three of four gaps closed by measurement. (1) THICKNESS: swept t/c 6-20 percent on a NACA 24xx family at design CL 0.30, Re 6e5 and 1e6 — section L/D and cavitation margin both fall monotonically, so there is NO hydrodynamic optimum; thickness is a structural variable with a quantified price (9 to 12 percent costs ~14 percent of section L/D and 3.8 kn of cavitation-free speed). This closes and reframes the base's largest evidence gap. (2) SECTIONS: vendored 11 coordinate sets from UIUC with SHA-256 hashes and measured geometry; discovered the Eppler hydrofoil set splits into 5 cambered lifting sections (7.90-10.98 percent t/c) and 3 symmetric strut-family sections (E836/E837/E838, 12.6-18.4 percent) — a split no secondary source states. Measured head-to-head: E818 reaches 42.1 kn cavitation-free vs NACA 4412's 31.4 kn, the first quantitative confirmation of the minimum-cavitation claim; NACA 64A410 records the best section L/D, confirming Tom Speer's 6-series recommendation by measurement; ranking flips with Reynolds so the catalog cannot have a single best. (3) TYPHOON: identified as Tornado VLM (Tomas Melin 1999/2007), MATLAB, GPL v2+ — reclassified from possible answer to reference/benchmark, and independent corroboration of the Option 2 VLM architecture. (4) TOOLING: NeuralFoil validated against analytic NACA truth; Cp_min absent as a field but recoverable from edge velocities, so section analysis needs no XFOIL binary. Caught a parser defect that would have corrupted the catalog: 6 of 8 Eppler files are Lednicer format, and reading them as Selig returned plausible wrong geometry. GPU questions remain open pending a CUDA install; none blocks Phase 1.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/phase-0-findings.md",
        "docs/knowledge/cfd-hydrofoil-simulation/sections/manifest.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "phase-0",
        "measurement",
        "sections",
        "thickness",
        "typhoon"
      ],
      "outcome": "success",
      "goal": "Merge to main, then execute Phase 0 — close evidence gaps by measurement, fold into the knowledge base, refine the proposal",
      "done_when": "main contains v2; Phase 0 questions have evidence or a recorded reason they could not close; knowledge docs and proposal updated; graph, audit and change log current",
      "tier": "T2",
      "fan_out": 0,
      "signals": {
        "verification_path": true,
        "verification_executed": true,
        "acceptance_met": true
      },
      "git": {
        "sha": "107e5ed817829d8b6156b64c3920eb2ba204f772",
        "short": "107e5ed81",
        "branch": "main",
        "pushed": false
      }
    },
    {
      "id": "al-01M1VMG1WKK82JD7KTDQGQSYJM",
      "shortname": "collectknowledge-wave2-plus-cuda",
      "datetime": "2026-09-06T15:13:24Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "continue building knowledge and proposals before specify; scope is designing front or rear wings not the whole assembly. (1) install CUDA toolkit. (2) collectknowledge on wrapping/orchestrating OpenFOAM from C# and interop architecture, no input file wrangling. (3) goal-driven design from a stated goal plus constraints with sliders, constraint solver and pre-evaluation, converging on a proposed shape - propose the UX. (4) CAD experience in WPF, study shape3d/rhino/multisurf/fusion360, collectknowledge on CAD UX in C#, OSS controls and libraries - propose the UX. (5) collectknowledge on MCP integration with CAD ranked by fidelity, gcode for molds, export formats. (6) collectknowledge on chart surfaces, 2D/3D streamline visualization with alpha and velocity sweeps and video export - propose.",
      "summary": "CUDA Toolkit 13.3.73 installed and VERIFIED: native sm_120 kernel compiled with MSVC 14.51 and executed on the RTX 5090 Laptop. Measured STREAM triad 811.6 GB/s = 90.6 percent of the 896.1 GB/s theoretical read from the device, which promotes the previously Flagged vendor bandwidth figure to Verified. The v2 throughput estimate is corroborated to 0.02 percent: FluidX3D's published desktop result implies 58.7 percent real-kernel efficiency, which applied to this device gives 9,572 MLUPs/s against the earlier 9,570, and 221.6 steps/s at 43.2M cells against the claimed ~220. Scope narrowed to a SINGLE WING (front or rear), with the multi-surface grammar retained as context because a rear wing sits in the front wing's downwash. Five new knowledge bases: cfd-orchestration (PyFoam/CaseFOAM/fluidsimfoam prior art, four Windows substrates, ICfdBackend boundary, meshing as the real work, cloud economics), design-automation (constraints vs objectives vs context, interactive MOPSO over AVL precedent, PAVED preference brush, 10us evaluation as the enabling asset), cad-ux-and-geometry (three CAD paradigms with direct-manipulation-of-constrained-parametric recommended, Shape3d interaction detail, G0-G3 continuity and curvature combs, HelixToolkit + OCCT stack, build-vs-buy table), fabrication-and-interop (STEP AP242 for CNC not STL, mold boolean needs B-Rep, do-not-build-CAM, CAD MCP fidelity ranking with Onshape FeatureScript highest), flow-visualization (12 charts across two tiers, quasi-3D alpha_eff correction for spanwise section views, LIC/streamlines, and the finding that NO VTK .NET binding exists). Three proposals written to docs/proposals/ as self-contained HTML: goal-driven-design-experience, cad-modelling-experience, visualisation-experience.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/knowledge/cfd-orchestration/index.md",
        "docs/knowledge/design-automation/index.md",
        "docs/knowledge/cad-ux-and-geometry/index.md",
        "docs/knowledge/fabrication-and-interop/index.md",
        "docs/knowledge/flow-visualization/index.md",
        "docs/proposals/goal-driven-design-experience.html",
        "docs/proposals/cad-modelling-experience.html",
        "docs/proposals/visualisation-experience.html"
      ],
      "tags": [
        "cuda",
        "openfoam",
        "cad-ux",
        "visualization",
        "constraints",
        "scope-change"
      ],
      "outcome": "success",
      "goal": "Five knowledge passes plus three proposals, CUDA installed, design scope narrowed to a single wing",
      "done_when": "CUDA installed or reason recorded; sourced knowledge for orchestration, design automation, CAD UX, fabrication and visualisation; three proposals in docs/proposals; scope reconciled; graph, audit and change log current",
      "tier": "T2",
      "fan_out": 0,
      "signals": {
        "verification_path": true,
        "verification_executed": true
      },
      "git": {
        "sha": "e7ec6d8c4bd9721994342c7a90db1684ab05c42c",
        "short": "e7ec6d8c4",
        "branch": "main",
        "pushed": false
      }
    },
    {
      "id": "al-01M1VNN7EV3YWHTNRQJVJP5PCB",
      "shortname": "gap-review-and-licensing-decision",
      "datetime": "2026-09-06T15:33:42Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "defer occt, avoid LGPL, is there an MIT/Apache alternative or should we implement our own; maintain verification-at-a-higher-tier; create a todo to spike HelixToolkit but defer; file import can be our own saved format; review all proposals end-to-end and identify what knowledge we have not accumulated",
      "summary": "LICENSING RESOLVED: OCCT deferred indefinitely. LGPL-2.1 section 6 obliges shipping OCCT sources and allowing relink against a modified OCCT — the taint to avoid. Fully permissive path found: rhino3dm is MIT (NURBS curves/surfaces/BReps/meshes, .NET via NuGet, 3DM only, no STEP) and STEPcode is BSD; decisively, OpenVSP already writes AP203 files containing only B_SPLINE_SURFACE_WITH_KNOTS via STEPcode, which is exactly our one surface type. Concluded no B-Rep kernel is needed at all: the only two requirements that would need one (mold-block booleans, arbitrary B-Rep import) are already out of scope, and the user's decision that import means our own saved format removes the last one. Recorded as decision-0001. Created docs/backlog.md with SPIKE-01 HelixToolkit control-point manipulation (deferred, with fallback), SPIKE-02 STEP writer round-trip, SPIKE-03 snappyHexMesh auto-generation, plus COMMIT-01 verification-at-a-higher-tier, COMMIT-02 no LGPL, COMMIT-03 own-format import. GAP REVIEW: 16 knowledge gaps plus 2 process gaps. Tier 1: validation data (partially closed — found DTIC ADA032272 DTNSRDC towing-tank data for NACA 16-309 vs 64A309 which independently confirms 6-series over 16-series, a third agreeing line after IHS prose and our NeuralFoil measurement); structural analysis (the largest hole — thickness is set by structure and nothing models it; beam+lifting-line hydroelastic methods exist at our fidelity tier); who the user is (three UX proposals written with zero user research, UX veto never convened); units and coordinate conventions (flagged as a defect class in v1, never settled). Tier 2: unsteady/pumping (Strouhal ~0.4, downwind IS pumping); multi-fidelity reconciliation; manufacturing constraints feeding back (our measured sections have physically unbuildable trailing edges); data/provenance model; how the app itself is tested. Process gaps: /adddomainexperts never run, and zero ADRs recorded.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/notes/decision-0001-defer-geometry-kernel.md",
        "docs/backlog.md",
        "docs/knowledge/knowledge-gap-register.md"
      ],
      "tags": [
        "licensing",
        "gaps",
        "review",
        "structures",
        "validation"
      ],
      "outcome": "success",
      "goal": "Answer the licensing question, record deferred spikes, apply the import scope decision, and identify end-to-end knowledge gaps",
      "done_when": "Kernel decision recorded with evidence; backlog created; CAD proposal and knowledge updated; gap register written and ranked; graph/audit/change log current",
      "tier": "T2",
      "fan_out": 0,
      "git": {
        "sha": "4f381d032382c7093e9e18e810fcc28bf7e19f8b",
        "short": "4f381d032",
        "branch": "main",
        "pushed": false
      }
    },
    {
      "id": "al-01M1VP1HJZ6EZT9E59HY1G55DA",
      "shortname": "ai-augmentation-proposal",
      "datetime": "2026-09-06T15:40:26Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "/also consider the role of LLMs in the end-to-end, i am assuming we will include a claude api key in the solution to infuse AI into the experience. write a proposal on where AI would be useful, a couple places i was thinking: the text description for a foil we want to design; an explain feature that takes the goals we set and the design we ended up with and explains the fit and tradeoffs etc",
      "summary": "Knowledge base and proposal on LLMs inside a deterministic engineering tool. Governing rule established: the model reads and writes LANGUAGE, the solver reads and writes NUMBERS, and numbers flow in as context but never out as results — which satisfies the AI Systems Engineer veto on non-determinism leaking into a deterministic path and is mechanically checkable (every numeral in model output must appear in the call's input). Seven capabilities ranked by value over risk, with the user's two ideas top: (a) brief to structured design intent using structured outputs plus a per-field stated/inferred/defaulted provenance flag and a human confirm gate; (b) explain the design against the goals, grounded with citations, under the hard constraint that every number must be passed in; (c) diagnose failed solver runs from logs, which is self-verifying and directly serves the no-input-files requirement; (d) knowledge-base Q&A over the ~25 sourced artifacts; (e) rider-to-engineer vocabulary bridging, which is the cheapest capability and may be what makes the tool usable by riders at all, connecting to GAP-03; (f) design reports; (g) section-selection rationale. Six explicit never-dos including computing any physical quantity, choosing the design, generating geometry, and judging structural safety (we have no structural model). Per-capability eval designs, with the numeral check as a deterministic guard on the non-deterministic component. Costs computed from Opus 5 rates: /usr/bin/bash.011 to /usr/bin/bash.085 per call, a heavy 74-interaction session about .57, and knowledge-prefix caching breaking even after 1.4 calls at 10x cheaper reads. Flagged honestly that a key shipped in a desktop binary is extractable, so BYOK is the correct design for this non-commercial single-user tool. C# integration surface taken from the official SDK reference rather than guessed. Added SPIKE-04 (numeral check) and COMMIT-04 (language in, numbers out) to the backlog.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/knowledge/ai-in-the-product/index.md",
        "docs/proposals/ai-augmentation-experience.html"
      ],
      "tags": [
        "llm",
        "claude-api",
        "ai-ux",
        "evals",
        "cost"
      ],
      "outcome": "success",
      "goal": "Proposal on where AI belongs in the end-to-end, with the boundary that keeps it out of the deterministic path",
      "done_when": "Knowledge base written with sourced capability inventory, eval designs, measured costs and the C# surface; proposal in docs/proposals; backlog updated; graph/audit current",
      "tier": "T2",
      "fan_out": 0,
      "git": {
        "sha": "a04cf22605174debbf2cbaf9648e39e67c46e375",
        "short": "a04cf2260",
        "branch": "main",
        "pushed": false
      }
    },
    {
      "id": "al-01M1VP9MGR52K4ZZHZVQFTEWDK",
      "shortname": "build-phasing-proposal",
      "datetime": "2026-09-06T15:44:51Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "prompt": "C:/Program Files/Git/also create a proposal on the phases we should consider for how to build this step by step that i can review and provide as input when we do get to a specify stage later",
      "summary": "Build-phasing proposal synthesised from the seven knowledge bases, four prior proposals, sixteen gaps and the backlog — no new research, a sequencing argument over existing evidence. Nine phases, each named for a verb the user gains: P0 conventions and spine (units/coordinate frames/file format/test strategy — the retrofit-hostile things, closes GAP-04/08/09), P1 estimator validated headless against DTIC ADA032272 (closes GAP-01), P2 read a wing (WPF + charts, gated on a provisional answer to GAP-03), P3 draw a wing (five distribution curves with live estimator — arguably the product, and a useful tool exists at 38 percent of effort), P4 trust the numbers (VLM + structures + multi-fidelity reconciliation, closes GAP-02/06), P5 state a goal (optimiser — HARD-GATED on P4 because COMMIT-01 forbids shipping estimator-only results), P6 build the wing (STEP export + manufacturing constraints feeding back, closes GAP-07, can run parallel from week 15), P7 explain it (AI, gated on SPIKE-04 numeral check, capabilities pullable forward), P8 prove it (CFD/LBM, gated on SPIKE-03). Key structural finding surfaced: COMMIT-01 is a dependency, not just a policy — it forces the VLM tier before the goal-driven experience, which is not the order enthusiasm would pick. Central risk named honestly: the differentiator (free surface) is last and might never arrive, leaving a very good XFLR5-for-hydrofoils; recommended a 1-2 week de-risking slice at week 15 costing ~4 percent of total to test the claim the other 96 percent rests on. Three natural stopping points identified with P6 as the honest v1 boundary at 72 percent. Four open questions listed that need user input before /specify, plus a recommendation to run /adddomainexperts first.",
      "kind": "skill",
      "skill": "collectknowledge",
      "tool": null,
      "actor": null,
      "artifacts": [
        "docs/proposals/build-phasing-plan.html"
      ],
      "tags": [
        "phasing",
        "roadmap",
        "specify-input",
        "sequencing"
      ],
      "outcome": "success",
      "goal": "A reviewable build-phasing proposal to feed into /specify",
      "done_when": "Proposal in docs/proposals with phases, gates, deliverables, the ordering risk, stopping points and open questions; graph and audit current",
      "tier": "T2",
      "fan_out": 0,
      "git": {
        "sha": "da44afb216539c3a97091c89507d9adc1c32a545",
        "short": "da44afb21",
        "branch": "main",
        "pushed": false
      }
    }
  ],
  "changes": [
    {
      "id": "cl-01M1TFBP7H6PPCTP1TNKD6TJV3",
      "datetime": "2026-09-06T04:24:24Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "kind": "knowledge",
      "skill": "collectknowledge",
      "title": "Hydrofoil/surfboard CFD is two physics problems, and salt vs fresh is a parameter not a branch",
      "prompt": "look at solutions for CFD like openfoam and stanford su2 also modern efficienct approaches for CFD analysis for hydrofoils... implementing a simpler, smaller solution instead of a full blown cfd package... hydrofoils and surfboards in salt and freshwater... create a proposal in html",
      "summary": "Establishes the evidence base that shapes all downstream design: (1) a submerged foil and a planing board are distinct problems requiring distinct solver tiers - one application is reasonable, one solver is not; (2) salt vs fresh water differs by only +2.69% density and +4.44% kinematic viscosity at 15C per ITTC 7.5-02-01-03, so it must be modelled as a two-field fluid property record, never a solver branch; (3) the foiling envelope Re 5.5e5-1.6e6 sits at or above where LBM foil validation is established, making that the central technical risk; (4) the RTX 5090 Laptop holds ~396M LBM cells and a 43M-cell foil box runs at ~220 steps/s estimated, so hardware is not the binding constraint - scope and fidelity are.",
      "rationale": "Design decisions taken without this base would very likely have produced a single general solver attempting both problems, a salt/fresh code branch, and a performance plan resting on a desktop GPU benchmark that overstates this laptop by 2x. The base also records the strongest disconfirming argument - that XFLR5, Typhoon, FluidX3D and Savitsky already cover every component for free - which survives scrutiny and narrows the defensible project to an integrated application over established methods rather than a novel solver.",
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/index.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "cfd",
        "hydrofoil",
        "data-model",
        "gpu"
      ],
      "git": {
        "before": "691174f",
        "after": "691174f7693b635ef8416286fb4e5af4956886b8",
        "branch": "main",
        "pushed": true,
        "commits": []
      },
      "audit_ref": "al-01M1TFBA3YRHVQ1RQEFN9DG824"
    },
    {
      "id": "cl-01M1TH4THK5HF9GKF468CJNJ0K",
      "datetime": "2026-09-06T04:55:36Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "kind": "knowledge",
      "skill": "collectknowledge",
      "title": "Hydrofoil design is mostly a closed-form problem; simulation is reserved for the free surface",
      "prompt": "lets simplify, focus on hydrofoil only, deeper dive on algorithms/approach/architecture, section catalog, pre-simulation L/D estimation, water-sports design best practices, geometry catalog, parametric multi-surface grammar, update the proposal to v2",
      "summary": "Reverses the v1 framing. A chain of published closed forms (XFOIL section polars, Helmbold lift slope, lifting-line induced drag, ITTC 1957 friction with a Hoerner form factor, incipient-cavitation critical speed) answers most hydrofoil design questions in microseconds, and was executed against real water-sports geometry producing physically correct spans (95-107 cm), chords (8-19 cm) and the induced/friction crossover (77% induced at surf take-off, 3% at race speed). Cavitation does not bind below ~25 kn, so it is a check rather than a driver. Geometry is modelled as four concepts (assembly, surface, station, loft rule) in two layers, where a small generative design vector emits explicit stations one-way. Area, aspect ratio and span are derived from stations and never stored, because manufacturers' published aspect ratios use inconsistent area conventions. Scope narrowed to hydrofoil only; surfboard/planing material retired in place.",
      "rationale": "v1 framed the decision as which solver to build, which was wrong for this scope: it would have led to building simulation infrastructure to answer questions that have closed-form answers, and to an interface built around batch runs rather than live response. The evidence also forced two corrections that would otherwise have propagated: the IHS source is internally inconsistent on vapour pressure (its own critical-speed constant requires ITTC's 1670.9 Pa, not the 17000 Pa it advises), and a widely-cited secondary source published physically impossible aspect ratios, so its thickness guidance is Flagged rather than adopted. The recommendation changed accordingly from a two-tier solver to a layered design tool whose GPU tier is gated on validation.",
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/index.md",
        "docs/knowledge/cfd-hydrofoil-simulation/estimation-methods.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "cfd",
        "hydrofoil",
        "architecture",
        "estimation",
        "scope-change"
      ],
      "git": {
        "before": "6e3dbde",
        "after": "6e3dbdeda2156709800d31f7a0ec97345f4475ee",
        "branch": "knowledge/cfd-hydrofoil-simulation",
        "pushed": null,
        "commits": []
      },
      "audit_ref": "al-01M1TH4AFVMR2WQKGV48BK84S3"
    },
    {
      "id": "cl-01M1TJERDZ740404622K49HQ35",
      "datetime": "2026-09-06T05:18:30Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "kind": "knowledge",
      "skill": "collectknowledge",
      "title": "Thickness has no hydrodynamic optimum; it is a structural variable with a measured price",
      "prompt": "start phase-0 collecting evidence in knowledge and refining the proposal accordingly",
      "summary": "Phase 0 measurement replaced the base's largest Flagged claim with a computed result and reframed it. Section L/D and cavitation margin fall monotonically from 6 to 20 percent t/c at both Re 6e5 and 1e6, so thickness has no optimum: it is set by structure and costs efficiency (9 to 12 percent costs ~14 percent of section L/D and 3.8 kn of cavitation-free speed). Eleven sections vendored from UIUC with hashes and measured geometry; the Eppler hydrofoil set splits into a cambered lifting family (7.90-10.98 percent t/c) and a symmetric strut family (E836/E837/E838). E818 measured 42.1 kn cavitation-free against NACA 4412's 31.4 kn; NACA 64A410 recorded the best section L/D, confirming the IHS 6-series recommendation; section ranking flips between Re 6e5 and 1e6 so the catalog must rank per operating point. Typhoon identified as Tornado VLM under GPL v2+ in MATLAB.",
      "rationale": "The thickness guidance was previously a single retailer source whose adjacent tables published impossible aspect ratios, and it was load-bearing for a design tool's defaults. Measuring it did not just raise confidence, it changed the shape of the feature: presenting thickness as a parameter with an optimum would have sent designers hunting a maximum that does not exist, whereas presenting it as a structural constraint with a displayed cost matches the physics. The section measurements also produced a requirement the earlier drafts missed — ranking must be per operating point, because the ordering flips with Reynolds number. Typhoon's identification cuts both ways: it rules out reuse on licence and runtime grounds while independently corroborating the recommended VLM architecture. A parser defect caught during the pass (Lednicer files read as Selig, returning plausible wrong geometry) is recorded as a class with the analytic NACA check as its control.",
      "artifacts": [
        "docs/knowledge/cfd-hydrofoil-simulation/phase-0-findings.md",
        "docs/knowledge/cfd-hydrofoil-simulation/sections/manifest.md",
        "docs/proposals/cfd-bench-solver-strategy.html"
      ],
      "tags": [
        "phase-0",
        "thickness",
        "sections",
        "measurement"
      ],
      "git": {
        "before": "107e5ed",
        "after": "107e5ed817829d8b6156b64c3920eb2ba204f772",
        "branch": "main",
        "pushed": false,
        "commits": []
      },
      "audit_ref": "al-01M1TJE84RRX29SEDW48Y189Y7"
    },
    {
      "id": "cl-01M1VMGPYXER4XQNCMWE64DSE6",
      "datetime": "2026-09-06T15:13:45Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "kind": "knowledge",
      "skill": "collectknowledge",
      "title": "Design object narrowed to a single wing; CUDA verified on hardware; five knowledge bases added",
      "prompt": "continue building knowledge and proposals before specify; scope should be designing front or rear wings not the whole foil assembly; install CUDA; collectknowledge on OpenFOAM orchestration from C#, goal-driven design with constraints, CAD UX in C#, MCP/gcode/export, and visualization; produce proposals",
      "summary": "Three structural decisions. (1) SCOPE: the design object is a single lifting surface, front or rear, not the assembly. Whole-craft equilibrium, stability eigenvalues, decalage as a design variable and strut drag leave scope; the multi-surface grammar is retained as CONTEXT because a rear wing operates in the front wing's downwash and evaluating it in free stream is wrong. (2) CUDA verified on hardware: native sm_120 compiles and runs; measured 811.6 GB/s STREAM triad at 90.6 percent of the 896.1 GB/s theoretical read from the device; the v2 throughput estimate is corroborated to 0.02 percent. ILGPU is now moot for the decision since the native path is demonstrated. (3) Five knowledge bases establish the architecture beyond the solver: OpenFOAM has no library API so orchestration is a generation-plus-process problem behind one ICfdBackend interface with meshing as the real work; constraints, objectives and context are three different input types that must not share a widget, and the 10us estimator is what makes interactive optimisation possible at all; the CAD paradigm is direct manipulation of a constrained parametric model where the editable objects are five distribution curves and never the surface; STEP AP242 not STL is the fabrication format and mold generation needs B-Rep booleans, which is the concrete argument for the OCCT dependency; and there is NO VTK binding for .NET, so 3D flow rendering must be built on the same HelixToolkit viewport the CAD editor already needs.",
      "rationale": "The scope cut aligns the product with the model that was already there - the parametric grammar, section catalog, estimator and CAD editor all operate on a wing - while preserving the one piece of assembly context that is physically load-bearing. The CUDA verification removes the last toolchain risk from the simulation tier and converts the performance plan from transferred estimate to measured hardware, leaving a single transferred figure (LBM kernel efficiency) instead of an unverified chain. The five knowledge bases were needed before /specify because each contains at least one finding that changes the architecture rather than merely informing it: the absence of a VTK .NET binding forces a build-it-ourselves visualisation decision; STEP-over-STL forces the OCCT dependency question to be answered explicitly rather than drifted into; the constraint/objective/context distinction determines the shape of the primary UI; and OpenFOAM's file-and-process interface means there is no FFI problem to solve, which is a materially cheaper integration than assumed.",
      "artifacts": [
        "docs/knowledge/cfd-orchestration/index.md",
        "docs/knowledge/cad-ux-and-geometry/index.md",
        "docs/knowledge/flow-visualization/index.md",
        "docs/proposals/goal-driven-design-experience.html"
      ],
      "tags": [
        "scope-change",
        "cuda",
        "architecture",
        "cad-ux",
        "visualization"
      ],
      "git": {
        "before": "e7ec6d8",
        "after": "e7ec6d8c4bd9721994342c7a90db1684ab05c42c",
        "branch": "main",
        "pushed": false,
        "commits": []
      },
      "audit_ref": "al-01M1VMG1WKK82JD7KTDQGQSYJM"
    },
    {
      "id": "cl-01M1VNP7E4DHJ2TKYX1VCVA0MG",
      "datetime": "2026-09-06T15:34:15Z",
      "session": "session_01XPJgQ4SAUcpSmsd3oJbfuj",
      "kind": "decision",
      "skill": "collectknowledge",
      "title": "No B-Rep kernel required; permissive-only dependencies; sixteen knowledge gaps identified",
      "prompt": "defer occt, avoid LGPL where possible, MIT/Apache alternative or implement our own; import can be our own format; review the proposals end to end for missing knowledge",
      "summary": "Three decisions and one review. (1) OCCT deferred indefinitely: LGPL-2.1 section 6 requires shipping the OCCT sources used and ensuring users can relink against a modified OCCT, which is the entanglement to avoid regardless of commercial intent. rhino3dm (MIT) covers NURBS if needed; STEPcode (BSD) or a bounded own writer covers STEP, with OpenVSP as proof that a lofted parametric surface reaches AP203 using only B_SPLINE_SURFACE_WITH_KNOTS. (2) No B-Rep kernel is needed at all — the only requirements that would need one are mold-block booleans (already scoped out; molds belong in CAM) and arbitrary B-Rep import (now scoped out by the decision that import reads our own saved format). (3) Verification-at-a-higher-tier confirmed as a standing commitment. The end-to-end review found 16 knowledge gaps and 2 process gaps, with structures, the user, units conventions and validation data as Tier 1.",
      "rationale": "The licensing question turned out to change the architecture rather than just the dependency list: asking whether a permissive alternative existed forced an audit of what a kernel was actually for, and the audit showed that on this scope it is for two things we had already scoped out. That is a materially simpler system, not a compromise. The gap review was run because four proposals now exist and the next step is /specify, which would otherwise bake in assumptions — two of which turned out to be load-bearing: nothing in the stack models structure, yet Phase 0 established that thickness is set by structure, so the tool has a variable decided entirely by physics it cannot see; and three UX proposals have been written with no user research at all, while the pack's UX Researcher lens holding the specification veto has never been convened. The validation gap partially closed during the review itself, and the data found independently corroborates the Phase 0 section ranking from a third direction.",
      "artifacts": [
        "docs/notes/decision-0001-defer-geometry-kernel.md",
        "docs/knowledge/knowledge-gap-register.md",
        "docs/backlog.md"
      ],
      "tags": [
        "licensing",
        "architecture",
        "gaps",
        "scope-change"
      ],
      "git": {
        "before": "4f381d0",
        "after": "4f381d032382c7093e9e18e810fcc28bf7e19f8b",
        "branch": "main",
        "pushed": false,
        "commits": []
      },
      "audit_ref": "al-01M1VNN7EV3YWHTNRQJVJP5PCB"
    }
  ]
};
