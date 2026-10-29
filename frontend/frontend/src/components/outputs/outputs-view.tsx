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

export const DEFAULT_OUTPUTS: FleetOutput[] = [
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
    <div style={{ background: "#ffffff", padding: "18px 22px", borderRadius: "6px", border: "1px solid #dce8e2", maxHeight: "430px", overflowY: "auto" }}>
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

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return outputs.filter((item) => {
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

          {/* Quick Dossier Jumps */}
          <div style={{ background: "#f8fbf9", border: "1px solid #dce8e2", borderRadius: "8px", padding: "14px 16px", marginBottom: "18px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#1b3832", marginBottom: "8px", textTransform: "uppercase" }}>
              Specialist Incident &amp; Proposal Dossier Views
            </div>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("gov_cloud"); }}
              >
                <FileText size={12} color="#195d56" /> Gov Cloud Migration Proposal
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("rfp"); }}
              >
                <FileText size={12} color="#195d56" /> MOE DevOps Server RFP
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("soc"); }}
              >
                <ShieldAlert size={12} color="#b44426" /> Host Ransomware SOC Dossier
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("k8s"); }}
              >
                <ShieldAlert size={12} color="#1f4870" /> K8s Breakout Dossier
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("azure"); }}
              >
                <ShieldAlert size={12} color="#6b338e" /> Azure AD Takeover Dossier
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("apt"); }}
              >
                <ShieldAlert size={12} color="#b44426" /> APT Enterprise Intrusion
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("case5"); }}
              >
                <ShieldAlert size={12} color="#7a4b12" /> DNS Tunneling Exfil
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "5px 10px" }}
                onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("case6"); }}
              >
                <ShieldAlert size={12} color="#8a2020" /> Perimeter DDoS &amp; Recon
              </button>
            </div>
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
    <div className="modal-shade" onClick={onClose}>
      <section
        className="modal-card"
        style={{ maxWidth: "850px", width: "95%" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <div className="eyebrow">{output.case || "DELIVERABLE ARTIFACT"}</div>
            <h3>{output.name}</h3>
          </div>
          <button className="icon-button" onClick={onClose}><X size={16} /></button>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "12px 0" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              type="button"
              className={modalView === "formatted" ? "primary-button" : "plain-button"}
              style={{ fontSize: "11px", padding: "4px 10px" }}
              onClick={() => setModalView("formatted")}
            >
              Structured Document
            </button>
            <button
              type="button"
              className={modalView === "raw" ? "primary-button" : "plain-button"}
              style={{ fontSize: "11px", padding: "4px 10px" }}
              onClick={() => setModalView("raw")}
            >
              <Code2 size={12} /> Raw Markdown
            </button>
          </div>
          <span style={{ fontSize: "11px", color: "#6a7c76" }}>
            Produced by {output.produced_by}
          </span>
        </div>

        {modalView === "formatted" ? (
          <FormattedDocumentPreview content={textContent} />
        ) : (
          <pre
            style={{
              maxHeight: "420px",
              overflowY: "auto",
              fontFamily: "var(--font-geist-mono), monospace",
              fontSize: "11px",
              whiteSpace: "pre-wrap",
              background: "#1b2d29",
              color: "#e4f0ec",
              padding: "16px",
              borderRadius: "6px",
            }}
          >
            {textContent}
          </pre>
        )}

        <div className="wizard-foot" style={{ marginTop: "16px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div style={{ display: "flex", gap: "8px" }}>
            <button className="secondary-button" onClick={copyContent}>
              {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
            </button>
            <button className="secondary-button" onClick={downloadOutput}>
              <Download size={14} /> Download
            </button>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            {isProposal && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("gov_cloud")} style={{ fontSize: "11px" }}>
                <FileText size={13} /> View in Dossier Studio
              </button>
            )}
            {isCase6 && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("case6")} style={{ fontSize: "11px", background: "#b44426" }}>
                <ShieldAlert size={13} /> View in Case 6 Dossier
              </button>
            )}
            {isAzureIncident && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("azure")} style={{ fontSize: "11px", background: "#6b338e" }}>
                <ShieldAlert size={13} /> View in Azure AD Dossier
              </button>
            )}
            {isK8sIncident && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("k8s")} style={{ fontSize: "11px", background: "#1f4870" }}>
                <ShieldAlert size={13} /> View in K8s Dossier
              </button>
            )}
            {isSocIncident && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("soc")} style={{ fontSize: "11px", background: "#b44426" }}>
                <ShieldAlert size={13} /> View in Host Ransomware Dossier
              </button>
            )}
            {isApt && onOpenDossier && (
              <button className="primary-button" onClick={() => onOpenDossier("apt")} style={{ fontSize: "11px", background: "#b44426" }}>
                <ShieldAlert size={13} /> View in APT Dossier
              </button>
            )}
            <button className="plain-button" onClick={onClose}>Close</button>
          </div>
        </div>
      </section>
    </div>
  );
}
