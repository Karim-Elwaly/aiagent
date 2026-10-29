"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Code2,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  LockKeyhole,
  MoreHorizontal,
  RefreshCw,
  Send,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { DistilledSkillCandidate, Room } from "@/lib/types";
import { Badge, PageTitle } from "@/components/ui/badge";
import {
  approveDistilledSkill,
  fetchApprovedDistilledSkills,
  fetchPendingDistilledSkills,
  postJson,
  rejectDistilledSkill,
} from "@/lib/api";

export function DecisionRooms({
  rooms,
  selected,
  onSelect,
  onResolve,
  onViewTranscript,
  onOpenSource,
}: {
  rooms: Room[];
  selected?: Room;
  onSelect: (room: Room) => void;
  onResolve: (room: Room, decision: "Approved" | "Returned") => void;
  onViewTranscript: (room: Room) => void;
  onOpenSource: (room: Room) => void;
}) {
  const [queueFilter, setQueueFilter] = useState<string>("ALL");
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"gates" | "distilled">("gates");
  const [queueMenuOpen, setQueueMenuOpen] = useState(false);
  const [roomMenuOpen, setRoomMenuOpen] = useState(false);

  const queueMenuRef = useRef<HTMLDivElement | null>(null);
  const roomMenuRef = useRef<HTMLDivElement | null>(null);
  const filterRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (queueMenuRef.current && !queueMenuRef.current.contains(event.target as Node)) {
        setQueueMenuOpen(false);
      }
      if (roomMenuRef.current && !roomMenuRef.current.contains(event.target as Node)) {
        setRoomMenuOpen(false);
      }
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
        setFilterOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setQueueMenuOpen(false);
        setRoomMenuOpen(false);
        setFilterOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const filteredRooms = rooms.filter((r) => {
    if (queueFilter === "ALL") return true;
    return r.status === queueFilter;
  });

  return (
    <>
      <PageTitle
        eyebrow="GOVERNANCE WORKSPACE  /  HUMAN DISPOSITION"
        title="Decision rooms"
        subtitle="Evidence-bound decisions and autonomously distilled skills awaiting an accountable human."
        action={
          <>
            {activeTab === "gates" && (
              <div ref={filterRef} style={{ position: "relative" }}>
                <button
                  className="secondary-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFilterOpen(!filterOpen);
                  }}
                >
                  <SlidersHorizontal size={15} />{" "}
                  {queueFilter === "ALL" ? "Filter queue" : `Queue: ${queueFilter}`}{" "}
                  <ChevronDown size={14} />
                </button>
                {filterOpen && (
                  <div
                    className="dropdown-menu"
                    style={{ right: 0, top: "100%", marginTop: 4, zIndex: 99999 }}
                    onClick={(e) => e.stopPropagation()}
                  >
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
            )}
            <Badge tone="orange">
              {rooms.filter((x) => x.status === "Pending").length} AWAITING REVIEW
            </Badge>
          </>
        }
      />

      <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid #cad8d1", paddingBottom: "10px", marginBottom: "16px" }}>
        <button
          type="button"
          onClick={() => setActiveTab("gates")}
          style={{
            padding: "7px 16px",
            fontSize: "12px",
            fontWeight: activeTab === "gates" ? 700 : 500,
            background: activeTab === "gates" ? "#195d56" : "transparent",
            color: activeTab === "gates" ? "#ffffff" : "#455953",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <FileCheck2 size={14} /> Decision Gates (HITL)
          <span style={{ fontSize: "10px", background: activeTab === "gates" ? "rgba(255,255,255,0.2)" : "#eef3f1", color: activeTab === "gates" ? "#ffffff" : "#195d56", padding: "1px 6px", borderRadius: "10px", fontWeight: 700 }}>
            {rooms.filter((x) => x.status === "Pending").length}
          </span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("distilled")}
          style={{
            padding: "7px 16px",
            fontSize: "12px",
            fontWeight: activeTab === "distilled" ? 700 : 500,
            background: activeTab === "distilled" ? "#195d56" : "transparent",
            color: activeTab === "distilled" ? "#ffffff" : "#455953",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <Sparkles size={14} /> Distilled Skills Review Queue
        </button>
      </div>

      {activeTab === "distilled" ? (
        <DistilledSkillsQueue />
      ) : (
        <div className="room-layout">
        <section className="panel room-queue">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">OPEN QUEUE</div>
              <h3>
                Needs disposition <b>{rooms.filter((x) => x.status === "Pending").length}</b>
              </h3>
            </div>
            <div ref={queueMenuRef} style={{ position: "relative" }}>
              <button
                type="button"
                className="icon-button"
                aria-label="Queue options"
                onClick={(e) => {
                  e.stopPropagation();
                  setQueueMenuOpen(!queueMenuOpen);
                }}
              >
                <MoreHorizontal size={17} />
              </button>
              {queueMenuOpen && (
                <div
                  className="dropdown-menu"
                  style={{
                    position: "absolute",
                    right: 0,
                    top: "100%",
                    marginTop: 4,
                    width: 200,
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
                    QUEUE ACTIONS
                  </div>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setQueueFilter("ALL");
                      setQueueMenuOpen(false);
                    }}
                  >
                    <span>Show all records ({rooms.length})</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#195d56", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setQueueFilter("Pending");
                      setQueueMenuOpen(false);
                    }}
                  >
                    <span>Pending review only</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setQueueFilter("Approved");
                      setQueueMenuOpen(false);
                    }}
                  >
                    <span>Approved only</span>
                  </button>
                  <button
                    type="button"
                    className="dropdown-item"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                    onClick={() => {
                      setQueueMenuOpen(false);
                      const blob = new Blob([JSON.stringify(rooms, null, 2)], { type: "application/json" });
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(blob);
                      a.download = `decision-rooms-${Date.now()}.json`;
                      a.click();
                    }}
                  >
                    <Download size={14} />
                    <span>Export rooms list (JSON)</span>
                  </button>
                </div>
              )}
            </div>
          </div>
          {filteredRooms.map((room) => (
            <button
              className={`room-item ${selected?.id === room.id ? "room-item--active" : ""}`}
              key={room.id}
              onClick={() => onSelect(room)}
            >
              <i
                className={`room-icon room-icon--${room.verdict.toLowerCase().replaceAll("_", "-")}`}
              >
                {room.verdict === "EVIDENCE_FOUND" ? (
                  <BadgeCheck size={16} />
                ) : room.verdict === "POLICY_BLOCKED" ? (
                  <ShieldAlert size={16} />
                ) : (
                  <CircleHelp size={16} />
                )}
              </i>
              <span>
                <strong>{room.title}</strong>
                <small>
                  {room.fleet} · {room.time}
                </small>
              </span>
              {room.status === "Pending" ? <b className="unread" /> : <CheckCircle2 size={15} />}
            </button>
          ))}
          {filteredRooms.length === 0 && (
            <div
              style={{
                padding: "24px 14px",
                color: "#8a9692",
                fontSize: 10,
                textAlign: "center",
              }}
            >
              No decisions match filter: {queueFilter}.
            </div>
          )}
          <div className="queue-note">
            <LockKeyhole size={13} /> Judgments are recorded to the audit trail.
          </div>
        </section>
        {selected ? (
          <section className="panel room-detail">
            <div className="room-detail-head">
              <div>
                <div className="eyebrow">
                  {selected.id} / {selected.fleet}
                </div>
                <h2>{selected.title}</h2>
                <p>
                  Submitted by {selected.agent} · {selected.time}
                </p>
              </div>
              <div ref={roomMenuRef} style={{ position: "relative" }}>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Room options"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRoomMenuOpen(!roomMenuOpen);
                  }}
                >
                  <MoreHorizontal size={18} />
                </button>
                {roomMenuOpen && (
                  <div
                    className="dropdown-menu"
                    style={{
                      position: "absolute",
                      right: 0,
                      top: "100%",
                      marginTop: 4,
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
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div style={{ padding: "4px 8px", fontSize: 10, fontWeight: 700, color: "#60746f" }}>
                      DECISION ACTIONS
                    </div>
                    <button
                      type="button"
                      className="dropdown-item"
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#195d56", fontWeight: 600, border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                      onClick={() => {
                        setRoomMenuOpen(false);
                        onViewTranscript(selected);
                      }}
                    >
                      <FileText size={14} />
                      <span>View audit transcript</span>
                    </button>
                    <button
                      type="button"
                      className="dropdown-item"
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                      onClick={() => {
                        setRoomMenuOpen(false);
                        onOpenSource(selected);
                      }}
                    >
                      <FileCheck2 size={14} />
                      <span>Open source evidence</span>
                    </button>
                    <button
                      type="button"
                      className="dropdown-item"
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", fontSize: 11.5, color: "#3b5f53", border: 0, background: "transparent", cursor: "pointer", width: "100%", textAlign: "left", borderRadius: 4 }}
                      onClick={() => {
                        setRoomMenuOpen(false);
                        const blob = new Blob([JSON.stringify(selected, null, 2)], { type: "application/json" });
                        const a = document.createElement("a");
                        a.href = URL.createObjectURL(blob);
                        a.download = `room-${selected.id}.json`;
                        a.click();
                      }}
                    >
                      <Database size={14} />
                      <span>Download room JSON</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="evidence-banner">
              <i
                className={`room-icon room-icon--${selected.verdict.toLowerCase().replaceAll("_", "-")}`}
              >
                <BadgeCheck size={17} />
              </i>
              <span>
                <strong>{selected.verdict.replaceAll("_", " ")}</strong>
                <small>{selected.summary}</small>
              </span>
              <button className="link-button" onClick={() => onViewTranscript(selected)}>
                View transcript <ArrowRight size={13} />
              </button>
            </div>
            <div className="evidence-columns">
              <div>
                <div className="detail-label">EPISTEMIC BASIS</div>
                <Badge tone="blue">{selected.basis}</Badge>
                <p>
                  Agent interpretation supported by source material. Human judgment is required for
                  disposition.
                </p>
              </div>
              <div>
                <div className="detail-label">ASSURANCE VERDICT</div>
                <Badge
                  tone={
                    selected.verdict === "EVIDENCE_FOUND"
                      ? "green"
                      : selected.verdict === "POLICY_BLOCKED"
                      ? "red"
                      : "orange"
                  }
                >
                  {selected.verdict.replaceAll("_", " ")}
                </Badge>
                <p>Transcript and trace correlation is attached to this decision record.</p>
              </div>
            </div>
            <div className="source-record">
              <div>
                <span>
                  <FileCheck2 size={15} /> Source evidence
                </span>
                <button className="link-button" onClick={() => onOpenSource(selected)}>
                  Open source <ArrowUpRight size={13} />
                </button>
              </div>
              <blockquote>
                {selected.evidence && typeof selected.evidence.quote === "string"
                  ? `“${selected.evidence.quote}”`
                  : selected.summary
                  ? `“${selected.summary}”`
                  : "“Security log evidence extracted and verified under local sovereign policy. Ready for human disposition.”"}
              </blockquote>
              <small>
                {(selected.evidence &&
                  typeof selected.evidence.path === "string" &&
                  selected.evidence.path) ||
                  selected.fleet ||
                  "sovereign/audit-trace"}{" "}
                <i>·</i> Correlated trace <b>{`trc_${selected.id.slice(-6)}`}</b>
              </small>
            </div>
            {selected.status === "Pending" ? (
              <div className="decision-actions">
                <span>
                  <Clock3 size={14} /> Decision is recorded to the signed audit trail.
                </span>
                <div>
                  <button
                    className="secondary-button"
                    onClick={() => onResolve(selected, "Returned")}
                  >
                    Return for evidence
                  </button>
                  <button
                    className="primary-button"
                    onClick={() => onResolve(selected, "Approved")}
                  >
                    <Check size={15} /> Record disposition
                  </button>
                </div>
              </div>
            ) : (
              <div className="decision-recorded">
                <CheckCircle2 size={16} />{" "}
                {selected.status === "Approved"
                  ? "Disposition recorded and signed."
                  : "Returned for additional evidence."}
              </div>
            )}
          </section>
        ) : (
          <section className="panel empty-state">
            <CheckCircle2 />
            <h3>Queue clear</h3>
            <p>No rooms await disposition.</p>
          </section>
        )}
      </div>
    )}
    </>
  );
}

export function DecisionOutputPanel({
  room,
  onOpenOutputs,
}: {
  room: Room;
  onOpenOutputs?: () => void;
}) {
  const [recipient, setRecipient] = useState("");
  const [schema, setSchema] = useState<{
    title: string;
    required: string[];
    properties: Record<
      string,
      { type?: string; enum?: string[]; title?: string; maxLength?: number }
    >;
  } | null>(null);
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
      setValues(
        Object.fromEntries(
          Object.keys(result.properties).map((key) => [key, values[key] ?? ""])
        )
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load the form schema.");
    } finally {
      setBusy(false);
    }
  }

  async function submitForm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await postJson(`/api/v1/rooms/${room.id}/form-response`, {
        method: "POST",
        body: JSON.stringify({ values }),
      });
      setMessage("Structured output dispatched.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Structured output dispatch failed.");
    } finally {
      setBusy(false);
    }
  }

  async function sendEmail() {
    setBusy(true);
    setMessage("");
    try {
      await postJson("/api/v1/outputs/email", {
        method: "POST",
        body: JSON.stringify({
          room_id: room.id,
          recipient,
          subject: `Fleet Studio decision: ${room.title}`,
        }),
      });
      setMessage("Governance email sent with redacted evidence references.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Governance email dispatch failed.");
    } finally {
      setBusy(false);
    }
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
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "11px",
              }}
            >
              <FileText size={13} /> Fleet outputs
            </button>
          )}
          <Badge tone={approved ? "green" : "neutral"}>
            {approved ? "APPROVED ROOM" : "WAITING FOR APPROVAL"}
          </Badge>
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
              <input
                type="email"
                value={recipient}
                onChange={(event) => setRecipient(event.target.value)}
                placeholder="approver@example.org"
              />
            </label>
            <button
              className="primary-button"
              onClick={() => void sendEmail()}
              disabled={busy || !recipient}
            >
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
                      <select
                        required={schema.required.includes(key)}
                        value={values[key] ?? ""}
                        onChange={(event) =>
                          setValues((current) => ({ ...current, [key]: event.target.value }))
                        }
                      >
                        <option value="">Choose…</option>
                        {property.enum.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <textarea
                        required={schema.required.includes(key)}
                        maxLength={property.maxLength}
                        value={values[key] ?? ""}
                        onChange={(event) =>
                          setValues((current) => ({ ...current, [key]: event.target.value }))
                        }
                        rows={2}
                      />
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
            <LockKeyhole size={15} /> Outputs unlock after a human Approver or Compliance Officer
            records a disposition.
          </p>
          <div
            style={{
              padding: "14px 16px",
              background: "rgba(35, 111, 102, 0.08)",
              border: "1px solid rgba(35, 111, 102, 0.3)",
              borderRadius: "6px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "10px",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <strong
                style={{
                  fontSize: "12px",
                  color: "#195d56",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Sparkles size={14} /> Mission Deliverable Ready for Review
              </strong>
              <small style={{ color: "#546862", fontSize: "11px" }}>
                All generated mission artifacts, proposals, and investigation reports are accessible
                in Fleet outputs.
              </small>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              {onOpenOutputs && (
                <button
                  className="primary-button"
                  onClick={onOpenOutputs}
                  style={{
                    fontSize: "11px",
                    padding: "6px 12px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <FileText size={13} /> View in Fleet outputs
                </button>
              )}
              <a
                href="http://localhost:8001/proposal"
                target="_blank"
                rel="noopener noreferrer"
                className="secondary-button"
                style={{
                  fontSize: "11px",
                  padding: "6px 10px",
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                }}
              >
                <ExternalLink size={12} /> External Portal
              </a>
            </div>
          </div>
        </div>
      )}
      {message && (
        <div className="output-message" role="status">
          {message}
        </div>
      )}
    </section>
  );
}

export function DistilledSkillsQueue() {
  const [candidates, setCandidates] = useState<DistilledSkillCandidate[]>([]);
  const [approvedSkills, setApprovedSkills] = useState<DistilledSkillCandidate[]>([]);
  const [filter, setFilter] = useState<"pending" | "approved">("pending");
  const [loading, setLoading] = useState(false);
  const [actingSkill, setActingSkill] = useState<string | null>(null);
  const [inspectedCode, setInspectedCode] = useState<{ name: string; code: string } | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [pending, approved] = await Promise.all([
        fetchPendingDistilledSkills(),
        fetchApprovedDistilledSkills(),
      ]);
      setCandidates(pending);
      setApprovedSkills(approved);
    } catch {
      // fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleApprove(name: string) {
    setActingSkill(name);
    try {
      await approveDistilledSkill(name);
      setToast({ type: "success", text: `Skill "${name}" approved and promoted into active tools.` });
      await loadData();
    } catch (e: unknown) {
      setToast({ type: "error", text: `Failed to approve skill: ${String(e)}` });
    } finally {
      setActingSkill(null);
    }
  }

  async function handleReject(name: string) {
    setActingSkill(name);
    try {
      await rejectDistilledSkill(name, "Rejected in governance review");
      setToast({ type: "success", text: `Candidate skill "${name}" rejected.` });
      await loadData();
    } catch (e: unknown) {
      setToast({ type: "error", text: `Failed to reject skill: ${String(e)}` });
    } finally {
      setActingSkill(null);
    }
  }

  const items = filter === "pending" ? candidates : approvedSkills;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
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

      {/* Control Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            className={filter === "pending" ? "primary-button" : "secondary-button"}
            style={{ fontSize: "12px", padding: "6px 14px" }}
            onClick={() => setFilter("pending")}
          >
            Awaiting Approval ({candidates.length})
          </button>
          <button
            type="button"
            className={filter === "approved" ? "primary-button" : "secondary-button"}
            style={{ fontSize: "12px", padding: "6px 14px" }}
            onClick={() => setFilter("approved")}
          >
            Approved &amp; Active ({approvedSkills.length})
          </button>
        </div>

        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadData()}
          disabled={loading}
          style={{ fontSize: "11px", padding: "6px 12px" }}
        >
          <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh queue
        </button>
      </div>

      {/* Candidate List */}
      {items.length === 0 ? (
        <section className="panel empty-state" style={{ padding: "40px 20px", textAlign: "center" }}>
          <Sparkles size={36} color="#236f66" style={{ margin: "0 auto 12px" }} />
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#163a33" }}>
            {filter === "pending" ? "No skills awaiting operator review" : "No approved distilled skills yet"}
          </h3>
          <p style={{ fontSize: "12px", color: "#6a7c76", maxWidth: "420px", margin: "4px auto 0" }}>
            {filter === "pending"
              ? "Autonomous workflows synthesize repeatable multi-step skills upon achieving high verification scores. Newly distilled capabilities will appear here for operator sign-off."
              : "Skills approved here are dynamically hot-loaded into the Hermes profile tool registry for subsequent missions."}
          </p>
        </section>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "14px" }}>
          {items.map((skill) => (
            <div
              key={skill.id || skill.name}
              style={{
                background: "#ffffff",
                border: "1px solid #dce8e2",
                borderRadius: "8px",
                padding: "18px 20px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
                boxShadow: "0 1px 3px rgba(18, 36, 32, 0.04)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", color: "#6a7c76" }}>
                    AUTONOMOUS SYNTHESIS · {skill.status.toUpperCase()}
                  </div>
                  <h4 style={{ fontSize: "15px", fontWeight: 700, color: "#163a33", margin: "3px 0 0" }}>
                    {skill.name}
                  </h4>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  {skill.supervisor_score !== undefined && (
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        background: skill.supervisor_score >= 0.8 ? "#e4f3ed" : "#fff8e6",
                        color: skill.supervisor_score >= 0.8 ? "#195d56" : "#b27810",
                        padding: "3px 8px",
                        borderRadius: "4px",
                      }}
                    >
                      {Math.round(skill.supervisor_score * 100)}% Quality
                    </span>
                  )}
                  {skill.tool_trace_len !== undefined && (
                    <span style={{ fontSize: "10px", fontWeight: 600, background: "#f0f5f2", color: "#4f655e", padding: "3px 8px", borderRadius: "4px" }}>
                      {skill.tool_trace_len} Steps
                    </span>
                  )}
                </div>
              </div>

              <div style={{ fontSize: "12px", color: "#365148", lineHeight: "1.5" }}>
                {skill.description || skill.goal}
              </div>

              {skill.skills_provided && skill.skills_provided.length > 0 && (
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {skill.skills_provided.map((s, idx) => (
                    <span key={idx} style={{ fontSize: "10px", background: "#edf4f1", color: "#236f66", padding: "2px 7px", borderRadius: "3px", fontWeight: 600 }}>
                      {s}
                    </span>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", paddingTop: "12px", borderTop: "1px solid #eef3f1" }}>
                <span style={{ fontSize: "10px", color: "#8a9e96" }}>
                  {skill.created_at ? new Date(skill.created_at).toLocaleString() : "Recently distilled"}
                </span>

                <div style={{ display: "flex", gap: "6px" }}>
                  {skill.code_preview && (
                    <button
                      type="button"
                      className="secondary-button"
                      style={{ fontSize: "11px", padding: "4px 8px" }}
                      onClick={() => setInspectedCode({ name: skill.name, code: skill.code_preview || "" })}
                    >
                      <Code2 size={12} /> Inspect
                    </button>
                  )}
                  {filter === "pending" && (
                    <>
                      <button
                        type="button"
                        className="secondary-button"
                        style={{ fontSize: "11px", padding: "4px 10px", color: "#b44426" }}
                        disabled={actingSkill === skill.name}
                        onClick={() => void handleReject(skill.name)}
                      >
                        <ThumbsDown size={12} /> Reject
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        style={{ fontSize: "11px", padding: "4px 12px" }}
                        disabled={actingSkill === skill.name}
                        onClick={() => void handleApprove(skill.name)}
                      >
                        {actingSkill === skill.name ? <RefreshCw size={12} className="spin" /> : <ThumbsUp size={12} />} Approve
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Code Inspection Modal */}
      {inspectedCode && (
        <div className="modal-shade" onClick={() => setInspectedCode(null)}>
          <div className="modal-card" style={{ maxWidth: "700px" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <div className="eyebrow">DISTILLED SKILL IMPLEMENTATION</div>
                <h3>{inspectedCode.name}</h3>
              </div>
              <button className="icon-button" onClick={() => setInspectedCode(null)}><X size={16} /></button>
            </div>
            <pre
              style={{
                background: "#162724",
                color: "#d9ede6",
                padding: "16px",
                borderRadius: "6px",
                fontSize: "11px",
                fontFamily: "var(--font-geist-mono), monospace",
                maxHeight: "400px",
                overflowY: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {inspectedCode.code}
            </pre>
            <div className="wizard-foot" style={{ marginTop: "14px" }}>
              <button className="plain-button" onClick={() => setInspectedCode(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
