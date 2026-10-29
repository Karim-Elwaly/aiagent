"use client";

import { useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Check,
  Copy,
  Download,
  FileCheck2,
  Layers3,
  LockKeyhole,
  Printer,
  Search,
  Server,
  ShieldAlert,
} from "lucide-react";
import { View } from "@/lib/types";
import { Dot, PageTitle } from "@/components/ui/badge";

export const RFP_PROPOSAL_MARKDOWN = `# Executive Proposal: DevOps Server Platform Implementation
## Ministry of Education (MOE) – Roxy Data Center
**Document ID:** RFP-MOE-ROXY-DEVOPS-2026-01  
**Target Installation:** Sovereign On-Premises Deployment, Roxy Data Center  
**Prepared for:** Ministry of Education Procurement & Evaluation Committee  
**Prepared by:** Sovereign Agentic Systems & Cloud Infrastructure Fleet  
**Status:** Complete Technical & Commercial Proposal  

---

### 1. Executive Summary & Strategic Scope
The Ministry of Education (MOE) is advancing a critical digital transformation initiative to modernize software development, automated testing, security compliance, and continuous delivery across national-scale educational platforms. We propose an enterprise-grade, sovereign on-premises deployment of the DevOps Server Platform at the Roxy Data Center.

#### Operational Imperatives Addressed:
1. **Eliminate Tool Fragmentation:** Replace disjointed legacy tools with a unified DevOps platform encompassing Git SCM, declarative CI/CD pipelines, Agile Scrum/Kanban boards, and a universal package registry.
2. **100% Sovereign Data Residency:** 100% on-premises deployment inside the Roxy Data Center with strict air-gapping—zero telemetry or external cloud egress dependencies.
3. **Embedded DevSecOps Automation:** Shift security left with automated SAST (OWASP Top 10), dependency vulnerability analysis (SCA), secret detection, and container image inspection.
4. **Automated Compliance & Governance:** Implement cryptographic two-person integrity approval gates before deployments reach production environments.

---

### 2. Sovereign Air-Gapped Architecture Blueprint (Roxy DC)
The platform is deployed in an active-active clustered architecture across high-availability compute tiers within the Roxy Data Center:
- **Perimeter & Ingress:** F5 / NGINX Plus HA Load Balancer terminating internal TLS 1.3 with SAML 2.0 and Kerberos integration into MOE Active Directory.
- **Application Control Plane:** Clustered DevOps Server nodes running distributed Git engines, Agile planning boards, and universal package registries.
- **Dynamic Runner Fabric:** Auto-scaling containerized execution nodes partitioned into build/test, DevSecOps security scanning, and Canary deployment pools.
- **Database & State Tier:** PostgreSQL High Availability cluster managed by Patroni with continuous streaming WAL archiving (RPO < 1h, RTO < 2h).
- **Enterprise Storage Tier:** NFSv4 / NVMe-oF enterprise SAN/NAS with AES-256 encryption at rest.

---

### 3. Mandatory Compliance Traceability Matrix (15/15 Compliant)
| Requirement ID | RFP Section | Requirement Item | Proposed Technical Solution | Verification & Test Protocol | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| REQ-01 | Section 1 & 2 | Sovereign Air-Gapped Deployment | 100% on-premises at Roxy DC with zero outbound telemetry | Network egress blocking test; bare-metal hypervisor verification | COMPLIANT |
| REQ-02 | Section 3 | Full Lifecycle Turnkey Support | Architecture, clustering, AD integration, 5 training tracks, hypercare | Milestone signoff protocol across all 5 deployment stages | COMPLIANT |
| REQ-03 | Section 4.1 | Distributed Git SCM & Code Review | Protected branch policies, required peer review gates, signed commits, RBAC | Tamper-evident audit log verification for push, pull, review | COMPLIANT |
| REQ-04 | Section 4.2 | Declarative CI/CD & Distributed Runners | YAML pipeline definitions, parallel containerized runners, artifact caching | End-to-end automated parallel test pipeline execution under load | COMPLIANT |
| REQ-05 | Section 4.3 | Agile Project & Work Management | Scrum & Kanban boards, portfolio roadmaps, commit-to-issue traceability | Bidirectional commit-to-issue reference linking validation | COMPLIANT |
| REQ-06 | Section 4.4 | Universal Package & Artifact Registry | Air-gapped proxy caching for Docker/OCI, Maven, npm, PyPI, Helm, NuGet | SHA-256 package verification, local proxy pull in air-gap mode | COMPLIANT |
| REQ-07 | Section 4.5 | Enterprise Identity & Active Directory | Native integration with MOE Active Directory & LDAP, role sync, CEF logging | SAML 2.0 / Kerberos SSO login and group role mapping | COMPLIANT |
| REQ-08 | Section 5.1 | Integrated DevSecOps Security Suite | Continuous SAST (OWASP Top 10), SCA scanning, pre-receive secret scanning | Automatic pipeline block on high/critical CVEs or leaked secrets | COMPLIANT |
| REQ-09 | Section 5.2 | Infrastructure as Code (IaC) Support | Native execution and linting for Terraform, Ansible, and Kubernetes manifests | Automated policy-as-code linting and staging dry-run validation | COMPLIANT |
| REQ-10 | Section 5.3 | Multi-Environment Deployment Strategies | Automated Canary splitting (5% -> 100%), Blue/Green VIP, zero-downtime rolling | Zero-packet-drop VIP failover and instant rollback drill | COMPLIANT |
| REQ-11 | Section 5.4 | Real-Time Observability & Monitoring | Pipeline performance analytics, developer metrics, syslog forwarding to SIEM | Real-time alert dispatch to MOE Network Operations Center webhook | COMPLIANT |
| REQ-12 | Section 5.5 | OpenAPI 3.0 REST Endpoints & Webhooks | Programmatic access via authenticated REST APIs and webhook dispatchers | Automated API contract testing and event webhook listener test | COMPLIANT |
| REQ-13 | Section 6.1-6.2 | Policy Enforcement & DORA Metrics | Two-person integrity approval gates for prod; real-time DORA analytics | Multi-signature production deployment challenge hold validation | COMPLIANT |
| REQ-14 | Section 6.3-6.4 | High Availability & Automated DR | Active/active cluster with PostgreSQL Patroni HA; WAL archiving (RPO<1h, RTO<2h) | Simulated hardware failover drill & bare-metal DR restore | COMPLIANT |
| REQ-15 | Section 7-11 | Turnkey Package, Licensing & 24/7 SLA | Unlimited Enterprise platform license; runbooks; 5 workshops; 24/7 Tier-3 SLA | 15-minute response SLA drill for Sev-1 incident simulation | COMPLIANT |

---

### 4. Commercial Model & Multi-Tier Labor Pricing
#### Professional Services Labor Breakdown (800 Hours)
- **Tier 1: Senior Principal DevOps Architect:** 120 hrs @ $210/hr = $25,200.00 USD  
- **Tier 2: Lead DevSecOps & Pipeline Engineers:** 280 hrs @ $160/hr = $44,800.00 USD  
- **Tier 3: Systems Integration & Identity Specialists:** 160 hrs @ $130/hr = $20,800.00 USD  
- **Tier 4: Training & Documentation Specialists:** 100 hrs @ $100/hr = $10,000.00 USD  
- **Tier 5: 24/7 Hypercare & Operations Engineers:** 140 hrs @ $90/hr = $12,600.00 USD  

**Subtotal Professional Services Labor:** $113,400.00 USD (800 Hours)

#### Software Licensing & Warranty
- **DevOps Server Enterprise Platform License (Unlimited Developer Seats):** $48,000.00 USD  
- **24/7 Mission-Critical SLA & Warranty (1 Year):** Included ($0.00 USD)  

**GRAND TOTAL TURNKEY FIXED PRICE:** **$161,400.00 USD**

---

### 5. 16-Week Phased Implementation Roadmap
- **Phase 1: Inception, Security Baseline & AD Federation (Weeks 1–4)**
- **Phase 2: Platform Clustered Installation at Roxy DC (Weeks 5–8)**
- **Phase 3: DevSecOps Automation, Runner Fabric & Pilot Onboarding (Weeks 9–12)**
- **Phase 4: Security Audit, Disaster Recovery & HA Drills (Weeks 13–14)**
- **Phase 5: Knowledge Transfer, Production Cutover & Hypercare (Weeks 15–16)**
`;

export const GOV_CLOUD_PROPOSAL_MARKDOWN = `# Mission Deliverable: Government Cloud Migration Executive Proposal
## Case: ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest RFP & Extract Mandatory Technical Compliance Criteria Specialist  
**Assigned Fleet:** Government Cloud Proposal Synthesis Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-26T20:44:23Z  

### Executive Summary & Final Solution

| Item | Detail |
|------|--------|
| **Proposal Title** | Government Cloud Migration – Executive Proposal |
| **Total Labor Cost** | **$50,500.00 USD** |
| **Compliance Coverage** | 9 mandatory technical criteria fully mapped |
| **Key Differentiators** | • DoD 8500.01 & FedRAMP High<br>• Multi-tiered engineering<br>• 99.95% uptime SLA |

---

## Solution Architecture & Technical Alignment
1. **Identity & Access Management (IAM):** MFA enforced for all administrative logins (CR-001).
2. **Storage Service:** FIPS 140-2 validated AES-256 encryption at rest (CR-002).
3. **SIEM Layer:** Continuous audit logging & telemetry streaming (CR-003).
4. **Regional U.S. Storage:** 100% data residency within CONUS facilities (CR-004).
5. **Geo-Separated Backup:** Automated daily DR replication to secondary facility >=500 miles away (CR-005).
6. **Compliance Module:** Automated quarterly ISO/IEC 27001 audit report synthesis (CR-006).
7. **Penetration Testing:** Annual accredited third-party penetration testing program (CR-007).
8. **High-Availability Fabric:** Multi-zone clustered topology delivering 99.95% availability (CR-008).
9. **Edge Caching & Optimization:** Global CDN guaranteeing latency <=200 ms (CR-009).

---

## Detailed Pricing Model (Total Labor Cost: $50,500.00 USD)
- **CR-001 (MFA):** Mid Engineer (40 hrs @ $80/hr) = $3,200.00 USD
- **CR-002 (Encryption):** Senior Engineer (60 hrs @ $120/hr) = $7,200.00 USD
- **CR-003 (SIEM Integration):** Senior Engineer (80 hrs @ $120/hr) = $9,600.00 USD
- **CR-004 (Data Residency):** Senior Engineer (20 hrs @ $120/hr) = $2,400.00 USD
- **CR-005 (Geo-Backup >=500mi):** Mid Engineer (30 hrs @ $80/hr) = $2,400.00 USD
- **CR-006 (ISO 27001 Audit):** Project Manager (30 hrs @ $110/hr) = $3,300.00 USD
- **CR-007 (Pen Testing):** Senior Engineer (50 hrs @ $120/hr) = $6,000.00 USD
- **CR-008 (99.95% Uptime SLA):** Mid Engineer (100 hrs @ $80/hr) = $8,000.00 USD
- **CR-009 (Latency <=200ms):** Senior Engineer (70 hrs @ $120/hr) = $8,400.00 USD

**GRAND TOTAL TURNKEY FIXED PRICE:** **$50,500.00 USD**
`;

export function ProposalDossierView({
  onNavigate,
  onBack,
  initialVersion,
}: {
  onNavigate?: (view: View) => void;
  onBack?: () => void;
  initialVersion?: "latest" | "moe";
}) {
  const [proposalVersion, setProposalVersion] = useState<"latest" | "moe">(initialVersion ?? "latest");
  const [activeTab, setActiveTab] = useState<"summary" | "architecture" | "compliance" | "pricing" | "roadmap" | "transmittal">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const latestComplianceItems = [
    { id: "CR-001", section: "Identity Controls", name: "Mandatory Admin MFA (NIST SP 800-63B)", desc: "MFA enforced for all administrative and elevated logins.", status: "COMPLIANT" },
    { id: "CR-002", section: "Security Controls", name: "Encryption at Rest (FIPS 140-2 AES-256)", desc: "FIPS-validated AES-256 encryption at rest for cloud storage and DBs.", status: "COMPLIANT" },
    { id: "CR-003", section: "Monitoring & SIEM", name: "Continuous SIEM Monitoring (NIST SP 800-137)", desc: "Real-time threat monitoring and automated SIEM ingestion.", status: "COMPLIANT" },
    { id: "CR-004", section: "Data Residency", name: "U.S. Data Residency Only (FedRAMP High)", desc: "All data stored exclusively within CONUS with zero foreign transfer.", status: "COMPLIANT" },
    { id: "CR-005", section: "Business Continuity", name: "Geo-Separated Backup (≥500 mi)", desc: "Automated daily snapshot backups stored in secondary region >=500 miles away.", status: "COMPLIANT" },
    { id: "CR-006", section: "Governance & Audit", name: "Quarterly ISO/IEC 27001 Audit Reports", desc: "Structured compliance reporting aligned to ISO/IEC 27001 Annex A.", status: "COMPLIANT" },
    { id: "CR-007", section: "Assurance", name: "Annual Third-Party Penetration Testing", desc: "Rigorous third-party penetration testing conducted annually by accredited auditors.", status: "COMPLIANT" },
    { id: "CR-008", section: "Availability SLA", name: "System Uptime SLA (99.95% Monthly)", desc: "High availability multi-zone architecture with auto-scaling.", status: "COMPLIANT" },
    { id: "CR-009", section: "Performance SLA", name: "End-User Latency ≤200 ms Average", desc: "Edge routing and CDN caching guaranteeing latency <= 200 ms.", status: "COMPLIANT" },
  ];

  const complianceItems = [
    { id: "REQ-01", section: "Section 1 & 2", name: "Sovereign Air-Gapped Deployment", desc: "DevOps platform deployed 100% on-premises at Roxy DC with zero outbound telemetry.", status: "COMPLIANT" },
    { id: "REQ-02", section: "Section 3", name: "Full Lifecycle Turnkey Support", desc: "Turnkey delivery covering architecture, clustering, AD, 5 training tracks, and hypercare.", status: "COMPLIANT" },
    { id: "REQ-03", section: "Section 4.1", name: "Distributed Git SCM & Code Review", desc: "Enterprise Git core with protected branches, peer reviews, signed commits, and RBAC.", status: "COMPLIANT" },
    { id: "REQ-04", section: "Section 4.2", name: "Declarative CI/CD & Distributed Runners", desc: "Declarative YAML pipelines with parallel containerized runners and artifact caching.", status: "COMPLIANT" },
    { id: "REQ-05", section: "Section 4.3", name: "Agile Project & Work Management", desc: "Integrated Scrum and Kanban planning boards, roadmaps, and commit traceability.", status: "COMPLIANT" },
    { id: "REQ-06", section: "Section 4.4", name: "Universal Package Registry", desc: "Air-gapped proxy caching for Docker, Maven, npm, PyPI, Helm, and NuGet.", status: "COMPLIANT" },
    { id: "REQ-07", section: "Section 4.5", name: "Enterprise Identity & Active Directory", desc: "Native integration with MOE Active Directory & LDAP with automated sync.", status: "COMPLIANT" },
    { id: "REQ-08", section: "Section 5.1", name: "Integrated DevSecOps Suite", desc: "Continuous SAST (OWASP Top 10), SCA scanning, pre-receive secret scanning.", status: "COMPLIANT" },
    { id: "REQ-09", section: "Section 5.2", name: "Infrastructure as Code Support", desc: "Native execution and linting for Terraform, Ansible, and Kubernetes manifests.", status: "COMPLIANT" },
    { id: "REQ-10", section: "Section 5.3", name: "Canary & Blue/Green Deployments", desc: "Automated Canary traffic splitting and zero-downtime rolling updates.", status: "COMPLIANT" },
    { id: "REQ-11", section: "Section 5.4", name: "Real-Time Observability & Monitoring", desc: "Pipeline performance analytics, developer metrics, syslog forwarding to SIEM.", status: "COMPLIANT" },
    { id: "REQ-12", section: "Section 5.5", name: "OpenAPI 3.0 Endpoints & Webhooks", desc: "Comprehensive programmatic access via authenticated REST APIs and webhooks.", status: "COMPLIANT" },
    { id: "REQ-13", section: "Section 6.1-6.2", name: "Policy Enforcement & DORA Metrics", desc: "Two-person integrity approval gates for prod; real-time DORA productivity analytics.", status: "COMPLIANT" },
    { id: "REQ-14", section: "Section 6.3-6.4", name: "High Availability & Automated DR", desc: "Active/active cluster with PostgreSQL Patroni HA (RPO < 1h, RTO < 2h).", status: "COMPLIANT" },
    { id: "REQ-15", section: "Section 7-11", name: "Turnkey Package, Licensing & 24/7 SLA", desc: "Unlimited Enterprise platform license; runbooks; 5 workshops; 24/7 Tier-3 SLA.", status: "COMPLIANT" },
  ];

  const currentCompliance = proposalVersion === "latest" ? latestComplianceItems : complianceItems;
  const filteredCompliance = currentCompliance.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q);
  });

  const currentMarkdown = proposalVersion === "latest" ? GOV_CLOUD_PROPOSAL_MARKDOWN : RFP_PROPOSAL_MARKDOWN;

  function copyMarkdown() {
    navigator.clipboard.writeText(currentMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadMarkdown() {
    const blob = new Blob([currentMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = proposalVersion === "latest" ? "gov_cloud_migration_proposal.md" : "moe_devops_server_rfp_proposal.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-shell">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f0f6f4", border: "1px solid #cce2d9", padding: "8px 16px", borderRadius: "6px", marginBottom: "14px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase" }}>Active Proposal:</span>
          <button
            type="button"
            onClick={() => setProposalVersion("latest")}
            style={{
              padding: "5px 12px",
              fontSize: "11px",
              fontWeight: proposalVersion === "latest" ? 700 : 500,
              background: proposalVersion === "latest" ? "#195d56" : "#ffffff",
              color: proposalVersion === "latest" ? "#ffffff" : "#455953",
              border: "1px solid #cad8d1",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Government Cloud Migration (Latest · 9/9 Compliant)
          </button>
          <button
            type="button"
            onClick={() => setProposalVersion("moe")}
            style={{
              padding: "5px 12px",
              fontSize: "11px",
              fontWeight: proposalVersion === "moe" ? 700 : 500,
              background: proposalVersion === "moe" ? "#195d56" : "#ffffff",
              color: proposalVersion === "moe" ? "#ffffff" : "#455953",
              border: "1px solid #cad8d1",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            MOE DevOps Server (Roxy DC · 15/15 Compliant)
          </button>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          {onBack && (
            <button className="secondary-button" onClick={onBack} style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontWeight: 700, color: "#195d56", background: "#ffffff" }}>
              <ArrowRight size={13} style={{ transform: "rotate(180deg)" }} /> All Deliverables
            </button>
          )}
          <button className="secondary-button" onClick={copyMarkdown}>
            {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy Markdown"}
          </button>
          <button className="secondary-button" onClick={downloadMarkdown}>
            <Download size={14} /> Download .md
          </button>
          <button className="secondary-button" onClick={() => window.print()}>
            <Printer size={14} /> Print / Export PDF
          </button>
        </div>
      </div>

      <PageTitle
        eyebrow={proposalVersion === "latest" ? "EXECUTIVE PROPOSAL · ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18" : "EXECUTIVE PROPOSAL · RFP-MOE-ROXY-DEVOPS-2026-01"}
        title={proposalVersion === "latest" ? "Government Cloud Migration Proposal" : "DevOps Server Platform Sovereign Implementation"}
        subtitle="Cryptographically verified autonomous proposal deliverable meeting 100% of technical, compliance, and commercial specifications."
      />

      {/* Tabs */}
      <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid #cad8d1", paddingBottom: "8px", margin: "16px 0" }}>
        {(["summary", "compliance", "pricing", "roadmap", "transmittal"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: activeTab === tab ? 700 : 500,
              background: activeTab === tab ? "#195d56" : "transparent",
              color: activeTab === tab ? "#ffffff" : "#455953",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a" }}>Executive Summary &amp; Strategic Alignment</h3>
          <p style={{ fontSize: "13px", lineHeight: "1.7", color: "#365148", marginTop: "8px" }}>
            {proposalVersion === "latest"
              ? "Comprehensive sovereign cloud migration proposal for government agency infrastructure. Fully adheres to DoD 8500.01 and FedRAMP High security baselines with 9/9 technical criteria verified."
              : "Enterprise-grade sovereign on-premises deployment of the DevOps Server Platform at the Roxy Data Center for the Ministry of Education. 15/15 mandatory requirements satisfied with zero external egress dependencies."}
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px", marginTop: "18px" }}>
            <div style={{ background: "#f5faf7", padding: "14px", borderRadius: "6px", border: "1px solid #dae7e0" }}>
              <div style={{ fontSize: "11px", color: "#5d7870", fontWeight: 700 }}>FIXED PRICE TOTAL</div>
              <div style={{ fontSize: "22px", fontWeight: 800, color: "#1a5c50", marginTop: "4px" }}>
                {proposalVersion === "latest" ? "$50,500.00 USD" : "$161,400.00 USD"}
              </div>
            </div>
            <div style={{ background: "#f5faf7", padding: "14px", borderRadius: "6px", border: "1px solid #dae7e0" }}>
              <div style={{ fontSize: "11px", color: "#5d7870", fontWeight: 700 }}>ENGINEERING HOURS</div>
              <div style={{ fontSize: "22px", fontWeight: 800, color: "#1a5c50", marginTop: "4px" }}>
                {proposalVersion === "latest" ? "480 Hours" : "800 Hours"}
              </div>
            </div>
            <div style={{ background: "#f5faf7", padding: "14px", borderRadius: "6px", border: "1px solid #dae7e0" }}>
              <div style={{ fontSize: "11px", color: "#5d7870", fontWeight: 700 }}>COMPLIANCE SCORE</div>
              <div style={{ fontSize: "22px", fontWeight: 800, color: "#236f66", marginTop: "4px" }}>
                100% Compliant
              </div>
            </div>
          </div>
        </section>
      )}

      {activeTab === "compliance" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a", margin: 0 }}>Compliance Traceability Matrix</h3>
            <div style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: "10px", top: "8px", color: "#7a9088" }} />
              <input
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Filter requirements..."
                style={{ padding: "6px 12px 6px 30px", fontSize: "12px", border: "1px solid #cad8d1", borderRadius: "4px" }}
              />
            </div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#f0f5f2", borderBottom: "2px solid #cad8d1" }}>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>ID</th>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>Requirement</th>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>Description</th>
                <th style={{ padding: "8px 12px", textAlign: "center", color: "#195d56" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredCompliance.map((item, idx) => (
                <tr key={item.id} style={{ borderBottom: "1px solid #eef3f1", background: idx % 2 === 0 ? "#ffffff" : "#fbfdfc" }}>
                  <td style={{ padding: "8px 12px", fontWeight: 700, color: "#163a33" }}>{item.id}</td>
                  <td style={{ padding: "8px 12px", fontWeight: 600, color: "#253b35" }}>{item.name}</td>
                  <td style={{ padding: "8px 12px", color: "#4f655e" }}>{item.desc}</td>
                  <td style={{ padding: "8px 12px", textAlign: "center" }}>
                    <span style={{ fontSize: "10px", background: "#e4f3ed", color: "#196656", padding: "2px 8px", borderRadius: "3px", fontWeight: 700 }}>
                      {item.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {activeTab === "pricing" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Commercial Pricing &amp; Labor Model</h3>
          <p style={{ fontSize: "12px", color: "#4f655e", marginTop: "4px" }}>
            Fixed-price turnkey delivery inclusive of all specialized engineering labor tiers, security reviews, and knowledge transfer.
          </p>
          <div style={{ marginTop: "14px", padding: "16px", background: "#f8fbf9", borderRadius: "6px", border: "1px solid #dae7e0" }}>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#163a33" }}>
              Total Contract Value: <span style={{ color: "#1a5c50" }}>{proposalVersion === "latest" ? "$50,500.00 USD" : "$161,400.00 USD"}</span>
            </div>
            <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "4px" }}>
              Zero scope creep fixed-price commitment with milestone acceptance sign-offs.
            </div>
          </div>
        </section>
      )}

      {activeTab === "roadmap" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Implementation Roadmap</h3>
          <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #236f66" }}>
              <strong style={{ fontSize: "13px", color: "#163a33" }}>Phase 1: Inception &amp; Security Baseline</strong>
              <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "2px" }}>Weeks 1–4 · Architecture review, network isolation, identity federation.</div>
            </div>
            <div style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #236f66" }}>
              <strong style={{ fontSize: "13px", color: "#163a33" }}>Phase 2: Clustered Installation &amp; Storage</strong>
              <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "2px" }}>Weeks 5–8 · HA compute, Patroni DB cluster, and enterprise SAN storage.</div>
            </div>
            <div style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #236f66" }}>
              <strong style={{ fontSize: "13px", color: "#163a33" }}>Phase 3: DevSecOps Runner Fabric &amp; Pilot Onboarding</strong>
              <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "2px" }}>Weeks 9–12 · Dynamic runners, SAST/SCA automation, onboarding pilot apps.</div>
            </div>
            <div style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #236f66" }}>
              <strong style={{ fontSize: "13px", color: "#163a33" }}>Phase 4: Security Audit, Penetration Test &amp; DR Drills</strong>
              <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "2px" }}>Weeks 13–14 · Third-party pen test, RPO/RTO validation, failover drill.</div>
            </div>
            <div style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #236f66" }}>
              <strong style={{ fontSize: "13px", color: "#163a33" }}>Phase 5: Knowledge Transfer, Cutover &amp; 30-Day Hypercare</strong>
              <div style={{ fontSize: "12px", color: "#5d7870", marginTop: "2px" }}>Weeks 15–16 · 5 training workshops, production go-live, 24/7 hypercare.</div>
            </div>
          </div>
        </section>
      )}

      {activeTab === "transmittal" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a" }}>Formal Transmittal &amp; Cryptographic Attestation</h3>
          <p style={{ fontSize: "12px", color: "#4f655e", lineHeight: "1.7", marginTop: "10px" }}>
            We confirm our commitment to execute this deployment within a fixed timeline and turnkey budget.
            All deliverables are signed and committed under SHA-256 cryptographic hashes.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "28px", paddingTop: "20px", borderTop: "1px dashed #cad8d1" }}>
            <div>
              <div style={{ borderBottom: "1px solid #94a89f", height: "30px", marginBottom: "8px" }} />
              <strong style={{ fontSize: "12px", color: "#1a3831" }}>Principal Architect</strong>
              <div style={{ fontSize: "11px", color: "#647770" }}>Sovereign Agentic Systems Fleet Lead</div>
            </div>
            <div>
              <div style={{ borderBottom: "1px solid #94a89f", height: "30px", marginBottom: "8px" }} />
              <strong style={{ fontSize: "12px", color: "#1a3831" }}>Committee Acceptance</strong>
              <div style={{ fontSize: "11px", color: "#647770" }}>Date of Review: ____________________</div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Incident Dossier Template Helper
// ─────────────────────────────────────────────────────────────────────────────

interface IncidentDossierConfig {
  caseId: string;
  classification: string;
  title: string;
  subtitle: string;
  overview: string;
  targetAsset: string;
  summaryHighlights: { label: string; value: string; color?: string }[];
  killChainEvents: { id: string; time: string; stage: string; desc: string; mitre: string }[];
  iocItems: { id: string; tactic: string; name: string; desc: string; test: string; status: string }[];
  containmentActions: { priority: string; action: string; target: string; protocol: string; status: string }[];
  reportMarkdown: string;
  downloadFilename: string;
}

function IncidentDossierTemplate({
  config,
  onNavigate,
  onBack,
}: {
  config: IncidentDossierConfig;
  onNavigate?: (view: View) => void;
  onBack?: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const filteredIOCs = config.iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  function copyMarkdown() {
    navigator.clipboard.writeText(config.reportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([config.reportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = config.downloadFilename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-shell">
      <PageTitle
        eyebrow={`${config.caseId} · ${config.classification}`}
        title={config.title}
        subtitle={config.subtitle}
        action={
          <>
            {onBack && (
              <button
                className="secondary-button"
                onClick={onBack}
                style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontWeight: 700, color: "#195d56", background: "#ffffff" }}
              >
                <ArrowRight size={13} style={{ transform: "rotate(180deg)" }} /> All Deliverables
              </button>
            )}
            <button className="secondary-button" onClick={copyMarkdown}>
              {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied report" : "Copy Report"}
            </button>
            <button className="secondary-button" onClick={downloadReport}>
              <Download size={14} /> Download .md
            </button>
            <button className="secondary-button" onClick={() => window.print()}>
              <Printer size={14} /> Print / Export PDF
            </button>
            {onNavigate && (
              <button className="primary-button" onClick={() => onNavigate("Decision rooms")}>
                <FileCheck2 size={14} /> Decision Rooms
              </button>
            )}
          </>
        }
      />

      <div className="scope" style={{ marginBottom: "16px" }}>
        <span><Layers3 size={14} /> {config.caseId}</span>
        <i />
        <span><Dot color="orange" /> CONTAINMENT ENFORCED</span>
        <i />
        <span><Server size={14} /> {config.targetAsset}</span>
        <i />
        <span>{config.iocItems.length} IOCs MITIGATED</span>
        <small>Status: Awaiting Governance Sign-Off</small>
      </div>

      {/* Header Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, #1d2b27 0%, #151e1c 50%, #1f3630 100%)",
          border: "1px solid #33594f",
          borderRadius: "8px",
          padding: "22px 28px",
          color: "#f5ece8",
          boxShadow: "0 4px 20px rgba(18, 36, 32, 0.2)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "18px",
          marginBottom: "16px",
        }}
      >
        <div style={{ flex: "1 1 560px" }}>
          <div style={{ fontSize: "9px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", color: "#8ee0c9", marginBottom: "4px" }}>
            CASE ID: {config.caseId} · {config.classification}
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0 8px", color: "#ffffff", letterSpacing: "-0.2px" }}>
            {config.title}
          </h2>
          <p style={{ color: "#d1e2dc", fontSize: "11.5px", margin: 0, lineHeight: 1.55, maxWidth: "680px" }}>
            {config.overview}
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            {config.summaryHighlights.map((h, i) => (
              <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "rgba(35, 111, 102, 0.25)", color: "#8ee0c9", border: "1px solid rgba(35, 111, 102, 0.4)" }}>
                <ShieldAlert size={12} /> {h.label}: {h.value}
              </span>
            ))}
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "4px", minWidth: "200px", background: "rgba(0,0,0,0.3)", padding: "14px 18px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ fontSize: "10px", color: "#8ee0c9", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 700 }}>
            THREAT SEVERITY
          </div>
          <div style={{ fontSize: "24px", fontWeight: 800, color: "#ff7043", fontFamily: "var(--font-geist-mono), monospace" }}>
            CRITICAL SEV-1
          </div>
          <div style={{ fontSize: "10px", color: "#8ee0c9", fontWeight: 600 }}>
            Containment Active
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid #cad8d1", paddingBottom: "8px", margin: "16px 0" }}>
        {(["summary", "killchain", "iocs", "remediation", "timeline", "attestation"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: activeTab === tab ? 700 : 500,
              background: activeTab === tab ? "#195d56" : "transparent",
              color: activeTab === tab ? "#ffffff" : "#455953",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {tab === "iocs" ? "Indicators (IOCs)" : tab === "killchain" ? "Attack Kill Chain" : tab}
          </button>
        ))}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Incident Triage &amp; Response Summary</h3>
          <p style={{ fontSize: "13px", lineHeight: "1.7", color: "#365148", marginTop: "8px" }}>
            {config.overview}
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px", marginTop: "16px" }}>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", padding: "14px", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#6a7c76", fontWeight: 700 }}>TARGET ASSET</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#163a33", marginTop: "4px" }}>{config.targetAsset}</div>
            </div>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", padding: "14px", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#6a7c76", fontWeight: 700 }}>NEUTRALIZED IOCs</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#236f66", marginTop: "4px" }}>{config.iocItems.length} Identified &amp; Blocked</div>
            </div>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", padding: "14px", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#6a7c76", fontWeight: 700 }}>CONTAINMENT STATUS</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#196656", marginTop: "4px" }}>Enforced &amp; Cryptographically Sealed</div>
            </div>
          </div>
        </section>
      )}

      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Reconstructed MITRE ATT&amp;CK Kill Chain</h3>
          <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
            {config.killChainEvents.map((evt) => (
              <div key={evt.id} style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", borderLeft: "4px solid #b44426" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontSize: "13px", color: "#163a33" }}>{evt.stage}</strong>
                  <span style={{ fontSize: "11px", color: "#8a9e96", fontFamily: "var(--font-geist-mono), monospace" }}>{evt.time}</span>
                </div>
                <div style={{ fontSize: "12px", color: "#475e56", marginTop: "4px" }}>{evt.desc}</div>
                <div style={{ fontSize: "10px", color: "#b44426", fontWeight: 700, marginTop: "4px" }}>MITRE: {evt.mitre}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a", margin: 0 }}>Indicators of Compromise (IOCs)</h3>
            <div style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: "10px", top: "8px", color: "#7a9088" }} />
              <input
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Filter IOCs..."
                style={{ padding: "6px 12px 6px 30px", fontSize: "12px", border: "1px solid #cad8d1", borderRadius: "4px" }}
              />
            </div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#f0f5f2", borderBottom: "2px solid #cad8d1" }}>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>IOC ID</th>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>Tactic</th>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#195d56" }}>Indicator Name &amp; Description</th>
                <th style={{ padding: "8px 12px", textAlign: "center", color: "#195d56" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredIOCs.map((ioc, idx) => (
                <tr key={ioc.id} style={{ borderBottom: "1px solid #eef3f1", background: idx % 2 === 0 ? "#ffffff" : "#fbfdfc" }}>
                  <td style={{ padding: "8px 12px", fontWeight: 700, color: "#163a33" }}>{ioc.id}</td>
                  <td style={{ padding: "8px 12px", fontWeight: 600, color: "#b44426" }}>{ioc.tactic}</td>
                  <td style={{ padding: "8px 12px", color: "#4f655e" }}>
                    <div style={{ fontWeight: 600, color: "#253b35" }}>{ioc.name}</div>
                    <div style={{ fontSize: "11px", marginTop: "2px" }}>{ioc.desc}</div>
                  </td>
                  <td style={{ padding: "8px 12px", textAlign: "center" }}>
                    <span style={{ fontSize: "10px", background: "#e4f3ed", color: "#196656", padding: "2px 8px", borderRadius: "3px", fontWeight: 700 }}>
                      {ioc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Containment &amp; Remediation Playbook</h3>
          <div style={{ marginTop: "14px", display: "flex", flexDirection: "column", gap: "10px" }}>
            {config.containmentActions.map((act, i) => (
              <div key={i} style={{ padding: "12px 16px", background: "#f8fbf9", borderRadius: "6px", border: "1px solid #dae7e0" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong style={{ fontSize: "13px", color: "#163a33" }}>{act.action}</strong>
                  <span style={{ fontSize: "10px", fontWeight: 700, background: "#e4f3ed", color: "#196656", padding: "2px 6px", borderRadius: "3px" }}>
                    {act.status}
                  </span>
                </div>
                <div style={{ fontSize: "11px", color: "#6a7c76", marginTop: "3px" }}>Target: {act.target}</div>
                <pre style={{ fontSize: "11px", background: "#edf4f1", padding: "8px 10px", borderRadius: "4px", marginTop: "6px", fontFamily: "var(--font-geist-mono), monospace", whiteSpace: "pre-wrap" }}>
                  {act.protocol}
                </pre>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "20px" }}>
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "#1b2f2a" }}>Chronological Incident Timeline</h3>
          <div style={{ marginTop: "16px", paddingLeft: "16px", borderLeft: "2px solid #236f66", display: "flex", flexDirection: "column", gap: "16px" }}>
            {config.killChainEvents.map((evt, i) => (
              <div key={i} style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: "-22px", top: "3px", width: "10px", height: "10px", borderRadius: "50%", background: "#236f66" }} />
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#b44426" }}>{evt.time} — {evt.stage}</div>
                <div style={{ fontSize: "12px", color: "#253b35", marginTop: "2px" }}>{evt.desc}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a" }}>Evidence Chain-of-Custody &amp; Sign-Off</h3>
          <p style={{ fontSize: "12px", color: "#4f655e", lineHeight: "1.7", marginTop: "8px" }}>
            This attestation certifies that all incident forensic logs and indicators for {config.caseId} have been preserved, sanitized, and contained.
            Automated defensive countermeasures were executed and cryptographically signed.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "28px", paddingTop: "20px", borderTop: "1px dashed #cad8d1" }}>
            <div>
              <div style={{ borderBottom: "1px solid #94a89f", height: "30px", marginBottom: "8px" }} />
              <strong style={{ fontSize: "12px", color: "#1a3831" }}>Lead Incident Commander</strong>
              <div style={{ fontSize: "11px", color: "#647770" }}>Autonomous SOC Specialist Fleet</div>
            </div>
            <div>
              <div style={{ borderBottom: "1px solid #94a89f", height: "30px", marginBottom: "8px" }} />
              <strong style={{ fontSize: "12px", color: "#1a3831" }}>Chief Information Security Officer (CISO)</strong>
              <div style={{ fontSize: "11px", color: "#647770" }}>Date of Review: ____________________</div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Specialized Incident Dossier Views
// ─────────────────────────────────────────────────────────────────────────────

export function SocIncidentDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "INCIDENT-SOC-2026-081",
        classification: "CONFIDENTIAL / TLP:AMBER",
        title: "Host Ransomware Triage & Lateral Movement Investigation",
        subtitle: "End-to-end incident triage, forensic threat analysis, MITRE ATT&CK mapping, and automated containment rule execution.",
        overview: "High-severity threat triage across finance endpoint WORKSTATION-FIN-09. Autonomous containment executed: outbound C2 beacons sinkholed, network egress quarantined via Palo Alto policy, and AD credential tokens revoked.",
        targetAsset: "WORKSTATION-FIN-09 (10.14.22.84)",
        summaryHighlights: [
          { label: "MITRE ATT&CK", value: "4 Techniques" },
          { label: "Endpoint", value: "Isolated" },
          { label: "IOCs", value: "6/6 Mitigated" },
        ],
        killChainEvents: [
          { id: "E1", time: "14:02:18", stage: "Initial Execution", desc: "Suspicious Base64 PowerShell execution on WORKSTATION-FIN-09 attempting memory injection.", mitre: "T1059.001 PowerShell" },
          { id: "E2", time: "14:05:30", stage: "Persistence", desc: "Scheduled task SysHealthCheck registered at \\Microsoft\\Windows\\UpdateOrchestrator\\SysHealthCheck.", mitre: "T1053.005 Scheduled Task" },
          { id: "E3", time: "14:08:12", stage: "Discovery", desc: "Automated port scan across 10.14.22.0/24 targeting SMB (445) and RDP (3389).", mitre: "T1046 Network Discovery" },
          { id: "E4", time: "14:12:00", stage: "Command & Control", desc: "Encrypted HTTPS beacons to 198.51.100.24:8443 every 60s with 10% jitter.", mitre: "T1071.001 TLS C2" },
        ],
        iocItems: [
          { id: "IOC-01", tactic: "T1059.001 Execution", name: "Base64 Encoded PowerShell", desc: "Encoded command spawned by svchost.exe parent process attempting memory injection and AMSI bypass.", test: "Sysmon Event ID 1 & PowerShell ScriptBlock Logging Event 4104", status: "CONTAINED" },
          { id: "IOC-02", tactic: "T1053.005 Persistence", name: "Scheduled Task SysHealthCheck", desc: "Persistence task registered to execute every 4 hours.", test: "Security Event ID 4698", status: "QUARANTINED" },
          { id: "IOC-03", tactic: "T1046 Network Discovery", name: "Internal Subnet Reconnaissance", desc: "Port scan across 10.14.22.0/24 targeting SMB (445) and RDP (3389).", test: "Zeek conn.log & Internal Switch Telemetry", status: "BLOCKED" },
          { id: "IOC-04", tactic: "T1071.001 C2", name: "TLS Outbound C2 Beacons", desc: "HTTPS beacons to 198.51.100.24:8443 every 60s.", test: "Palo Alto App-ID ssl logs", status: "SINKHOLED" },
          { id: "IOC-05", tactic: "T1078.002 Priv Abuse", name: "Domain User Credential Compromise", desc: "Kerberos TGT ticket requested for corp\\jsmith from non-standard subnet.", test: "AD Event ID 4768 / 4769", status: "REVOKED" },
          { id: "IOC-06", tactic: "T1027 Defense Evasion", name: "High Entropy Obfuscated Payload", desc: "Payload disguised as update cache binary with Shannon entropy 7.84.", test: "PE header & memory scan", status: "IDENTIFIED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "Palo Alto Edge Firewall Quarantine", target: "10.14.22.84", protocol: "Policy Drop rule applied on Top-of-Rack Switch & Palo Alto Gateway", status: "EXECUTED" },
          { priority: "P1: Critical", action: "Active Directory Session Revocation", target: "corp\\jsmith", protocol: "Kerberos TGT invalidated; password reset enforced across MOE domain", status: "EXECUTED" },
          { priority: "P2: High", action: "Forensic Memory Image Capture", target: "WORKSTATION-FIN-09", protocol: "16 GB raw physical memory captured via Volatility agent", status: "COMPLETED" },
          { priority: "P2: High", action: "External C2 Sinkholing", target: "198.51.100.24", protocol: "BGP null-route and internal DNS sinkholing", status: "ENFORCED" },
        ],
        reportMarkdown: `# Incident Investigation Report: Threat Triage & Containment\n## SOC Incident: INCIDENT-SOC-2026-081\n**Classification:** CONFIDENTIAL / TLP:AMBER\n**Target Asset:** WORKSTATION-FIN-09 (10.14.22.84)\n\n### 1. Executive Summary\nHigh-severity telemetry alerts confirmed ransomware staging and persistence on WORKSTATION-FIN-09. All 6 IOCs neutralized.`,
        downloadFilename: "soc_incident_investigation_report.md",
      }}
    />
  );
}

export function K8sBreakoutDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
        classification: "CONFIDENTIAL / TLP:AMBER",
        title: "Kubernetes Container Breakout & Diamorphine LKM Rootkit Dossier",
        subtitle: "Multi-source correlation across container namespaces, kernel audits, and host authentication logs.",
        overview: "A multi-stage container breakout attack was detected, reconstructed, and correlated across container namespaces, kernel audits, and host logs. An initial web compromise escalated to root within the container, followed by injection of Diamorphine LKM rootkit and container breakout to host node execution.",
        targetAsset: "worker-k8s-node-03.prod.internal",
        summaryHighlights: [
          { label: "Attack Stages", value: "4 Mapped" },
          { label: "Host Node", value: "Cordoned & Drained" },
          { label: "Kernel LKM", value: "Diamorphine Blacklisted" },
        ],
        killChainEvents: [
          { id: "Stage 1", time: "12:14:02", stage: "Initial Access & Cron", desc: "Cron job injected into /var/spool/cron/crontabs/www-data establishing reverse shell to 198.51.100.77:4444.", mitre: "T1053.003 Cron" },
          { id: "Stage 2", time: "12:18:40", stage: "Privilege Escalation", desc: "Sudo find passwordless privesc executed elevating to UID 0 inside container.", mitre: "T1548.003 Sudo Caching" },
          { id: "Stage 3", time: "12:22:11", stage: "Kernel Rootkit Injection", desc: "Diamorphine.ko compiled and inserted into kernel; hooked sys_getdents to cloak rootkit PIDs.", mitre: "T1547.006 Kernel Modules" },
          { id: "Stage 4", time: "12:28:55", stage: "Container Escape to Host", desc: "Container mounted host /dev with CAP_SYS_ADMIN; triggered cgroup release_agent escaping to host.", mitre: "T1611 Escape to Host" },
        ],
        iocItems: [
          { id: "IOC-K8S-01", tactic: "T1053.003 Cron", name: "Crontab Reverse Shell Injection", desc: "Reverse TCP shell to 198.51.100.77:4444 from container.", test: "Linux syslog & auditd", status: "CONTAINED" },
          { id: "IOC-K8S-02", tactic: "T1548.003 Sudo", name: "Sudo find Passwordless Privesc", desc: "www-data ran find -exec /bin/sh to obtain UID 0.", test: "Linux auth.log", status: "QUARANTINED" },
          { id: "IOC-K8S-03", tactic: "T1547.006 LKM", name: "Diamorphine LKM Rootkit", desc: "diamorphine.ko hooks sys_getdents and kill -31.", test: "dmesg taint & auditd init_module", status: "BLACK-LISTED" },
          { id: "IOC-K8S-04", tactic: "T1611 Breakout", name: "cgroup release_agent Escape", desc: "Host root filesystem mounted at /mnt/host-root via CAP_SYS_ADMIN.", test: "auditd mount/cgroup", status: "BLOCKED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "Container Network Namespace Isolation", target: "default/web-frontend-79c864-xk8p9", protocol: "Cilium/Calico NetworkPolicy Ingress & Egress Deny-All enforced immediately", status: "EXECUTED" },
          { priority: "P1: Critical", action: "Kubernetes Host Node Cordon & Drain", target: "worker-k8s-node-03.prod.internal", protocol: "kubectl cordon worker-k8s-node-03; evict non-system workloads", status: "EXECUTED" },
          { priority: "P1: Critical", action: "Kernel Module modprobe Blacklist", target: "worker-k8s-node-03", protocol: "echo 'blacklist diamorphine' >> /etc/modprobe.d/blacklist.conf; unload via rmmod", status: "APPLIED" },
          { priority: "P2: High", action: "eBPF Tetragon Enforcement", target: "Cluster Daemon", protocol: "Real-time block on unauthorized namespace transitions and CAP_SYS_ADMIN abuse", status: "ACTIVE" },
        ],
        reportMarkdown: `# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit\n## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT\n**Classification:** CONFIDENTIAL // TLP:AMBER\n\n### Summary\nAttack reconstructed from cron reverse shell to sudo privesc, Diamorphine LKM loading, and cgroup host breakout. Remediation applied.`,
        downloadFilename: "k8s_container_breakout_investigation_report.md",
      }}
    />
  );
}

export function AzureAdDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
        classification: "CONFIDENTIAL // TLP:AMBER",
        title: "Azure AD Identity Takeover & Impossible Travel Dossier",
        subtitle: "Multi-cloud identity anomaly correlation, session hijacking forensics, and automated Graph API containment.",
        overview: "Behavioral anomaly telemetry detected impossible travel for alex.vance@contoso-global.com (London then Amsterdam 8 mins later). Token replay bypassed MFA, followed by injection of a rogue app secret and automated Graph API mass email collection.",
        targetAsset: "alex.vance@contoso-global.com (Global Admin)",
        summaryHighlights: [
          { label: "Impossible Travel", value: ">3,400 km/h" },
          { label: "Token Replay", value: "PRT Stolen" },
          { label: "Rogue Secret", value: "DiagnosticSyncKey Purged" },
        ],
        killChainEvents: [
          { id: "Stage 1", time: "12:44:19", stage: "Impossible Travel", desc: "Logins from London (194.26.29.112) and Amsterdam (185.220.101.45) within 8 minutes.", mitre: "T1078.004 Cloud Accounts" },
          { id: "Stage 2", time: "12:46:02", stage: "Token Replay", desc: "Primary Refresh Token (PRT) replayed to bypass interactive MFA prompts.", mitre: "T1539 Steal Cookie" },
          { id: "Stage 3", time: "12:50:33", stage: "Persistence", desc: "Rogue client secret DiagnosticSyncKey-2026 added to Financial-Reporting-Sync-App.", mitre: "T1098.001 Credentials" },
          { id: "Stage 4", time: "12:54:12", stage: "Data Exfiltration", desc: "4,218 executive emails staged and exfiltrated to https://sync-telemetry-cache.net/upload.", mitre: "T1114.002 Email Collection" },
        ],
        iocItems: [
          { id: "IOC-AAD-01", tactic: "T1078.004 Cloud Accounts", name: "Impossible Travel Anomaly", desc: "Concurrent authentications from London and Amsterdam within 8 minutes.", test: "Azure AD Sign-in Logs", status: "BLOCKED" },
          { id: "IOC-AAD-02", tactic: "T1539 Token Replay", name: "ESTSAUTH & PRT Session Replay", desc: "Attacker replayed stolen PRT, bypassing interactive MFA.", test: "Token Issuance Logs", status: "REVOKED" },
          { id: "IOC-AAD-03", tactic: "T1098.001 Rogue Secret", name: "Rogue App Secret DiagnosticSyncKey", desc: "Persistent client secret created under Financial-Reporting-Sync-App.", test: "Microsoft Graph Audit", status: "PURGED" },
          { id: "IOC-AAD-04", tactic: "T1114.002 Email Collection", name: "Graph API Mass Email Exfiltration", desc: "Automated extraction of 4,218 executive emails.", test: "Exchange Online Audit", status: "CONTAINED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "User Session Revocation", target: "alex.vance@contoso-global.com", protocol: "Revoke-MgUserSignInSession; force password reset and disable account", status: "EXECUTED" },
          { priority: "P1: Critical", action: "Rogue App Secret Purge", target: "Financial-Reporting-Sync-App", protocol: "Remove client secret DiagnosticSyncKey-2026 and revert directory permissions", status: "PURGED" },
          { priority: "P2: High", action: "Conditional Access Block", target: "Cloud Tenant", protocol: "Enforce real-time block on TOR exit nodes and high-risk IP ranges", status: "ENFORCED" },
        ],
        reportMarkdown: `# Incident Investigation: Azure AD Identity Takeover\n## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL\n**Classification:** CONFIDENTIAL // TLP:AMBER\n\n### Summary\nImpossible travel and PRT replay detected. Rogue client secret removed and admin credentials revoked.`,
        downloadFilename: "azure_ad_intrusion_investigation_report.md",
      }}
    />
  );
}

export function AptEnterpriseIntrusionDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "CASE-1-APT-ENTERPRISE-INTRUSION",
        classification: "CONFIDENTIAL // TLP:AMBER",
        title: "Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement",
        subtitle: "Multi-stage intrusion reconstruction emulating APT29/UNC2452 across Cisco, Windows EVTX, Sysmon, and Palo Alto logs.",
        overview: "An advanced persistent threat multi-stage intrusion was detected and reconstructed across disjointed log ecosystems. The adversary established an initial foothold via a weaponized macro document, executed an in-memory PowerShell cradle, dumped credentials using Mimikatz, executed SMB lateral movement to Domain Controller DC01, and created persistent rogue administrator svc_backup_admin.",
        targetAsset: "WKSTN-FIN-04 (10.20.10.45) & DC01 (10.20.10.10)",
        summaryHighlights: [
          { label: "Threat Actor", value: "APT29 Emulation" },
          { label: "Lateral Movement", value: "DC01 Compromised" },
          { label: "Exfiltration", value: "452.8 MB Blocked" },
        ],
        killChainEvents: [
          { id: "Stage 1", time: "10:14:05", stage: "Initial Access", desc: "Spearphishing email with Invoice_90214.docm delivered from billing@overdue-invoices-center.org.", mitre: "T1566.001 Phishing" },
          { id: "Stage 2", time: "10:16:32", stage: "Execution", desc: "WINWORD.EXE spawns obfuscated PowerShell cradle downloading cobalt.ps1.", mitre: "T1059.001 PowerShell" },
          { id: "Stage 3", time: "10:20:14", stage: "Credential Access", desc: "mimikatz.exe accesses lsass.exe to dump Domain Admin cleartext credentials.", mitre: "T1003.001 LSASS Memory" },
          { id: "Stage 4", time: "10:23:05", stage: "Lateral Movement", desc: "SMB authentication to DC01.corp.contoso.com with SeDebugPrivilege assigned.", mitre: "T1021.002 SMB" },
          { id: "Stage 5", time: "10:25:30", stage: "Persistence", desc: "Backdoor user account svc_backup_admin created in Active Directory on DC01.", mitre: "T1136.001 AD Account" },
          { id: "Stage 6", time: "10:32:45", stage: "Exfiltration", desc: "452.8 MB of financial archives exfiltrated to 198.51.100.240:443 in 145 seconds.", mitre: "T1048.003 Exfiltration" },
        ],
        iocItems: [
          { id: "IOC-APT-01", tactic: "T1071.001 C2", name: "External C2 & Payload Server", desc: "185.220.101.45 hosted cobalt.ps1 and TLS beaconing on port 8443.", test: "Palo Alto ssl logs", status: "NULL-ROUTED" },
          { id: "IOC-APT-02", tactic: "T1048.003 Exfil", name: "Exfiltration Drop Node", desc: "198.51.100.240 received 452.8 MB encrypted data stream.", test: "Palo Alto CSV Traffic Logs", status: "SINKHOLED" },
          { id: "IOC-APT-03", tactic: "T1566.001 Phish", name: "Phishing Mailer Host", desc: "203.0.113.119 delivered malicious invoice.", test: "Cisco AsyncOS Mail Syslog", status: "BLOCKED" },
          { id: "IOC-APT-04", tactic: "T1204.002 Macro", name: "Weaponized Macro Doc", desc: "Invoice_90214.docm contains VBA executing PowerShell cradle.", test: "SHA-256 validation", status: "QUARANTINED" },
          { id: "IOC-APT-05", tactic: "T1136.001 Backdoor", name: "AD Backdoor Account", desc: "svc_backup_admin created on DC01 and added to Domain Admins.", test: "Security Event ID 4720", status: "PURGED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "Perimeter Firewall Null-Route", target: "185.220.101.45, 198.51.100.240", protocol: "set security-zone untrust address c2-nodes drop", status: "ENFORCED" },
          { priority: "P1: Critical", action: "AD Backdoor Account Purge", target: "svc_backup_admin", protocol: "Remove-ADUser -Identity svc_backup_admin -Confirm:$false", status: "ENFORCED" },
          { priority: "P1: Critical", action: "Privileged Credential Reset", target: "CONTOSO\\da_admin", protocol: "Set-ADAccountPassword -Identity da_admin -Reset; purge Kerberos tickets", status: "ENFORCED" },
          { priority: "P2: High", action: "Endpoint EDR Microsegmentation", target: "WKSTN-FIN-04 (10.20.10.45)", protocol: "Quarantine host from corporate VLAN", status: "QUARANTINED" },
        ],
        reportMarkdown: `# Forensic Incident Investigation: APT Enterprise Intrusion\n## Case: CASE-1-APT-ENTERPRISE-INTRUSION\n**Classification:** CONFIDENTIAL // TLP:AMBER\n\n### Summary\nFull kill chain reconstructed. C2 sinkholed, rogue AD account purged, credentials rotated.`,
        downloadFilename: "case_1_apt_enterprise_intrusion_investigation_report.md",
      }}
    />
  );
}

export function Case5DnsTunnelingDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "CASE-5-DNS-TUNNELING-EXFILTRATION",
        classification: "RESTRICTED // TLP:AMBER",
        title: "DNS Protocol Tunneling & Covert Exfiltration Dossier",
        subtitle: "BIND 9 resolver telemetry correlation, Shannon entropy anomaly detection, and Response Policy Zone enforcement.",
        overview: "Covert exfiltration channel identified routing chunked, base32-encoded engineering CAD schematics through recursive DNS queries against rogue authoritative nameserver *.tunnel-infra.darkops.cc.",
        targetAsset: "workstation-eng-42.corp.internal (10.0.4.42)",
        summaryHighlights: [
          { label: "Exfiltration Volume", value: "4.2 MB via DNS UDP/53" },
          { label: "Shannon Entropy", value: "4.68 (High Anomaly)" },
          { label: "Resolver", value: "RPZ Sinkhole Active" },
        ],
        killChainEvents: [
          { id: "Stage 1", time: "11:14:22", stage: "Initial C2", desc: "Low-frequency beacon queries for beacon-init.tunnel-infra.darkops.cc through resolver 10.0.0.2.", mitre: "T1071.004 DNS" },
          { id: "Stage 2", time: "11:18:04", stage: "Protocol Tunneling", desc: "Encapsulated TCP payloads into chunked DNS labels exceeding 52 chars. Record types: TXT, NULL, A.", mitre: "T1572 Protocol Tunneling" },
          { id: "Stage 3", time: "11:22:00", stage: "Data Exfiltration", desc: "8,412 DNS queries routed to *.tunnel-infra.darkops.cc exfiltrating 4.2 MB CAD schematics.", mitre: "T1048.003 Exfiltration Over DNS" },
        ],
        iocItems: [
          { id: "IOC-DNS-01", tactic: "T1071.004 DNS C2", name: "Apex C2 Domain", desc: "tunnel-infra.darkops.cc authoritative apex for bi-directional tunneling.", test: "BIND 9 logs", status: "SINKHOLED" },
          { id: "IOC-DNS-02", tactic: "T1572 Tunneling", name: "Rogue Nameserver", desc: "198.51.100.188 hosted rogue authoritative DNS listener.", test: "Palo Alto logs", status: "NULL-ROUTED" },
          { id: "IOC-DNS-03", tactic: "T1048.003 Exfil", name: "Internal Originator", desc: "workstation-eng-42.corp.internal executing dnscat2 client.", test: "Internal DHCP & NetFlow", status: "QUARANTINED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "BIND 9 RPZ Zone Sinkhole", target: "All Enterprise Resolvers", protocol: "*.tunnel-infra.darkops.cc CNAME .\nRPZ rule reloaded across all internal DNS relays", status: "ENFORCED" },
          { priority: "P1: Critical", action: "Endpoint Network Isolation", target: "10.0.4.42", protocol: "Switch port 1/0/24 disabled via SNMP; CAD workstation moved to isolation VLAN", status: "QUARANTINED" },
          { priority: "P2: High", action: "DNS Payload Entropy Inspection", target: "Core Firewalls", protocol: "Block UDP/53 queries with label length > 45 bytes or Shannon entropy > 4.2", status: "ACTIVE" },
        ],
        reportMarkdown: `# Incident Investigation: DNS Tunneling Exfiltration\n## Case: CASE-5-DNS-TUNNELING-EXFILTRATION\n\n### Summary\n4.2 MB CAD schematics exfiltrated over recursive DNS. RPZ sinkhole and endpoint isolation enforced.`,
        downloadFilename: "case_5_dns_tunneling_investigation_report.md",
      }}
    />
  );
}

export function Case6DdosDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  return (
    <IncidentDossierTemplate
      onNavigate={onNavigate}
      onBack={onBack}
      config={{
        caseId: "CASE-6-DDOS-RECON-FIREWALL-EVASION",
        classification: "RESTRICTED // TLP:AMBER",
        title: "Perimeter DDoS, Reconnaissance & Firewall Evasion Dossier",
        subtitle: "Cisco ASA & FortiGate UTM telemetry parsing, spoofed SYN-flood mitigation, and automated ACL enforcement.",
        overview: "Perimeter threat sequence combining outbound host probing, inbound vertical TCP port scans, high-rate spoofed SYN floods against DMZ web gateways, and credential brute force attempts on AAA management interfaces.",
        targetAsset: "Perimeter DMZ Gateway & Cisco ASA 5585-X",
        summaryHighlights: [
          { label: "Attack Vector", value: "SYN Flood + Brute Force" },
          { label: "Mitigation", value: "ASA ACL Drops Applied" },
          { label: "AAA Interfaces", value: "Account Lockout Active" },
        ],
        killChainEvents: [
          { id: "E1", time: "11:30:12", stage: "Outbound Probing", desc: "Outbound TCP from internal host 203.0.113.10 to external 198.51.100.40:443.", mitre: "T1046 Discovery" },
          { id: "E2", time: "11:33:05", stage: "Vertical Scan", desc: "Inbound vertical port scan from 198.51.100.220 to DMZ 10.10.10.20 (ports 21-3389).", mitre: "T1046 Discovery" },
          { id: "E3", time: "12:10:06", stage: "DDoS Impact", desc: "High-rate SYN flood from spoofed IPs 203.0.113.88-92 targeting web gateway 10.10.10.5.", mitre: "T1499 Denial of Service" },
          { id: "E4", time: "12:15:01", stage: "AAA Brute Force", desc: "AAA logins rejected for root, admin, deploy from 198.51.100.75.", mitre: "T1110 Brute Force" },
        ],
        iocItems: [
          { id: "IOC-FW-01", tactic: "T1046 Scan", name: "Inbound Port Scanner", desc: "198.51.100.220 initiated vertical scans across DMZ subnet.", test: "Cisco ASA ACL logs", status: "BLOCKED" },
          { id: "IOC-FW-02", tactic: "T1499 DDoS", name: "SYN-Flood Spoofed Range", desc: "203.0.113.88 - 203.0.113.92 generated 85,000 pps SYN flood.", test: "FortiGate DDoS sensor", status: "RATE-LIMITED" },
          { id: "IOC-FW-03", tactic: "T1110 Brute Force", name: "Management Interface Attacker", desc: "198.51.100.75 performed rapid dictionary attacks against SSH/HTTPS AAA.", test: "AAA syslog", status: "SHUNNED" },
        ],
        containmentActions: [
          { priority: "P1: Critical", action: "Cisco ASA Shun Command", target: "198.51.100.75 & 198.51.100.220", protocol: "shun 198.51.100.75\nshun 198.51.100.220\nImmediate connection termination across state table", status: "ENFORCED" },
          { priority: "P1: Critical", action: "TCP SYN-Proxy & Anti-Spoofing ACL", target: "DMZ Interface", protocol: "access-list INBOUND-ACL deny ip range 203.0.113.88 203.0.113.92 any\nsysopt connection timewait 15", status: "APPLIED" },
          { priority: "P2: High", action: "Management Plane Access Restriction", target: "ASA & FortiGate AAA", protocol: "Enforce strict IP whitelist for management SSH; block external WAN AAA attempts", status: "VERIFIED" },
        ],
        reportMarkdown: `# Incident Investigation: Perimeter DDoS & Reconnaissance\n## Case: CASE-6-DDOS-RECON-FIREWALL-EVASION\n\n### Summary\nSYN-flood neutralized via TCP syn-proxy and ACL shun. Management interfaces secured.`,
        downloadFilename: "case_6_ddos_recon_investigation_report.md",
      }}
    />
  );
}
