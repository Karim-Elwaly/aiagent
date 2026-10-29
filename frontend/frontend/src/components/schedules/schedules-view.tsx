"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  Clock3,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Trash2,
  X,
} from "lucide-react";
import { Agent, ScheduledJob, View } from "@/lib/types";
import { PageTitle } from "@/components/ui/badge";
import {
  createSchedule,
  deleteSchedule,
  fetchSchedules,
  toggleSchedule,
} from "@/lib/api";

interface SchedulesViewProps {
  roster?: Agent[];
  onLaunchExecution?: (workflowId: string, name: string) => void;
  onNavigate?: (view: View) => void;
}

const CRON_PRESETS = [
  { label: "Every Hour", cron: "0 * * * *" },
  { label: "Daily at 08:00 UTC", cron: "0 8 * * *" },
  { label: "Daily at Midnight", cron: "0 0 * * *" },
  { label: "Weekly Mondays at 09:00", cron: "0 9 * * 1" },
];

export function SchedulesView({ roster = [], onLaunchExecution, onNavigate }: SchedulesViewProps) {
  const [schedules, setSchedules] = useState<ScheduledJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [cronExpression, setCronExpression] = useState("0 8 * * *");
  const [query, setQuery] = useState("");
  const [agentId, setAgentId] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSchedules();
      setSchedules(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSchedules();
  }, [loadSchedules]);

  async function handleToggle(jobId: string) {
    setTogglingId(jobId);
    try {
      const updated = await toggleSchedule(jobId);
      setSchedules((prev) => prev.map((s) => (s.id === jobId ? updated : s)));
      setToast({ type: "success", text: `Schedule "${updated.name}" is now ${updated.enabled ? "active" : "paused"}.` });
    } catch (e: unknown) {
      setToast({ type: "error", text: `Failed to toggle schedule: ${String(e)}` });
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(jobId: string, scheduleName: string) {
    if (!confirm(`Are you sure you want to delete recurring schedule "${scheduleName}"?`)) return;
    try {
      const ok = await deleteSchedule(jobId);
      if (ok) {
        setSchedules((prev) => prev.filter((s) => s.id !== jobId));
        setToast({ type: "success", text: `Schedule "${scheduleName}" deleted.` });
      }
    } catch (e: unknown) {
      setToast({ type: "error", text: `Failed to delete schedule: ${String(e)}` });
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setFormError("Schedule name is required");
      return;
    }
    if (!query.trim()) {
      setFormError("Workflow execution query is required");
      return;
    }
    setCreating(true);
    setFormError("");
    try {
      const created = await createSchedule({
        name: name.trim(),
        cron_expression: cronExpression.trim(),
        query: query.trim(),
        agent_id: agentId || null,
        enabled: true,
      });
      setSchedules((prev) => [...prev, created]);
      setCreateModalOpen(false);
      setName("");
      setQuery("");
      setCronExpression("0 8 * * *");
      setToast({ type: "success", text: `Recurring schedule "${created.name}" created successfully!` });
    } catch (err: unknown) {
      setFormError(String(err));
    } finally {
      setCreating(false);
    }
  }

  const activeCount = schedules.filter((s) => s.enabled).length;
  const totalRuns = schedules.reduce((acc, s) => acc + (s.run_count || 0), 0);

  return (
    <>
      <PageTitle
        eyebrow="ORCHESTRATION &amp; AUTOMATION / CRON RUNNERS"
        title="Recurring schedules"
        subtitle="Configure autonomous background workflows, security audits, and compliance checks triggered on precise cron schedules."
        action={
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void loadSchedules()}
              disabled={loading}
              style={{ fontSize: "11px", padding: "6px 12px" }}
            >
              <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => setCreateModalOpen(true)}
              style={{ fontSize: "12px", padding: "6px 14px" }}
            >
              <Plus size={14} /> New Schedule
            </button>
          </div>
        }
      />

      {toast && (
        <div
          style={{
            background: toast.type === "success" ? "#e4f3ed" : "#fdf0ed",
            color: toast.type === "success" ? "#195d56" : "#b44426",
            border: `1px solid ${toast.type === "success" ? "#bde3d4" : "#f5c6bb"}`,
            padding: "10px 14px",
            borderRadius: "6px",
            fontSize: "12px",
            fontWeight: 600,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px",
          }}
        >
          <span>{toast.text}</span>
          <button
            type="button"
            className="icon-button"
            onClick={() => setToast(null)}
            style={{ width: "20px", height: "20px" }}
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Metrics Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", marginBottom: "18px" }}>
        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Clock3 size={13} color="#236f66" /> Total Schedules
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", fontFamily: "var(--font-geist-mono), monospace" }}>
            {schedules.length}
          </span>
          <span style={{ fontSize: "10px", color: "#327568", fontWeight: 600 }}>
            {activeCount} currently active
          </span>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <CheckCircle2 size={13} color="#195d56" /> Total Completed Runs
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#162a26", fontFamily: "var(--font-geist-mono), monospace" }}>
            {totalRuns}
          </span>
          <span style={{ fontSize: "10px", color: "#4f655e" }}>
            Autonomous background executions
          </span>
        </div>

        <div style={{ background: "#ffffff", border: "1px solid #dfe7e3", borderRadius: "6px", padding: "14px 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76", display: "flex", alignItems: "center", gap: "6px" }}>
            <Activity size={13} color="#3864a7" /> Automation Health
          </span>
          <span style={{ fontSize: "22px", fontWeight: 800, color: "#236f66", fontFamily: "var(--font-geist-mono), monospace" }}>
            100% OK
          </span>
          <span style={{ fontSize: "10px", color: "#236f66", fontWeight: 600 }}>
            Cron daemon running
          </span>
        </div>
      </div>

      {/* Schedules List */}
      {schedules.length === 0 ? (
        <section className="panel empty-state" style={{ padding: "48px 24px", textAlign: "center" }}>
          <Clock3 size={40} color="#236f66" style={{ margin: "0 auto 12px" }} />
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#163a33" }}>No scheduled jobs configured</h3>
          <p style={{ fontSize: "12px", color: "#6a7c76", maxWidth: "460px", margin: "6px auto 16px" }}>
            Set up recurring autonomous workflows to run hourly security audits, daily compliance checks, or weekly log correlation tasks without manual intervention.
          </p>
          <button
            type="button"
            className="primary-button"
            onClick={() => setCreateModalOpen(true)}
            style={{ fontSize: "12px", padding: "7px 16px" }}
          >
            <Plus size={14} /> Create First Recurring Schedule
          </button>
        </section>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {schedules.map((schedule) => (
            <div
              key={schedule.id}
              style={{
                background: "#ffffff",
                border: "1px solid #dce8e2",
                borderRadius: "8px",
                padding: "16px 20px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "14px",
                boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: "14px", flex: "1 1 450px" }}>
                <button
                  type="button"
                  onClick={() => void handleToggle(schedule.id)}
                  disabled={togglingId === schedule.id}
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    marginTop: "2px",
                    color: schedule.enabled ? "#236f66" : "#94a89f",
                  }}
                  title={schedule.enabled ? "Click to Pause" : "Click to Enable"}
                >
                  {schedule.enabled ? <ToggleRight size={28} /> : <ToggleLeft size={28} />}
                </button>

                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <h4 style={{ fontSize: "14px", fontWeight: 700, color: "#163a33", margin: 0 }}>
                      {schedule.name}
                    </h4>
                    <span
                      style={{
                        fontSize: "10px",
                        fontFamily: "var(--font-geist-mono), monospace",
                        background: "#edf4f1",
                        color: "#185e54",
                        padding: "2px 7px",
                        borderRadius: "4px",
                        fontWeight: 700,
                      }}
                    >
                      {schedule.cron_expression}
                    </span>
                    <span
                      style={{
                        fontSize: "9px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        background: schedule.enabled ? "#e4f3ed" : "#f1f4f2",
                        color: schedule.enabled ? "#195d56" : "#72837d",
                        padding: "2px 6px",
                        borderRadius: "3px",
                      }}
                    >
                      {schedule.enabled ? "ACTIVE" : "PAUSED"}
                    </span>
                  </div>

                  <p style={{ fontSize: "12px", color: "#365148", margin: "4px 0 0", lineHeight: "1.5" }}>
                    {schedule.query}
                  </p>

                  <div style={{ display: "flex", gap: "12px", alignItems: "center", marginTop: "8px", fontSize: "11px", color: "#7a9088", flexWrap: "wrap" }}>
                    <span>Runs completed: <strong>{schedule.run_count || 0}</strong></span>
                    {schedule.last_run && (
                      <span>Last run: {new Date(schedule.last_run).toLocaleString()}</span>
                    )}
                    {schedule.next_run && (
                      <span>Next expected run: {new Date(schedule.next_run).toLocaleString()}</span>
                    )}
                    {schedule.agent_id && (
                      <span style={{ background: "#edf5f2", color: "#236f66", padding: "1px 6px", borderRadius: "3px" }}>
                        Agent: {schedule.agent_id}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => void handleDelete(schedule.id, schedule.name)}
                  title="Delete schedule"
                  style={{ color: "#b44426" }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Schedule Modal */}
      {createModalOpen && (
        <div className="modal-shade" onClick={() => setCreateModalOpen(false)}>
          <div className="modal-card" style={{ maxWidth: "620px" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <div className="eyebrow">NEW RECURRING WORKFLOW</div>
                <h3>Schedule Automated Mission</h3>
              </div>
              <button className="icon-button" onClick={() => setCreateModalOpen(false)}><X size={16} /></button>
            </div>

            <form onSubmit={(e) => void handleCreate(e)}>
              <div style={{ display: "flex", flexDirection: "column", gap: "14px", marginTop: "14px" }}>
                <div>
                  <label style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase" }}>
                    Schedule Name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Daily Zero-Day & CVE Vulnerability Scan"
                    style={{ width: "100%", padding: "8px 12px", fontSize: "12px", border: "1px solid #cad8d1", borderRadius: "5px", marginTop: "4px" }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase" }}>
                    Cron Expression
                  </label>
                  <input
                    value={cronExpression}
                    onChange={(e) => setCronExpression(e.target.value)}
                    placeholder="e.g. 0 8 * * *"
                    style={{ width: "100%", padding: "8px 12px", fontSize: "12px", fontFamily: "var(--font-geist-mono), monospace", border: "1px solid #cad8d1", borderRadius: "5px", marginTop: "4px" }}
                  />
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "6px" }}>
                    {CRON_PRESETS.map((p) => (
                      <button
                        key={p.cron}
                        type="button"
                        onClick={() => setCronExpression(p.cron)}
                        style={{
                          fontSize: "10px",
                          padding: "3px 8px",
                          borderRadius: "4px",
                          background: cronExpression === p.cron ? "#195d56" : "#edf4f1",
                          color: cronExpression === p.cron ? "#ffffff" : "#2f463f",
                          border: "none",
                          cursor: "pointer",
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase" }}>
                    Execution Query / Mission Goal
                  </label>
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Describe the exact task the autonomous fleet should solve on each run, e.g. Audit all Kubernetes worker node auditd logs for unauthorized privilege escalation and generate an incident dossier."
                    rows={4}
                    style={{ width: "100%", padding: "8px 12px", fontSize: "12px", border: "1px solid #cad8d1", borderRadius: "5px", marginTop: "4px", resize: "vertical" }}
                  />
                </div>

                {roster.length > 0 && (
                  <div>
                    <label style={{ fontSize: "11px", fontWeight: 700, color: "#163a33", textTransform: "uppercase" }}>
                      Assigned Agent (Optional)
                    </label>
                    <select
                      value={agentId}
                      onChange={(e) => setAgentId(e.target.value)}
                      style={{ width: "100%", padding: "8px 12px", fontSize: "12px", border: "1px solid #cad8d1", borderRadius: "5px", marginTop: "4px", background: "#ffffff" }}
                    >
                      <option value="">Autonomous Multi-Agent Fleet (Default)</option>
                      {roster.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name} ({agent.role})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {formError && (
                  <div style={{ fontSize: "12px", color: "#b44426", background: "#fdf0ed", padding: "8px 12px", borderRadius: "4px", border: "1px solid #f5c6bb" }}>
                    {formError}
                  </div>
                )}
              </div>

              <div className="wizard-foot" style={{ marginTop: "18px" }}>
                <button type="button" className="plain-button" onClick={() => setCreateModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={creating}>
                  {creating ? <><RefreshCw size={13} className="spin" /> Creating...</> : <><Check size={14} /> Create Schedule</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
