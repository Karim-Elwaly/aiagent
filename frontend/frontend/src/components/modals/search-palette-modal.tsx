"use client";

import React, { useState } from "react";
import { Blocks, Bot, FileCheck2, Layers3, Search, X } from "lucide-react";
import { Agent, InventoryData, MissionRecord, View } from "@/lib/types";

export function SearchPaletteModal({
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

  const views: View[] = [
    "Mission control",
    "Missions",
    "Fleet roster",
    "Battle arena",
    "Skills marketplace",
    "Fleet outputs",
    "Decision rooms",
    "Schedules",
    "Estate inventory",
  ];
  const q = query.trim().toLowerCase();

  const matchingViews = views.filter((v) => !q || v.toLowerCase().includes(q));
  const matchingMissions = missions.filter(
    (m) => !q || m.name.toLowerCase().includes(q) || m.goal.toLowerCase().includes(q)
  );
  const matchingAgents = roster.filter(
    (a) => !q || a.name.toLowerCase().includes(q) || a.role.toLowerCase().includes(q)
  );
  const matchingSkills = (inventory?.installed_skills ?? []).filter(
    (s) => !q || s.skill_id.toLowerCase().includes(q)
  );

  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        className="wizard search-palette"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="search-palette-input">
          <Search size={16} color="#60706a" />
          <input
            placeholder="Type to search views, missions, agents, skills..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button
            onClick={onClose}
            style={{
              border: 0,
              background: "transparent",
              color: "#8a9692",
              cursor: "pointer",
            }}
          >
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
              <span>
                Go to <strong>{v}</strong>
              </span>
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
              <span>
                Mission: <strong>{m.name}</strong>
              </span>
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
              <span>
                Agent: <strong>{a.name}</strong>
              </span>
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
              <span>
                Skill: <strong>{s.skill_id}</strong>
              </span>
              <small>v{s.version}</small>
            </button>
          ))}

          {matchingViews.length === 0 &&
            matchingMissions.length === 0 &&
            matchingAgents.length === 0 &&
            matchingSkills.length === 0 && (
              <div
                style={{
                  padding: 20,
                  textAlign: "center",
                  color: "#889490",
                  fontSize: 11,
                }}
              >
                No items matching &ldquo;{query}&rdquo;
              </div>
            )}
        </div>
      </section>
    </div>
  );
}
