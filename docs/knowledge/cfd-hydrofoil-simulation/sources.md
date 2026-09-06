---
id: kb-cfd-sources
title: "Sources"
type: knowledge
status: draft
owner: "@timianmalloo"
tags: [sources, citations, provenance]
links:
  - { to: kb-cfd-hydrofoil-simulation, rel: refines }
review-by: 2026-12-04
summary: >-
  Full source list with access dates and the specific claim each supports, so every confidence label
  in this knowledge base is traceable to the evidence that produced it.
---

# Sources

All accessed **2026-09-05**.

| # | Title / source | Type | URL | Used for |
|---|---|---|---|---|
| 1 | ITTC 7.5-02-01-03 Rev 02, Fresh Water and Seawater Properties | standard (primary) | https://www.ittc.info/media/9585/75-02-01-03.pdf | All density / viscosity / vapour-pressure values; standard salinity 35.16504 g/kg; IAPWS + TEOS-10 basis. Tables read directly from the PDF |
| 2 | FluidX3D (ProjectPhysX) | primary repo | https://github.com/ProjectPhysX/FluidX3D | 93 and 55 B/cell; 19,141 MLUPs/s desktop RTX 5090; OpenCL not CUDA; no AMR; free-surface VOF+PLIC; Smagorinsky-Lilly; force/torque extraction; non-commercial licence |
| 3 | ILGPU | primary repo + releases | https://github.com/m4rs-mt/ILGPU/releases | v1.5.3 (July 2024) is current; no sm_120/Blackwell mention; NCSA licence; .NET 6.0 / VS2022 toolchain |
| 4 | NVIDIA Blackwell Compatibility Guide | vendor standard | https://docs.nvidia.com/cuda/blackwell-compatibility-guide/ | CUDA 12.8 minimum for native sm_120; PTX forward-compatibility rule |
| 5 | Typhoon (Ghent University) | primary | https://typhoon.ugent.be/ | Static forces/moments; Newton-Raphson equilibrium; eigenvalue stability; open source. Numerical method not documented |
| 6 | SU2 AIAA papers (Stanford ADL) | primary | https://su2code.github.io/documents/SU2_AIAA_SciTech2014.pdf | Compressible RANS core; incompressible/artificial compressibility; level-set free surface; adjoint optimisation focus |
| 7 | Free surface flows around shallowly submerged hydrofoil by OpenFOAM | secondary (peer-reviewed) | https://www.sciencedirect.com/science/article/abs/pii/S0029801815001365 | interFoam applied to submerged hydrofoils |
| 8 | Beyond VoF: alternative OpenFOAM solvers for numerical wave tanks | secondary (peer-reviewed) | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7608737/ | interFoam free-surface wiggles, light-phase acceleration, VOF sub-cycling; VOF resolution and time-step cost |
| 9 | Vortex Lattice Method for sailing yacht foil design vs RANS | secondary (peer-reviewed) | https://link.springer.com/article/10.1007/s12008-025-02378-4 | VLM meshes surfaces only; orders of magnitude faster than RANS; validity limited to small alpha, attached flow, high Re |
| 10 | A new non-linear vortex lattice method | secondary (peer-reviewed) | https://www.sciencedirect.com/science/article/pii/S1000936116300954 | Non-linear VLM at ~1% of CFD execution time |
| 11 | XFLR5 project discussions and analysis guide | secondary (practitioner) | https://sourceforge.net/p/xflr5/discussion/679396/ | VLM/panel methods are linear; stall not represented; XFOIL polar interpolation assumes infinite-wing behaviour; convergence issues |
| 12 | On the ventilation of surface-piercing hydrofoils under steady-state conditions | primary (JFM) | https://arxiv.org/pdf/2503.18015 | FW/PV/FV regimes and stability regions; ventilation onset requires air ingress into separated sub-atmospheric flow; washout via re-entrant jet |
| 13 | Ventilated cavities on a surface-piercing hydrofoil at moderate Froude numbers | primary (JFM) | https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/abs/ventilated-cavities-on-a-surfacepiercing-hydrofoil-at-moderate-froude-numbers/3A3C55533CD1A36BAA53B4AA2102C068 | Froude-number thresholds for tail ventilation; free-surface drawdown of about c/2 |
| 14 | Savitsky method literature (optimum trim, planing prediction) | secondary (peer-reviewed) | https://www.researchgate.net/publication/357321148 | Savitsky 1964 basis; prismatic hulls, deadrise, trim, L/B; ignores lateral wave-making and spray; calm-water steady-state limits |
| 15 | RANS Simulation of Dynamic Trim and Sinkage of a Planing Hull | secondary (peer-reviewed) | https://pubs.sciepub.com/amp/1/1/2/index.html | RANS+VOF with SST k-omega and overset for free trim/sinkage; divergence beyond V/sqrt(L) greater than 2.79 |
| 16 | Physics-informed data-driven near-wall modelling for LBM at high Re | primary (Nature Comms Physics) | https://www.nature.com/articles/s42005-024-01832-1 | Bounce-back mispredicts wall shear on coarse grids at high Re; data-driven near-wall models to friction-Re 1e6 |
| 17 | A wall function approach in lattice Boltzmann method | primary (arXiv) | https://arxiv.org/pdf/2009.04352 | Wall-function bounce-back (WFB); BGK collision operator limits high-Re application |
| 18 | Lattice Boltzmann wall boundary conditions for RANS | primary (arXiv) | https://arxiv.org/pdf/2506.03905 | RANS-coupled LBM wall treatment; cost of resolving wall layers at high Re |
| 19 | Deep neural operators as accurate surrogates for shape optimization | primary (arXiv) | https://arxiv.org/pdf/2302.00807 | DeepONet generalisation; orders-of-magnitude online speedup with little accuracy loss |
| 20 | Airfoil aerodynamic performance prediction using ML and surrogate modeling | secondary (peer-reviewed) | https://pmc.ncbi.nlm.nih.gov/articles/PMC11024608/ | Surrogate accuracy degrades for high-drag samples; training-distribution dependence |
| 21 | NVIDIA GeForce RTX 5090 Laptop GPU specifications | vendor/secondary | https://laptopmedia.com/video-card/nvidia-geforce-rtx-5090-laptop/ | 24 GB GDDR7, 256-bit, 896 GB/s — the bandwidth used to scale the throughput estimate (Flagged: not read from the device) |
| 22 | FoilBoard and community foil tools | secondary (practitioner) | https://github.com/dmitrynizh/foilboard | Band C prior art; FoilBoard real-time-feedback positioning; WingHopper XFLR5 XML export |
| 23 | Kiteboarding hydrofoil design Reynolds discussion | secondary (practitioner) | https://www.boatdesign.net/threads/kiteboarding-hydrofoil-design-for-reynolds-600k-1-5mm.59452/ | Foiling speed bands: racers 22-35 kn (~1e6 Re), free riders 12-22 kn (~6.5e5), surfers 5-12 kn |
| 24 | Local machine probe (nvidia-smi, dotnet --list-sdks, vswhere) | primary (direct measurement) | n/a — this machine, 2026-09-05 | RTX 5090 Laptop GPU, compute cap 12.0, 24463 MiB, driver 591.91, CUDA 13.1 capable; .NET SDK 10.0.303; WindowsDesktop 10.0.11; VS Community 2026 18.7 with MSVC x64; no CUDA Toolkit installed |

## Source-quality note

Findings 1, 4 and 24 rest on **primary** sources (a standard, a vendor compatibility guide, and
direct measurement) and are the most reliable in this base. The performance estimate depends on
source 21, a **secondary vendor-spec aggregator**, which is why the throughput figure is labelled
Inferred and carries an instruction to measure rather than trust it.
