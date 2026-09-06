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
      "sourceSha256": "89f18807b7ae9692766237fc7b486b700c5681d075e45bc1d299d70c76aee0db"
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
      "sourceSha256": "fd99b44775a234aa93db0bf1838706bd85d7c4924c6e1fce60f7d76f359cf8d7"
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
      "id": "kb-cfd-hydrofoil-simulation",
      "path": "docs/knowledge/cfd-hydrofoil-simulation/index.md",
      "title": "Small-Footprint CFD for Hydrofoils and Surfboards",
      "type": "knowledge",
      "status": "draft",
      "owner": "@timianmalloo",
      "phase": "pre-specification",
      "reviewBy": "2026-12-04",
      "reviewSuggested": [],
      "summary": "Evidence base for building a small, local CFD tool for hydrofoils and surfboards in salt and fresh water on a single Windows/NVIDIA machine. Establishes that salt vs fresh is a parameter change rather than a physics change, that the foiling Reynolds envelope is 5.5e5-1.6e6, that this laptop's GPU is not the binding constraint, and that hydrofoils and surfboards are two distinct physics problems requiring two different solver tiers.",
      "tags": [
        "cfd",
        "hydrofoil",
        "surfboard",
        "lbm",
        "gpu",
        "cuda",
        "marine-hydrodynamics"
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
      "sourceSha256": "63bbb5670e4b1297d109697ecc42c0e4bfeeb8d6df67fac0500952fa90cc33f4"
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
      "sourceSha256": "f9850672ab213a542431e5e1bc00764a855d3445bef3edf12e45d1fa332494c7"
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
      "sourceSha256": "cf13cf055a062b86f5f97a4e08206b9370ccb025f16ce5b967766db1a7f7b938"
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
      "sourceSha256": "cd4bfeca282d8b71d04069f5d091a927290562a20c0377ef5c63498bf6ad8cf4"
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
    }
  ],
  "graphSha256": "f06610aa14b5a8b4c93fd6d8b626d334c3c80de61ba659d9f8062115b6e02d29"
};
