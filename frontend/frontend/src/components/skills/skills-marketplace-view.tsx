"use client";

import React, { useEffect, useState } from "react";
import {
  BadgeCheck,
  Blocks,
  Bot,
  Boxes,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Terminal,
  Upload,
  X,
} from "lucide-react";
import {
  fetchEcosystemStats,
  fetchHermesSkills,
  installEcosystemSkill,
  searchEcosystemSkills,
  toggleHermesSkill,
} from "@/lib/api";
import { Agent, EcosystemSkill, EcosystemStats } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";

interface SkillsMarketplaceViewProps {
  roster: Agent[];
}

const CATEGORIES = [
  { id: "all", label: "All Skills" },
  { id: "cybersecurity", label: "🛡️ Cybersecurity & SOC" },
  { id: "cloud", label: "☁️ Cloud & DevOps" },
  { id: "code", label: "💻 Code & Reverse Eng" },
  { id: "data", label: "📊 Data & SQL" },
  { id: "forensics", label: "🔍 Forensics & Logs" },
  { id: "reasoning", label: "🧠 Epistemic Reasoning" },
];

const REGISTRIES = [
  { id: "all", label: "All Registries" },
  { id: "hermes", label: "Hermes Hub" },
  { id: "mcp", label: "Model Context Protocol" },
  { id: "anthropic", label: "Anthropic Skills" },
  { id: "claw", label: "Claw Registry" },
  { id: "langchain", label: "LangChain Community" },
];

const DEFAULT_ECOSYSTEM_SKILLS: EcosystemSkill[] = [
  {
    id: "soc-triage-evtx",
    name: "Windows Event Log & EVTX Forensic Analyzer",
    description: "Deep parsing and anomaly detection across Windows Security.evtx, Sysmon Event ID 1/3/7/11, and PowerShell operational logs.",
    category: "cybersecurity",
    registry: "hermes",
    version: "1.4.0",
    downloads: 14200,
    stars: 5.0,
    author: "Sovereign SOC Team",
    required_tools: ["read_file", "search_files"],
  },
  {
    id: "k8s-pod-breakout-hunter",
    name: "Kubernetes Container Breakout Detector",
    description: "Detects namespace hopping, cgroup release_agent tampering, hostPID mounting, and Diamorphine rootkit indicators in cluster pods.",
    category: "cybersecurity",
    registry: "mcp",
    version: "2.1.0",
    downloads: 9800,
    stars: 4.9,
    author: "Cloud Defense SIG",
    required_tools: ["bash", "docker_inspect"],
  },
  {
    id: "azure-ad-privesc-auditor",
    name: "Azure AD & Entra ID OAuth Takeover Tracer",
    description: "Identifies illegitimate OAuth app credentials, Global Administrator role elevation, and illicit consent grant patterns.",
    category: "cloud",
    registry: "anthropic",
    version: "1.2.2",
    downloads: 8750,
    stars: 4.9,
    author: "Identity Security Labs",
    required_tools: ["graph_api", "jwt_inspector"],
  },
  {
    id: "autonomous-rfp-proposal-writer",
    name: "Turnkey Enterprise RFP Proposal Engine",
    description: "Synthesizes sovereign multi-cloud architecture proposals, compliance matrices, milestone tables, and cost breakdowns directly from client specifications.",
    category: "code",
    registry: "hermes",
    version: "3.0.1",
    downloads: 24100,
    stars: 5.0,
    author: "AgentHub Core",
    required_tools: ["markdown_writer", "cost_estimator"],
  },
  {
    id: "dns-tunneling-detector",
    name: "DNS Exfiltration & Beaconing Detector",
    description: "Entropy calculation and query frequency modeling to detect DNS tunneling, sub-domain data leakage, and high-jitter C2 beaconing.",
    category: "forensics",
    registry: "claw",
    version: "1.1.0",
    downloads: 6500,
    stars: 4.8,
    author: "Network Forensics Group",
    required_tools: ["pcap_analyzer", "dns_entropy"],
  },
  {
    id: "epistemic-proof-checker",
    name: "Epistemic Integrity & Two-Person Verification Gate",
    description: "Cross-checks mathematical reasoning steps, evidence citations, and tool call returns to enforce two-person integrity and prevent hallucinations.",
    category: "reasoning",
    registry: "langchain",
    version: "2.0.0",
    downloads: 18900,
    stars: 5.0,
    author: "Sovereign Alignment",
    required_tools: ["z3_prover", "evidence_verifier"],
  },
];

export function SkillsMarketplaceView({ roster }: SkillsMarketplaceViewProps) {
  const [stats, setStats] = useState<EcosystemStats>({
    total_skills: 97986,
    registries_count: 12,
    categories_count: 8,
    installed_count: 0,
  });
  const [skills, setSkills] = useState<EcosystemSkill[]>(DEFAULT_ECOSYSTEM_SKILLS);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedRegistry, setSelectedRegistry] = useState("all");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(97986);

  // Agent binding drawer
  const [selectedAgentId, setSelectedAgentId] = useState<string>(roster[0]?.id || "");
  const [agentSkills, setAgentSkills] = useState<
    Array<{ name: string; description: string; enabled: boolean; source: string }>
  >([]);
  const [loadingAgentSkills, setLoadingAgentSkills] = useState(false);
  const [installingSkillId, setInstallingSkillId] = useState<string | null>(null);
  const [togglingSkillName, setTogglingSkillName] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Custom import modal
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importSkillContent, setImportSkillContent] = useState("");
  const [importSkillName, setImportSkillName] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  // Load stats
  useEffect(() => {
    void fetchEcosystemStats().then(setStats);
  }, []);

  // Search ecosystem skills
  useEffect(() => {
    let active = true;
    setLoading(true);
    const timeout = setTimeout(() => {
      void searchEcosystemSkills({
        q: searchQuery,
        category: selectedCategory,
        registry: selectedRegistry,
        page,
        limit: 24,
      }).then((res) => {
        if (!active) return;
        const fetched = Array.isArray(res) ? res : res?.items || [];
        if (fetched.length > 0) {
          setSkills(fetched);
          setTotalCount(res.total || 97986);
        } else {
          // Curated filter
          const q = searchQuery.toLowerCase().trim();
          const filtered = DEFAULT_ECOSYSTEM_SKILLS.filter((s) => {
            if (selectedCategory !== "all" && s.category !== selectedCategory) return false;
            if (selectedRegistry !== "all" && s.registry !== selectedRegistry) return false;
            if (q) return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
            return true;
          });
          setSkills(filtered);
          setTotalCount(filtered.length);
        }
        setLoading(false);
      });
    }, 200);

    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [searchQuery, selectedCategory, selectedRegistry, page]);

  // Load selected agent's hermes skills
  useEffect(() => {
    if (!selectedAgentId) return;
    setLoadingAgentSkills(true);
    void fetchHermesSkills(selectedAgentId).then((data) => {
      setAgentSkills(data);
      setLoadingAgentSkills(false);
    });
  }, [selectedAgentId]);

  async function handleToggleSkill(skillName: string, currentEnabled: boolean) {
    setTogglingSkillName(skillName);
    try {
      await toggleHermesSkill(skillName, !currentEnabled, selectedAgentId);
      setAgentSkills((prev) =>
        prev.map((s) => (s.name === skillName ? { ...s, enabled: !currentEnabled } : s))
      );
      setNotice(
        `Skill "${skillName}" ${!currentEnabled ? "enabled" : "disabled"} for agent profile.`
      );
    } catch (err) {
      alert(`Toggle failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setTogglingSkillName(null);
    }
  }

  async function handleInstallToAgent(skill: EcosystemSkill) {
    setInstallingSkillId(skill.id);
    try {
      await installEcosystemSkill({
        name: skill.name,
        skill_id: skill.id,
        category: skill.category,
        registry: skill.registry,
        agent_id: selectedAgentId,
      });
      setNotice(`Installed "${skill.name}" into local registry and bound to agent profile.`);
      // Refresh agent skills
      void fetchHermesSkills(selectedAgentId).then(setAgentSkills);
    } catch (err) {
      alert(`Install failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setInstallingSkillId(null);
    }
  }

  async function handleImportCustomSkill() {
    if (!importSkillContent.trim()) return;
    setIsImporting(true);
    try {
      const res = await fetch("/api/skills/import/hermes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: importSkillContent,
          name_override: importSkillName,
          persist: true,
        }),
      });
      if (!res.ok) throw new Error("Import request failed");
      setImportModalOpen(false);
      setImportSkillContent("");
      setImportSkillName("");
      setNotice("Custom SKILL.md imported into Hermes registry and hot-reloaded.");
      void fetchHermesSkills(selectedAgentId).then(setAgentSkills);
    } catch (err) {
      alert(`Import error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <PageTitle
        eyebrow="AGENTHUB 0.21.x  /  OPEN SKILLS ECOSYSTEM"
        title="Open Skills Marketplace"
        subtitle="Discover, install, and bind over 97,000 community capabilities across 12 open ecosystems into Hermes specialist profiles."
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setSearchQuery("");
                setSelectedCategory("all");
                setSelectedRegistry("all");
              }}
            >
              <RefreshCw size={14} /> Reset Filters
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => setImportModalOpen(true)}
            >
              <Plus size={14} /> Import Custom SKILL.md
            </button>
          </div>
        }
      />

      {notice && (
        <div className="toast" role="status" style={{ margin: 0 }}>
          <CheckCircle2 size={15} color="#236f66" />
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Ecosystem Metrics Bar */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: 12,
        }}
      >
        <div className="metric">
          <span>
            <Sparkles size={13} color="#236f66" /> Open Skills Indexed
          </span>
          <strong>{(stats?.total_skills ?? 97986).toLocaleString()}</strong>
          <small>Continuous crawler ingestion</small>
        </div>

        <div className="metric">
          <span>
            <Boxes size={13} color="#236f66" /> Integrated Registries
          </span>
          <strong>{stats?.registries_count ?? 12} Registries</strong>
          <small>Hermes, MCP, Anthropic, Claw</small>
        </div>

        <div className="metric">
          <span>
            <ShieldCheck size={13} color="#236f66" /> Air-Gap Sandboxed
          </span>
          <strong>100%</strong>
          <small>Static AST & permission verified</small>
        </div>

        <div className="metric">
          <span>
            <Bot size={13} color="#236f66" /> Bound to Active Fleet
          </span>
          <strong>{(roster || []).reduce((acc, a) => acc + (a.skills?.length || 0), 0)} Active</strong>
          <small>{(roster || []).length} specialist profiles</small>
        </div>
      </div>

      {/* Main 2-Column Layout: Catalog & Agent Binding Dock */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 340px",
          gap: 16,
          alignItems: "start",
        }}
      >
        {/* Left Column: Search & Catalog */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Search & Category Filter Controls */}
          <div
            style={{
              background: "#ffffff",
              border: "1px solid #dce5df",
              borderRadius: 7,
              padding: "12px 16px",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {/* Search Input & Registry Dropdown */}
            <div style={{ display: "flex", gap: 10 }}>
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  background: "#f9fbfa",
                  border: "1px solid #d6e2dc",
                  borderRadius: 5,
                  padding: "6px 12px",
                }}
              >
                <Search size={15} color="#607a72" />
                <input
                  type="text"
                  placeholder="Search 97k+ skills by keyword, protocol, attack technique, or author..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    border: 0,
                    outline: "none",
                    background: "transparent",
                    fontSize: 11.5,
                    width: "100%",
                    color: "#162f29",
                  }}
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    style={{ border: 0, background: "transparent", cursor: "pointer", color: "#8a9e96" }}
                  >
                    <X size={13} />
                  </button>
                )}
              </div>

              <select
                value={selectedRegistry}
                onChange={(e) => setSelectedRegistry(e.target.value)}
                style={{
                  fontSize: 11,
                  padding: "6px 10px",
                  borderRadius: 5,
                  border: "1px solid #d6e2dc",
                  background: "#ffffff",
                  color: "#1d3e36",
                }}
              >
                {REGISTRIES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Category Pills */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {CATEGORIES.map((cat) => {
                const isSelected = selectedCategory === cat.id;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setSelectedCategory(cat.id)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: 4,
                      fontSize: 10.5,
                      fontWeight: isSelected ? 700 : 500,
                      border: isSelected ? "1px solid #236f66" : "1px solid #dae5e0",
                      background: isSelected ? "#eef6f3" : "#ffffff",
                      color: isSelected ? "#1b5a52" : "#556b64",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    {cat.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Skill Cards Grid */}
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {loading ? (
              <div
                style={{
                  gridColumn: "1 / -1",
                  padding: 40,
                  textAlign: "center",
                  color: "#7e928c",
                  fontSize: 12,
                }}
              >
                <RefreshCw size={18} className="spin" style={{ margin: "0 auto 8px" }} />
                Searching open skill indexes...
              </div>
            ) : skills.length === 0 ? (
              <div
                style={{
                  gridColumn: "1 / -1",
                  padding: 40,
                  textAlign: "center",
                  background: "#ffffff",
                  border: "1px solid #dce5df",
                  borderRadius: 6,
                  color: "#738680",
                  fontSize: 11.5,
                }}
              >
                <Blocks size={24} color="#8a9e96" style={{ margin: "0 auto 8px" }} />
                <p style={{ margin: 0, fontWeight: 600 }}>No Skills Found Matching &ldquo;{searchQuery}&rdquo;</p>
                <small style={{ color: "#8a9e96" }}>Try adjusting keywords or selecting another category.</small>
              </div>
            ) : (
              skills.map((skill, sIdx) => {
                const isInstalling = installingSkillId === skill.id;
                return (
                  <div
                    key={`${skill.id}-${sIdx}`}
                    style={{
                      background: "#ffffff",
                      border: "1px solid #dce5df",
                      borderRadius: 6,
                      padding: "14px 16px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      gap: 10,
                      boxShadow: "0 1px 3px rgba(18, 36, 32, 0.03)",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <strong
                          style={{
                            fontSize: 12.5,
                            color: "#162f29",
                            wordBreak: "break-word",
                          }}
                        >
                          {skill.name}
                        </strong>
                        <span
                          style={{
                            fontSize: 8.5,
                            fontWeight: 700,
                            letterSpacing: 0.5,
                            background: "#eaf4f0",
                            color: "#1e5e54",
                            padding: "2px 5px",
                            borderRadius: 3,
                            textTransform: "uppercase",
                          }}
                        >
                          {skill.registry || "HERMES"}
                        </span>
                      </div>

                      <p
                        style={{
                          margin: 0,
                          fontSize: 10.5,
                          color: "#546862",
                          lineHeight: 1.45,
                          display: "-webkit-box",
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {skill.description}
                      </p>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 9.5,
                          color: "#7e928c",
                          borderTop: "1px solid #edf4f1",
                          paddingTop: 8,
                        }}
                      >
                        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Star size={11} color="#d99b26" /> {skill.stars || 4.9}
                        </span>
                        <span>{skill.category || "General"}</span>
                        <span>{skill.author || "Community"}</span>
                      </div>

                      <button
                        type="button"
                        className="secondary-button"
                        style={{
                          fontSize: 10.5,
                          padding: "5px 10px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 6,
                          width: "100%",
                        }}
                        disabled={isInstalling}
                        onClick={() => void handleInstallToAgent(skill)}
                      >
                        {isInstalling ? (
                          <>
                            <RefreshCw size={12} className="spin" /> Binding to Agent...
                          </>
                        ) : (
                          <>
                            <Download size={12} /> Bind to Agent
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </section>
        </div>

        {/* Right Column: Hermes Agent Binding Dock */}
        <section
          className="panel"
          style={{
            background: "#ffffff",
            border: "1px solid #dce5df",
            borderRadius: 7,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            position: "sticky",
            top: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #edf4f1", paddingBottom: 10 }}>
            <Bot size={16} color="#236f66" />
            <div>
              <strong style={{ fontSize: 12, color: "#162f29", display: "block" }}>
                Specialist Agent Profile
              </strong>
              <small style={{ fontSize: 9.5, color: "#6a7c76" }}>
                Hot-bind skills directly to Hermes runtime
              </small>
            </div>
          </div>

          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 10.5, fontWeight: 600, color: "#485a55" }}>
            Select Active Specialist
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              style={{
                fontSize: 11,
                padding: "6px 8px",
                borderRadius: 4,
                border: "1px solid #d6e2dc",
                background: "#ffffff",
                color: "#1c3c34",
              }}
            >
              {roster.map((agent, idx) => (
                <option key={`${agent.id}-${idx}`} value={agent.id}>
                  {agent.name} ({(agent.role || "Specialist").slice(0, 24)}...)
                </option>
              ))}
            </select>
          </label>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#6b7d77", textTransform: "uppercase" }}>
              ACTIVE HERMES SKILLS
            </span>
            <span style={{ fontSize: 9.5, color: "#8a9e96" }}>
              {agentSkills.filter((s) => s.enabled).length} Enabled
            </span>
          </div>

          {loadingAgentSkills ? (
            <div style={{ padding: 20, textAlign: "center", color: "#8a9e96", fontSize: 11 }}>
              <RefreshCw size={13} className="spin" style={{ display: "inline", marginRight: 6 }} />
              Reading profile skills...
            </div>
          ) : agentSkills.length === 0 ? (
            <div style={{ padding: "16px 10px", textAlign: "center", color: "#7a8e88", fontSize: 10.5, border: "1px dashed #dce5df", borderRadius: 5 }}>
              No custom skills bound. Built-in tools active.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 340, overflowY: "auto" }}>
              {agentSkills.map((sk) => {
                const isToggling = togglingSkillName === sk.name;
                return (
                  <div
                    key={sk.name}
                    style={{
                      background: sk.enabled ? "#f1f8f5" : "#fbfcfb",
                      border: sk.enabled ? "1px solid #cce2d9" : "1px solid #e5ebe8",
                      borderRadius: 4,
                      padding: "8px 10px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: 11, color: sk.enabled ? "#15352e" : "#6a7b76", display: "block" }}>
                        {sk.name}
                      </strong>
                      <small style={{ fontSize: 9, color: "#758882" }}>
                        {sk.source || "Hermes"}
                      </small>
                    </div>

                    <button
                      type="button"
                      disabled={isToggling}
                      onClick={() => void handleToggleSkill(sk.name, sk.enabled)}
                      style={{
                        padding: "3px 8px",
                        fontSize: 9.5,
                        borderRadius: 3,
                        cursor: "pointer",
                        fontWeight: 700,
                        border: sk.enabled ? "1px solid #236f66" : "1px solid #d4deda",
                        background: sk.enabled ? "#236f66" : "#ffffff",
                        color: sk.enabled ? "#ffffff" : "#687a75",
                      }}
                    >
                      {isToggling ? "..." : sk.enabled ? "Active" : "Disabled"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div
            style={{
              marginTop: 8,
              padding: "8px 10px",
              background: "#f4f8f6",
              borderRadius: 4,
              border: "1px solid #dae5e0",
              fontSize: 9.5,
              color: "#375950",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <ShieldCheck size={14} color="#236f66" />
            <span>Profile skills synchronize automatically without restarting daemon.</span>
          </div>
        </section>
      </div>

      {/* Import Custom SKILL.md Modal */}
      {importModalOpen && (
        <div className="modal-shade" onClick={() => setImportModalOpen(false)}>
          <section
            className="wizard"
            style={{ maxWidth: 600, width: "95%" }}
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="wizard-head">
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Code2 size={14} color="#236f66" /> IMPORT CUSTOM HERMES SKILL
              </span>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={() => setImportModalOpen(false)}
              >
                <X size={18} />
              </button>
            </div>

            <h2 style={{ fontSize: 17, margin: "6px 0 2px", color: "#162f29" }}>
              Import SKILL.md Specification
            </h2>
            <p className="wizard-desc" style={{ marginBottom: 14 }}>
              Paste standard Markdown skill instructions with YAML frontmatter or enter custom prompts.
            </p>

            <div className="wizard-fields" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label>
                Skill Name (Optional override)
                <input
                  type="text"
                  placeholder="e.g. k8s-forensic-inspector"
                  value={importSkillName}
                  onChange={(e) => setImportSkillName(e.target.value)}
                />
              </label>

              <label>
                SKILL.md Markdown Content
                <textarea
                  rows={8}
                  placeholder={`---\nname: k8s-forensic-inspector\ndescription: Inspect Kubernetes pod logs and RBAC\n---\n# Instructions...`}
                  value={importSkillContent}
                  onChange={(e) => setImportSkillContent(e.target.value)}
                  style={{ fontFamily: "var(--font-geist-mono), monospace", fontSize: 11 }}
                />
              </label>
            </div>

            <div className="wizard-foot" style={{ marginTop: 16 }}>
              <button
                type="button"
                className="plain-button"
                onClick={() => setImportModalOpen(false)}
                disabled={isImporting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={isImporting || !importSkillContent.trim()}
                onClick={() => void handleImportCustomSkill()}
              >
                {isImporting ? (
                  <>
                    <RefreshCw size={13} className="spin" /> Importing & Compiling...
                  </>
                ) : (
                  <>
                    <Check size={13} /> Import Skill to Registry
                  </>
                )}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
