"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Command,
  GitBranch,
  Layers3,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { Agent, InventoryData, MissionRecord } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";

export function makeTopology(roster: Agent[]): { nodes: Node[]; edges: Edge[] } {
  const uniqueRoster: Agent[] = [];
  const seenIds = new Set<string>();
  for (const agent of roster) {
    if (agent && agent.id && !seenIds.has(agent.id)) {
      seenIds.add(agent.id);
      uniqueRoster.push(agent);
    }
  }

  const rowGap = 88;
  const centerY = Math.max(48, ((uniqueRoster.length - 1) * rowGap) / 2);
  const palette = [
    { background: "#e4f3ef", color: "#1d554f", border: "#c2e0d7", edge: "#5b9c8e" },
    { background: "#fff0e8", color: "#955230", border: "#f2d5c5", edge: "#c98a63" },
    { background: "#e9eef7", color: "#445779", border: "#d2daeb", edge: "#7f899d" },
  ];
  const baseStyle = { borderRadius: 5, width: 155, padding: 15, fontSize: 12, fontWeight: 700 };
  const topologyNodes: Node[] = [
    {
      id: "source",
      position: { x: 10, y: centerY },
      data: { label: "Incoming records" },
      style: { ...baseStyle, background: "#183034", color: "#fff", border: 0, width: 145, fontWeight: 600 },
    },
    ...uniqueRoster.map((agent, index) => {
      const colors = palette[index % palette.length];
      return {
        id: agent.id,
        position: { x: 245, y: index * rowGap },
        data: { label: agent.name },
        style: {
          ...baseStyle,
          background: colors.background,
          color: colors.color,
          border: `1px solid ${colors.border}`,
        },
      };
    }),
    {
      id: "decision-room",
      position: { x: 500, y: centerY },
      data: { label: "Decision Room" },
      style: { ...baseStyle, background: "#fbf3d9", color: "#80672d", border: "1px solid #ebdfb5", width: 145 },
    },
  ];
  const topologyEdges = uniqueRoster.flatMap((agent, index) => [
    {
      id: `source-${agent.id}-${index}`,
      source: "source",
      target: agent.id,
      animated: index === 0,
      style: { stroke: palette[index % palette.length].edge },
    },
    {
      id: `${agent.id}-decision-${index}`,
      source: agent.id,
      target: "decision-room",
      animated: agent.state === "Approval held",
      style: { stroke: "#a88d4c" },
    },
  ]);
  return { nodes: topologyNodes, edges: topologyEdges };
}

export function EmptyRoster({ onCreate }: { onCreate: () => void }) {
  return (
    <>
      <PageTitle
        eyebrow="LIVE ESTATE  /  SPECIALIST FLEETS"
        title="Fleet roster"
        subtitle="No agent specifications have been compiled yet."
        action={
          <button className="primary-button" onClick={onCreate}>
            <Plus size={16} /> Design a fleet
          </button>
        }
      />
      <section className="panel empty-state">
        <GitBranch size={24} />
        <h3>No declared agents</h3>
        <p>Complete the mission challenge gates and compile a blueprint to populate this roster.</p>
      </section>
    </>
  );
}

export function ModelBindingEditor({
  agent,
  inventory,
  onModel,
}: {
  agent: Agent;
  inventory: InventoryData | null;
  onModel: (agent: Agent, key: string) => void;
}) {
  return (
    <section className="panel roster-model-binding">
      <div>
        <div className="eyebrow">PINNED MODEL FAMILY + VERSION</div>
        <strong>{agent.name}</strong>
      </div>
      <select
        aria-label={`Model for ${agent.name}`}
        value={`${agent.assignedLlm.family}\u0000${agent.assignedLlm.version}`}
        onChange={(event) => onModel(agent, event.target.value)}
      >
        {(inventory?.available_models ?? []).map((model) => (
          <option
            key={`${model.family}/${model.version}`}
            value={`${model.family}\u0000${model.version}`}
          >
            {model.family} · {model.version}
            {model.cloud ? " · provider" : " · local"}
          </option>
        ))}
      </select>
      <span>
        {agent.assignedLlm.family} · {agent.assignedLlm.version}
      </span>
    </section>
  );
}

export function RosterDraftEditor({
  roster,
  inventory,
  onRoster,
  onSkill,
  onTools,
  onModel,
  onAdd,
  onSplit,
  onRemove,
}: {
  roster: Agent[];
  inventory: InventoryData | null;
  onRoster: (roster: Agent[]) => void;
  onSkill: (agent: Agent, skillInput: string[] | string) => void;
  onTools: (agent: Agent, tools: string[]) => void;
  onModel: (agent: Agent, key: string) => void;
  onAdd: () => void;
  onSplit: (agent: Agent) => void;
  onRemove: (agent: Agent) => void;
}) {
  const [skillFilters, setSkillFilters] = useState<Record<string, string>>({});
  const [toolFilters, setToolFilters] = useState<Record<string, string>>({});

  function updateAgent(agent: Agent, patch: Partial<Agent>) {
    onRoster(roster.map((item) => (item.id === agent.id ? { ...item, ...patch } : item)));
  }

  return (
    <div className="draft-list">
      {roster.map((agent, index) => {
        const qSkill = (skillFilters[agent.id] ?? "").toLowerCase().trim();
        const visibleSkills = (inventory?.installed_skills ?? []).filter((s) => {
          if (!qSkill) return true;
          return (
            s.skill_id.toLowerCase().includes(qSkill) ||
            s.required_tools.some((t) => t.toLowerCase().includes(qSkill))
          );
        });

        const qTool = (toolFilters[agent.id] ?? "").toLowerCase().trim();
        const visibleTools = (inventory?.registered_tools ?? []).filter((t) => {
          if (!qTool) return true;
          return (
            t.tool_id.toLowerCase().includes(qTool) ||
            t.risk_level.toLowerCase().includes(qTool)
          );
        });

        return (
          <div className="specialist-card" key={`${agent.id}-${index}`}>
            <div className="specialist-card-head">
              <div className="specialist-card-title">
                <span className={`agent-icon agent-icon--${agent.tint}`}>
                  <Bot size={16} />
                </span>
                <div>
                  <strong>{agent.name}</strong>
                  <small>
                    Specialist 0{index + 1} · {agent.triggerPolicy}
                  </small>
                </div>
              </div>
              <div className="specialist-card-actions">
                <button
                  className="icon-button"
                  title="Split specialist role"
                  aria-label={`Split ${agent.name}`}
                  onClick={() => onSplit(agent)}
                >
                  <GitBranch size={14} />
                </button>
                {roster.length > 1 && (
                  <button
                    className="icon-button"
                    title="Remove specialist"
                    aria-label={`Remove ${agent.name}`}
                    onClick={() => onRemove(agent)}
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>

            <div className="specialist-card-grid">
              <label className="field-group">
                <span className="field-label">Specialist Role Name</span>
                <input
                  className="field-input"
                  value={agent.name}
                  onChange={(event) => updateAgent(agent, { name: event.target.value })}
                />
              </label>

              <label className="field-group">
                <span className="field-label">Execution Trigger</span>
                <select
                  className="field-select"
                  value={agent.triggerPolicy}
                  onChange={(event) => updateAgent(agent, { triggerPolicy: event.target.value })}
                >
                  <option value="CRON">Cron (Scheduled)</option>
                  <option value="CONTINUOUS_POLL">Continuous poll</option>
                  <option value="EVENT_DRIVEN">Upstream event</option>
                  <option value="WEBHOOK">External webhook</option>
                </select>
              </label>

              {agent.triggerPolicy === "CRON" && (
                <label className="field-group" style={{ gridColumn: "1 / -1" }}>
                  <span className="field-label">Cron Schedule Expression</span>
                  <input
                    className="field-input"
                    value={agent.schedule}
                    onChange={(event) => updateAgent(agent, { schedule: event.target.value })}
                    placeholder="0 * * * *"
                  />
                </label>
              )}

              {agent.triggerPolicy === "EVENT_DRIVEN" && (
                <label className="field-group" style={{ gridColumn: "1 / -1" }}>
                  <span className="field-label">Upstream Specialists (Event Handoff)</span>
                  <select
                    multiple
                    className="field-select-multi"
                    value={agent.upstreamAgentIds}
                    onChange={(event) =>
                      updateAgent(agent, {
                        upstreamAgentIds: Array.from(
                          event.target.selectedOptions,
                          (option) => option.value
                        ),
                      })
                    }
                  >
                    {roster
                      .filter((candidate) => candidate.id !== agent.id)
                      .map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {candidate.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}

              <label className="field-group" style={{ gridColumn: "1 / -1" }}>
                <span className="field-label">Operational Scope & Boundaries</span>
                <textarea
                  className="field-textarea"
                  rows={2}
                  value={agent.scope}
                  onChange={(event) => updateAgent(agent, { scope: event.target.value })}
                />
              </label>

              <div className="field-group" style={{ gridColumn: "1 / -1" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "4px",
                  }}
                >
                  <span className="field-label">Bound AgentHub Skills (Multi-select)</span>
                  <span style={{ fontSize: "11px", color: "var(--color-text-dim)" }}>
                    {agent.skills.length} skill{agent.skills.length !== 1 ? "s" : ""} bound
                  </span>
                </div>
                {agent.skills.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      marginBottom: "8px",
                    }}
                  >
                    {agent.skills.map((sId) => (
                      <span
                        key={sId}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          fontSize: "11px",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: "rgba(16, 185, 129, 0.15)",
                          border: "1px solid rgba(16, 185, 129, 0.3)",
                          color: "var(--color-emerald-light, #34d399)",
                        }}
                      >
                        ⚡ {sId}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            onSkill(
                              agent,
                              agent.skills.filter((x) => x !== sId)
                            );
                          }}
                          style={{
                            background: "none",
                            border: "none",
                            color: "inherit",
                            cursor: "pointer",
                            padding: 0,
                            marginLeft: "2px",
                            lineHeight: 1,
                          }}
                          title="Remove skill"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <input
                  type="text"
                  className="field-input"
                  style={{ height: "26px", fontSize: "10px", padding: "0 8px", marginBottom: "6px" }}
                  placeholder={`Search ${inventory?.installed_skills?.length ?? 0} skills...`}
                  value={skillFilters[agent.id] ?? ""}
                  onChange={(e) =>
                    setSkillFilters((prev) => ({ ...prev, [agent.id]: e.target.value }))
                  }
                />
                <select
                  multiple
                  className="field-select-multi"
                  style={{ minHeight: "84px" }}
                  value={agent.skills}
                  onChange={(event) => {
                    const selectedInView = Array.from(
                      event.target.selectedOptions,
                      (option) => option.value
                    );
                    const hiddenSelected = agent.skills.filter(
                      (s) => !visibleSkills.some((vs) => vs.skill_id === s)
                    );
                    onSkill(agent, Array.from(new Set([...hiddenSelected, ...selectedInView])));
                  }}
                >
                  {visibleSkills.map((skill) => (
                    <option key={skill.skill_id} value={skill.skill_id}>
                      {skill.skill_id}{" "}
                      {(skill.required_tools?.length ?? 0) > 0
                        ? `· (${skill.required_tools.slice(0, 3).join(", ")})`
                        : ""}
                    </option>
                  ))}
                </select>
              </div>

              <label className="field-group">
                <span className="field-label">Assigned LLM Model</span>
                <select
                  className="field-select"
                  value={`${agent.assignedLlm.family}\u0000${agent.assignedLlm.version}`}
                  onChange={(event) => onModel(agent, event.target.value)}
                >
                  {(inventory?.available_models ?? []).map((model) => (
                    <option
                      key={`${model.family}/${model.version}`}
                      value={`${model.family}\u0000${model.version}`}
                    >
                      {model.family} · {model.version}
                      {model.cloud ? " (Cloud)" : " (Local)"}
                    </option>
                  ))}
                </select>
              </label>

              <div className="field-group" style={{ gridColumn: "1 / -1" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "4px",
                  }}
                >
                  <span className="field-label">Additional AgentHub Tools</span>
                  <span style={{ fontSize: "11px", color: "var(--color-text-dim)" }}>
                    {agent.tools.length} tool{agent.tools.length !== 1 ? "s" : ""} bound
                  </span>
                </div>
                {agent.tools.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      marginBottom: "8px",
                    }}
                  >
                    {agent.tools.map((tId) => (
                      <span
                        key={tId}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          fontSize: "11px",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          background: "rgba(59, 130, 246, 0.15)",
                          border: "1px solid rgba(59, 130, 246, 0.3)",
                          color: "#60a5fa",
                        }}
                      >
                        🔧 {tId}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            onTools(
                              agent,
                              agent.tools.filter((x) => x !== tId)
                            );
                          }}
                          style={{
                            background: "none",
                            border: "none",
                            color: "inherit",
                            cursor: "pointer",
                            padding: 0,
                            marginLeft: "2px",
                            lineHeight: 1,
                          }}
                          title="Remove tool"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <input
                  type="text"
                  className="field-input"
                  style={{ height: "26px", fontSize: "10px", padding: "0 8px", marginBottom: "6px" }}
                  placeholder={`Search ${inventory?.registered_tools?.length ?? 0} tools...`}
                  value={toolFilters[agent.id] ?? ""}
                  onChange={(e) => setToolFilters((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                />
                <select
                  multiple
                  className="field-select-multi"
                  style={{ minHeight: "84px" }}
                  value={agent.tools}
                  onChange={(event) => {
                    const selectedInView = Array.from(
                      event.target.selectedOptions,
                      (option) => option.value
                    );
                    const hiddenSelected = agent.tools.filter(
                      (t) => !visibleTools.some((vt) => vt.tool_id === t)
                    );
                    onTools(agent, Array.from(new Set([...hiddenSelected, ...selectedInView])));
                  }}
                >
                  {visibleTools.map((tool) => (
                    <option key={tool.tool_id} value={tool.tool_id}>
                      {tool.tool_id} · {tool.risk_level}
                      {tool.requires_hitl_approval ? " · HITL Approval Required" : ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {agent.workflowSteps.length > 0 && (
              <div className="specialist-card-steps">
                {agent.workflowSteps.map((step) => (
                  <label className="check-label" key={step.step_id}>
                    <input
                      type="checkbox"
                      checked={step.requires_step_challenge}
                      onChange={(event) =>
                        updateAgent(agent, {
                          workflowSteps: agent.workflowSteps.map((c) =>
                            c.step_id === step.step_id
                              ? { ...c, requires_step_challenge: event.target.checked }
                              : c
                          ),
                        })
                      }
                    />
                    <span>
                      Require human challenge gate before executing <code>{step.name}</code>
                    </span>
                  </label>
                ))}
              </div>
            )}

            {agent.capabilityGaps.length > 0 && (
              <div className="specialist-card-gaps">
                {agent.capabilityGaps.map((gap) => (
                  <small className="gap-warning" key={gap.capability_id}>
                    Capability Gap: {gap.capability_id} — {gap.reason}
                  </small>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <button className="add-agent-btn" onClick={onAdd}>
        <Plus size={15} /> Add specialist
      </button>
    </div>
  );
}

export function FleetRoster({
  missionName,
  roster,
  selected,
  inventory,
  missions = [],
  activeMissionId,
  onSelectMission,
  onSelect,
  onAdd,
  onRemove,
  onSplit,
  onSkill,
  onTools,
  onRun,
  uploadingMission,
}: {
  missionName?: string;
  roster: Agent[];
  selected: Agent;
  inventory: InventoryData | null;
  missions?: MissionRecord[];
  activeMissionId?: string | null;
  onSelectMission?: (missionId: string) => void;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onRemove: (agent: Agent) => void;
  onSplit: (agent: Agent) => void;
  onSkill: (agent: Agent, skillInput: string[] | string) => void;
  onTools: (agent: Agent, selectedTools: string[]) => void;
  onRun?: (mission: MissionRecord) => void;
  uploadingMission?: MissionRecord | null;
}) {
  const [selectedMissionId, setSelectedMissionId] = useState<string>(activeMissionId || "ALL");
  const [missionMenuOpen, setMissionMenuOpen] = useState(false);
  const [showDagHelp, setShowDagHelp] = useState(false);
  const [rosterMenuOpen, setRosterMenuOpen] = useState(false);

  const rosterMenuRef = useRef<HTMLDivElement | null>(null);
  const missionMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (rosterMenuRef.current && !rosterMenuRef.current.contains(event.target as globalThis.Node)) {
        setRosterMenuOpen(false);
      }
      if (missionMenuRef.current && !missionMenuRef.current.contains(event.target as globalThis.Node)) {
        setMissionMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setRosterMenuOpen(false);
        setMissionMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    if (activeMissionId) {
      setSelectedMissionId(activeMissionId);
    }
  }, [activeMissionId]);

  const currentMission = useMemo(() => {
    if (selectedMissionId === "ALL") return null;
    return missions.find((m) => m.mission_id === selectedMissionId) ?? null;
  }, [missions, selectedMissionId]);

  const displayedRoster = useMemo(() => {
    let source = roster;
    if (selectedMissionId !== "ALL") {
      const targetMission = missions.find((m) => m.mission_id === selectedMissionId);
      const filtered = roster.filter((agent) => {
        if (agent.missionId && agent.missionId === selectedMissionId) return true;
        if (targetMission) {
          const gLower = (targetMission.goal || "").toLowerCase();
          const nLower = (targetMission.name || "").toLowerCase();
          const sLower = (agent.scope || "").toLowerCase();
          if (
            (nLower.includes("soc") ||
              gLower.includes("firewall") ||
              gLower.includes("endpoint") ||
              gLower.includes("soc")) &&
            (sLower.includes("firewall") ||
              sLower.includes("soc") ||
              sLower.includes("endpoint") ||
              sLower.includes("incident") ||
              sLower.includes("triage"))
          ) {
            return true;
          }
          if (
            (nLower.includes("smoke") ||
              gLower.includes("supplier") ||
              gLower.includes("smoke")) &&
            (sLower.includes("supplier") ||
              sLower.includes("smoke") ||
              sLower.includes("source documents"))
          ) {
            return true;
          }
          if (
            (nLower.includes("runtime") || gLower.includes("runtime")) &&
            (sLower.includes("runtime") || sLower.includes("challenge"))
          ) {
            return true;
          }
        }
        return false;
      });
      source = filtered.length > 0 ? filtered : roster;
    }
    const seen = new Set<string>();
    return source.filter((agent) => {
      const key = `${agent.missionId ?? ""}-${agent.name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [roster, selectedMissionId, missions]);

  useEffect(() => {
    if (displayedRoster.length > 0 && !displayedRoster.some((a) => a.id === selected.id)) {
      onSelect(displayedRoster[0].id);
    }
  }, [displayedRoster, selected.id, onSelect]);

  const currentAgent =
    displayedRoster.find((a) => a.id === selected.id) ?? displayedRoster[0] ?? selected;
  const topology = useMemo(() => makeTopology(displayedRoster), [displayedRoster]);
  const activeTitle = currentMission
    ? currentMission.name
    : selectedMissionId === "ALL"
    ? "All Missions"
    : missionName ?? "Active Fleet";

  return (
    <>
      <PageTitle
        eyebrow={
          currentMission
            ? `MISSION: ${currentMission.name.toUpperCase()}  /  ${displayedRoster.length} SPECIALISTS`
            : `AGENTHUB ESTATE  /  ${displayedRoster.length} SPECIALISTS`
        }
        title="Fleet roster"
        subtitle={`Declared specialist specifications for ${activeTitle} and their enforced capability bindings.`}
        action={
          <>
            <div ref={missionMenuRef} style={{ position: "relative" }}>
              <button
                className="secondary-button"
                onClick={(e) => {
                  e.stopPropagation();
                  setMissionMenuOpen(!missionMenuOpen);
                }}
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600 }}
              >
                <Layers3 size={15} color="#236f66" />
                <span>{currentMission ? currentMission.name : "Filter by Mission (All)"}</span>
                <ChevronDown size={14} />
              </button>
              {missionMenuOpen && (
                <div
                  className="dropdown-menu"
                  style={{ right: 0, top: "100%", marginTop: 4, minWidth: 280, zIndex: 99999 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div
                    style={{
                      padding: "6px 12px",
                      borderBottom: "1px solid #edf2ee",
                      fontSize: 10,
                      fontWeight: 700,
                      color: "#8a9692",
                      letterSpacing: "0.06em",
                    }}
                  >
                    SELECT MISSION FLEET
                  </div>
                  <button
                    className={`dropdown-item ${selectedMissionId === "ALL" ? "active" : ""}`}
                    onClick={() => {
                      setSelectedMissionId("ALL");
                      if (onSelectMission) onSelectMission("ALL");
                      setMissionMenuOpen(false);
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, textAlign: "left" }}>
                      <strong style={{ fontSize: 12 }}>All Estate Specialists</strong>
                      <small style={{ color: "#778580", fontSize: 10 }}>
                        Show all {roster.length} agents across the estate
                      </small>
                    </div>
                    {selectedMissionId === "ALL" && <Check size={14} color="#236f66" />}
                  </button>
                  {missions.map((m) => (
                    <button
                      key={m.mission_id}
                      className={`dropdown-item ${selectedMissionId === m.mission_id ? "active" : ""}`}
                      onClick={() => {
                        setSelectedMissionId(m.mission_id);
                        if (onSelectMission) onSelectMission(m.mission_id);
                        setMissionMenuOpen(false);
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: 2, textAlign: "left" }}>
                        <strong style={{ fontSize: 12 }}>{m.name}</strong>
                        <small style={{ color: "#778580", fontSize: 10 }}>
                          {m.status} · {m.mission_id.slice(0, 8)}
                        </small>
                      </div>
                      {selectedMissionId === m.mission_id && <Check size={14} color="#236f66" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="secondary-button" onClick={() => setShowDagHelp(!showDagHelp)}>
              <GitBranch size={15} /> Workflow DAG
            </button>
            {currentMission &&
              (currentMission.status === "READY" || currentMission.status === "APPLIED") &&
              onRun && (
                <button
                  className="primary-button"
                  style={{
                    background: "#236f66",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                  onClick={() => void onRun(currentMission)}
                  disabled={uploadingMission?.mission_id === currentMission.mission_id}
                >
                  {uploadingMission?.mission_id === currentMission.mission_id ? (
                    <>
                      <RefreshCw size={15} className="spin" /> Dispatching fleet...
                    </>
                  ) : (
                    <>
                      <Play size={15} /> Run fleet
                    </>
                  )}
                </button>
              )}
            <button className="secondary-button" onClick={onAdd}>
              <Plus size={15} /> Add specialist
            </button>
          </>
        }
      />
      {showDagHelp && (
        <div
          className="filter-bar"
          style={{ justifyContent: "space-between", margin: "10px 0" }}
        >
          <span>
            Interactive Workflow DAG: click nodes or pan/zoom the topology canvas below to inspect
            agent handoffs.
          </span>
          <button
            onClick={() => setShowDagHelp(false)}
            style={{
              border: 0,
              background: "transparent",
              color: "#889",
              cursor: "pointer",
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}
      <div className="scope">
        <span>
          <Layers3 size={14} /> MISSION: <strong>{activeTitle}</strong>
        </span>
        <i />
        <span>
          <Dot color={currentAgent.state === "Applied" ? "green" : "orange"} />{" "}
          {currentAgent.state.toUpperCase()}
        </span>
        <i />
        <span>
          {currentAgent.triggerPolicy}
          {currentAgent.triggerPolicy === "CRON" ? ` · ${currentAgent.schedule}` : ""}
        </span>
        <i />
        <span>{inventory?.profile ?? "default AgentHub profile"}</span>
        <small>
          {inventory?.provider_configured ? "Inference ready" : "Inference unavailable"}
        </small>
      </div>
      <section className="panel topology">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">AGENT HANDOFF TOPOLOGY</div>
            <h3>
              {activeTitle} ·{" "}
              <span style={{ fontWeight: 400, color: "#687a74" }}>{currentAgent.name}</span>
            </h3>
          </div>
          <span className="select-button">
            <Dot color={inventory?.connected ? "green" : "orange"} />{" "}
            {inventory?.connected ? "AgentHub connected" : "AgentHub unavailable"}
          </span>
        </div>
        <div className="flow-canvas">
          <ReactFlow
            nodes={topology.nodes}
            edges={topology.edges}
            fitView
            fitViewOptions={{ padding: 0.16 }}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#d8e0dc" gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap nodeStrokeWidth={3} zoomable pannable />
          </ReactFlow>
        </div>
        <div className="flow-foot">
          <span>
            <i /> Upstream handoff
          </span>
          <span>
            <i className="dashed" /> Human approval boundary
          </span>
          <b>
            {displayedRoster.length} declared agents ·{" "}
            {displayedRoster.reduce(
              (count, agent) => count + agent.workflowSteps.length,
              0
            )}{" "}
            workflow steps
          </b>
        </div>
      </section>
      <div className="roster-detail">
        <section className="panel agent-list">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">SPECIALIST ROSTER</div>
              <h3>Agent responsibilities</h3>
            </div>
            <div ref={rosterMenuRef} style={{ position: "relative" }}>
              <button
                type="button"
                className="icon-button"
                aria-label="Roster options"
                onClick={(e) => {
                  e.stopPropagation();
                  setRosterMenuOpen(!rosterMenuOpen);
                }}
              >
                <MoreHorizontal size={17} />
              </button>
              {rosterMenuOpen && (
                <div
                  className="dropdown-menu"
                  style={{
                    position: "absolute",
                    right: 0,
                    top: "100%",
                    marginTop: 4,
                    width: 210,
                    zIndex: 99999,
                    background: "#ffffff",
                    border: "1px solid #dce5df",
                    borderRadius: 6,
                    boxShadow: "0 12px 32px rgba(23, 40, 43, 0.22)",
                    padding: "6px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div style={{ padding: "4px 8px", fontSize: 10, fontWeight: 700, color: "#60746f" }}>
                    ROSTER ACTIONS
                  </div>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#195d56", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setRosterMenuOpen(false);
                      onAdd();
                    }}
                  >
                    <Plus size={14} />
                    <span>Add specialist</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setRosterMenuOpen(false);
                      setShowDagHelp(!showDagHelp);
                    }}
                  >
                    <GitBranch size={14} />
                    <span>{showDagHelp ? "Hide DAG guide" : "Show DAG topology guide"}</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setRosterMenuOpen(false);
                      const blob = new Blob([JSON.stringify(roster, null, 2)], { type: "application/json" });
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(blob);
                      a.download = `fleet-roster-${Date.now()}.json`;
                      a.click();
                    }}
                  >
                    <RefreshCw size={14} />
                    <span>Export roster (JSON)</span>
                  </button>
                </div>
              )}
            </div>
          </div>
          {displayedRoster.map((agent) => (
            <button
              className={`agent-row ${currentAgent.id === agent.id ? "selected" : ""}`}
              key={`${agent.id}-${agent.missionId ?? ""}`}
              onClick={() => onSelect(agent.id)}
            >
              <i className={`agent-icon agent-icon--${agent.tint}`}>
                <Bot size={16} />
              </i>
              <span>
                <strong>{agent.name}</strong>
                <small>
                  {agent.role} · {agent.state}
                </small>
              </span>
              <Badge tone={agent.state === "Applied" ? "green" : "orange"}>
                {agent.state}
              </Badge>
              <ChevronRight size={14} />
            </button>
          ))}
        </section>
        <section className="panel agent-detail">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">AGENT DETAIL</div>
              <h3>{currentAgent.name}</h3>
            </div>
            <div className="agent-actions">
              <button
                className="icon-button"
                title="Split specialist role"
                aria-label="Split specialist role"
                onClick={() => onSplit(currentAgent)}
              >
                <GitBranch size={15} />
              </button>
              <button
                className="icon-button"
                title="Remove specialist"
                aria-label="Remove specialist"
                onClick={() => onRemove(currentAgent)}
              >
                <X size={15} />
              </button>
            </div>
          </div>
          <p>{currentAgent.scope}</p>
          <div className="detail-label">CAPABILITY BINDINGS</div>
          <div className="binding-editors" style={{ flexDirection: "column", gap: "10px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: "11px", fontWeight: 700, color: "#374e47" }}>
                  Bound AgentHub Skills (Multi-select)
                </span>
                <span style={{ fontSize: "10px", color: "#687a74" }}>
                  {currentAgent.skills.length} bound
                </span>
              </div>
              {currentAgent.skills.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {currentAgent.skills.map((sId) => (
                    <span
                      key={sId}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "11px",
                        padding: "2px 8px",
                        borderRadius: "12px",
                        background: "#e4f3ef",
                        border: "1px solid #c2e0d7",
                        color: "#1d554f",
                        fontWeight: 600,
                      }}
                    >
                      ⚡ {sId}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          onSkill(
                            currentAgent,
                            currentAgent.skills.filter((x) => x !== sId)
                          );
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "inherit",
                          cursor: "pointer",
                          padding: 0,
                          marginLeft: "2px",
                          lineHeight: 1,
                        }}
                        title="Remove skill"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <select
                multiple
                className="field-select-multi"
                style={{
                  minHeight: "76px",
                  width: "100%",
                  padding: "6px",
                  borderRadius: "5px",
                  border: "1px solid #ccd8d2",
                }}
                value={currentAgent.skills}
                onChange={(event) =>
                  onSkill(
                    currentAgent,
                    Array.from(event.target.selectedOptions, (option) => option.value)
                  )
                }
              >
                {inventory?.installed_skills.map((skill) => (
                  <option key={skill.skill_id} value={skill.skill_id}>
                    {skill.skill_id}{" "}
                    {skill.required_tools.length > 0
                      ? `· (${skill.required_tools.slice(0, 3).join(", ")})`
                      : ""}
                  </option>
                ))}
              </select>
            </div>
            <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#374e47" }}>
                Bound AgentHub Tools ({currentAgent.tools.length} active)
              </span>
              <select
                multiple
                className="field-select-multi"
                style={{
                  minHeight: "96px",
                  width: "100%",
                  padding: "6px",
                  borderRadius: "5px",
                  border: "1px solid #ccd8d2",
                }}
                value={currentAgent.tools}
                onChange={(event) =>
                  onTools(
                    currentAgent,
                    Array.from(event.target.selectedOptions, (option) => option.value)
                  )
                }
              >
                {inventory?.registered_tools.map((tool) => (
                  <option key={tool.tool_id} value={tool.tool_id}>
                    {tool.tool_id} · {tool.risk_level}
                    {tool.requires_hitl_approval ? " · approval required" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {currentAgent.capabilityGaps.map((gap) => (
            <div className="gap-warning" key={gap.capability_id}>
              {gap.capability_id}: {gap.reason}
            </div>
          ))}
          <div className="detail-label spaced">ASSIGNED MODEL</div>
          <div className="model-row">
            <Command size={16} />
            <span>
              <strong>{currentAgent.model}</strong>
              <small>Version reported by AgentHub</small>
            </span>
            <Badge tone="blue">PINNED</Badge>
          </div>
          <div className="detail-label spaced">INTERNAL WORKFLOW</div>
          <div className="workflow-list">
            {currentAgent.workflowSteps.map((step, index) => (
              <span key={step.step_id}>
                <i>{String(index + 1).padStart(2, "0")}</i> {step.name} · {step.capability_id}{" "}
                <Badge tone="neutral">{step.retries} retries</Badge>
              </span>
            ))}
            {currentAgent.workflowSteps.length === 0 && (
              <span>No workflow steps declared.</span>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
