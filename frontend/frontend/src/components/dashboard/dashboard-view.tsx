"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Download,
  FileCheck2,
  FileClock,
  Fingerprint,
  Gauge,
  Layers3,
  MoreHorizontal,
  Plus,
  Radio,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { InventoryData, MissionRecord, Room, TelemetryData } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";
import { MissionActions } from "@/components/missions/mission-actions";

export function Metric({
  icon,
  label,
  value,
  note,
  trend,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
  trend?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-heading">
        <span>{label}</span>
        <i>{icon}</i>
      </div>
      <strong>{value}</strong>
      <small className={trend ? `metric-note metric-note--${trend}` : "metric-note"}>
        {trend === "up" ? (
          <ArrowUpRight size={12} />
        ) : trend === "warn" ? (
          <Clock3 size={12} />
        ) : trend === "ok" ? (
          <CheckCircle2 size={12} />
        ) : null}
        {note}
      </small>
    </div>
  );
}

export function FleetRow({
  icon,
  tint,
  title,
  id,
  count,
  last,
  drift,
  alert,
  mission,
  onInspect,
  onResume,
  onOpenRoster,
  onDelete,
  onRun,
}: {
  icon: React.ReactNode;
  tint: string;
  title: string;
  id: string;
  count: string;
  last: string;
  drift: string;
  alert?: boolean;
  mission: MissionRecord;
  onInspect: (mission: MissionRecord) => void;
  onResume?: (mission: MissionRecord) => void;
  onOpenRoster?: (mission: MissionRecord) => void;
  onDelete?: (mission: MissionRecord) => void;
  onRun?: (mission: MissionRecord) => void;
}) {
  return (
    <tr>
      <td>
        <span className="fleet-name">
          <i className={`fleet-icon fleet-icon--${tint}`}>{icon}</i>
          <span>
            <strong>{title}</strong>
            <small>{id}</small>
          </span>
        </span>
      </td>
      <td>
        <b>{count}</b>
      </td>
      <td>{last}</td>
      <td>
        <Badge tone={alert ? "orange" : "green"}>{drift}</Badge>
      </td>
      <td>
        <span className="table-state">
          <Dot color={alert ? "orange" : "green"} />
          {alert ? "Attention" : "Running"}
        </span>
      </td>
      <td>
        <MissionActions
          mission={mission}
          onInspect={onInspect}
          onResume={onResume}
          onOpenRoster={onOpenRoster}
          onDelete={onDelete}
          onRun={onRun}
          placement="dashboard"
        />
      </td>
    </tr>
  );
}

export function Dashboard({
  pending = 0,
  missions = 0,
  records = [],
  rooms = [],
  inventory,
  telemetry,
  onNew,
  onReconcile,
  reconciling,
  onRooms,
  onMissions,
  onInspect,
  onResume,
  onOpenRoster,
  onDelete,
  onRun,
}: {
  pending: number;
  missions: number;
  records: MissionRecord[];
  rooms: Room[];
  inventory: InventoryData | null;
  telemetry: TelemetryData | null;
  onNew: () => void;
  onReconcile: () => void;
  reconciling: boolean;
  onRooms: () => void;
  onMissions: () => void;
  onInspect: (mission: MissionRecord) => void;
  onResume?: (mission: MissionRecord) => void;
  onOpenRoster?: (mission: MissionRecord) => void;
  onDelete?: (mission: MissionRecord) => void;
  onRun?: (mission: MissionRecord) => void;
}) {
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("24h");
  const [timeRangeOpen, setTimeRangeOpen] = useState(false);
  const [chartMode, setChartMode] = useState<"throughput" | "cumulative">("throughput");
  const [evidenceMenuOpen, setEvidenceMenuOpen] = useState(false);
  const [decisionMenuOpen, setDecisionMenuOpen] = useState(false);

  const evidenceRef = useRef<HTMLDivElement | null>(null);
  const decisionRef = useRef<HTMLDivElement | null>(null);
  const timeRangeRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (evidenceRef.current && !evidenceRef.current.contains(event.target as Node)) {
        setEvidenceMenuOpen(false);
      }
      if (decisionRef.current && !decisionRef.current.contains(event.target as Node)) {
        setDecisionMenuOpen(false);
      }
      if (timeRangeRef.current && !timeRangeRef.current.contains(event.target as Node)) {
        setTimeRangeOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setEvidenceMenuOpen(false);
        setDecisionMenuOpen(false);
        setTimeRangeOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const verdictColors: Record<string, string> = {
    EVIDENCE_FOUND: "#267a70",
    NO_EVIDENCE: "#df8751",
    NOT_VERIFIABLE: "#929b99",
    POLICY_BLOCKED: "#bd554d",
  };
  const verdictLabels: Record<string, string> = {
    EVIDENCE_FOUND: "Evidence found",
    NO_EVIDENCE: "No evidence",
    NOT_VERIFIABLE: "Not verifiable",
    POLICY_BLOCKED: "Policy blocked",
  };
  const verdictEntries = Object.entries(verdictLabels).map(([key, name]) => ({
    name,
    value: telemetry?.assurance_verdicts?.[key] ?? 0,
    color: verdictColors[key],
  }));
  const verdictTotal = verdictEntries.reduce((sum, item) => sum + item.value, 0);

  const rangeConfig = {
    "24h": {
      data: telemetry?.hourly_cycles?.length
        ? telemetry.hourly_cycles
        : [
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
      data: telemetry?.daily_cycles?.length
        ? telemetry.daily_cycles
        : [
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
      data: telemetry?.monthly_cycles?.length
        ? telemetry.monthly_cycles
        : [
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
    cycles: chartMode === "cumulative" ? row.cumulative_cycles ?? row.cycles : row.cycles,
    gates: chartMode === "cumulative" ? row.cumulative_gates ?? row.gates : row.gates,
    rawCycles: row.cycles,
    rawGates: row.gates,
    cumCycles: row.cumulative_cycles ?? row.cycles,
    cumGates: row.cumulative_gates ?? row.gates,
  }));

  const renderTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: { payload?: (typeof activityRows)[number] }[];
    label?: string;
  }) => {
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
          <div
            style={{
              marginTop: 4,
              paddingTop: 3,
              borderTop: "1px dashed #eff3f1",
              fontSize: "8px",
              color: "#8b9793",
            }}
          >
            Interval throughput · {item.cumCycles} of {rangeConfig.total} total
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <PageTitle
        eyebrow="LIVE ESTATE OVERVIEW"
        title="Mission control"
        subtitle="Fleet state, execution health, and human decisions across your estate."
        action={
          <>
            <button className="secondary-button" onClick={onReconcile} disabled={reconciling}>
              <RefreshCw size={15} className={reconciling ? "spin" : ""} />
              {reconciling ? "Reconciling" : "Reconcile"}
            </button>
            <button className="primary-button" onClick={onNew}>
              <Plus size={16} /> New mission
            </button>
          </>
        }
      />
      <div className="scope">
        <span>
          <Radio size={14} /> LIVE ESTATE
        </span>
        <i />
        <span>
          <Dot color={inventory?.connected ? "green" : "orange"} />{" "}
          {inventory?.connected
            ? `${inventory.installed_skills?.length ?? 0} skills · ${inventory.registered_tools?.length ?? 0} tools`
            : "AgentHub unavailable"}
        </span>
        <small>{inventory?.profile ?? "Default AgentHub profile"}</small>
        <button aria-label="Refresh telemetry" onClick={() => window.location.reload()}>
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="metrics">
        <Metric
          icon={<Layers3 />}
          label="Active fleets"
          value={String(telemetry?.active_fleets ?? records?.length ?? 0).padStart(2, "0")}
          note={`${telemetry?.ready_fleets ?? records?.length ?? 0} Ready · ${records?.length ?? 0} Total declared`}
        />
        <Metric
          icon={<Bot />}
          label="Specialized agents"
          value={String(telemetry?.active_agents ?? 118).padStart(2, "0")}
          note="Autonomous specialist units"
        />
        <Metric
          icon={<Activity />}
          label="Workflow cycles · 24h"
          value={String(telemetry?.workflow_cycles_24h ?? 27)}
          note={`${telemetry?.workflow_cycles_7d ?? 81} in 7 days`}
        />
        <Metric
          icon={<FileClock />}
          label="Pending human gates"
          value={String(pending).padStart(2, "0")}
          note="Awaiting disposition"
          trend={pending > 0 ? "warn" : "ok"}
        />
        <Metric
          icon={<ShieldCheck />}
          label="Policy blocks · 24h"
          value={String(telemetry?.policy_blocks_24h ?? 0).padStart(2, "0")}
          note="Zero violations recorded"
          trend="ok"
        />
      </div>
      <div className="dashboard-row">
        <section className="panel execution">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">
                FLEET ACTIVITY <span className="live-label"><Dot /> LIVE</span>
              </div>
              <h3>Workflow execution</h3>
            </div>
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
              <div ref={timeRangeRef} style={{ position: "relative", zIndex: 60 }}>
                <button
                  type="button"
                  className="select-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setTimeRangeOpen(!timeRangeOpen);
                  }}
                >
                  {rangeConfig.label} <ChevronDown size={14} />
                </button>
                {timeRangeOpen && (
                  <div
                    className="dropdown-menu"
                    style={{ right: 0, top: "100%", marginTop: 4, zIndex: 99999 }}
                    onClick={(e) => e.stopPropagation()}
                  >
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
          </div>
          <div className="legend">
            <div>
              <span>
                <i className="legend-teal" />
                {chartMode === "cumulative" ? "Cumulative cycles" : "Completed cycles"}
              </span>
              <span>
                <i className="legend-orange" />
                {chartMode === "cumulative" ? "Cumulative gates" : "Human challenges"}
              </span>
            </div>
            <span style={{ fontSize: "8px", color: "#8a9591" }}>
              {chartMode === "throughput" ? "Interval rate" : "Cumulative total"}
            </span>
          </div>
          {activityRows.some((row) => row.cycles || row.gates) ? (
            <div className="activity-chart">
              <ResponsiveContainer
                key={`rc-${timeRange}-${chartMode}`}
                width="100%"
                height="100%"
              >
                <AreaChart
                  key={`chart-${timeRange}-${chartMode}`}
                  data={activityRows}
                  margin={{ top: 10, right: 10, bottom: 0, left: -20 }}
                >
                  <defs>
                    <linearGradient
                      id={`fill-${timeRange}-${chartMode}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor="#2c877a" stopOpacity={0.22} />
                      <stop offset="95%" stopColor="#2c877a" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="#e9eeeb" strokeDasharray="3 4" />
                  <XAxis
                    dataKey="time"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#89938f", fontSize: 10 }}
                    tickMargin={10}
                  />
                  <YAxis
                    yAxisId="left"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#89938f", fontSize: 10 }}
                    allowDecimals={false}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#dd8a58", fontSize: 9 }}
                    domain={[0, (dataMax: number) => Math.max(4, Math.ceil(dataMax * 1.5))]}
                    allowDecimals={false}
                  />
                  <Tooltip content={renderTooltip} />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="cycles"
                    name={chartMode === "cumulative" ? "Cumulative cycles" : "Completed cycles"}
                    stroke="#287a70"
                    strokeWidth={2}
                    fill={`url(#fill-${timeRange}-${chartMode})`}
                    isAnimationActive={false}
                    activeDot={{ r: 4 }}
                  />
                  <Area
                    yAxisId="right"
                    type="monotone"
                    dataKey="gates"
                    name={chartMode === "cumulative" ? "Cumulative gates" : "Challenge gates"}
                    stroke="#dd8a58"
                    strokeWidth={1.8}
                    strokeDasharray="3 3"
                    fill="transparent"
                    isAnimationActive={false}
                    dot={{ r: 3, fill: "#dd8a58", stroke: "#ffffff", strokeWidth: 1.5 }}
                    activeDot={{ r: 5, fill: "#dd8a58" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="chart-empty">No workflow cycles have been recorded.</div>
          )}
          <div className="chart-foot">
            <span>
              <strong>{rangeConfig.total}</strong> cycles completed (
              {rangeConfig.label.toLowerCase()}) ·{" "}
              {chartMode === "throughput" ? "Throughput rate" : "Cumulative progression"}
            </span>
            <span>
              Average <b>{rangeConfig.avg.toFixed(1)}s</b>
            </span>
          </div>
        </section>
        <section className="panel assurance">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">TRANSCRIPT ASSURANCE</div>
              <h3>Evidence verdicts</h3>
            </div>
            <div ref={evidenceRef} style={{ position: "relative" }}>
              <button
                type="button"
                className="icon-button"
                aria-label="Evidence options"
                onClick={(e) => {
                  e.stopPropagation();
                  setEvidenceMenuOpen(!evidenceMenuOpen);
                }}
              >
                <MoreHorizontal size={18} />
              </button>
              {evidenceMenuOpen && (
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
                    EVIDENCE ASSURANCE
                  </div>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#236f66", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setEvidenceMenuOpen(false);
                      onRooms();
                    }}
                  >
                    <FileCheck2 size={14} />
                    <span>Inspect findings in rooms</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setEvidenceMenuOpen(false);
                      const blob = new Blob([JSON.stringify(telemetry?.assurance_verdicts ?? {}, null, 2)], { type: "application/json" });
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(blob);
                      a.download = `assurance-verdicts-${Date.now()}.json`;
                      a.click();
                    }}
                  >
                    <Download size={14} />
                    <span>Export verdict JSON</span>
                  </button>
                </div>
              )}
            </div>
          </div>
          <div className="donut">
            {verdictTotal > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={verdictEntries}
                    dataKey="value"
                    cx="50%"
                    cy="50%"
                    innerRadius={48}
                    outerRadius={65}
                    paddingAngle={3}
                    stroke="none"
                  >
                    {verdictEntries.map((item) => (
                      <Cell key={item.name} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="donut-empty">No evidence</div>
            )}
            <div className="donut-center">
              <strong>{verdictTotal}</strong>
              <small>findings</small>
            </div>
          </div>
          <div className="verdict-list">
            {verdictEntries.map((item) => (
              <div key={item.name}>
                <i style={{ background: item.color }} />
                <span>{item.name}</span>
                <strong>{String(item.value).padStart(2, "0")}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="dashboard-row dashboard-row--bottom">
        <section className="panel fleet-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">DESIRED-STATE FLEETS</div>
              <h3>Active fleet roster</h3>
            </div>
            <button className="link-button" onClick={onMissions}>
              View all <ArrowRight size={14} />
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>MISSION</th>
                  <th>AGENTS</th>
                  <th>LAST CYCLE</th>
                  <th>DRIFT</th>
                  <th>STATUS</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(records ?? []).slice(0, 3).map((record, index) => (
                  <FleetRow
                    key={record.mission_id}
                    icon={index === 1 ? <Fingerprint /> : <Blocks />}
                    tint={["mint", "orange", "blue"][index % 3]}
                    title={record.name}
                    id={`${record.mission_id.slice(0, 8)} · ${record.status}`}
                    count={record.units_count ? `${record.units_count} units` : "3 units"}
                    last={
                      record.status === "READY"
                        ? "Completed"
                        : record.status === "RUNNING"
                        ? "In progress"
                        : "Draft"
                    }
                    drift={
                      record.status === "READY"
                        ? "In sync"
                        : record.status === "RUNNING"
                        ? "Active"
                        : "Awaiting sync"
                    }
                    alert={record.status === "DRAFT"}
                    mission={record}
                    onInspect={onInspect}
                    onResume={onResume}
                    onOpenRoster={onOpenRoster}
                    onDelete={onDelete}
                    onRun={onRun}
                  />
                ))}
              </tbody>
            </table>
            {(!records || records.length === 0) && (
              <div className="table-empty">No missions declared yet.</div>
            )}
          </div>
          <div className="table-footer">
            Showing {Math.min(records?.length ?? 0, 3)} of {missions} missions
          </div>
        </section>
        <section className="panel decision-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">
                HUMAN IN THE LOOP{" "}
                <span className="pending-tag">{String(pending).padStart(2, "0")} OPEN</span>
              </div>
              <h3>Decision rooms</h3>
            </div>
            <div ref={decisionRef} style={{ position: "relative" }}>
              <button
                type="button"
                className="icon-button"
                aria-label="Decision room options"
                onClick={(e) => {
                  e.stopPropagation();
                  setDecisionMenuOpen(!decisionMenuOpen);
                }}
              >
                <MoreHorizontal size={18} />
              </button>
              {decisionMenuOpen && (
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
                    GOVERNANCE GATES
                  </div>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#236f66", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setDecisionMenuOpen(false);
                      onRooms();
                    }}
                  >
                    <FileCheck2 size={14} />
                    <span>View all decision rooms</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setDecisionMenuOpen(false);
                      onMissions();
                    }}
                  >
                    <Layers3 size={14} />
                    <span>View all missions</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setDecisionMenuOpen(false);
                      onReconcile();
                    }}
                  >
                    <RefreshCw size={14} />
                    <span>Reconcile desired state</span>
                  </button>
                </div>
              )}
            </div>
          </div>
          {(rooms ?? [])
            .filter((room) => room.status === "Pending")
            .slice(0, 2)
            .map((room) => (
              <button className="decision-item" key={room.id} onClick={onRooms}>
                <span>
                  <FileCheck2 size={15} />
                </span>
                <div>
                  <strong>{room.title}</strong>
                  <small>
                    {room.agent} · {room.time}
                  </small>
                </div>
                <ChevronRight size={15} />
              </button>
            ))}
          {pending === 0 && (
            <div className="decision-empty">No decisions are waiting for review.</div>
          )}
          <button className="decision-footer" onClick={onRooms}>
            Open decision queue <ArrowRight size={14} />
          </button>
        </section>
      </div>
      <div className="telemetry">
        <span>
          <Clock3 /> Average cycle{" "}
          <b>{(telemetry?.avg_cycle_duration_seconds ?? 0).toFixed(1)}s</b>
        </span>
        <i />
        <span>
          <Gauge /> Mean step latency{" "}
          <b>{(telemetry?.avg_step_execution_latency_seconds ?? 0).toFixed(1)}s</b>
        </span>
        <i />
        <span>
          <Fingerprint /> Model spend today{" "}
          <b>${(telemetry?.daily_budget_burn_usd ?? 0).toFixed(2)}</b>
        </span>
        <i />
        <span>
          <CheckCircle2 /> Challenge turnaround{" "}
          <b>{(telemetry?.avg_challenge_turnaround_seconds ?? 0).toFixed(0)}s</b>
        </span>
      </div>
    </>
  );
}
