"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Blocks,
  Check,
  ChevronDown,
  Dot as DotIcon,
  GitBranch,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { Agent, MissionRecord } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";
import { MissionActions } from "./mission-actions";

export function Missions({
  records,
  roster,
  onNew,
  onInspect,
  onResume,
  onOpenPlanReview,
  onOpenRoster,
  onDelete,
  onRun,
  uploadingMission,
}: {
  records: MissionRecord[];
  roster?: Agent[];
  onNew: () => void;
  onInspect: (mission: MissionRecord) => void;
  onResume?: (mission: MissionRecord) => void;
  onOpenPlanReview: () => void;
  onOpenRoster?: (mission: MissionRecord) => void;
  onDelete?: (mission: MissionRecord) => void;
  onRun?: (mission: MissionRecord) => void;
  uploadingMission?: MissionRecord | null;
}) {
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [statusOpen, setStatusOpen] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [keyword, setKeyword] = useState("");

  const statusRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (statusRef.current && !statusRef.current.contains(event.target as Node)) {
        setStatusOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setStatusOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

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
            <button
              className={`secondary-button ${showSearch ? "active" : ""}`}
              onClick={() => setShowSearch(!showSearch)}
            >
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
            <button
              onClick={() => setKeyword("")}
              style={{ border: 0, background: "transparent", color: "#889" }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      )}
      <div className="scope">
        <span>
          <Layers3 size={14} /> {filteredRecords.length} of {records.length} DECLARED FLEETS
        </span>
        <i />
        <span>
          <Dot /> Persisted missions
        </span>
        <small>{statusFilter === "ALL" ? "All statuses active" : `Filter: ${statusFilter}`}</small>
      </div>
      <section className="panel missions-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">FLEET BLUEPRINTS</div>
            <h3>All missions</h3>
          </div>
          <div ref={statusRef} style={{ position: "relative" }}>
            <button
              className="select-button"
              onClick={(e) => {
                e.stopPropagation();
                setStatusOpen(!statusOpen);
              }}
            >
              {statusFilter === "ALL" ? "All statuses" : `Status: ${statusFilter}`}{" "}
              <ChevronDown size={14} />
            </button>
            {statusOpen && (
              <div
                className="dropdown-menu"
                style={{ right: 0, top: "100%", marginTop: 4, zIndex: 99999 }}
                onClick={(e) => e.stopPropagation()}
              >
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
            <div
              className="mission-row"
              key={record.mission_id}
              style={{ cursor: "pointer" }}
              onClick={() => onInspect(record)}
            >
              <i
                className={`fleet-icon fleet-icon--${["mint", "orange", "blue"][index % 3]}`}
              >
                <Blocks />
              </i>
              <span className="mission-copy">
                <strong>{record.name}</strong>
                <small>{record.goal}</small>
              </span>
              <span>
                {(() => {
                  const count = (roster ?? []).filter(
                    (a: Agent) => a.missionId === record.mission_id
                  ).length;
                  return count > 0 ? `${count} agents` : "4 agents";
                })()}
              </span>
              <code>{record.status}</code>
              <span>
                {record.status === "RUNNING" ? (
                  <span
                    style={{
                      color: "#236f66",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      fontWeight: 600,
                    }}
                  >
                    <RefreshCw size={11} className="spin" /> In progress
                  </span>
                ) : record.status === "READY" ? (
                  <span style={{ color: "#4f6560" }}>Ready</span>
                ) : record.status === "COMPLETED" ? (
                  <span style={{ color: "#236f66", fontWeight: 600 }}>Completed</span>
                ) : (
                  <span>{record.status}</span>
                )}
              </span>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  whiteSpace: "nowrap",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <Badge
                  tone={
                    record.status === "READY" ||
                    record.status === "RUNNING" ||
                    record.status === "COMPLETED"
                      ? "green"
                      : "orange"
                  }
                >
                  {record.status}
                </Badge>
                {onResume && record.status === "RUNNING" && (
                  <button
                    className="secondary-button"
                    style={{
                      padding: "4px 9px",
                      fontSize: 11,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      borderColor: "#236f66",
                      color: "#195d56",
                      fontWeight: 700,
                    }}
                    onClick={() => void onResume(record)}
                    title="Resume execution directly from checkpoint (Phase 4 & 5)"
                  >
                    <Play size={11} color="#236f66" /> Resume
                  </button>
                )}
                {onRun && (
                  <button
                    className="primary-button"
                    style={{
                      padding: "4px 9px",
                      fontSize: 11,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
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
              <div
                style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
                onClick={(e) => e.stopPropagation()}
              >
                <MissionActions
                  mission={record}
                  onInspect={onInspect}
                  onResume={onResume}
                  onOpenRoster={onOpenRoster}
                  onDelete={onDelete}
                  onRun={onRun}
                  placement="missions"
                />
              </div>
            </div>
          ))}
          {filteredRecords.length === 0 && (
            <div style={{ padding: "30px 15px", textAlign: "center", color: "#8a9692" }}>
              No missions found matching the selected filter.
            </div>
          )}
        </div>
        <div className="table-footer">
          Showing {filteredRecords.length} of {records.length} missions
        </div>
      </section>
      <div className="wide-callout">
        <GitBranch size={18} />
        <span>
          <strong>Drift is a proposal, never an automatic surprise.</strong>
          <small>
            Review managed-field diffs and required approvals before applying changes to AgentHub.
          </small>
        </span>
        <button className="secondary-button" onClick={onOpenPlanReview}>
          Open plan review <ArrowRight size={14} />
        </button>
      </div>
    </>
  );
}
