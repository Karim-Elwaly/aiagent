"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Boxes,
  Check,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  FileCheck2,
  Folder,
  Layers,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Swords,
  Terminal,
  Upload,
  X,
} from "lucide-react";
import {
  fetchFleetArenas,
  planFleetArena,
  provisionFleetArena,
  startFleetArena,
} from "@/lib/api";
import { FleetArenaManifest, FleetArenaUnit } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";

interface BattleArenaViewProps {
  onLaunchExecution: (workflowId: string, arenaName: string) => void;
  onNavigate: (view: string) => void;
}

const STRATEGIES = [
  {
    id: "soc_forensic_deep_dive",
    name: "SOC Forensic Deep-Dive",
    desc: "Autonomous multi-ecosystem triage, blast radius discovery, timeline synthesis, and containment rule generation.",
  },
  {
    id: "adversarial_red_blue",
    name: "Red vs Blue Adversarial",
    desc: "Autonomous attacker agent deploys simulated attack vectors while defending fleet detects and neutralizes.",
  },
  {
    id: "multi_agent_consensus",
    name: "Multi-Agent Consensus Verification",
    desc: "Specialist agents cross-examine claims with two-person integrity and mathematical proofing.",
  },
  {
    id: "turnkey_infrastructure",
    name: "Turnkey Cloud & Platform DevOps",
    desc: "Architect, provision, deploy, and verify air-gapped infrastructure systems end-to-end.",
  },
];

export function BattleArenaView({ onLaunchExecution, onNavigate }: BattleArenaViewProps) {
  const [arenas, setArenas] = useState<FleetArenaManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [planningOpen, setPlanningOpen] = useState(false);
  const [selectedArena, setSelectedArena] = useState<FleetArenaManifest | null>(null);

  // Planning form state
  const [missionPrompt, setMissionPrompt] = useState("");
  const [arenaName, setArenaName] = useState("");
  const [strategy, setStrategy] = useState("soc_forensic_deep_dive");
  const [isPlanning, setIsPlanning] = useState(false);
  const [isProvisioning, setIsProvisioning] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadArenas() {
    setLoading(true);
    try {
      const data = await fetchFleetArenas();
      setArenas(data);
      if (data.length > 0 && !selectedArena) {
        setSelectedArena(data[0]);
      }
    } catch {
      // Mock initial arena if empty
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadArenas();
  }, []);

  async function handlePlanArena() {
    if (!missionPrompt.trim()) return;
    setIsPlanning(true);
    try {
      const planned = await planFleetArena({
        mission_prompt: missionPrompt,
        arena_name: arenaName || "Autonomous SOC Investigation Arena",
        strategy_profile: strategy,
      });
      setArenas((prev) => [planned, ...prev]);
      setSelectedArena(planned);
      setPlanningOpen(false);
      setMissionPrompt("");
      setArenaName("");
      setNotice(`Arena "${planned.arena_name}" planned with ${planned.units.length} reusable specialist profiles.`);
    } catch (err) {
      alert(`Planning failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsPlanning(false);
    }
  }

  async function handleProvision(arenaId: string) {
    setIsProvisioning(arenaId);
    try {
      const updated = await provisionFleetArena(arenaId);
      setArenas((prev) => prev.map((a) => (a.arena_id === arenaId ? updated : a)));
      if (selectedArena?.arena_id === arenaId) setSelectedArena(updated);
      setNotice(`Profiles for arena "${updated.arena_name}" provisioned. Hermes gateway synchronized.`);
    } catch (err) {
      alert(`Provisioning failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProvisioning(null);
    }
  }

  async function handleStart(arena: FleetArenaManifest) {
    setIsStarting(arena.arena_id);
    try {
      const res = await startFleetArena(arena.arena_id);
      arena.status = "running";
      arena.workflow_id = res.workflow_id;
      setArenas([...arenas]);
      onLaunchExecution(res.workflow_id, arena.arena_name);
    } catch (err) {
      alert(`Execution start failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsStarting(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <PageTitle
        eyebrow="AGENTHUB 0.21.x  /  AUTONOMOUS FLEET ARENA"
        title="Fleet Battle Arena"
        subtitle="Multi-agent coordinated simulations, adversarial benchmarks, and reusable named Hermes profiles."
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void loadArenas()}
            >
              <RefreshCw size={14} /> Refresh
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => setPlanningOpen(true)}
            >
              <Plus size={14} /> Plan Fleet Arena
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

      {/* Arena Metrics Banner */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: 12,
        }}
      >
        <div className="metric">
          <span>
            <Swords size={13} color="#236f66" /> Configured Arenas
          </span>
          <strong>{arenas.length}</strong>
          <small>Autonomous simulations</small>
        </div>

        <div className="metric">
          <span>
            <Bot size={13} color="#236f66" /> Reusable Fleet Units
          </span>
          <strong>
            {arenas.reduce((acc, a) => acc + (a.units?.length || 0), 0)}
          </strong>
          <small>Named Hermes profiles</small>
        </div>

        <div className="metric">
          <span>
            <ShieldCheck size={13} color="#236f66" /> Evaluation Score
          </span>
          <strong>100%</strong>
          <small>Air-gap sovereignty compliant</small>
        </div>

        <div className="metric">
          <span>
            <SlidersHorizontal size={13} color="#236f66" /> Strategy Profiles
          </span>
          <strong>4 Active</strong>
          <small>SOC, Red/Blue, Consensus</small>
        </div>
      </div>

      {/* Main Arena Layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "340px 1fr",
          gap: 16,
          alignItems: "start",
        }}
      >
        {/* Left Arena Selector List */}
        <section
          className="panel"
          style={{
            background: "#ffffff",
            border: "1px solid #dce5df",
            borderRadius: 7,
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.5,
                color: "#6a7b75",
                textTransform: "uppercase",
              }}
            >
              ARENA MANIFESTS
            </span>
            <span style={{ fontSize: 10, color: "#8a9a94" }}>
              {arenas.length} total
            </span>
          </div>

          {loading ? (
            <div style={{ padding: 20, textAlign: "center", color: "#889490", fontSize: 11 }}>
              <RefreshCw size={14} className="spin" style={{ display: "inline", marginRight: 6 }} />
              Discovering arenas...
            </div>
          ) : arenas.length === 0 ? (
            <div
              style={{
                padding: "24px 16px",
                textAlign: "center",
                color: "#6b7a74",
                fontSize: 11,
                border: "1px dashed #dce5df",
                borderRadius: 6,
              }}
            >
              <Swords size={24} color="#8a9e96" style={{ margin: "0 auto 8px" }} />
              <p style={{ margin: "0 0 10px", fontWeight: 600 }}>No Battle Arenas Created</p>
              <p style={{ margin: "0 0 12px", fontSize: 10, color: "#80928b" }}>
                Plan an autonomous multi-agent simulation to test specialized fleet units.
              </p>
              <button
                type="button"
                className="primary-button"
                style={{ fontSize: 11, padding: "5px 12px", margin: "0 auto" }}
                onClick={() => setPlanningOpen(true)}
              >
                Plan First Arena
              </button>
            </div>
          ) : (
            arenas.map((arena) => {
              const isSelected = selectedArena?.arena_id === arena.arena_id;
              const isProvisioned = arena.status === "provisioned" || arena.status === "running" || arena.status === "completed";
              return (
                <div
                  key={arena.arena_id}
                  onClick={() => setSelectedArena(arena)}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 5,
                    border: isSelected ? "1px solid #28776b" : "1px solid #e1ebe6",
                    background: isSelected ? "#f1f8f5" : "#ffffff",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    transition: "all 0.15s ease",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong style={{ fontSize: 12, color: "#162f29" }}>
                      {arena.arena_name || arena.arena_id}
                    </strong>
                    <Badge tone={isProvisioned ? "green" : "orange"}>
                      {arena.status.toUpperCase()}
                    </Badge>
                  </div>
                  <p
                    style={{
                      margin: 0,
                      fontSize: 10.5,
                      color: "#546862",
                      lineHeight: 1.4,
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {arena.mission_prompt}
                  </p>
                  <div style={{ display: "flex", gap: 10, fontSize: 9.5, color: "#7a8e88" }}>
                    <span>{arena.units?.length || 0} Named Units</span>
                    <span>•</span>
                    <span>{arena.strategy_profile?.replace(/_/g, " ") || "Standard"}</span>
                  </div>
                </div>
              );
            })
          )}
        </section>

        {/* Right Arena Details & Topology */}
        <section
          className="panel"
          style={{
            background: "#ffffff",
            border: "1px solid #dce5df",
            borderRadius: 7,
            padding: 20,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {selectedArena ? (
            <>
              {/* Header */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  borderBottom: "1px solid #edf4f0",
                  paddingBottom: 14,
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <Swords size={18} color="#236f66" />
                    <h2 style={{ margin: 0, fontSize: 17, color: "#152c27", fontWeight: 800 }}>
                      {selectedArena.arena_name || selectedArena.arena_id}
                    </h2>
                    <Badge tone={selectedArena.status === "running" ? "green" : selectedArena.status === "provisioned" ? "blue" : "orange"}>
                      <Dot color={selectedArena.status === "running" ? "green" : "orange"} />
                      {selectedArena.status.toUpperCase()}
                    </Badge>
                  </div>
                  <p style={{ margin: 0, fontSize: 11, color: "#546862" }}>
                    {selectedArena.mission_prompt}
                  </p>
                </div>

                {/* Actions */}
                <div style={{ display: "flex", gap: 8 }}>
                  {selectedArena.status === "draft" && (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={isProvisioning === selectedArena.arena_id}
                      onClick={() => void handleProvision(selectedArena.arena_id)}
                    >
                      {isProvisioning === selectedArena.arena_id ? (
                        <>
                          <RefreshCw size={13} className="spin" /> Provisioning...
                        </>
                      ) : (
                        <>
                          <Cpu size={13} /> Provision Profiles
                        </>
                      )}
                    </button>
                  )}

                  <button
                    type="button"
                    className="primary-button"
                    disabled={isStarting === selectedArena.arena_id}
                    onClick={() => void handleStart(selectedArena)}
                  >
                    {isStarting === selectedArena.arena_id ? (
                      <>
                        <RefreshCw size={13} className="spin" /> Launching...
                      </>
                    ) : (
                      <>
                        <Play size={13} /> Launch Arena Run
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Units Grid */}
              <div>
                <span
                  style={{
                    display: "block",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: 0.6,
                    color: "#6b7c76",
                    textTransform: "uppercase",
                    marginBottom: 10,
                  }}
                >
                  ASSIGNED SPECIALIST FLEET UNITS ({selectedArena.units?.length || 0})
                </span>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                    gap: 10,
                  }}
                >
                  {selectedArena.units?.map((unit: FleetArenaUnit, idx: number) => (
                    <div
                      key={unit.id || idx}
                      style={{
                        background: "#f9fbfa",
                        border: "1px solid #e1ece7",
                        borderRadius: 6,
                        padding: "12px 14px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <strong style={{ fontSize: 12, color: "#193630", display: "flex", alignItems: "center", gap: 6 }}>
                          <Bot size={14} color="#2b7a6d" /> {unit.name}
                        </strong>
                        <span
                          style={{
                            fontSize: 9,
                            background: "#e8f4f0",
                            color: "#1e5e54",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontFamily: "var(--font-geist-mono), monospace",
                          }}
                        >
                          {unit.profile_name || "hermes-default"}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: 10.5, color: "#5d706a", lineHeight: 1.4 }}>
                        {unit.role}
                      </p>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                        {unit.skills?.map((s) => (
                          <span
                            key={s}
                            style={{
                              fontSize: 9,
                              background: "#ffffff",
                              border: "1px solid #d4e2db",
                              color: "#376c61",
                              padding: "1px 5px",
                              borderRadius: 3,
                            }}
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Task DAG breakdown */}
              {selectedArena.dag && selectedArena.dag.tasks && (
                <div>
                  <span
                    style={{
                      display: "block",
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: 0.6,
                      color: "#6b7c76",
                      textTransform: "uppercase",
                      marginBottom: 10,
                    }}
                  >
                    COORDINATED TASK DAG PHASES ({selectedArena.dag.tasks.length})
                  </span>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {selectedArena.dag.tasks.map((task, idx) => (
                      <div
                        key={task.id || idx}
                        style={{
                          background: "#ffffff",
                          border: "1px solid #e1ece7",
                          borderRadius: 5,
                          padding: "10px 14px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              background: "#eaf5f1",
                              color: "#226a5e",
                              width: 22,
                              height: 22,
                              borderRadius: "50%",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            {idx + 1}
                          </span>
                          <div>
                            <strong style={{ fontSize: 11.5, color: "#162f29", display: "block" }}>
                              {task.name}
                            </strong>
                            <small style={{ color: "#6a7d77", fontSize: 10 }}>
                              {task.description.slice(0, 100)}...
                            </small>
                          </div>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span
                            style={{
                              fontSize: 9.5,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background: task.risk_level === "high" ? "#fae8e8" : "#edf4f0",
                              color: task.risk_level === "high" ? "#a83e3e" : "#2a6c60",
                            }}
                          >
                            {task.risk_level ? task.risk_level.toUpperCase() : "STANDARD"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ padding: 40, textAlign: "center", color: "#8a9a94" }}>
              Select an arena to view unit composition and coordinated phases.
            </div>
          )}
        </section>
      </div>

      {/* Plan Arena Modal */}
      {planningOpen && (
        <div className="modal-shade" onClick={() => setPlanningOpen(false)}>
          <section
            className="wizard"
            style={{ maxWidth: 620, width: "95%" }}
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="wizard-head">
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Swords size={14} color="#236f66" /> PLAN AUTONOMOUS FLEET ARENA
              </span>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={() => setPlanningOpen(false)}
              >
                <X size={18} />
              </button>
            </div>

            <h2 style={{ fontSize: 17, margin: "6px 0 2px", color: "#162f29" }}>
              Compose Reusable Named Fleet
            </h2>
            <p className="wizard-desc" style={{ marginBottom: 14 }}>
              Decompose your scenario into specialized Hermes units with deterministic named profiles.
            </p>

            <div className="wizard-fields" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label>
                Arena Name
                <input
                  type="text"
                  placeholder="e.g. APT Enterprise Intrusion Benchmark Arena"
                  value={arenaName}
                  onChange={(e) => setArenaName(e.target.value)}
                />
              </label>

              <label>
                Mission Prompt & Scenario
                <textarea
                  rows={4}
                  placeholder="Describe the adversarial challenge or operational outcome..."
                  value={missionPrompt}
                  onChange={(e) => setMissionPrompt(e.target.value)}
                />
              </label>

              <label>
                Coordination Strategy Profile
                <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {STRATEGIES.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <small style={{ color: "#6b7d77", fontSize: 10, marginTop: 4 }}>
                  {STRATEGIES.find((s) => s.id === strategy)?.desc}
                </small>
              </label>
            </div>

            <div className="wizard-foot" style={{ marginTop: 16 }}>
              <button
                type="button"
                className="plain-button"
                onClick={() => setPlanningOpen(false)}
                disabled={isPlanning}
              >
                Cancel
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={isPlanning || !missionPrompt.trim()}
                onClick={() => void handlePlanArena()}
              >
                {isPlanning ? (
                  <>
                    <RefreshCw size={13} className="spin" /> Decomposing Units...
                  </>
                ) : (
                  <>
                    <Sparkles size={13} /> Generate Arena Blueprint
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
