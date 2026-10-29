"use client";

import React, { useState } from "react";
import { Check, CheckCircle2, GitBranch, LockKeyhole, RefreshCw, X } from "lucide-react";
import { Agent, InventoryData, MissionRecord } from "@/lib/types";
import { Badge, Dot } from "@/components/ui/badge";

export function PlanReviewModal({
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
    options?: {
      confirm_changes?: boolean;
      confirm_removals?: boolean;
      confirm_external_actions?: boolean;
    }
  ) => Promise<void>;
}) {
  const [selectedMissionId, setSelectedMissionId] = useState<string>(
    missions[0]?.mission_id ?? ""
  );
  const [confirmChanges, setConfirmChanges] = useState(true);
  const [confirmRemovals, setConfirmRemovals] = useState(false);
  const [confirmExternal, setConfirmExternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  const targetMission =
    missions.find((m) => m.mission_id === selectedMissionId) ?? missions[0];

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
      <section
        className="wizard plan-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="wizard-head">
          <span>
            <GitBranch size={14} /> DRIFT & BLUEPRINT RECONCILIATION
          </span>
          <button className="icon-button" aria-label="Close plan review" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <h2>Reconciliation Plan</h2>
        <p className="wizard-desc">
          Compare declared desired-state blueprints against the active AgentHub runtime estate
          before applying changes.
        </p>

        {missions.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <label
              style={{
                display: "grid",
                gap: 5,
                fontSize: 10,
                fontWeight: 600,
                color: "#55645f",
              }}
            >
              Target Mission Blueprint
              <select
                value={selectedMissionId}
                onChange={(e) => setSelectedMissionId(e.target.value)}
                style={{
                  padding: "7px 9px",
                  borderRadius: 4,
                  border: "1px solid #dce5df",
                  background: "#fff",
                  fontSize: 10,
                }}
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
              <small>
                Specialists: {uniqueSpecialists.join(", ") || "Declared mission agents"}
              </small>
            </div>
            <Dot color="green" />
          </div>
          <div className="plan-change-item">
            <Badge tone="blue">BIND</Badge>
            <div>
              <strong>Attach capability bindings & AgentHub tools</strong>
              <small>
                Skills & Tools: {inventory?.installed_skills.length ?? 0} skills installed,{" "}
                {inventory?.registered_tools.length ?? 0} tools available
              </small>
            </div>
            <Dot color="green" />
          </div>
          <div className="plan-change-item">
            <Badge tone="orange">GATE</Badge>
            <div>
              <strong>Enforce Human-in-the-Loop challenge boundaries</strong>
              <small>
                Actions requiring external side-effects will hold for Decision Room sign-off
              </small>
            </div>
            <Dot color="orange" />
          </div>
        </div>

        <div
          style={{
            background: "#f6f8f7",
            padding: "12px 14px",
            borderRadius: 5,
            border: "1px solid #e2ece7",
            margin: "14px 0",
          }}
        >
          <div
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: "#5a6a65",
              letterSpacing: 0.5,
              marginBottom: 8,
            }}
          >
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
          <div
            style={{
              padding: "10px 12px",
              background: resultMessage.includes("failed") ? "#fbeeed" : "#eef6f2",
              border: "1px solid #c7e2d4",
              borderRadius: 4,
              color: resultMessage.includes("failed") ? "#a8453d" : "#24665a",
              fontSize: 10,
              lineHeight: 1.5,
              marginBottom: 12,
            }}
          >
            <CheckCircle2
              size={14}
              style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }}
            />
            {resultMessage}
          </div>
        )}

        <div className="wizard-foot">
          <button className="plain-button" onClick={onClose}>
            Cancel
          </button>
          <span>
            <LockKeyhole size={13} /> Requires human authorization
          </span>
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
