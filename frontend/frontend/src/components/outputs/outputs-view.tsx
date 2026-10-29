"use client";

import { useMemo, useState } from "react";
import {
  Check,
  ChevronRight,
  Code2,
  Copy,
  Database,
  Download,
  FileCheck2,
  FileText,
  GitBranch,
  Layers3,
  RefreshCw,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { FleetOutput, View } from "@/lib/types";
import { PageTitle } from "@/components/ui/badge";
import {
  AptEnterpriseIntrusionDossierView,
  AzureAdDossierView,
  Case5DnsTunnelingDossierView,
  Case6DdosDossierView,
  GOV_CLOUD_PROPOSAL_MARKDOWN,
  K8sBreakoutDossierView,
  ProposalDossierView,
  RFP_PROPOSAL_MARKDOWN,
  SocIncidentDossierView,
} from "./dossiers";

export const RESEARCH_ESP32_DELIVERABLE_MARKDOWN = `# Mission Deliverable: RESEARCH 
## Case: ARENA-RESEARCH-RECENT-DEVELOPM-1FECA9
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Collect Latest ESP32 Development Information  
**Assigned Fleet:** RESEARCH Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-29T17:05:00Z  

### Executive Summary & Final Solution

Between 2024 and 2026, Espressif Systems underwent a major architectural transition, expanding the ESP32 family from classic dual-core Xtensa microcontrollers into a high-performance RISC-V computing ecosystem spanning multi-protocol wireless connectivity, edge AI inference, and industrial human-machine interfaces (HMI). 

Key 2026 breakthroughs center on three strategic vectors:
1. **Next-Generation Wireless**: The official debut of the **ESP32-E22** bringing tri-band Wi-Fi 6E (6 GHz) and the ultra-low-power **ESP32-H21** dedicated 802.15.4 / Thread / Matter node.
2. **Software & SDK Consolidation**: The release of **ESP-IDF v6.0**, introducing unified multi-core RISC-V runtime optimizations, expanded Matter 1.3 integration, and dedicated edge neural network acceleration.
3. **Mass-Market Edge Hardware**: The commercial launch of the **ESP32-C61-MINI** sub-$2 Matter/Wi-Fi 6 module family, alongside developer-ready form factors including the **ESP32-P4 Hydra** (Arduino UNO shape) and **ESP32-C5 Pico**.

---

## 1. 2026 Milestone Timeline & Evidence Matrix

The following milestones represent verified silicon releases, firmware announcements, and hardware platforms extracted by the autonomous research fleet:

| Date | Milestone | Key Hardware & Software Features | Verified Source URL | Operational & Ecosystem Impact |
| :--- | :--- | :--- | :--- | :--- |
| **2026‑01‑07** | **ESP32‑E22 & ESP32‑H21 Announced at CES 2026** | • **ESP32-E22**: 6 GHz tri-band Wi-Fi 6E, single-core RISC-V @ 160 MHz, BLE 5.3, native Matter readiness, high-throughput low-latency design.<br>• **ESP32-H21**: Single-core RISC-V @ 96–160 MHz, IEEE 802.15.4 + BLE 5.3, Thread/Matter border node support, ultra-low power DC-DC converter. | [CNX Software CES 2026 Announcement](https://news.google.com/rss/articles/CBMi2AFBVV95cUxONzVCa25FUjlsUU9RaW5QTFpxU2NvUVNCUlJ6YmlvMUpVdG9wM2ZPQlVsdHBzM1FJcFpVVk9mNHdMdXJMRGttcHpndkF5TlhUY2hPV0V6eERYcHpXbnlKTHlpTUc1T3VETUY1QzE1dWhGOWU5N0ZDZUVEZkRJWXN0YTh5d2hfZ1g2SE1kNnFSZjh0R19CV2FUNFZZc2RVWFlSOUVxWGtKY2JkRTR5dm0xRm5QN04xcWdCNFExTHRxZnJ2RmN1Z2RpSkFUMy1UMHIxYWw3d3ZJWVk) | Enables enterprise IoT gateways, multi-gigabit mesh backhauls, and battery-operated smart home devices with multi-year life. |
| **2026‑03‑24** | **Espressif ESP‑IDF v6.0 Production Release** | • Native multi-target support for ESP32-C5, ESP32-C61, ESP32-P4, ESP32-E22, and ESP32-H21.<br>• Enhanced Wi-Fi 6/6E radio stack with OFDMA and TWT (Target Wake Time).<br>• Zero-copy DMA data pipelines and hardware-accelerated crypto (AES-256-XTS, RSA-3072, ECC). | [CNX Software ESP-IDF v6.0 Release](https://news.google.com/rss/articles/CBMingFBVV95cUxOeVptWVJqWGFaZzIxRmRILUdETTEwaUlsUk9QcGNtbnVlTkJjOVdTdWZ1d2JuM3FqRS1RY01yQ2w1ZURfVTBHbVhOXzJRYWJvN0d3TUNfN3U0NVliR1dxeURqY29tVjI4NDJZMmZJWHV4aE90aEJWZHVCOHRST2hEcHF6NjQ3ZEZlaDRrcC1lcXNyek1zOHJBWE81QnBTdw) | Consolidates fragmentation across diverse silicon lines; developers maintain a single codebase across low-cost sensors and multi-core HMI boards. |
| **2026‑04‑26** | **ESP32‑P4 Hydra Board Released** | • Dual-core RISC-V @ 400 MHz + single-core RISC-V LP core @ 40 MHz.<br>• Arduino UNO form-factor compatibility.<br>• MIPI-CSI camera interface, MIPI-DSI display interface, H.264 video encoding, and hardware pixel acceleration. | [Hackster.io ESP32-P4 Hydra Overview](https://news.google.com/rss/articles/CBMi4gFBVV95cUxNUDV1alM3NS0xWjRzN0RYdm1jRy1vLTUtU3RMQm5DMUh6QTh1YW1nYko1QkZMNmhoTjlFbUVtREVoZ1FkWkcweE45ekx3R0RxZlFlM2ZKLXV5S1FaaHRzdEhQZnI4dUlzTzI5X1A0Z1BNVkE0Y2V1cnNGMmRRd2ZubTBxQW56YW96a0haTnhhY3dGcVZHd0xRRGpfaEY2RjA4eFdRVWpLMTU5aVItMTRPSnNTZUd3UERSelhvZ2lQZGtfNVhrSHB3cjVLS09pcm1jdVM4MGRYaV84Y1ZCUFBNYV9B) | Bridges maker ecosystems with industrial-grade GUI and video analytics without needing external co-processors. |
| **2026‑05‑03** | **ESP32‑C5 Pico Form-Factor Launch** | • Dual-band Wi-Fi 6 (2.4 GHz & 5 GHz) + BLE 5.0 in Raspberry Pi Pico footprint.<br>• On-board ceramic antenna with U.FL external option.<br>• Low standby power consumption (<15 µA in deep sleep). | [CNX Software ESP32-C5 Pico](https://news.google.com/rss/articles/CBMi1AFBVV95cUxOajlZZGRrTFctSEF6RE5TU2pRZmNDNXR1Y1JpUnJXbTYxdlBKbVR3Y1p1cDljV0h4MHlOdzhQUEExYldGLXU4b3FhQzhITzBuTThBbEFYSFZ6VWNiLWU5cV9UZXo0SW85aGluTjE3VFViVUJvbVdvaDZOZTgtMFR4Rkc5Uk43Zk9GU0xfQWg3VnZSQ1NjUFJqYnNkZ3FuelVwRGZra1FoNWRlMTFaMkZpb0U2RWRmNk1uSER6SXZyZEMxbmV2Rm1MZFBGS2VwOVdtTWxDQQ) | Democratizes 5 GHz Wi-Fi 6 adoption for dense RF environments where 2.4 GHz spectrum saturation degrades sensor networks. |
| **2026‑08‑05** | **ESP32‑C61‑MINI Commercial Module Family** | • Sub-$2 budget Wi-Fi 6 + Bluetooth 5 (LE) + 802.15.4 silicon.<br>• Ultra-compact PCB layout with integrated RF matching, crystal, and shielded flash.<br>• Certified for Matter-over-Thread and Matter-over-Wi-Fi. | [Hackster.io C61-MINI Launch](https://news.google.com/rss/articles/CBMi1AFBVV95cUxQaHdDWXRDaUcxRVFadVNZbVlVUFRYTEJLczZLUTF1YWptV1dDQ1pSVzdVcXJTQ0w3U3ptOVJ2OXdVWTU5clNIR1d1VnBHZEFqMTc3aU5GTGR1MTFCYmZYeDJFM2F2bk82dW1TbGpMWjRVRGlPQjRQTlo3alJ1eUxvOFV4bFJ5OGREX01NaWwwVDF1RHJJdTFxVF8yN0FZQnN0eGFVb190VGMtbEh5SFlTVndfR3phOV8tUmNicEFna2hoamo2T3VUUWo5WGlUdDBhQ0N6Nw) | Lowers BOM cost for appliance manufacturers transitioning legacy Zigbee/Wi-Fi 4 products to modern Matter compliance. |

---

## 2. Foundations: 2024–2025 Upstream Breakthroughs

The 2026 milestone breakthroughs build upon critical innovations developed across 2024 and 2025:

1. **Edge AI & SIMD Vision (2024)**: Espressif deployed SIMD extensions on the ESP32-S3 RISC-V/Xtensa pipelines, enabling real-time computer vision, keyword spotting, and OpenAI Embedded SDK streaming directly on-chip without cloud roundtrips.
2. **Dual-Band Wi-Fi 6 Transition (2025)**: The release of the **ESP32-C5** marked Espressif's first volume production 2.4/5 GHz dual-band solution, solving latency jitter in industrial factory environments.
3. **Multimedia Separation (2025)**: Introduction of the **ESP32-P4** dedicated non-wireless application processor, featuring dual RISC-V cores up to 400 MHz, MIPI camera/display pipelines, and native H.264 video compression for smart displays.

---

## 3. Hardware Architecture & Silicon Portfolio Comparison

| Series | Primary CPU Core | Max Frequency | Wireless Protocols | Primary Target Application |
| :--- | :--- | :--- | :--- | :--- |
| **ESP32-E22** | 32-bit RISC-V | 160 MHz | Tri-band Wi-Fi 6E (2.4/5/6 GHz), BLE 5.3 | High-throughput IoT gateways, VR/AR streaming nodes |
| **ESP32-H21** | 32-bit RISC-V | 96 MHz | IEEE 802.15.4 (Thread/Zigbee), BLE 5.3 | Ultra-low-power battery sensors, Matter end-devices |
| **ESP32-C61** | 32-bit RISC-V | 160 MHz | Wi-Fi 6 (2.4 GHz), BLE 5.3, 802.15.4 | Cost-optimized smart home bulbs, switches, plugs |
| **ESP32-C5** | 32-bit RISC-V | 240 MHz | Dual-band Wi-Fi 6 (2.4 & 5 GHz), BLE 5.0 | Industrial telemetry, noisy RF smart metering |
| **ESP32-P4** | Dual RISC-V (HP) + LP | 400 MHz + 40 MHz | No RF (Uses external C6/H2/E22 co-processor) | Smart thermostats, medical touchscreens, security cameras |

---

## 4. Software Ecosystem & Firmware Support

- **ESP-IDF v6.0**: Unified build system supporting CMake 3.28+, FreeRTOS v11 SMP, and automated peripheral power-gating.
- **Matter 1.3 Readiness**: Full support for energy monitoring, water valves, EVSE chargers, and robot vacuums embedded natively into the ESP-Matter component registry.
- **Home Assistant & ESPHome**: First-class support for the ESP32-P4 smart display pipelines and C5 dual-band radios natively merged into ESPHome 2025/2026 releases.

---

## 5. Strategic Conclusion

Espressif's 2026 milestone portfolio solidifies its dominance across both extremes of the IoT spectrum:
- At the **ultra-low-cost tier**, the sub-$2 **ESP32-C61-MINI** ensures seamless Matter compliance for mass-market consumer electronics.
- At the **high-performance tier**, the combination of the **ESP32-E22 (Wi-Fi 6E)** and **ESP32-P4 (400 MHz Multimedia)** offers a viable RISC-V alternative to complex Linux MPUs with lower power consumption and sub-second boot times.`;

export const RESEARCH_FUSION_PAPER_MARKDOWN = `# Mission Deliverable: paper
## Case: ARENA-CREATE-RESEARCH-PAPER-C0942E
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Collect Recent Fusion Reactor Literature & News  
**Assigned Fleet:** paper Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-29T17:31:00Z  

### Executive Summary & Final Solution
# Executive Summary  

The year 2026 marked a watershed for fusion energy research, with six landmark milestones spanning magnetised‑target fusion (MTF), pulsed‑power tokamaks, inertial confinement fusion (ICF), and Z‑pinch technologies.  Key achievements include the first MTF device to reach keV plasma temperatures, the inaugural deuterium–tritium (D‑T) fusion event in a privately built tokamak, repeatable breakeven in laser‑driven ICF, and federal endorsement of a 50 MW net‑output Z‑pinch module.  These breakthroughs collectively demonstrate that multiple reactor families are converging toward scalable, commercial power generation, underscoring the importance of continued public–private collaboration and targeted policy support.

---

## 1 Introduction  

Fusion energy promises abundant, low‑carbon electricity by replicating the processes powering stars.  Over the past decade, a diverse portfolio of reactor concepts has advanced from laboratory proof‑of‑concept to near‑commercial prototypes.  In 2026, several independent teams achieved critical performance metrics that validate their respective approaches and bring them closer to economic viability.

---

## 2 Methodology  

Data were collated from peer‑reviewed publications, conference proceedings, corporate press releases, and government reports issued between January 1 and December 31 2026.  Each milestone was verified against at least two independent sources (e.g., laboratory logs and third‑party media coverage).  Quantitative metrics such as plasma temperature, energy yield, shot count, and design targets were extracted verbatim to ensure accuracy.

---

## 3 2026 Fusion Milestones  

| Reactor / Technology | Milestone (Name & Org.) | Key Technical Achievement | Quantitative Metrics | Commercial‑Impact Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **Magnetised‑Target Fusion (MTF)** | *General Fusion LM26* – Canada, General Fusion Group Ltd. | First MTF device to reach keV plasma temperatures during compression. | Electron temperature >12 million °C (>1 keV) achieved on 2026-10-08 | Demonstrates scalability of the MTF concept and provides a clear path toward ignition-grade reactors, reducing the need for large external magnets and lowering capital costs. |
| **Tokamak‑style Pulsed‑Power** | *Helion Polaris* – USA, Helion Energy | First privately built machine to produce measurable D-T fusion. | 150 million °C plasma temperature; first D-T fusion event on 2026-02-13 | Validates a compact, high-temperature design that can be scaled into commercial plants with lower upfront investment and faster engineering cycles. |
| **Tokamak‑style Pulsed‑Power** | *Pacific Fusion Sirius* – USA, Pacific Fusion | High-throughput pulsed-power system with proven reliability. | >3,000 shots delivered with stable operation on 2026-07-20 | Shows that pulsed-power platforms can achieve the shot-throughput required for commercial power generation, reducing downtime and maintenance costs. |
| **Inertial Confinement Fusion (ICF)** | *LLNL NIF* – USA, Lawrence Livermore National Laboratory | 11th ignition experiment confirming repeatable scientific breakeven. | 7.9 MJ fusion energy yield; target gain ≈3.8 on 2026-06-20 | Provides the first evidence that laser-driven ICF can reach breakeven, a critical milestone for future inertial fusion power plants and for validating high-energy-density physics models. |
| **Z‑Pinch** | *Zap Energy* – USA, Zap Energy | DOE approval of a pre-conceptual 50 MW net-output module design using sheared-flow-stabilised Z-pinch. | Design target: 50 MW net output (pre-concept) on 2026-05-19 | Signals federal support for a potentially lower-cost fusion pathway that can be engineered rapidly, accelerating the transition from laboratory to commercial deployment. |
| **Tokamak – Current‑Drive Innovation** | *General Atomics DIII‑D Helicon* – USA, General Atomics Energy Group | First helicon radio-wave current drive sustaining plasma without a central solenoid. | Operational on 2026-10-27 | Reduces the complexity and cost of tokamak construction by eliminating the need for large central solenoids, improving pulse length and overall plant economics. |

---

## 4 Emerging Trends  

| Trend | Evidence |
| :--- | :--- |
| **Dominant Reactor Families** | Tokamak-style pulsed-power (Helion, Pacific Fusion) and MTF (General Fusion) lead the field; ICF and Z-pinch also gaining traction. |
| **Geographic Concentration** | 5 of 6 milestones from the United States; Canada contributes a pivotal MTF breakthrough. |
| **Public–Private Collaboration** | DOE approval for Zap Energy, private sector breakthroughs (Helion, Pacific Fusion) indicate growing synergy between government and industry. |
| **Technological Innovation** | New current-drive technique (helicon), high-temperature D-T fusion, and repeatable breakeven experiments signal rapid progress in core physics and engineering. |

---

## 5 Discussion & Engineering Implications  

The convergence of multiple reactor concepts toward practical power generation suggests a diversified pathway to commercial fusion. MTF's reduced magnetic infrastructure lowers capital costs; pulsed-power tokamaks offer compactness and high temperature; ICF demonstrates repeatable breakeven, validating the physics underpinning inertial fusion plants; Z-pinch presents a potentially rapid engineering route with federal backing.

Key challenges remain: sustaining long-duration operation, managing neutron damage to structural materials, and scaling up power output while maintaining economic viability. The 2026 milestones provide critical data points for refining reactor designs, informing material science research, and shaping policy incentives.

---

## 6 Conclusion & Outlook  

The six 2026 milestones collectively illustrate that fusion energy is transitioning from laboratory proof-of-concept to near-commercial readiness across multiple technological families. Breakthroughs in temperature achievement, repeatable breakeven, high-reliability operation, and innovative current-drive techniques mark a decisive shift toward scalable power generation. Continued investment, cross-sector collaboration, and supportive policy frameworks will be essential to translate these scientific advances into the first generation of fusion power plants (projected 2030–2035).

---

## 7 References  

1. General Fusion Group Ltd., *LM26 MTF Demonstration*, 2026-10-08.  
2. Helion Energy, *Polaris D-T Fusion Event Report*, 2026-02-13.  
3. Pacific Fusion, *Sirius High-Throughput Operation Summary*, 2026-07-20.  
4. Lawrence Livermore National Laboratory, *NIF 11th Ignition Experiment Results*, 2026-06-20.  
5. Zap Energy, *DOE Pre-Conceptual 50 MW Z-Pinch Module Design Approval*, 2026-05-19.  
6. General Atomics Energy Group, *DIII-D Helicon Current Drive Operational Report*, 2026-10-27.`;

export const DEFAULT_OUTPUTS: FleetOutput[] = [
  {
    id: "out-research-fusion-paper-report",
    output_id: "art_paper_deliverable_report_md",
    name: "paper_deliverable_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Collect Recent Fusion Reactor Literature & News",
    case: "ARENA-CREATE-RESEARCH-PAPER-C0942E",
    case_name: "paper (Fusion Energy Reactors & 2026 Milestones)",
    size: 7529,
    size_bytes: 7529,
    at: "2026-10-29T17:31:00Z",
    created_at: "2026-10-29T17:31:00Z",
    text: RESEARCH_FUSION_PAPER_MARKDOWN,
    snippet: "# Mission Deliverable: paper\\n## Case: ARENA-CREATE-RESEARCH-PAPER-C0942E\\nThe year 2026 marked a watershed for fusion energy research, with six landmark milestones spanning MTF, pulsed-power tokamaks, ICF, and Z-pinch...",
    source: {
      kind: "workflow_cycle",
      filename: "paper_deliverable_report.md",
      path: "data/artifacts/paper_deliverable_report.md",
      step_name: "draft_research_paper",
    },
    provenance: "Collect Recent Fusion Reactor Literature & News produced it for paper (Fusion Reactors & 2026 Milestones)",
  },
  {
    id: "out-research-esp32-report",
    output_id: "art_research_deliverable_report_md",
    name: "research_deliverable_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Collect Latest ESP32 Development Information",
    case: "ARENA-RESEARCH-RECENT-DEVELOPM-1FECA9",
    case_name: "RESEARCH (ESP32 Recent Developments & 2026 Milestones)",
    size: 8506,
    size_bytes: 8506,
    at: "2026-10-29T17:05:00Z",
    created_at: "2026-10-29T17:05:00Z",
    text: RESEARCH_ESP32_DELIVERABLE_MARKDOWN,
    snippet: "# Mission Deliverable: RESEARCH\\n## Case: ARENA-RESEARCH-RECENT-DEVELOPM-1FECA9\\nBetween 2024 and 2026, Espressif Systems underwent a major architectural transition (ESP32-E22, ESP32-H21, ESP-IDF v6.0, ESP32-C61-MINI)...",
    source: {
      kind: "workflow_cycle",
      filename: "research_deliverable_report.md",
      path: "data/artifacts/research_deliverable_report.md",
      step_name: "summarize_2026_esp32_milestones",
    },
    provenance: "Collect Latest ESP32 Development Information produced it for RESEARCH (ESP-IDF v6.0, E22/H21/P4/C61)",
  },
  {
    id: "out-government-cloud-proposal",
    output_id: "out-government-cloud-proposal",
    name: "government_cloud_migration_proposal.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Government Cloud Proposal Synthesis Fleet",
    case: "ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18",
    case_name: "Government Cloud Migration RFP",
    size: 6123,
    size_bytes: 6123,
    at: "2026-10-26T20:44:23Z",
    created_at: "2026-10-26T20:44:23Z",
    text: GOV_CLOUD_PROPOSAL_MARKDOWN,
    snippet: "# Mission Deliverable: Government Cloud Migration Executive Proposal\n## Case: ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18\nTotal Labor Cost: $50,500.00 USD (480 Engineering Hours)...",
    source: {
      kind: "workflow_cycle",
      filename: "government_cloud_migration_proposal.md",
      path: "data/artifacts/government_cloud_migration_proposal.md",
      step_name: "generate_proposal",
    },
    provenance: "Government Cloud Proposal Synthesis Fleet produced it for ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18 (9/9 Compliant · $50,500.00 USD)",
  },
  {
    id: "out-moe-rfp-proposal",
    output_id: "out-moe-rfp-proposal",
    name: "moe_devops_server_rfp_proposal.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Sovereign Agentic Systems & Cloud Infrastructure Fleet",
    case: "RFP-MOE-ROXY-DEVOPS-2026-01",
    case_name: "MOE DevOps Server Platform (Roxy DC)",
    size: 14200,
    size_bytes: 14200,
    at: "2026-10-25T16:30:00Z",
    created_at: "2026-10-25T16:30:00Z",
    text: RFP_PROPOSAL_MARKDOWN,
    snippet: "# Executive Proposal: DevOps Server Platform Implementation\n## Ministry of Education (MOE) – Roxy Data Center\nDocument ID: RFP-MOE-ROXY-DEVOPS-2026-01...",
    source: {
      kind: "workflow_cycle",
      filename: "moe_devops_server_rfp_proposal.md",
      path: "data/artifacts/moe_devops_server_rfp_proposal.md",
      step_name: "generate_rfp_proposal",
    },
    provenance: "Sovereign Cloud Fleet produced it for RFP-MOE-ROXY-DEVOPS-2026-01 (15/15 Compliant · $161,400.00 USD)",
  },
  {
    id: "out-k8s-breakout-report",
    output_id: "out-k8s-breakout-report",
    name: "k8s_container_breakout_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "K8s Container Breakout SOC Fleet",
    case: "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
    case_name: "K8s Container Breakout SOC Investigation",
    size: 18450,
    size_bytes: 18450,
    at: "2026-10-26T12:31:45Z",
    created_at: "2026-10-26T12:31:45Z",
    text: `# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit\n## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT\n**Target Node:** worker-k8s-node-03.prod.internal\n**Classification:** CONFIDENTIAL // TLP:AMBER\n\n### 1. Executive Summary\nA multi-stage container breakout was reconstructed across container namespaces, syslogs, and auditd on worker-k8s-node-03. The attacker used sudo find privesc, injected Diamorphine LKM, and escaped to host via cgroup release_agent.`,
    snippet: "# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit\n## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT...",
    source: {
      kind: "k8s_soc_investigation",
      filename: "k8s_container_breakout_investigation_report.md",
      step_name: "reconstruct_breakout_kill_chain",
    },
    provenance: "K8s Breakout SOC Fleet produced it for CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
  },
  {
    id: "out-azure-ad-intrusion-report",
    output_id: "out-azure-ad-intrusion-report",
    name: "azure_ad_intrusion_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Azure AD & Cloud Identity Defense Fleet",
    case: "CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
    case_name: "Azure AD Identity Takeover SOC Investigation",
    size: 16840,
    size_bytes: 16840,
    at: "2026-10-26T13:07:28Z",
    created_at: "2026-10-26T13:07:28Z",
    text: `# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel\n## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL\n**Target Identity:** alex.vance@contoso-global.com (Global Admin)\n**Classification:** CONFIDENTIAL // TLP:AMBER\n\n### 1. Executive Summary\nImpossible travel detected between London and Amsterdam within 8 minutes (>3,400 km/h). PRT token replayed to bypass MFA. Persistent client secret DiagnosticSyncKey-2026 injected. Mass email exfiltration contained.`,
    snippet: "# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel\n## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL...",
    source: {
      kind: "cloud_identity_investigation",
      filename: "azure_ad_intrusion_investigation_report.md",
      step_name: "reconstruct_identity_attack_chain",
    },
    provenance: "Azure AD Defense Fleet produced it for CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
  },
  {
    id: "out-case-1-apt-report",
    output_id: "out-case-1-apt-report",
    name: "case_1_apt_enterprise_intrusion_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "APT Enterprise Intrusion SOC Fleet",
    case: "CASE-1-APT-ENTERPRISE-INTRUSION",
    case_name: "Case A: APT Enterprise Intrusion SOC Investigation",
    size: 24190,
    size_bytes: 24190,
    at: "2026-10-26T18:10:45Z",
    created_at: "2026-10-26T18:10:45Z",
    text: `# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement\n## Case: CASE-1-APT-ENTERPRISE-INTRUSION\n**Target Domain:** corp.contoso.com\n**Primary Host:** WKSTN-FIN-04 (10.20.10.45)\n**Domain Controller:** DC01 (10.20.10.10)\n\n### 1. Executive Summary\nMulti-stage APT intrusion emulating APT29/UNC2452 was detected and reconstructed across disjointed log ecosystems. Malicious macro document led to in-memory PowerShell execution, Mimikatz credential theft, SMB lateral movement to DC01, and creation of rogue administrator account svc_backup_admin. 452.8 MB exfiltration sinkholed.`,
    snippet: "# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement\n## Case: CASE-1-APT-ENTERPRISE-INTRUSION...",
    source: {
      kind: "soc_investigation",
      filename: "case_1_apt_enterprise_intrusion_investigation_report.md",
      step_name: "assemble_final_solution",
    },
    provenance: "APT Enterprise Intrusion SOC Fleet produced it for CASE-1-APT-ENTERPRISE-INTRUSION",
  },
];

export function FormattedInline({ text }: { text: string }) {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) {
          return <strong key={i} style={{ color: "#142c26", fontWeight: 700 }}>{p.slice(2, -2)}</strong>;
        }
        if (p.startsWith("`") && p.endsWith("`")) {
          return (
            <code
              key={i}
              style={{
                background: "#eef5f2",
                color: "#185e54",
                padding: "1px 5px",
                borderRadius: "3px",
                fontSize: "10px",
                fontFamily: "var(--font-geist-mono), monospace",
              }}
            >
              {p.slice(1, -1)}
            </code>
          );
        }
        return p;
      })}
    </>
  );
}

export function FormattedDocumentPreview({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let tableRows: string[] = [];
  let inTable = false;
  let keyIdx = 0;

  function flushTable() {
    if (tableRows.length === 0) return;
    const headerRow = tableRows[0];
    const headers = headerRow.split("|").slice(1, -1).map((s) => s.trim());
    const dataRows = tableRows.slice(2);

    elements.push(
      <div key={`table-${keyIdx++}`} style={{ overflowX: "auto", margin: "14px 0", border: "1px solid #dce8e2", borderRadius: "6px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", fontFamily: "var(--font-geist-mono), monospace" }}>
          <thead>
            <tr style={{ background: "#f0f5f2", borderBottom: "2px solid #cad8d1" }}>
              {headers.map((h, i) => (
                <th key={i} style={{ padding: "8px 12px", textAlign: "left", color: "#195d56", fontWeight: 700 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((r, ri) => {
              const cells = r.split("|").slice(1, -1).map((s) => s.trim());
              return (
                <tr key={ri} style={{ borderBottom: "1px solid #eef3f1", background: ri % 2 === 0 ? "#ffffff" : "#fbfdfc" }}>
                  {cells.map((c, ci) => {
                    const isStatus = c === "COMPLIANT" || c === "PASS";
                    return (
                      <td key={ci} style={{ padding: "8px 12px", color: "#253b35" }}>
                        {isStatus ? (
                          <span style={{ fontSize: "9px", background: "#e4f3ed", color: "#196656", padding: "2px 6px", borderRadius: "3px", fontWeight: 700 }}>
                            {c}
                          </span>
                        ) : (
                          <FormattedInline text={c} />
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
    tableRows = [];
    inTable = false;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      inTable = true;
      tableRows.push(trimmed);
      continue;
    } else if (inTable) {
      flushTable();
    }

    if (!trimmed) continue;

    if (trimmed.startsWith("# ")) {
      elements.push(
        <h1 key={`h1-${keyIdx++}`} style={{ fontSize: "17px", fontWeight: 800, color: "#142c26", margin: "16px 0 6px", borderBottom: "1px solid #e2ede8", paddingBottom: "6px" }}>
          {trimmed.replace(/^#\s+/, "")}
        </h1>
      );
    } else if (trimmed.startsWith("## ")) {
      elements.push(
        <h2 key={`h2-${keyIdx++}`} style={{ fontSize: "14px", fontWeight: 700, color: "#1e3e36", margin: "14px 0 6px" }}>
          {trimmed.replace(/^##\s+/, "")}
        </h2>
      );
    } else if (trimmed.startsWith("### ")) {
      elements.push(
        <h3 key={`h3-${keyIdx++}`} style={{ fontSize: "12px", fontWeight: 700, color: "#245f54", margin: "12px 0 4px", display: "flex", alignItems: "center", gap: "6px" }}>
          <ChevronRight size={13} color="#245f54" /> {trimmed.replace(/^###\s+/, "")}
        </h3>
      );
    } else if (trimmed === "---") {
      elements.push(<hr key={`hr-${keyIdx++}`} style={{ border: "none", borderTop: "1px solid #e0ebe6", margin: "14px 0" }} />);
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      const text = trimmed.replace(/^[-*]\s+/, "");
      elements.push(
        <li key={`li-${keyIdx++}`} style={{ fontSize: "11px", color: "#314942", margin: "3px 0 3px 18px", lineHeight: "1.5" }}>
          <FormattedInline text={text} />
        </li>
      );
    } else {
      elements.push(
        <p key={`p-${keyIdx++}`} style={{ fontSize: "11px", color: "#334943", margin: "5px 0", lineHeight: "1.6" }}>
          <FormattedInline text={trimmed} />
        </p>
      );
    }
  }

  if (inTable) flushTable();

  return (
    <div
      style={{
        background: "#ffffff",
        padding: "20px 24px",
        borderRadius: "6px",
        border: "1px solid #dce8e2",
        maxHeight: "56vh",
        overflowY: "auto",
        lineHeight: "1.65",
      }}
    >
      {elements}
    </div>
  );
}

export function FleetOutputsView({
  outputs,
  onSelectOutput,
  onNavigate,
  onRefresh,
  activeViewMode: controlledViewMode,
  setActiveViewMode: setControlledViewMode,
  activeDossierCase: controlledDossierCase,
  setActiveDossierCase: setControlledDossierCase,
}: {
  outputs: FleetOutput[];
  onSelectOutput: (output: FleetOutput) => void;
  onNavigate?: (view: View) => void;
  onRefresh?: () => void;
  activeViewMode?: "dossier" | "registry";
  setActiveViewMode?: (mode: "dossier" | "registry") => void;
  activeDossierCase?: "rfp" | "gov_cloud" | "soc" | "k8s" | "azure" | "case5" | "case6" | "apt";
  setActiveDossierCase?: (c: "rfp" | "gov_cloud" | "soc" | "k8s" | "azure" | "case5" | "case6" | "apt") => void;
}) {
  const [internalViewMode, setInternalViewMode] = useState<"dossier" | "registry">("registry");
  const [internalDossierCase, setInternalDossierCase] = useState<"rfp" | "gov_cloud" | "soc" | "k8s" | "azure" | "case5" | "case6" | "apt">("gov_cloud");
  const activeViewMode = controlledViewMode ?? internalViewMode;
  const setActiveViewMode = setControlledViewMode ?? setInternalViewMode;
  const activeDossierCase = controlledDossierCase ?? internalDossierCase;
  const setActiveDossierCase = setControlledDossierCase ?? setInternalDossierCase;
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [caseFilter, setCaseFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const cases = useMemo(() => {
    const set = new Set<string>();
    outputs.forEach((o) => {
      if (o.case) set.add(o.case);
      if (o.case_name && o.case_name !== o.case) set.add(o.case_name);
    });
    return Array.from(set);
  }, [outputs]);

  function parseOutputTime(item: FleetOutput): number {
    if (typeof item.at === "number") {
      return item.at > 1e11 ? item.at : item.at * 1000;
    }
    if (item.created_at) {
      const t = Date.parse(item.created_at);
      if (!isNaN(t)) return t;
    }
    if (typeof item.at === "string") {
      const t = Date.parse(item.at);
      if (!isNaN(t)) return t;
    }
    return 0;
  }

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const result = outputs.filter((item) => {
      if (kindFilter !== "all" && item.kind !== kindFilter) return false;
      if (caseFilter !== "all" && item.case !== caseFilter && item.case_name !== caseFilter) return false;
      if (!q) return true;
      return (
        item.name.toLowerCase().includes(q) ||
        (item.case || "").toLowerCase().includes(q) ||
        (item.case_name || "").toLowerCase().includes(q) ||
        item.produced_by.toLowerCase().includes(q) ||
        (item.snippet || "").toLowerCase().includes(q) ||
        (item.provenance || "").toLowerCase().includes(q)
      );
    });
    return [...result].sort((a, b) => parseOutputTime(b) - parseOutputTime(a));
  }, [outputs, kindFilter, caseFilter, searchQuery]);

  const totalBytes = useMemo(() => outputs.reduce((acc, curr) => acc + (curr.size_bytes || curr.size || 0), 0), [outputs]);

  function formatBytes(bytes: number) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px", background: "#f0f5f2", padding: "10px 14px", borderRadius: "8px", border: "1px solid #dce8e2" }}>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <button
            type="button"
            style={{
              padding: "7px 14px",
              fontSize: "11px",
              fontWeight: activeViewMode === "registry" ? 700 : 600,
              background: activeViewMode === "registry" ? "#ffffff" : "transparent",
              color: activeViewMode === "registry" ? "#195d56" : "#51635d",
              border: activeViewMode === "registry" ? "1px solid #cad8d1" : "1px solid transparent",
              borderRadius: "4px",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
            }}
            onClick={() => setActiveViewMode("registry")}
          >
            <Database size={13} color={activeViewMode === "registry" ? "#236f66" : "#6a7b75"} />
            <span>All Deliverables Registry</span>
            <span style={{ fontSize: "9px", background: "#eef3f1", color: "#425650", padding: "1px 6px", borderRadius: "3px", fontWeight: 700 }}>{outputs.length}</span>
          </button>
          {activeViewMode === "dossier" && (
            <span style={{ fontSize: "11px", color: "#6a7b75", display: "inline-flex", alignItems: "center", gap: "6px", paddingLeft: "8px" }}>
              / <span style={{ fontWeight: 700, color: "#195d56" }}>Specialist Dossier View</span>
            </span>
          )}
        </div>

        {onRefresh && (
          <button className="secondary-button" onClick={onRefresh} style={{ fontSize: "11px", padding: "6px 12px" }}>
            <RefreshCw size={13} /> Refresh outputs
          </button>
        )}
      </div>

      {activeViewMode === "dossier" && activeDossierCase === "gov_cloud" && (
        <ProposalDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} initialVersion="latest" />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "rfp" && (
        <ProposalDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} initialVersion="moe" />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "apt" && (
        <AptEnterpriseIntrusionDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "soc" && (
        <SocIncidentDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "azure" && (
        <AzureAdDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "k8s" && (
        <K8sBreakoutDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "case5" && (
        <Case5DnsTunnelingDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "dossier" && activeDossierCase === "case6" && (
        <Case6DdosDossierView onNavigate={onNavigate} onBack={() => setActiveViewMode("registry")} />
      )}

      {activeViewMode === "registry" && (
        <>
          <PageTitle
            eyebrow="AGENTHUB 0.21.x  /  DELIVERABLES & ARTIFACTS"
            title="All Deliverables Registry"
            subtitle="Immutable deliverables produced across missions, workflow cycles, and specialist agent runs."
          />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "12px", marginBottom: "18px" }}>
            <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
                <FileText size={14} color="#236f66" /> Total Deliverables
              </span>
              <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", fontFamily: "var(--font-geist-mono), monospace" }}>
                {outputs.length}
              </span>
              <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
                {formatBytes(totalBytes)} across all runs
              </span>
            </div>
            <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
                <Database size={14} color="#3864a7" /> Distinct Cases
              </span>
              <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", fontFamily: "var(--font-geist-mono), monospace" }}>
                {cases.length}
              </span>
              <span style={{ fontSize: "10px", color: "#3864a7", fontWeight: 600 }}>
                Across security &amp; enterprise domains
              </span>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "14px", flexWrap: "wrap", background: "#ffffff", padding: "10px 14px", borderRadius: "6px", border: "1px solid #dce8e2" }}>
            <div style={{ position: "relative", flex: 1, minWidth: "240px" }}>
              <Search size={14} color="#6a7c76" style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)" }} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search deliverables by name, keyword, or case (e.g. esp32, research, proposal, k8s)..."
                style={{
                  width: "100%",
                  padding: "7px 10px 7px 32px",
                  fontSize: "12px",
                  borderRadius: "4px",
                  border: "1px solid #cad8d1",
                  background: "#f9fcfa",
                  outline: "none",
                }}
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  style={{ position: "absolute", right: "8px", top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", cursor: "pointer" }}
                >
                  <X size={13} color="#6a7c76" />
                </button>
              )}
            </div>
            <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
              <button
                type="button"
                className="secondary-button"
                style={{
                  fontSize: "10px",
                  padding: "4px 8px",
                  background: searchQuery === "esp32" || searchQuery === "research" ? "#e0f0ea" : "transparent",
                  borderColor: searchQuery === "esp32" || searchQuery === "research" ? "#236f66" : "#cad8d1",
                }}
                onClick={() => setSearchQuery(searchQuery === "esp32" ? "" : "esp32")}
              >
                ESP32 / Research
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{
                  fontSize: "10px",
                  padding: "4px 8px",
                  background: searchQuery === "proposal" || searchQuery === "rfp" ? "#e0f0ea" : "transparent",
                  borderColor: searchQuery === "proposal" || searchQuery === "rfp" ? "#236f66" : "#cad8d1",
                }}
                onClick={() => setSearchQuery(searchQuery === "proposal" ? "" : "proposal")}
              >
                Proposals &amp; RFP
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{
                  fontSize: "10px",
                  padding: "4px 8px",
                  background: searchQuery === "soc" || searchQuery === "apt" ? "#e0f0ea" : "transparent",
                  borderColor: searchQuery === "soc" || searchQuery === "apt" ? "#236f66" : "#cad8d1",
                }}
                onClick={() => setSearchQuery(searchQuery === "soc" ? "" : "soc")}
              >
                SOC / Incidents
              </button>
            </div>
            <span style={{ fontSize: "11px", color: "#6a7c76", marginLeft: "auto", fontWeight: 600 }}>
              Showing {filtered.length} of {outputs.length} deliverables
            </span>
          </div>

          {/* Deliverables List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {filtered.map((item) => (
              <div
                key={item.id || item.output_id}
                onClick={() => onSelectOutput(item)}
                style={{
                  background: "#ffffff",
                  border: "1px solid #dce8e2",
                  borderRadius: "6px",
                  padding: "12px 16px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  cursor: "pointer",
                  transition: "border-color 0.15s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <FileText size={18} color="#236f66" />
                  <div>
                    <div style={{ fontSize: "13px", fontWeight: 700, color: "#1a3831" }}>{item.name}</div>
                    <div style={{ fontSize: "11px", color: "#6a7c76", marginTop: "2px" }}>
                      {item.produced_by} · {item.case_name || item.case}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <span style={{ fontSize: "11px", color: "#6a7c76" }}>{formatBytes(item.size_bytes || item.size || 0)}</span>
                  <span style={{ fontSize: "10px", fontWeight: 700, background: "#edf5f1", color: "#196656", padding: "3px 8px", borderRadius: "3px" }}>
                    {item.classification.toUpperCase()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export function OutputDetailModal({
  output,
  onClose,
  onNavigate,
  onOpenDossier,
}: {
  output: FleetOutput;
  onClose: () => void;
  onNavigate?: (view: View) => void;
  onOpenDossier?: (caseType: "rfp" | "gov_cloud" | "soc" | "k8s" | "azure" | "case5" | "case6" | "apt") => void;
}) {
  const [copied, setCopied] = useState(false);
  const [modalView, setModalView] = useState<"formatted" | "raw">("formatted");

  const isProposal = output.name.toLowerCase().includes("proposal");
  const isCase6 = output.name.toLowerCase().includes("case_6") || (output.case || "").includes("CASE-6");
  const isAzureIncident = output.name.toLowerCase().includes("azure") || (output.case || "").includes("CASE-3");
  const isK8sIncident = output.name.toLowerCase().includes("k8s") || (output.case || "").includes("CASE-4");
  const isSocIncident = output.name.toLowerCase().includes("soc") || (output.case || "").includes("SOC");
  const isApt = output.name.toLowerCase().includes("apt") || (output.case || "").includes("CASE-1");

  const textContent = output.text || output.snippet || "No deliverable text available.";

  function copyContent() {
    navigator.clipboard.writeText(textContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadOutput() {
    const blob = new Blob([textContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = output.name || "deliverable.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div
      className="modal-shade"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "grid",
        placeItems: "center",
        backgroundColor: "rgba(10, 24, 22, 0.65)",
        backdropFilter: "blur(4px)",
        padding: "20px",
      }}
    >
      <section
        className="modal-card"
        style={{
          maxWidth: "920px",
          width: "100%",
          maxHeight: "88vh",
          background: "#ffffff",
          border: "1px solid #dce6e2",
          borderRadius: "10px",
          boxShadow: "0 25px 70px rgba(0, 0, 0, 0.35)",
          display: "flex",
          flexDirection: "column",
          padding: "22px 24px",
          animation: "modal-in 0.18s ease-out",
          position: "relative",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="modal-head"
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            borderBottom: "1px solid #e9f0ec",
            paddingBottom: "12px",
            marginBottom: "14px",
          }}
        >
          <div>
            <div
              className="eyebrow"
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#185d54",
                letterSpacing: "0.8px",
                textTransform: "uppercase",
                marginBottom: "3px",
              }}
            >
              {output.case || "DELIVERABLE ARTIFACT"}
            </div>
            <h3
              style={{
                margin: 0,
                fontSize: "17px",
                fontWeight: 700,
                color: "#162e28",
                fontFamily: "var(--font-geist-mono), monospace",
              }}
            >
              {output.name}
            </h3>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            style={{
              padding: "6px",
              borderRadius: "5px",
              background: "#f0f5f2",
              border: "1px solid #dbe6e1",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            title="Close modal"
          >
            <X size={16} color="#27463f" />
          </button>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "12px",
            flexWrap: "wrap",
            gap: "10px",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              gap: "4px",
              background: "#eef5f2",
              padding: "3px",
              borderRadius: "6px",
              border: "1px solid #dbe6e1",
            }}
          >
            <button
              type="button"
              style={{
                fontSize: "11px",
                fontWeight: 650,
                padding: "5px 13px",
                borderRadius: "4px",
                border: "none",
                cursor: "pointer",
                background: modalView === "formatted" ? "#185d54" : "transparent",
                color: modalView === "formatted" ? "#ffffff" : "#45615a",
                transition: "all 0.15s ease",
              }}
              onClick={() => setModalView("formatted")}
            >
              Structured Document
            </button>
            <button
              type="button"
              style={{
                fontSize: "11px",
                fontWeight: 650,
                padding: "5px 13px",
                borderRadius: "4px",
                border: "none",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                background: modalView === "raw" ? "#185d54" : "transparent",
                color: modalView === "raw" ? "#ffffff" : "#45615a",
                transition: "all 0.15s ease",
              }}
              onClick={() => setModalView("raw")}
            >
              <Code2 size={13} /> Raw Markdown
            </button>
          </div>
          <span style={{ fontSize: "11px", color: "#6a7c76" }}>
            Produced by <strong style={{ color: "#1a3b34" }}>{output.produced_by}</strong>
          </span>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {modalView === "formatted" ? (
            <FormattedDocumentPreview content={textContent} />
          ) : (
            <pre
              style={{
                flex: 1,
                maxHeight: "56vh",
                overflowY: "auto",
                fontFamily: "var(--font-geist-mono), monospace",
                fontSize: "11px",
                lineHeight: "1.65",
                whiteSpace: "pre-wrap",
                background: "#162522",
                color: "#e2eee9",
                padding: "18px 22px",
                borderRadius: "6px",
                border: "1px solid #233b35",
                margin: 0,
              }}
            >
              {textContent}
            </pre>
          )}
        </div>

        <div
          style={{
            marginTop: "16px",
            paddingTop: "14px",
            borderTop: "1px solid #eef3f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "10px",
          }}
        >
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              className="secondary-button"
              onClick={copyContent}
              style={{ fontSize: "11px", padding: "6px 12px" }}
            >
              {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={downloadOutput}
              style={{ fontSize: "11px", padding: "6px 12px" }}
            >
              <Download size={14} /> Download
            </button>
          </div>
          <button
            type="button"
            className="plain-button"
            onClick={onClose}
            style={{
              fontSize: "11px",
              padding: "6px 14px",
              borderRadius: "4px",
              background: "#f0f5f2",
              border: "1px solid #dce8e2",
              color: "#28443e",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
