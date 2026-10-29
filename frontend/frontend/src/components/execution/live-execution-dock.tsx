"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Maximize2,
  Minimize2,
  Play,
  RefreshCw,
  Send,
  ShieldAlert,
  Terminal,
  X,
  XCircle,
} from "lucide-react";
import { approveWorkflowTask, cancelWorkflow, subscribeToWorkflowStream } from "@/lib/api";
import { Badge, Dot } from "@/components/ui/badge";

export type StreamLogItem = {
  id: string;
  timestamp: string;
  type: "token" | "step" | "task_start" | "task_complete" | "approval_required" | "error" | "info";
  agent?: string;
  task?: string;
  message: string;
};

interface LiveExecutionDockProps {
  workflowId: string;
  missionName?: string;
  onClose: () => void;
  onComplete?: () => void;
}

export function LiveExecutionDock({
  workflowId,
  missionName,
  onClose,
  onComplete,
}: LiveExecutionDockProps) {
  const [logs, setLogs] = useState<StreamLogItem[]>([]);
  const [isMinimized, setIsMinimized] = useState(false);
  const [status, setStatus] = useState<"running" | "paused" | "completed" | "failed">("running");
  const [activeTask, setActiveTask] = useState<string>("Initializing execution...");
  const [activeAgent, setActiveAgent] = useState<string>("Sovereign Fleet");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [pendingApproval, setPendingApproval] = useState<{
    taskId?: string;
    description?: string;
    risk?: string;
  } | null>(null);
  const [approvalGuidance, setApprovalGuidance] = useState("");
  const [approvalBusy, setApprovalBusy] = useState(false);

  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Timer
  useEffect(() => {
    if (status !== "running") return;
    const interval = setInterval(() => {
      setElapsedSeconds((s) => s + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [status]);

  // SSE Stream subscription
  useEffect(() => {
    if (!workflowId) return;

    // Add initial log
    setLogs([
      {
        id: `init-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        type: "info",
        message: `Connected to live SSE stream for workflow: ${workflowId}`,
      },
    ]);

    const unsubscribe = subscribeToWorkflowStream(
      workflowId,
      (event) => {
        try {
          const raw = JSON.parse(event.data);
          const nowStr = new Date().toLocaleTimeString();

          // Handle workflow level events
          if (raw.type === "task_started" || raw.event === "task_started") {
            const taskName = raw.task_name || raw.task_id || "Task Execution";
            const agentName = raw.agent_name || raw.agent_id || "Specialist Agent";
            setActiveTask(taskName);
            setActiveAgent(agentName);
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "task_start",
                agent: agentName,
                task: taskName,
                message: `Starting task: ${taskName}`,
              },
            ]);
          } else if (raw.type === "approval_required" || raw.event === "approval_required") {
            setStatus("paused");
            setPendingApproval({
              taskId: raw.task_id,
              description: raw.description || raw.message || "High-risk action requires human authorization",
              risk: raw.risk_level || "HIGH",
            });
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "approval_required",
                message: `[DECISION GATE] High-risk operation paused for operator sign-off.`,
              },
            ]);
          } else if (raw.type === "approval_resolved" || raw.event === "approval_resolved") {
            setStatus("running");
            setPendingApproval(null);
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "info",
                message: `Approval signal received. Workflow resumed.`,
              },
            ]);
          } else if (raw.type === "task_completed" || raw.event === "task_completed") {
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "task_complete",
                message: `Task completed successfully: ${raw.task_id || ""}`,
              },
            ]);
          } else if (raw.type === "workflow_completed" || raw.status === "completed") {
            setStatus("completed");
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "info",
                message: "✓ Workflow finished successfully. Final output dispatched.",
              },
            ]);
            onComplete?.();
          } else if (raw.type === "workflow_failed" || raw.status === "failed") {
            setStatus("failed");
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: "error",
                message: `Workflow error: ${raw.error || raw.message || "Execution terminated"}`,
              },
            ]);
          } else if (raw.message || raw.chunk || raw.thought) {
            const msg = raw.message || raw.chunk || raw.thought;
            setLogs((prev) => [
              ...prev,
              {
                id: `log-${Date.now()}-${Math.random()}`,
                timestamp: nowStr,
                type: raw.thought ? "step" : "info",
                agent: raw.agent_name || activeAgent,
                message: msg,
              },
            ]);
          }
        } catch {
          // If message is raw string
          setLogs((prev) => [
            ...prev,
            {
              id: `log-${Date.now()}-${Math.random()}`,
              timestamp: new Date().toLocaleTimeString(),
              type: "info",
              message: String(event.data),
            },
          ]);
        }
      },
      () => {
        // Fallback / heartbeat error handling
      }
    );

    return () => {
      unsubscribe();
    };
  }, [workflowId, activeAgent, onComplete]);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (scrollRef.current && !isMinimized) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isMinimized]);

  async function handleApprove(decision: boolean) {
    setApprovalBusy(true);
    try {
      await approveWorkflowTask(workflowId, decision, approvalGuidance);
      setPendingApproval(null);
      setApprovalGuidance("");
    } catch (err) {
      alert(`Approval error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setApprovalBusy(false);
    }
  }

  async function handleCancel() {
    if (confirm("Terminate this running fleet workflow?")) {
      await cancelWorkflow(workflowId);
      setStatus("failed");
    }
  }

  const formatTimer = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };

  return (
    <div
      style={{
        position: "fixed",
        bottom: 16,
        right: 20,
        width: isMinimized ? 340 : 680,
        maxHeight: isMinimized ? 52 : 480,
        height: isMinimized ? 52 : 460,
        zIndex: 9999,
        background: "#0c1715",
        border: "1px solid #1f3d35",
        borderRadius: 8,
        boxShadow: "0 12px 36px rgba(0,0,0,0.45)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        transition: "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--font-geist-mono), monospace",
      }}
    >
      {/* Dock Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          background: "#0f201d",
          borderBottom: isMinimized ? "none" : "1px solid #1a352e",
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setIsMinimized(!isMinimized)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Terminal size={15} color="#45c5a7" />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#e3f4ef", letterSpacing: "0.4px" }}>
              LIVE EXECUTION
            </span>
            <span
              style={{
                fontSize: 9,
                color: "#6b9489",
                background: "#122a24",
                padding: "2px 6px",
                borderRadius: 4,
                border: "1px solid #1d4036",
              }}
            >
              {workflowId.slice(0, 16)}
            </span>
          </div>
          <Dot color={status === "running" ? "green" : status === "paused" ? "orange" : status === "completed" ? "green" : "red"} />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#8abcb0" }}>
            <Clock size={12} />
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>

          <button
            type="button"
            style={{ background: "transparent", border: 0, color: "#88ada2", cursor: "pointer", padding: 2 }}
            onClick={() => setIsMinimized(!isMinimized)}
            title={isMinimized ? "Expand terminal" : "Minimize"}
          >
            {isMinimized ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          <button
            type="button"
            style={{ background: "transparent", border: 0, color: "#88ada2", cursor: "pointer", padding: 2 }}
            onClick={onClose}
            title="Close dock"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* Dock Content */}
      {!isMinimized && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "#08100e" }}>
          {/* Active Context Bar */}
          <div
            style={{
              padding: "7px 14px",
              background: "#0c1a17",
              borderBottom: "1px solid #142e27",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 10.5,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#a5cdc3" }}>
              <Bot size={13} color="#45c5a7" />
              <span>
                Agent: <strong style={{ color: "#d2f3eb" }}>{activeAgent}</strong>
              </span>
              <span style={{ color: "#375950" }}>|</span>
              <span style={{ color: "#7ea99f" }}>{activeTask}</span>
            </div>
            {status === "running" && (
              <button
                type="button"
                onClick={handleCancel}
                style={{
                  background: "#221415",
                  border: "1px solid #4a2123",
                  color: "#e27878",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 9.5,
                  cursor: "pointer",
                }}
              >
                Cancel Run
              </button>
            )}
          </div>

          {/* Pending Human Gate Alert */}
          {pendingApproval && (
            <div
              style={{
                margin: "10px 12px",
                background: "#1c1409",
                border: "1px solid #573a11",
                borderRadius: 6,
                padding: "10px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ShieldAlert size={15} color="#e69c24" />
                <span style={{ fontSize: 11, fontWeight: 700, color: "#fed686" }}>
                  DECISION ROOM GATE: Operator Sign-off Required
                </span>
                <span style={{ fontSize: 9, background: "#3d2807", color: "#fed686", padding: "1px 5px", borderRadius: 3 }}>
                  RISK: {pendingApproval.risk}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 10.5, color: "#d9bc82", lineHeight: 1.4 }}>
                {pendingApproval.description}
              </p>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="text"
                  placeholder="Optional guidance or parameter instruction..."
                  value={approvalGuidance}
                  onChange={(e) => setApprovalGuidance(e.target.value)}
                  style={{
                    flex: 1,
                    background: "#0c1715",
                    border: "1px solid #375950",
                    borderRadius: 4,
                    padding: "5px 10px",
                    color: "#e3f4ef",
                    fontSize: 10.5,
                  }}
                />
                <button
                  type="button"
                  disabled={approvalBusy}
                  onClick={() => handleApprove(true)}
                  style={{
                    background: "#1c4f42",
                    border: "1px solid #2d7d69",
                    color: "#ffffff",
                    padding: "5px 12px",
                    borderRadius: 4,
                    fontSize: 10.5,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  {approvalBusy ? "Signaling..." : "Approve"}
                </button>
                <button
                  type="button"
                  disabled={approvalBusy}
                  onClick={() => handleApprove(false)}
                  style={{
                    background: "#381717",
                    border: "1px solid #662626",
                    color: "#f59a9a",
                    padding: "5px 10px",
                    borderRadius: 4,
                    fontSize: 10.5,
                    cursor: "pointer",
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          )}

          {/* Logs Viewport */}
          <div
            ref={scrollRef}
            style={{
              flex: 1,
              padding: "10px 14px",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            {logs.map((log) => {
              const isTaskStart = log.type === "task_start";
              const isComplete = log.type === "task_complete";
              const isError = log.type === "error";
              const isGate = log.type === "approval_required";

              return (
                <div
                  key={log.id}
                  style={{
                    fontSize: 10.5,
                    lineHeight: 1.5,
                    color: isError
                      ? "#f48787"
                      : isGate
                      ? "#fed686"
                      : isTaskStart
                      ? "#64e3c3"
                      : isComplete
                      ? "#a3e8d2"
                      : "#85aba0",
                    display: "flex",
                    gap: 8,
                    fontFamily: "var(--font-geist-mono), monospace",
                  }}
                >
                  <span style={{ color: "#36574f", flexShrink: 0 }}>[{log.timestamp}]</span>
                  {log.agent && (
                    <span style={{ color: "#3a9680", flexShrink: 0, fontWeight: 700 }}>
                      [{log.agent}]
                    </span>
                  )}
                  <span style={{ wordBreak: "break-word" }}>{log.message}</span>
                </div>
              );
            })}
          </div>

          {/* Status footer */}
          <div
            style={{
              padding: "6px 14px",
              background: "#081311",
              borderTop: "1px solid #132a24",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 10,
              color: "#5b847a",
            }}
          >
            <span>Air-gapped telemetry committed to sovereign audit log.</span>
            <span>Status: <strong style={{ color: "#74cfba" }}>{status.toUpperCase()}</strong></span>
          </div>
        </div>
      )}
    </div>
  );
}
