"use client";

import React, { useState } from "react";
import {
  Blocks,
  CircleHelp,
  Command,
  FileCheck2,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { InventoryData } from "@/lib/types";
import { Badge, Dot, PageTitle } from "@/components/ui/badge";

export function Inventory({
  inventory,
  loading,
}: {
  inventory: InventoryData | null;
  loading: boolean;
}) {
  const [tab, setTab] = useState("Skills");
  const [searchQuery, setSearchQuery] = useState("");
  const allSkillRows = inventory?.installed_skills ?? [];
  const allToolRows = inventory?.registered_tools ?? [];
  const allModelRows = (inventory?.available_models ?? []) as {
    family: string;
    version: string;
    cloud?: boolean;
    residency_verified?: boolean;
    data_residencies?: string[];
    reasoning_tier?: string;
    estimated_daily_cost_usd?: number | null;
  }[];

  const sq = searchQuery.trim().toLowerCase();
  const skillRows = allSkillRows.filter(
    (row) =>
      !sq ||
      row.skill_id.toLowerCase().includes(sq) ||
      row.description.toLowerCase().includes(sq)
  );
  const toolRows = allToolRows.filter(
    (row) =>
      !sq ||
      row.tool_id.toLowerCase().includes(sq) ||
      (row.description ?? "").toLowerCase().includes(sq)
  );
  const modelRows = allModelRows.filter(
    (row) =>
      !sq ||
      row.family.toLowerCase().includes(sq) ||
      row.version.toLowerCase().includes(sq)
  );

  const counts = [skillRows.length, toolRows.length, modelRows.length];
  const connectionLabel = loading
    ? "DISCOVERING"
    : inventory?.connected
    ? "LIVE INVENTORY"
    : "DISCONNECTED";

  return (
    <>
      <PageTitle
        eyebrow="AGENTHUB 0.21.x  /  ESTATE DISCOVERY"
        title="Capability inventory"
        subtitle="Only discovered capabilities are eligible for fleet bindings."
        action={
          <>
            <button className="secondary-button" onClick={() => window.location.reload()}>
              <RefreshCw size={15} /> Refresh estate
            </button>
            <Badge tone={inventory?.connected ? "green" : "orange"}>
              <Dot color={inventory?.connected ? "green" : "orange"} /> {connectionLabel}
            </Badge>
          </>
        }
      />
      <div className="inventory-warning">
        <CircleHelp size={16} />
        <span>
          {inventory?.connected
            ? inventory.provider_configured
              ? `Connected to AgentHub${
                  inventory.hermes_version ? ` ${inventory.hermes_version}` : ""
                }; inference provider ${inventory.inference_provider || "configured"}.`
              : `Connected to AgentHub, but inference is not configured${
                  inventory.inference_provider ? ` (${inventory.inference_provider})` : ""
                }. Blueprints remain drafts until runtime is ready.`
            : inventory?.connection_error ?? "Waiting for the AgentHub gateway connection."}
        </span>
      </div>
      <section className="panel inventory-panel">
        <div className="inventory-tabs">
          {["Skills", "Tools", "Models"].map((item, index) => (
            <button
              key={item}
              className={tab === item ? "active" : ""}
              onClick={() => setTab(item)}
            >
              {item}
              <i>{String(counts[index]).padStart(2, "0")}</i>
            </button>
          ))}
          <label>
            <Search size={14} />
            <input
              placeholder={`Search ${tab.toLowerCase()}...`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </label>
        </div>
        {tab === "Skills" && (
          <div className="inventory-table">
            <div className="inventory-row inventory-row--head">
              <span>SKILL</span>
              <span>VERSION</span>
              <span>REQUIRES</span>
              <span>HOST NODE</span>
              <span>STATUS</span>
            </div>
            {skillRows.map((row) => (
              <div className="inventory-row" key={row.skill_id}>
                <span className="inventory-name">
                  <i>
                    <FileCheck2 size={16} />
                  </i>
                  <span>
                    <strong>{row.skill_id}</strong>
                    <small>{row.description}</small>
                  </span>
                </span>
                <code>{row.version}</code>
                <code>{row.required_tools.join(", ") || "Not reported"}</code>
                <span>{row.host_node_ids.join(", ") || "AgentHub gateway"}</span>
                <Badge tone="green">Installed</Badge>
              </div>
            ))}
          </div>
        )}
        {tab === "Tools" && (
          <div className="inventory-table">
            <div className="inventory-row inventory-row--head">
              <span>TOOL</span>
              <span>RISK</span>
              <span>MCP SERVER</span>
              <span>HITL</span>
              <span>STATUS</span>
            </div>
            {toolRows.map((row) => (
              <div className="inventory-row" key={row.tool_id}>
                <span className="inventory-name">
                  <i>
                    <Blocks size={16} />
                  </i>
                  <span>
                    <strong>{row.tool_id}</strong>
                    <small>{row.description || "Description not reported by AgentHub."}</small>
                  </span>
                </span>
                <Badge
                  tone={
                    row.risk_assessed
                      ? row.risk_level === "READ_ONLY"
                        ? "green"
                        : "orange"
                      : "orange"
                  }
                >
                  {row.risk_assessed
                    ? row.risk_level.replaceAll("_", " ")
                    : "UNCLASSIFIED · SAFE DEFAULT"}
                </Badge>
                <span>{row.mcp_server || "Native AgentHub"}</span>
                <span>{row.requires_hitl_approval ? "Required" : "No"}</span>
                <Badge tone="green">Enabled</Badge>
              </div>
            ))}
          </div>
        )}
        {tab === "Models" && (
          <div className="inventory-table">
            <div className="inventory-row inventory-row--head">
              <span>MODEL FAMILY</span>
              <span>MODEL ID</span>
              <span>RESIDENCY</span>
              <span>REASONING</span>
              <span>EST. DAILY</span>
            </div>
            {modelRows.map((row) => (
              <div className="inventory-row" key={`${row.family}/${row.version}`}>
                <span className="inventory-name">
                  <i>
                    <Command size={16} />
                  </i>
                  <span>
                    <strong>{row.family}</strong>
                    <small>{row.cloud ? "Provider model" : "Local provider"}</small>
                  </span>
                </span>
                <code>{row.version}</code>
                <span>
                  {row.residency_verified ? row.data_residencies?.join(", ") : "Not reported"}
                </span>
                <span>{row.reasoning_tier ?? "Not reported"}</span>
                <strong>
                  {row.estimated_daily_cost_usd === null || row.estimated_daily_cost_usd === undefined
                    ? "Not reported"
                    : `$${row.estimated_daily_cost_usd.toFixed(2)}`}
                </strong>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="inventory-foot">
        <span>
          <ShieldCheck size={15} /> AgentHub does not report some risk, schema, residency, or pricing
          metadata.
        </span>
        <span>{inventory?.connected ? "Connected" : "Unavailable"}</span>
      </div>
    </>
  );
}
