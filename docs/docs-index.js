// Derived from artifact frontmatter by scripts/docs-graph.py — DO NOT hand-edit (frontmatter wins; see knowledge-visualization.md V2/V18).
window.DOCS_INDEX = {
  "schemaVersion": "docs-index/v2",
  "project": "cfd-bench",
  "generator": "docs-graph.py derive",
  "rootId": "audit-log",
  "artifactTypes": [
    "knowledge",
    "glossary",
    "spec",
    "architecture",
    "adr",
    "design",
    "design-language",
    "investigation",
    "proof-pack",
    "decision-note",
    "threat-model",
    "privacy-review",
    "api",
    "source",
    "doc",
    "index"
  ],
  "relationRegistry": [
    "implements",
    "refines",
    "depends-on",
    "supersedes",
    "tested-by",
    "documents",
    "uses-term",
    "relates-to"
  ],
  "policyVersion": "traversal-policy/v1",
  "policySha256": "968b035a9618e6f997592e4f7ae91fd412b1c059c0ee89d6d8ff3025c26279fd",
  "traversalPolicies": {
    "grounding": [
      {
        "rel": "implements",
        "direction": "outbound",
        "priority": 0
      },
      {
        "rel": "refines",
        "direction": "outbound",
        "priority": 1
      },
      {
        "rel": "depends-on",
        "direction": "outbound",
        "priority": 2
      },
      {
        "rel": "uses-term",
        "direction": "outbound",
        "priority": 3
      },
      {
        "rel": "tested-by",
        "direction": "outbound",
        "priority": 4
      },
      {
        "rel": "documents",
        "direction": "outbound",
        "priority": 5
      }
    ],
    "impact": [
      {
        "rel": "implements",
        "direction": "inbound",
        "priority": 0
      },
      {
        "rel": "refines",
        "direction": "inbound",
        "priority": 1
      },
      {
        "rel": "depends-on",
        "direction": "inbound",
        "priority": 2
      },
      {
        "rel": "tested-by",
        "direction": "inbound",
        "priority": 3
      },
      {
        "rel": "uses-term",
        "direction": "inbound",
        "priority": 4
      }
    ],
    "proof": [
      {
        "rel": "tested-by",
        "direction": "outbound",
        "priority": 0
      }
    ],
    "explore-neighborhood": [
      {
        "rel": "depends-on",
        "direction": "outbound",
        "priority": 0
      },
      {
        "rel": "depends-on",
        "direction": "inbound",
        "priority": 0
      },
      {
        "rel": "documents",
        "direction": "outbound",
        "priority": 1
      },
      {
        "rel": "documents",
        "direction": "inbound",
        "priority": 1
      },
      {
        "rel": "implements",
        "direction": "outbound",
        "priority": 2
      },
      {
        "rel": "implements",
        "direction": "inbound",
        "priority": 2
      },
      {
        "rel": "refines",
        "direction": "outbound",
        "priority": 3
      },
      {
        "rel": "refines",
        "direction": "inbound",
        "priority": 3
      },
      {
        "rel": "relates-to",
        "direction": "outbound",
        "priority": 4
      },
      {
        "rel": "relates-to",
        "direction": "inbound",
        "priority": 4
      },
      {
        "rel": "supersedes",
        "direction": "outbound",
        "priority": 5
      },
      {
        "rel": "supersedes",
        "direction": "inbound",
        "priority": 5
      },
      {
        "rel": "tested-by",
        "direction": "outbound",
        "priority": 6
      },
      {
        "rel": "tested-by",
        "direction": "inbound",
        "priority": 6
      },
      {
        "rel": "uses-term",
        "direction": "outbound",
        "priority": 7
      },
      {
        "rel": "uses-term",
        "direction": "inbound",
        "priority": 7
      }
    ]
  },
  "limits": {
    "indexBytes": 5242880,
    "artifacts": 1000,
    "relationships": 5000,
    "spatialNodes": 500,
    "spatialEdges": 1000,
    "visibleLabels": 150,
    "surfaces": 100
  },
  "artifacts": [
    {
      "id": "decision-0001-geometry-kernel",
      "path": "docs/notes/decision-0001-defer-geometry-kernel.md",
      "title": "Defer OCCT; Take the Permissive Geometry Path",
      "type": "decision-note",
      "status": "accepted",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2027-03-06",
      "reviewSuggested": [],
      "summary": "OCCT is deferred and probably permanently avoidable. LGPL-2.1 section 6 obligations are the taint the user wants to escape, and a fully permissive path exists — rhino3dm under MIT for NURBS, and STEPcode under BSD (or a bounded own implementation) for STEP export, which OpenVSP already proves works for exactly our one surface type.",
      "tags": [
        "licensing",
        "geometry",
        "occt",
        "rhino3dm",
        "stepcode",
        "step-export"
      ],
      "links": [
        {
          "to": "kb-cad-ux-geometry",
          "rel": "depends-on"
        },
        {
          "to": "kb-fabrication-interop",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "ad9fcedf0ec192bc8780403d34f031b9e17196c3f7ab7ebe01baf8258789b517"
    },
    {
      "id": "audit-log",
      "path": "docs/audit/audit-log.md",
      "title": "Audit & Change Log",
      "type": "doc",
      "status": "accepted",
      "owner": "@maintainers",
      "phase": "",
      "reviewBy": "2027-09-06",
      "reviewSuggested": [],
      "summary": "The durable, committed history of what was prompted, done, and decided in this repository, so work compounds across sessions. The two JSONL files are the source of truth; audit-data.js and index.html are derived projections.",
      "tags": [
        "audit",
        "history",
        "change-log",
        "project-memory"
      ],
      "links": [],
      "diagrams": [],
      "sourceSha256": "f0b6d9b5fd78da97bbc40a9dedcc884f48ee2d79f68a66beaa182a9948d8f534"
    },
    {
      "id": "backlog",
      "path": "docs/backlog.md",
      "title": "Deferred Work and Spikes",
      "type": "doc",
      "status": "accepted",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-06",
      "reviewSuggested": [],
      "summary": "Work that has been consciously deferred rather than forgotten — spikes with a stated question and a definition of done, decisions waiting on evidence, and the standing engineering commitments this project has made to itself.",
      "tags": [
        "backlog",
        "spikes",
        "todo",
        "deferred",
        "ai",
        "evals"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "depends-on"
        },
        {
          "to": "decision-0001-geometry-kernel",
          "rel": "depends-on"
        },
        {
          "to": "kb-ai-in-the-product",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "53f1aa87cda645497ad9d834f9888fa0f7099ff5a61f040f764e43d4974adb67"
    },
    {
      "id": "glossary-cfd-hydrofoil",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/glossary.md",
      "title": "Glossary — Hydrofoil and CFD Ubiquitous Language",
      "type": "glossary",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "The domain's ubiquitous language for hydrofoil and planing-craft simulation — the exact terms to use in code, specs and UI, each with its near-miss disambiguation so the vocabulary resolves identically across artifacts and sessions.",
      "tags": [
        "glossary",
        "ubiquitous-language",
        "cfd",
        "hydrofoil"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "a1370d492bbe2485c564b0c58865371469bd855eb17105bcacd5422974a531da"
    },
    {
      "id": "kb-ai-in-the-product",
      "path": "docs/knowledge/ai-in-the-product/index.md",
      "title": "LLMs Inside an Engineering Tool",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-06",
      "reviewSuggested": [],
      "summary": "Where a language model belongs in a deterministic engineering tool and where it must not go — the language/numbers boundary that keeps non-determinism out of the solver path, the capability inventory ranked by value over risk, the eval each capability needs before it ships, and the measured Claude API cost and C# integration surface.",
      "tags": [
        "llm",
        "claude-api",
        "ai-ux",
        "evals",
        "structured-outputs",
        "prompt-caching",
        "csharp"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-design-automation",
          "rel": "refines"
        },
        {
          "to": "knowledge-gap-register",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "61d83202330b7215c8f6de25472f4d6c2776ad1670edcac087ed2ce2f5f6543f"
    },
    {
      "id": "kb-cad-ux-geometry",
      "path": "docs/knowledge/cad-ux-and-geometry/index.md",
      "title": "CAD UX Paradigms and the .NET Geometry Stack",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-05",
      "reviewSuggested": [],
      "summary": "The three CAD interaction paradigms and which fits a foil editor, what Shape3d and Rhino actually do at the control-point level, the continuity and curvature-comb vocabulary a surface editor must speak, and the concrete .NET stack — HelixToolkit for the viewport and a fully permissive geometry path (rhino3dm MIT, STEPcode BSD) that removes the need for a B-Rep kernel entirely.",
      "tags": [
        "cad",
        "ux",
        "wpf",
        "nurbs",
        "helixtoolkit",
        "rhino3dm",
        "stepcode",
        "licensing",
        "splines",
        "shape3d"
      ],
      "links": [
        {
          "to": "kb-cfd-parametric-geometry",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "decision-0001-geometry-kernel",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "a1e8ec5dfd0cc09b3b0446aff4a7926602cb2fb48800bff2ce168f70708bf5b1"
    },
    {
      "id": "kb-cfd-comparables",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/comparables.md",
      "title": "Comparable Solutions — Foil and CFD Tools",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Named prior art across three bands — full CFD packages, GPU LBM solvers, and small foil-design tools — with what each does well and badly. Establishes that the small-tool band is already occupied by XFLR5, Typhoon and FoilBoard, which any new tool must beat rather than duplicate.",
      "tags": [
        "comparables",
        "prior-art",
        "xflr5",
        "typhoon",
        "fluidx3d",
        "openfoam",
        "su2"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "cb5b326465d026e32c137459983641d1cc594606e00a98cc99560e3b27bd1b3b"
    },
    {
      "id": "kb-cfd-data-and-constants",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/data-and-constants.md",
      "title": "Domain Data, Constants and Invariants",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Primary-source fluid properties for fresh water and standard seawater from ITTC 7.5-02-01-03, the non-dimensional groups that govern this problem, the derived Reynolds envelope for foiling, and the computed GPU memory and throughput budget for the target machine.",
      "tags": [
        "constants",
        "ittc",
        "seawater",
        "reynolds",
        "froude",
        "gpu-budget"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "ce6c7297737bf2fc2057a68cc646e104169bdc5b911fb1ab5805d3ac22132cd0"
    },
    {
      "id": "kb-cfd-estimation-methods",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/estimation-methods.md",
      "title": "Pre-Simulation Estimation Methods",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "The closed-form chain that estimates L/D, Cl/Cd and cavitation margin for a 3D hydrofoil before any simulation runs — section polars, Helmbold lift slope, lifting-line induced drag, ITTC skin friction with a Hoerner form factor, and the incipient-cavitation critical speed — with every formula sourced and the whole chain executed against real water-sports geometry.",
      "tags": [
        "estimation",
        "lifting-line",
        "helmbold",
        "ittc",
        "cavitation",
        "xfoil",
        "algorithms"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-foil-sections",
          "rel": "depends-on"
        },
        {
          "to": "glossary-cfd-hydrofoil",
          "rel": "uses-term"
        }
      ],
      "diagrams": [],
      "sourceSha256": "2a9714b8139dcf7b87768e5afc3422880842c3ebe00eb165ddfc00d302a714e9"
    },
    {
      "id": "kb-cfd-foil-sections",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/foil-sections.md",
      "title": "Foil Section Catalog and Selection",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "The 2D section families relevant to water-sports hydrofoils — the Eppler hydrofoil series, the NACA 16- and 6-series, and the wider low-Reynolds catalog — with the design criteria that select between them, the sources the coordinates come from, and the data model a catalog needs.",
      "tags": [
        "sections",
        "airfoil",
        "eppler",
        "naca",
        "catalog",
        "cavitation",
        "selection"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "glossary-cfd-hydrofoil",
          "rel": "uses-term"
        }
      ],
      "diagrams": [],
      "sourceSha256": "f9c74d828e322fa187c7eefd569216bf1afd558275a31c04689c70bfecd37683"
    },
    {
      "id": "kb-cfd-hydrofoil-simulation",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/index.md",
      "title": "Small-Footprint CFD for Water-Sports Hydrofoils",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "pre-specification",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Evidence base for a small, local design and simulation tool for water-sports hydrofoils — surf, SUP/downwind, wing and windsurf foiling — on a single Windows/NVIDIA machine. Establishes the closed-form estimation chain that answers most design questions in microseconds, the section and geometry catalogs, a four-concept parametric grammar, and the narrow band where simulation is actually required.",
      "tags": [
        "cfd",
        "hydrofoil",
        "lbm",
        "gpu",
        "cuda",
        "marine-hydrodynamics",
        "water-sports"
      ],
      "links": [
        {
          "to": "kb-cfd-state-of-the-art",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-comparables",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-references",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-data-and-constants",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-foil-sections",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-estimation-methods",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-watersports-practice",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-parametric-geometry",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-phase-0-findings",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-section-manifest",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-open-questions",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-sources",
          "rel": "refines"
        },
        {
          "to": "glossary-cfd-hydrofoil",
          "rel": "uses-term"
        }
      ],
      "diagrams": [],
      "sourceSha256": "40d1cb8ed98c75a61b433f26a7fcbc8c9f76aa054ea2e9cc342867c89f80b848"
    },
    {
      "id": "kb-cfd-open-questions",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/open-questions.md",
      "title": "Open Questions and Domain Failure Modes",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "What the research could not settle, the ways this domain silently produces wrong answers, and the disconfirming views deliberately sought against the headline findings — including the strongest argument for not building this at all.",
      "tags": [
        "open-questions",
        "risks",
        "failure-modes",
        "disconfirming"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "5b721f6ee292e9ad7a234442232946974069680e7d91914c5f1c00001402de5e"
    },
    {
      "id": "kb-cfd-orchestration",
      "path": "docs/knowledge/cfd-orchestration/index.md",
      "title": "Orchestrating OpenFOAM and SU2 from a C# Application",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-05",
      "reviewSuggested": [],
      "summary": "How a C# desktop application can drive OpenFOAM and SU2 without the user ever seeing a dictionary file — the case-generation layer, the four candidate execution substrates on Windows, the interop boundary that keeps solvers replaceable, and what cloud execution costs.",
      "tags": [
        "openfoam",
        "su2",
        "orchestration",
        "interop",
        "docker",
        "wsl",
        "cloud",
        "csharp"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "56bc896bbfadb69e0919d9dc5edfc4ae3b9df20f60e275a80f0e894730766925"
    },
    {
      "id": "kb-cfd-parametric-geometry",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/parametric-geometry.md",
      "title": "Parametric Multi-Surface Foil Geometry",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "How to describe a complete 3D hydrofoil assembly parametrically — CST section parameterisation, a four-concept station-and-loft grammar covering front wing, stabiliser and strut alike, and a two-layer split between a small generative design vector and explicit geometry.",
      "tags": [
        "parametric",
        "cst",
        "kulfan",
        "geometry",
        "grammar",
        "loft",
        "openvsp",
        "avl"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-foil-sections",
          "rel": "depends-on"
        },
        {
          "to": "glossary-cfd-hydrofoil",
          "rel": "uses-term"
        }
      ],
      "diagrams": [],
      "sourceSha256": "772913086e9dfb8817b2a7f6809936118b84bb35cea48e1beab944f51759b60b"
    },
    {
      "id": "kb-cfd-phase-0-findings",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/phase-0-findings.md",
      "title": "Phase 0 Findings — Evidence Gaps Closed by Measurement",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Results of the Phase 0 evidence pass — the thickness question answered by computed section polars, the Eppler hydrofoil set measured head-to-head against NACA baselines, Typhoon identified as Tornado VLM under GPL, and a working section-analysis toolchain established without XFOIL.",
      "tags": [
        "phase-0",
        "measurement",
        "thickness",
        "sections",
        "typhoon",
        "neuralfoil",
        "evidence"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-foil-sections",
          "rel": "depends-on"
        },
        {
          "to": "kb-cfd-estimation-methods",
          "rel": "depends-on"
        },
        {
          "to": "kb-cfd-section-manifest",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "d21b3f53622731d65bf9917f44ecc7cb29ed004bf0e4e9908d5ef0649b2c1251"
    },
    {
      "id": "kb-cfd-references",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/references.md",
      "title": "Reference Standards, Specifications and Seminal Works",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "The standards, specifications and seminal works this project must honour — ITTC water properties, IAPWS/TEOS-10, NVIDIA Blackwell compatibility, and the foundational method papers for planing hulls, potential-flow foil analysis and lattice Boltzmann.",
      "tags": [
        "references",
        "standards",
        "ittc",
        "iapws",
        "teos-10",
        "savitsky"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "5e65c270cb85405cf4e99e87122aa4bd5cf6ad8c709f9e3fe0ad4ef90368ed1e"
    },
    {
      "id": "kb-cfd-section-manifest",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/sections/manifest.md",
      "title": "Vendored Section Coordinate Manifest",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Provenance record for the section coordinate files vendored into this repo from the UIUC Airfoil Data Site, with geometry measured from the coordinates themselves and a parser verified against analytic NACA truth.",
      "tags": [
        "sections",
        "coordinates",
        "provenance",
        "catalog",
        "phase-0"
      ],
      "links": [
        {
          "to": "kb-cfd-foil-sections",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "0ceeaeafcf5da133054c0cf909cfd2842a06f79c985c8062ac4abb75535dac50"
    },
    {
      "id": "kb-cfd-sources",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/sources.md",
      "title": "Sources",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Full source list with access dates and the specific claim each supports, so every confidence label in this knowledge base is traceable to the evidence that produced it.",
      "tags": [
        "sources",
        "citations",
        "provenance"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "e57b89705e682e261a00a830b6a60c24c4a19e0495d261eeccbfa37a2c2e75ee"
    },
    {
      "id": "kb-cfd-state-of-the-art",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/state-of-the-art.md",
      "title": "State of the Art — Hydrofoil and Planing-Craft Simulation",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Current best-practice methods for hydrofoil and planing-craft hydrodynamics, ordered by cost: empirical correlations, potential-flow panel/VLM methods, GPU lattice Boltzmann, RANS+VOF, and ML surrogates — with where each wins and where each fails.",
      "tags": [
        "cfd",
        "state-of-the-art",
        "lbm",
        "panel-method",
        "rans",
        "surrogate"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "c015eee7083db205d4a00b420b80e1e2838531438886683c3358fc741d1a7494"
    },
    {
      "id": "kb-cfd-watersports-practice",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/watersports-design-practice.md",
      "title": "Water-Sports Hydrofoil Design Practice and Geometry Catalog",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Design practice and a geometry catalog for surf, SUP/downwind, wing and windsurf/race foiling — aspect-ratio bands with the formula and its measurement ambiguity, planform and thickness guidance, stabiliser sizing, and the low-speed-lift versus glide trade-off that separates the disciplines.",
      "tags": [
        "design-practice",
        "aspect-ratio",
        "geometry",
        "surf-foil",
        "downwind",
        "wing-foil",
        "windsurf"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-estimation-methods",
          "rel": "depends-on"
        },
        {
          "to": "glossary-cfd-hydrofoil",
          "rel": "uses-term"
        }
      ],
      "diagrams": [],
      "sourceSha256": "007dac5f0e95e9ea2a7409705f5113b054e0919f7d3bc1d30c67eac285b71065"
    },
    {
      "id": "kb-design-automation",
      "path": "docs/knowledge/design-automation/index.md",
      "title": "Goal-Driven Design, Constraints and Interactive Optimisation",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-05",
      "reviewSuggested": [],
      "summary": "Evidence for turning a stated design goal and a set of constraints into a proposed wing — the distinction between constraints and objectives, interactive multi-objective optimisation with a low-fidelity solver in the loop, Pareto-front interaction patterns, and why the estimation chain is what makes any of it feasible.",
      "tags": [
        "optimization",
        "constraints",
        "pareto",
        "surrogate",
        "design-space",
        "interaction"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-estimation-methods",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "f8440987728abce7d22ea7379f9009bfd1a989d0be8419c7b7885d1c058dce87"
    },
    {
      "id": "kb-fabrication-interop",
      "path": "docs/knowledge/fabrication-and-interop/index.md",
      "title": "Fabrication, Export Formats and CAD Interoperability",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-05",
      "reviewSuggested": [],
      "summary": "What format a foil should leave the tool in for each destination — STEP for machining, STL/3MF for printing — why STL is the wrong answer for a mold, where CAM and G-code generation sit, and an honest ranking of what CAD MCP servers can and cannot model today.",
      "tags": [
        "export",
        "step",
        "stl",
        "3mf",
        "cam",
        "gcode",
        "mcp",
        "cad-interop",
        "molds"
      ],
      "links": [
        {
          "to": "kb-cad-ux-geometry",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "32ecd9c83983d7c3bb601508ccf8299b1d7c7c84b024e1e71ff0a028fb8d8198"
    },
    {
      "id": "kb-flow-visualization",
      "path": "docs/knowledge/flow-visualization/index.md",
      "title": "Analysis Charts and Flow Visualisation for Foil Design",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-05",
      "reviewSuggested": [],
      "summary": "The chart set that actually diagnoses a foil, the quasi-3D coupling that makes a 2D section view at a spanwise station physically meaningful, streamline and LIC techniques for 2D and 3D flow, and the .NET libraries for plotting and video export — including the gap where VTK has no .NET binding.",
      "tags": [
        "visualization",
        "charts",
        "cp",
        "polars",
        "streamlines",
        "lic",
        "video",
        "scottplot"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-estimation-methods",
          "rel": "depends-on"
        }
      ],
      "diagrams": [],
      "sourceSha256": "f61df53b34799c6a19a0d8d535d11f085beeb1d68ee4935d3fe537f03aa5e8d2"
    },
    {
      "id": "knowledge-gap-register",
      "path": "docs/knowledge/knowledge-gap-register.md",
      "title": "Knowledge Gap Register — What the End-to-End Is Missing",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "",
      "reviewBy": "2026-12-06",
      "reviewSuggested": [],
      "summary": "A deliberate sweep of the whole design-to-fabrication chain for knowledge we have not gathered. Sixteen gaps ranked by whether they block, reshape, or merely inform — with the two that would most change the product named explicitly, and two process gaps in how this project has been run.",
      "tags": [
        "gaps",
        "review",
        "end-to-end",
        "validation",
        "structures",
        "unsteady",
        "process"
      ],
      "links": [
        {
          "to": "kb-cfd-hydrofoil-simulation",
          "rel": "refines"
        },
        {
          "to": "kb-design-automation",
          "rel": "refines"
        },
        {
          "to": "kb-cad-ux-geometry",
          "rel": "refines"
        },
        {
          "to": "kb-flow-visualization",
          "rel": "refines"
        },
        {
          "to": "kb-fabrication-interop",
          "rel": "refines"
        },
        {
          "to": "kb-cfd-orchestration",
          "rel": "refines"
        }
      ],
      "diagrams": [],
      "sourceSha256": "d4daf28cdb09e62ba46a3593c2c260743f20f929bf5cd3282ef680131a3e366e"
    }
  ],
  "surfaces": [
    {
      "id": "surface-audit-index",
      "path": "docs/audit/index.html",
      "title": "cfd-bench — Audit & Change Log",
      "kind": "audit",
      "description": "Browse the committed audit and change timeline.",
      "artifactId": "audit-log"
    },
    {
      "id": "surface-proposals-ai-augmentation-experience",
      "path": "docs/proposals/ai-augmentation-experience.html",
      "title": "AI in the Foil Designer",
      "kind": "knowledge-tool",
      "description": "Open an interactive knowledge artifact."
    },
    {
      "id": "surface-proposals-cfd-bench-solver-strategy",
      "path": "docs/proposals/cfd-bench-solver-strategy.html",
      "title": "CFD-Bench Solver Strategy",
      "kind": "knowledge-tool",
      "description": "Open an interactive knowledge artifact."
    },
    {
      "id": "surface-proposals-visualisation-experience",
      "path": "docs/proposals/visualisation-experience.html",
      "title": "Foil Visualisation",
      "kind": "knowledge-tool",
      "description": "Open an interactive knowledge artifact."
    },
    {
      "id": "surface-proposals-goal-driven-design-experience",
      "path": "docs/proposals/goal-driven-design-experience.html",
      "title": "Goal-Driven Wing Design",
      "kind": "knowledge-tool",
      "description": "Open an interactive knowledge artifact."
    },
    {
      "id": "surface-proposals-cad-modelling-experience",
      "path": "docs/proposals/cad-modelling-experience.html",
      "title": "Wing Modelling Experience",
      "kind": "knowledge-tool",
      "description": "Open an interactive knowledge artifact."
    }
  ],
  "graphSha256": "e81ddfbd1e503c7b06c713e039a7d4226d9f6890b0174f759fdccdf2dd4377fc"
};
