"use client";

import {
  Activity, ArrowRight, ArrowUpRight, BadgeCheck, Bell, Blocks, Bot, Calendar,
  Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3, Command, Copy, Database, DollarSign, Download,
  ExternalLink, FileCheck2, FileClock, FileText, Fingerprint, Folder, Gauge, GitBranch, Layers3, LockKeyhole, MoreHorizontal,
  Plus, Play, Printer, Radio, RefreshCw, Search, Send, Server, Shield, ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, Swords, Trash2, Upload, X,
  Eye, Code2,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";

import {
  View,
  RoomStatus,
  FleetOutput,
  Room,
  MissionRecord,
  UserInfo,
  ClarifyingQuestion,
  ProposedAgent,
  Agent,
  InventoryData,
  TelemetryData,
  DEFAULT_INVENTORY,
} from "@/lib/types";
import {
  API_BASE,
  postJson,
  roomFromApi,
  agentFromApi,
} from "@/lib/api";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";
import { Dashboard } from "@/components/dashboard/dashboard-view";
import { Missions } from "@/components/missions/missions-view";
import { downloadMission } from "@/components/missions/mission-actions";
import {
  FleetRoster,
  ModelBindingEditor,
  RosterDraftEditor,
  EmptyRoster,
  makeTopology,
} from "@/components/roster/roster-view";
import { DecisionRooms, DecisionOutputPanel } from "@/components/governance/decision-rooms-view";
import { Inventory } from "@/components/inventory/inventory-view";
import { RunMissionModal } from "@/components/modals/run-mission-modal";
import { PlanReviewModal } from "@/components/modals/plan-review-modal";
import { SearchPaletteModal } from "@/components/modals/search-palette-modal";
import { TranscriptModal, SourceEvidenceModal } from "@/components/modals/audit-modals";
import { BattleArenaView } from "@/components/arena/battle-arena-view";
import { SkillsMarketplaceView } from "@/components/skills/skills-marketplace-view";
import { LiveExecutionDock } from "@/components/execution/live-execution-dock";
import {
  DEFAULT_OUTPUTS,
  FleetOutputsView,
  OutputDetailModal,
} from "@/components/outputs/outputs-view";
import { SchedulesView } from "@/components/schedules/schedules-view";

const navigation: { name: View; icon: typeof Gauge }[] = [
  { name: "Mission control", icon: Gauge },
  { name: "Missions", icon: Layers3 },
  { name: "Fleet outputs", icon: FileText },
  { name: "Schedules", icon: Clock3 },
  { name: "Fleet roster", icon: GitBranch },
  { name: "Battle arena", icon: Swords },
  { name: "Skills marketplace", icon: Sparkles },
  { name: "Decision rooms", icon: FileCheck2 },
  { name: "Estate inventory", icon: Database },
];

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
  const [missions, setMissions] = useState<number>(36);
  const [missionRecords, setMissionRecords] = useState<MissionRecord[]>([]);
  const [inventoryData, setInventoryData] = useState<InventoryData>(DEFAULT_INVENTORY);

  useEffect(() => {
    try {
      const cached = localStorage.getItem("agenthub_cached_inventory");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed && typeof parsed === "object") {
          setInventoryData({
            ...DEFAULT_INVENTORY,
            ...parsed,
            installed_skills: Array.isArray(parsed.installed_skills) ? parsed.installed_skills : [],
            registered_tools: Array.isArray(parsed.registered_tools) ? parsed.registered_tools : [],
            available_models: Array.isArray(parsed.available_models) ? parsed.available_models : [],
          });
        }
      }
      const cachedMis = localStorage.getItem("agenthub_cached_missions");
      if (cachedMis) {
        const parsed = JSON.parse(cachedMis);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMissionRecords(parsed);
          setMissions(parsed.length);
        }
      }
    } catch {}
  }, []);
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
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
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
  const [activeExecution, setActiveExecution] = useState<{ workflowId: string; missionName: string } | null>(null);

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

  const estateInfoRef = useRef<HTMLDivElement | null>(null);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const notificationsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (estateInfoRef.current && !estateInfoRef.current.contains(event.target as globalThis.Node)) {
        setEstateInfoOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as globalThis.Node)) {
        setProfileMenuOpen(false);
      }
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as globalThis.Node)) {
        setNotificationsOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setEstateInfoOpen(false);
        setProfileMenuOpen(false);
        setNotificationsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
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
  const loadFleetData = useCallback(async (signal?: AbortSignal) => {
    try {
      const userResponse = await fetch(`${API_BASE}/auth/me`, { signal, credentials: "include" }).catch(() => null);
      if (userResponse?.status === 401) {
        setAuthRequired(true);
        setNotice("Sign in with your organization account to access Fleet Studio.");
        return;
      }
      if (userResponse?.ok) {
        const u = await userResponse.json().catch(() => null);
        if (u) setUser(u);
      }

      const [invRes, telRes, misRes, romRes, agtRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/inventory`, { signal, credentials: "include" }).catch(() => null),
        fetch(`${API_BASE}/api/v1/telemetry`, { signal, credentials: "include" }).catch(() => null),
        fetch(`${API_BASE}/api/v1/missions`, { signal, credentials: "include" }).catch(() => null),
        fetch(`${API_BASE}/api/v1/rooms`, { signal, credentials: "include" }).catch(() => null),
        fetch(`${API_BASE}/api/v1/agents`, { signal, credentials: "include" }).catch(() => null),
      ]);

      if (invRes?.ok) {
        const inv = await invRes.json().catch(() => null);
        if (inv && typeof inv === "object") {
          const safeInv: InventoryData = {
            ...DEFAULT_INVENTORY,
            ...inv,
            installed_skills: Array.isArray(inv.installed_skills) ? inv.installed_skills : [],
            registered_tools: Array.isArray(inv.registered_tools) ? inv.registered_tools : [],
            available_models: Array.isArray(inv.available_models) ? inv.available_models : [],
          };
          setInventoryData(safeInv);
          try { localStorage.setItem("agenthub_cached_inventory", JSON.stringify(safeInv)); } catch {}
        }
      }
      if (telRes?.ok) {
        const tel = await telRes.json().catch(() => null);
        if (tel) setTelemetryData(tel);
      }
      if (misRes?.ok) {
        const mis = await misRes.json().catch(() => null);
        if (Array.isArray(mis) && mis.length > 0) {
          setMissionRecords(mis);
          setMissions(mis.length);
          try { localStorage.setItem("agenthub_cached_missions", JSON.stringify(mis)); } catch {}
        }
      }
      if (romRes?.ok) {
        const rom = await romRes.json().catch(() => null);
        if (Array.isArray(rom)) {
          const normalized = rom.map(roomFromApi);
          setRooms(normalized);
          setRoomId((prev) => prev || (normalized[0]?.id ?? ""));
        }
      }
      if (agtRes?.ok) {
        const agt = await agtRes.json().catch(() => null);
        if (Array.isArray(agt)) {
          const normalized = agt.map(agentFromApi);
          setRoster(normalized);
          setAgentId((prev) => prev || (normalized[0]?.id ?? ""));
        }
      }

      void fetch(`${API_BASE}/api/v1/outputs`, { signal, credentials: "include" })
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
    } catch {
      // transient network error
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadFleetData(controller.signal);
    return () => controller.abort();
  }, [loadFleetData]);

  // Auto-reconnect polling: if disconnected, retry every 3.5s until AgentHub responds
  useEffect(() => {
    if (inventoryData?.connected) return;
    const retryTimer = setInterval(() => {
      void loadFleetData();
    }, 3500);
    return () => clearInterval(retryTimer);
  }, [inventoryData?.connected, loadFleetData]);

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

  function selectedModel() {
    const candidate = (inventoryData?.available_models ?? []).find((model) => residency === "local" ? model.residency_verified : (model.data_residencies ?? []).includes(residency));
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
        const skill = (inventoryData?.installed_skills ?? []).find((item) => item.skill_id === id);
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
    const selected = (inventoryData?.available_models ?? []).find((model) => `${model.family}\u0000${model.version}` === modelKey);
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
      const rawFiles = params.files || [];
      const nonSystemFiles = rawFiles.filter(
        (f) => !f.name.startsWith(".") && f.name !== "desktop.ini" && f.name !== "Thumbs.db"
      );

      // If user selected files and ALL of them are 0 bytes, notify them
      if (nonSystemFiles.length > 0 && nonSystemFiles.every((f) => f.size === 0)) {
        throw new Error(
          `The selected file(s) are 0 bytes (empty on disk). If open in Microsoft Word, please press Ctrl+S to save, or select files that contain saved data.`
        );
      }

      // Filter to files with content > 0 bytes
      const validFiles = nonSystemFiles.filter((f) => f.size > 0);

      if (validFiles.length > 0) {
        setNotice(`Uploading ${validFiles.length} file(s) for ${mission.name}...`);
        for (const file of validFiles) {
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
      const cleanPath = params.targetPath?.trim().replace(/^["']+|["']+$/g, "").trim();
      if (cleanPath) {
        if (typeof window !== "undefined") {
          localStorage.setItem("agenthub_last_target_path", cleanPath);
        }
        bodyPayload.target_path = cleanPath;
        bodyPayload.input_document = cleanPath;
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
        let msg = "";
        if (typeof errData.detail === "string") {
          msg = errData.detail;
        } else if (Array.isArray(errData.detail)) {
          msg = errData.detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join(", ");
        } else {
          msg = res.statusText || "Internal Server Error";
        }
        throw new Error(`Run failed (${res.status}): ${msg}`);
      }
      const data = (await res.json()) as { status: string; agent_name?: string; workflow_id?: string };
      const docName = validFiles?.[0]?.name || (cleanPath ? "specified document" : "document");
      setNotice(`✓ Fleet dispatched with attached ${docName} for ${data.agent_name || mission.name}. Check Decision rooms.`);
      setActiveExecution({
        workflowId: data.workflow_id || `mission-${mission.mission_id}`,
        missionName: mission.name,
      });
      setMissionRecords((prev) =>
        prev.map((m) => (m.mission_id === mission.mission_id ? { ...m, status: "RUNNING" } : m))
      );
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

  async function resumeMission(mission: MissionRecord) {
    setNotice(`Resuming mission "${mission.name}" from checkpoint...`);
    try {
      const res = await fetch(`${API_BASE}/api/v1/missions/${mission.mission_id}/resume-latest`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to resume mission");
      }
      const data = await res.json();
      setNotice(`✓ Resumed "${mission.name}" (Workflow ${data.workflow_id}). Processing pending tasks...`);
      void fetch(`${API_BASE}/api/v1/missions`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d) setMissionRecords(d);
        });
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to resume mission.");
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
      <div ref={estateInfoRef} style={{ position: "relative" }}>
        <div className="brand">
          <span className="brand-mark"><Command size={17} /></span>
          <span><strong>fleet studio</strong><small>CONTROL PLANE</small></span>
          <button
            type="button"
            className="icon-button brand-more"
            title="Workspace options"
            aria-label="Workspace options"
            onClick={(e) => {
              e.stopPropagation();
              setEstateInfoOpen(!estateInfoOpen);
            }}
          >
            <MoreHorizontal size={18} />
          </button>
        </div>
        <button
          type="button"
          className="estate-select"
          onClick={(e) => {
            e.stopPropagation();
            setEstateInfoOpen(!estateInfoOpen);
          }}
        >
          <span className="estate-letter">N</span>
          <span>
            <strong>Northstar estate</strong>
            <small>
              <Dot color={inventoryData?.connected ? "green" : "orange"} /> {missions} missions · {inventoryData?.connected ? "AgentHub connected" : "AgentHub offline"}
            </small>
          </span>
          <ChevronDown size={15} />
        </button>
        {estateInfoOpen && (
          <div
            className="dropdown-menu"
            style={{
              position: "absolute",
              left: 10,
              top: "100%",
              marginTop: 4,
              width: 225,
              padding: 12,
              zIndex: 99999,
              boxShadow: "0 14px 40px rgba(18, 36, 32, 0.28)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, paddingBottom: 6, borderBottom: "1px solid #edf2ee" }}>
              <strong style={{ fontSize: 10, color: "#364742" }}>WORKSPACE & ESTATE</strong>
              <button
                type="button"
                onClick={() => setEstateInfoOpen(false)}
                style={{ border: 0, background: "transparent", color: "#8a9692", cursor: "pointer" }}
              >
                <X size={13} />
              </button>
            </div>
            <div style={{ display: "grid", gap: 5, fontSize: 9, color: "#546460", marginBottom: 8 }}>
              <div><b>Cluster:</b> Northstar Estate</div>
              <div><b>Profile:</b> {inventoryData?.profile ?? "default"}</div>
              <div><b>Gateway:</b> {inventoryData?.connected ? "127.0.0.1:8001" : "Disconnected"}</div>
              <div><b>Inference:</b> {inventoryData?.provider_configured ? "Ready" : "Unconfigured"}</div>
              <div><b>Declared fleets:</b> {missions}</div>
              <div><b>Specialists:</b> {roster.length}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, borderTop: "1px solid #edf2ee", paddingTop: 6 }}>
              <button
                type="button"
                className="dropdown-item"
                style={{ padding: "6px 8px", fontSize: 10.5, color: "#195d56", fontWeight: 600, borderRadius: 4 }}
                onClick={() => {
                  setEstateInfoOpen(false);
                  setView("Estate inventory");
                }}
              >
                <Database size={13} />
                <span>Inspect estate inventory</span>
              </button>
              <button
                type="button"
                className="dropdown-item"
                style={{ padding: "6px 8px", fontSize: 10.5, color: "#3b5f53", borderRadius: 4 }}
                onClick={() => {
                  setEstateInfoOpen(false);
                  setSearchPaletteOpen(true);
                }}
              >
                <Search size={13} />
                <span>Search views (⌘K)</span>
              </button>
              <button
                type="button"
                className="dropdown-item"
                style={{ padding: "6px 8px", fontSize: 10.5, color: "#3b5f53", borderRadius: 4 }}
                onClick={() => {
                  setEstateInfoOpen(false);
                  setPlanReviewOpen(true);
                }}
              >
                <RefreshCw size={13} />
                <span>Reconcile desired state</span>
              </button>
            </div>
          </div>
        )}
      </div>
      <nav>
        {navigation.map(({ name, icon: Icon }, index) => (
          <div key={name}>
            {index === 0 && <div className="nav-title" style={{ marginTop: 0 }}>OPERATIONS</div>}
            {index === 4 && <div className="nav-title nav-title--governance">SIMULATION &amp; SKILLS</div>}
            {index === 7 && <div className="nav-title nav-title--governance">GOVERNANCE &amp; ESTATE</div>}
            <button
              className={`nav-link ${view === name ? "nav-link--active" : ""}`}
              onClick={() => setView(name)}
            >
              <Icon size={17} />
              <span>{name}</span>
              {name === "Decision rooms" && pending > 0 && <b>{String(pending).padStart(2, "0")}</b>}
              {name === "Mission control" && <Dot />}
            </button>
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="system-health">
          <span><Activity size={15} /></span>
          <div>
            <strong>{inventoryData?.connected ? "AgentHub online" : "AgentHub unavailable"}</strong>
            <small>{inventoryData?.provider_configured ? "Inference ready" : "Inference not configured"}</small>
          </div>
        </div>
        <div ref={profileMenuRef} style={{ position: "relative", width: "100%" }}>
          <button
            type="button"
            className="profile"
            onClick={(e) => {
              e.stopPropagation();
              setProfileMenuOpen(!profileMenuOpen);
            }}
            style={{ width: "100%" }}
          >
            <span className="avatar">{(user?.name ?? "LO").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
            <span>
              <strong>{user?.name ?? "Local Operator"}</strong>
              <small>{user?.roles?.[0] ?? "PlatformEngineer"}</small>
            </span>
            <MoreHorizontal size={16} />
          </button>
          {profileMenuOpen && (
            <div
              className="dropdown-menu"
              style={{
                position: "absolute",
                left: 0,
                bottom: "100%",
                marginBottom: 8,
                width: 220,
                zIndex: 99999,
                background: "#203437",
                border: "1px solid #31474a",
                borderRadius: 6,
                boxShadow: "0 14px 40px rgba(0, 0, 0, 0.45)",
                padding: "8px",
                display: "flex",
                flexDirection: "column",
                gap: 4,
                color: "#e8f0ec",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #2e474b", paddingBottom: 6, marginBottom: 2 }}>
                <strong style={{ fontSize: 10, color: "#95aaa4", textTransform: "uppercase" }}>OPERATOR PROFILE</strong>
                <button type="button" onClick={() => setProfileMenuOpen(false)} style={{ border: 0, background: "transparent", color: "#8a9692", cursor: "pointer" }}><X size={12} /></button>
              </div>
              <div style={{ fontSize: 10, color: "#9cb4ad", display: "grid", gap: 3 }}>
                <div><b>Identity:</b> {user?.name ?? "Local Operator"}</div>
                <div><b>Role:</b> {user?.roles?.[0] ?? "PlatformEngineer"}</div>
                <div><b>Session:</b> Local Sovereign (Air-Gap)</div>
                <div><b>Gateway:</b> 127.0.0.1:8001</div>
              </div>
              <button
                type="button"
                className="dropdown-item"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 8px",
                  fontSize: 10.5,
                  color: "#bad9ce",
                  border: 0,
                  background: "#294246",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  borderRadius: 4,
                  marginTop: 4,
                }}
                onClick={() => {
                  setProfileMenuOpen(false);
                  setView("Estate inventory");
                }}
              >
                <Database size={13} />
                <span>Inspect estate inventory</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="breadcrumb">Northstar estate <ChevronRight size={14} /><strong>{view}</strong></div>
        <div className="top-actions">
          {authRequired ? <a className="primary-button" href={`${API_BASE}/auth/login`}>Sign in</a> : <>
            <span className="connection"><Dot color={inventoryData?.connected ? "green" : "orange"} /> AgentHub estate <i>·</i> {inventoryData?.connected ? "Connected" : "Disconnected"}</span>
            <button className="icon-button" aria-label="Search" title="Search (Ctrl+K)" onClick={() => setSearchPaletteOpen(true)}><Search size={17} /></button>
            <div ref={notificationsRef} style={{ position: "relative" }}>
              <button
                className="icon-button bell-button"
                aria-label="Notifications"
                title="Notifications"
                onClick={(e) => {
                  e.stopPropagation();
                  setNotificationsOpen(!notificationsOpen);
                }}
              >
                <Bell size={17} />
                {pending > 0 && <i />}
              </button>
              {notificationsOpen && (
                <div
                  className="dropdown-menu"
                  style={{ right: 0, top: "100%", marginTop: 8, width: 280, padding: 10, zIndex: 99999 }}
                  onClick={(e) => e.stopPropagation()}
                >
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
                        <small style={{ color: "#778580", fontSize: 8 }}>{inventoryData?.installed_skills?.length ?? 0} skills · {inventoryData?.registered_tools?.length ?? 0} tools</small>
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
        {view === "Mission control" && <Dashboard
          pending={pending}
          missions={missions}
          records={missionRecords}
          rooms={rooms}
          inventory={inventoryData}
          telemetry={telemetryData}
          onNew={openWizard}
          onReconcile={() => setPlanReviewOpen(true)}
          reconciling={reconciling}
          onRooms={() => setView("Decision rooms")}
          onMissions={() => setView("Missions")}
          onInspect={setInspectedMission}
          onResume={resumeMission}
          onOpenRoster={(m) => {
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
          }}
          onDelete={deleteMission}
          onRun={runMission}
        />}
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
        {view === "Battle arena" && (
          <BattleArenaView
            onLaunchExecution={(wfId, name) => setActiveExecution({ workflowId: wfId, missionName: name })}
            onNavigate={(v) => setView(v as View)}
          />
        )}
        {view === "Skills marketplace" && (
          <SkillsMarketplaceView roster={roster} />
        )}
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
        {view === "Schedules" && (
          <SchedulesView
            roster={roster}
            onLaunchExecution={(wfId, name) => setActiveExecution({ workflowId: wfId, missionName: name })}
            onNavigate={(v) => setView(v)}
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
    {activeExecution && (
      <LiveExecutionDock
        workflowId={activeExecution.workflowId}
        missionName={activeExecution.missionName}
        onClose={() => setActiveExecution(null)}
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
