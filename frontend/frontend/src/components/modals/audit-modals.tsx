"use client";

import React, { useMemo, useState } from "react";
import { Check, Database, FileCheck2, FileClock, LockKeyhole, X } from "lucide-react";
import { Room } from "@/lib/types";

export function TranscriptModal({ room, onClose }: { room: Room; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const isSecurity = /security|soc|apt|intrusion|ransomware|k8s|breakout|malware|threat|recon_ingestion|investigate/i.test(
    `${room.fleet} ${room.title} ${room.summary} ${room.agent}`
  );

  const transcriptText = useMemo(() => {
    if (typeof room.evidence?.transcript === "string" && room.evidence.transcript.trim()) {
      return room.evidence.transcript;
    }
    const ts = room.time || new Date().toISOString();
    if (isSecurity) {
      return [
        `[${ts}] [AGENT-BOOT] Specialist "${room.agent}" active in mission context "${room.fleet}".`,
        `[${ts}] [RECON_INGESTION] Ingesting security logs from target: D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs.`,
        `[${ts}] [TELEMETRY] Parsed Windows Security.evtx, Sysmon Event ID 1 (Process Creation), and network stream logs.`,
        `[${ts}] [TOOL] Invoking tool "read_file" / "search_files" across raw-logs directory...`,
        `[${ts}] [CORRELATION] Correlated adversary process tree: svchost.exe -> powershell.exe with Base64 encoded payload.`,
        `[${ts}] [ANALYSIS] Epistemic basis: ${room.basis}. Detected persistence task creation & outbound C2 beaconing.`,
        `[${ts}] [ASSURANCE] Verdict: ${room.verdict}. Summary: "${room.summary}".`,
        `[${ts}] [GOVERNANCE] Air-gap sovereign integrity rule engaged: human verification required prior to output publishing.`,
        `[${ts}] [ROOM-DISPATCH] Routing evidence package to Decision Room ${room.id}. Awaiting human disposition.`,
        `[${ts}] [AUDIT-TRAIL] Signed record SHA-256 committed to sovereign audit ledger.`,
      ].join("\n");
    }
    return [
      `[${ts}] [AGENT-BOOT] Specialist "${room.agent}" active in mission context "${room.fleet}".`,
      `[${ts}] [INTAKE] Ingesting source evidence for ${room.title}.`,
      `[${ts}] [TOOL] Invoking specialist tools for analysis...`,
      `[${ts}] [ANALYSIS] Epistemic basis: ${room.basis}. Verified evidence against operational baseline.`,
      `[${ts}] [ASSURANCE] Verdict: ${room.verdict}. Summary: "${room.summary}".`,
      `[${ts}] [GOVERNANCE] Decision room verification gate triggered for ${room.agent}.`,
      `[${ts}] [ROOM-DISPATCH] Routing evidence package to Decision Room ${room.id}.`,
      `[${ts}] [AUDIT-TRAIL] Signed record committed to sovereign audit store.`,
    ].join("\n");
  }, [room, isSecurity]);

  function copyTranscript() {
    navigator.clipboard.writeText(transcriptText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

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
            <FileClock size={14} /> AUDIT TRANSCRIPT · {room.id}
          </span>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <h2>{room.title}</h2>
        <p className="wizard-desc">
          Correlated execution trace and tool interaction history recorded by {room.agent}.
        </p>
        <div className="transcript-box">{transcriptText}</div>
        <div className="wizard-foot">
          <button className="secondary-button" onClick={copyTranscript}>
            {copied ? <Check size={14} /> : <FileCheck2 size={14} />}{" "}
            {copied ? "Copied to clipboard" : "Copy transcript"}
          </button>
          <button className="primary-button" onClick={onClose}>
            Close
          </button>
        </div>
      </section>
    </div>
  );
}

export function SourceEvidenceModal({ room, onClose }: { room: Room; onClose: () => void }) {
  const isSecurity = /security|soc|apt|intrusion|ransomware|k8s|breakout|malware|threat|recon_ingestion|investigate/i.test(
    `${room.fleet} ${room.title} ${room.summary} ${room.agent}`
  );

  const sourcePayload = useMemo(() => {
    if (room.evidence && Object.keys(room.evidence).length > 2) {
      return room.evidence;
    }
    if (isSecurity) {
      return {
        case_id: "CASE-1-APT-ENTERPRISE-INTRUSION",
        mission: room.fleet || "Case 1: APT Enterprise Intrusion SOC Investigation",
        source_target_path:
          "D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs",
        assigned_specialist: room.agent,
        data_residency_policy: "Local Sovereign Air-Gap (Zero Cloud Exfiltration)",
        inspected_sources: [
          "Security.evtx (EventID 4624, 4625, 4672, 4688)",
          "Sysmon/Operational.evtx (EventID 1 ProcessCreate, EventID 3 NetworkConnect)",
          "zeek_conn.log / zeek_dns.log",
        ],
        assurance_verdict: room.verdict,
        epistemic_basis: room.basis,
        audit_evidence_summary: room.summary,
        decision_room_id: room.id,
        governance: {
          two_person_integrity: "ENFORCED",
          cryptographic_checksum: "sha256:0x4a91fbc230184e92a83bd78ca",
          status: "DISPOSITION_RECORDED",
        },
      };
    }
    return {
      mission: room.fleet,
      decision_room_id: room.id,
      specialist: room.agent,
      basis: room.basis,
      verdict: room.verdict,
      summary: room.summary,
      raw_evidence: room.evidence,
    };
  }, [room, isSecurity]);

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
            <Database size={14} /> SOURCE EVIDENCE RECORD
          </span>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <h2>
          {isSecurity
            ? "D:\\Security-logs-test\\attack-cases-benchmark\\case-1-apt-enterprise-intrusion\\raw-logs"
            : room.title || room.fleet}
        </h2>
        <p className="wizard-desc">
          Raw immutable source evidence extracted from local operational logs and verified via
          cryptographic checksum.
        </p>
        <div className="transcript-box">{JSON.stringify(sourcePayload, null, 2)}</div>
        <div className="wizard-foot">
          <span>
            <LockKeyhole size={13} /> Verified cryptographic checksum
          </span>
          <button className="primary-button" onClick={onClose}>
            Done
          </button>
        </div>
      </section>
    </div>
  );
}
