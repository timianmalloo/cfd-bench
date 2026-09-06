// Derived from docs/audit/*.jsonl by scripts/audit-log.py — DO NOT hand-edit (the JSONL logs are the source of truth; see audit-and-change-log.md).
window.AUDIT_DATA = {
  "project": "cfd-bench",
  "generated": "2026-09-06T05:18:30Z",
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
    }
  ]
};
