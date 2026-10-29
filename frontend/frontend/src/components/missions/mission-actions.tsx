"use client";

import React, { useEffect, useRef, useState } from "react";
import { Database, FileCheck2, GitBranch, MoreHorizontal, Play, Trash2 } from "lucide-react";
import { MissionRecord } from "@/lib/types";

export function downloadMission(mission: MissionRecord) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(mission, null, 2)], { type: "application/json" })
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `mission-${mission.mission_id}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function MissionActions({
  mission,
  onInspect,
  onResume,
  onOpenRoster,
  onDelete,
  onRun,
  placement,
}: {
  mission: MissionRecord;
  onInspect: (mission: MissionRecord) => void;
  onResume?: (mission: MissionRecord) => void;
  onOpenRoster?: (mission: MissionRecord) => void;
  onDelete?: (mission: MissionRecord) => void;
  onRun?: (mission: MissionRecord) => void;
  placement: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [openUpward, setOpenUpward] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      setOpenUpward(spaceBelow < 260 && rect.top > 260);
    }
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        className="icon-button"
        aria-label={`${mission.name} options`}
        title="Mission actions"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
      >
        <MoreHorizontal size={16} />
      </button>

      {isOpen && (
        <div
          className="dropdown-menu"
          style={{
            position: "absolute",
            right: 0,
            top: openUpward ? "auto" : "100%",
            bottom: openUpward ? "100%" : "auto",
            marginTop: openUpward ? 0 : 4,
            marginBottom: openUpward ? 4 : 0,
            width: 220,
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
          role="menu"
          aria-label={`Actions for ${mission.name}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ padding: "6px 8px 4px", fontSize: 11, fontWeight: 700, color: "#162f29", borderBottom: "1px solid #edf4ef", wordBreak: "break-word" }}>
            {mission.name}
          </div>

          {onRun && (mission.status === "READY" || mission.status === "APPLIED") && (
            <button
              type="button"
              className="dropdown-item"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#195d56", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen(false);
                onRun(mission);
              }}
            >
              <Play size={14} color="#236f66" />
              <span>Run fleet execution</span>
            </button>
          )}

          {onOpenRoster && (
            <button
              type="button"
              className="dropdown-item"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen(false);
                onOpenRoster(mission);
              }}
            >
              <GitBranch size={14} />
              <span>View fleet roster</span>
            </button>
          )}

          {onResume && mission.status !== "READY" && mission.status !== "APPLIED" && (
            <button
              type="button"
              className="dropdown-item"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#236f66", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen(false);
                onResume(mission);
              }}
            >
              <Play size={14} color="#236f66" />
              <span>Resume design</span>
            </button>
          )}

          <button
            type="button"
            className="dropdown-item"
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen(false);
              onInspect(mission);
            }}
          >
            <FileCheck2 size={14} />
            <span>View mission details</span>
          </button>

          <button
            type="button"
            className="dropdown-item"
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen(false);
              downloadMission(mission);
            }}
          >
            <Database size={14} />
            <span>Download mission JSON</span>
          </button>

          {onDelete && (
            <button
              type="button"
              className="dropdown-item"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#bd554d", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4, borderTop: "1px solid #edf4ef", marginTop: 2 }}
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen(false);
                onDelete(mission);
              }}
            >
              <Trash2 size={14} />
              <span>Delete mission</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
