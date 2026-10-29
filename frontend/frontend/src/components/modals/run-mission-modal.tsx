"use client";

import React, { useEffect, useRef, useState } from "react";
import { BadgeCheck, CheckCircle2, FileText, Folder, Play, RefreshCw, X } from "lucide-react";
import { MissionRecord } from "@/lib/types";

export function RunMissionModal({
  mission,
  onClose,
  onExecute,
  isExecuting,
}: {
  mission: MissionRecord;
  onClose: () => void;
  onExecute: (params: { targetPath?: string; files?: File[] }) => Promise<void>;
  isExecuting: boolean;
}) {
  const defaultPath =
    (mission.clarification_answers?.["source-log-path"] as string) ||
    (mission.clarification_answers?.["target_path"] as string) ||
    (mission.goal?.match(/([a-zA-Z]:\\[^\s"'\n]+)/)?.[0] ?? "") ||
    (typeof window !== "undefined"
      ? localStorage.getItem("agenthub_last_target_path") ?? ""
      : "");

  const [targetPath, setTargetPath] = useState<string>(defaultPath);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!targetPath && typeof window !== "undefined") {
      const cached = localStorage.getItem("agenthub_last_target_path");
      if (cached) setTargetPath(cached);
    }
  }, [targetPath]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files).filter(
        (f) => !f.name.startsWith(".") && f.name !== "desktop.ini" && f.name !== "Thumbs.db"
      );
      setSelectedFiles(files);
    }
  }

  function handleFolderChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files).filter(
        (f) => !f.name.startsWith(".") && f.name !== "desktop.ini" && f.name !== "Thumbs.db"
      );
      setSelectedFiles(files);
    }
  }

  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        className="wizard"
        style={{ maxWidth: "620px", width: "95%" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-mission-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="wizard-head">
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <Play size={13} color="#236f66" /> DISPATCH FLEET EXECUTION
          </span>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <h2
          id="run-mission-title"
          style={{ fontSize: "17px", margin: "6px 0 2px", color: "#162f29" }}
        >
          {mission.name}
        </h2>
        <p className="wizard-desc" style={{ marginBottom: "16px" }}>
          Configure target directory or attach files/folder. Attaching files is completely optional.
        </p>

        {targetPath && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "#e8f5f1",
              padding: "7px 12px",
              borderRadius: "5px",
              fontSize: "11px",
              color: "#195d56",
              marginBottom: "10px",
              border: "1px solid #c2e2d8",
            }}
          >
            <CheckCircle2 size={14} color="#236f66" />
            <span>Target path auto-loaded. No need to re-type or re-upload files.</span>
          </div>
        )}

        <div
          className="wizard-fields"
          style={{ display: "flex", flexDirection: "column", gap: "14px" }}
        >
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "6px",
              fontSize: "11px",
              fontWeight: 700,
              color: "#253b35",
            }}
          >
            <span>Target directory or local path (Optional)</span>
            <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
              <input
                type="text"
                value={targetPath}
                onChange={(e) => {
                  setTargetPath(e.target.value);
                  if (typeof window !== "undefined") {
                    if (e.target.value) {
                      localStorage.setItem("agenthub_last_target_path", e.target.value);
                    } else {
                      localStorage.removeItem("agenthub_last_target_path");
                    }
                  }
                }}
                placeholder="e.g. D:\Security-logs-test\attack-cases-benchmark\case-4-k8s-linux-container-breakout\raw-logs"
                style={{
                  flex: 1,
                  padding: "8px 32px 8px 12px",
                  fontSize: "11px",
                  border: "1px solid #c9d8d1",
                  borderRadius: "5px",
                  background: "#ffffff",
                  color: "#162a26",
                  outline: "none",
                  fontFamily: "var(--font-geist-mono), monospace",
                  width: "100%",
                }}
              />
              {targetPath && (
                <button
                  type="button"
                  aria-label="Clear path"
                  onClick={() => {
                    setTargetPath("");
                    if (typeof window !== "undefined") {
                      localStorage.removeItem("agenthub_last_target_path");
                    }
                  }}
                  style={{
                    position: "absolute",
                    right: "8px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: "2px",
                    display: "flex",
                    alignItems: "center",
                    color: "#8a9e97",
                    lineHeight: 1,
                  }}
                >
                  <X size={13} />
                </button>
              )}
            </div>
            <small style={{ color: "#6a7c76", fontWeight: 400, fontSize: "10px" }}>
              Specialist agents will inspect this local directory path directly using terminal tools.
            </small>
          </label>

          <div
            style={{
              background: "#f8faf9",
              border: "1px solid #dce8e2",
              borderRadius: "6px",
              padding: "12px 14px",
            }}
          >
            <span
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 700,
                color: "#253b35",
                marginBottom: "8px",
              }}
            >
              Attach files or folder (Optional)
            </span>

            <input
              type="file"
              ref={fileInputRef}
              multiple
              accept=".log,.txt,.json,.csv,.audit,.evtx,.xml,.yaml,.yml,.conf,.cfg,.sh,.py,.md,.docx,.pdf,.raw,.pcap,text/*"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />

            <input
              type="file"
              ref={folderInputRef}
              // @ts-expect-error folder directory attributes
              webkitdirectory=""
              directory=""
              style={{ display: "none" }}
              onChange={handleFolderChange}
            />

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <button
                type="button"
                className="secondary-button"
                style={{
                  fontSize: "11px",
                  padding: "6px 12px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <FileText size={13} color="#236f66" /> Select Log / Text Files
              </button>

              <button
                type="button"
                className="secondary-button"
                style={{
                  fontSize: "11px",
                  padding: "6px 12px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                }}
                onClick={() => folderInputRef.current?.click()}
              >
                <Folder size={13} color="#236f66" /> Select Entire Folder
              </button>

              {selectedFiles.length > 0 && (
                <button
                  type="button"
                  style={{
                    border: 0,
                    background: "transparent",
                    color: "#a84e22",
                    fontSize: "11px",
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                  onClick={() => setSelectedFiles([])}
                >
                  Clear files ({selectedFiles.length})
                </button>
              )}
            </div>

            {selectedFiles.length > 0 ? (
              <div
                style={{
                  marginTop: "10px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                }}
              >
                {selectedFiles.map((f, idx) => {
                  const isZero = f.size === 0;
                  return (
                    <div
                      key={idx}
                      style={{
                        background: isZero ? "#fdf2f2" : "#ffffff",
                        border: isZero ? "1px solid #f5c2c7" : "1px solid #cce0d8",
                        borderRadius: "4px",
                        padding: "6px 10px",
                        fontSize: "11px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        color: isZero ? "#842029" : "#195d56",
                      }}
                    >
                      <span style={{ fontWeight: 600 }}>{f.name}</span>
                      <span
                        style={{
                          fontSize: "10px",
                          color: isZero ? "#dc3545" : "#557a70",
                          fontWeight: isZero ? 700 : 400,
                        }}
                      >
                        {isZero
                          ? "⚠️ 0 BYTES (EMPTY FILE ON DISK)"
                          : `${(f.size / 1024).toFixed(1)} KB (${f.size.toLocaleString()} bytes)`}
                      </span>
                    </div>
                  );
                })}
                {selectedFiles.some((f) => f.size === 0) && (
                  <p
                    style={{
                      margin: "2px 0 0",
                      color: "#dc3545",
                      fontSize: "10.5px",
                      fontWeight: 600,
                    }}
                  >
                    ⚠️ Your selected file has 0 bytes on disk. If it is open in Microsoft Word,
                    please press <strong>Ctrl+S</strong> to save it, or choose a document with saved
                    content.
                  </p>
                )}
              </div>
            ) : (
              <div style={{ marginTop: "6px", fontSize: "10px", color: "#778a84" }}>
                Accepts all log &amp; text formats: .log, .txt, .json, .evtx, .audit, .csv, .xml,
                .yaml, .conf, .md, .docx, or an entire directory.
              </div>
            )}
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "#f2f7f4",
              padding: "8px 12px",
              borderRadius: "5px",
              border: "1px solid #dbe8e1",
            }}
          >
            <BadgeCheck size={14} color="#236f66" />
            <span style={{ fontSize: "10.5px", color: "#23554b" }}>
              Execution runs on AgentHub host runtime. Human gates pause in{" "}
              <strong>Decision rooms</strong> for sign-off.
            </span>
          </div>
        </div>

        <div
          className="wizard-foot"
          style={{
            marginTop: "18px",
            display: "flex",
            justifyContent: "flex-end",
            gap: "8px",
          }}
        >
          <button
            type="button"
            className="plain-button"
            onClick={onClose}
            disabled={isExecuting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="primary-button"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 16px",
            }}
            onClick={() => void onExecute({ targetPath, files: selectedFiles })}
            disabled={
              isExecuting ||
              (selectedFiles.length > 0 && selectedFiles.every((f) => f.size === 0))
            }
          >
            {isExecuting ? (
              <>
                <RefreshCw size={13} className="spin" /> Dispatching...
              </>
            ) : selectedFiles.length > 0 && selectedFiles.every((f) => f.size === 0) ? (
              "File(s) 0 bytes (Empty)"
            ) : (
              <>
                <Play size={13} /> Run Fleet Now
              </>
            )}
          </button>
        </div>
      </section>
    </div>
  );
}
