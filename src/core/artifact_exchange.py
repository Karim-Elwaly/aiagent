"""
Workflow Artifact Exchange

Provides file-backed structured artifact storage for intermediate and source task outputs.
Eliminates context-window truncation cliffs by allowing upstream tasks (e.g. Ingestion,
Extraction, Analysis) to store complete, lossless tables, matrices, and documents on disk,
and passing concise executive summaries alongside exact file-path pointers to downstream tasks.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = ROOT_DIR / "data" / "artifacts"


class WorkflowArtifactExchange:
    """Manages file-backed artifacts for a specific workflow execution."""

    def __init__(self, workflow_id: str, base_dir: Path | None = None):
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "-", workflow_id).strip("-") or "default"
        self.workflow_id = clean_id
        self.base_dir = (base_dir or ARTIFACTS_ROOT) / self.workflow_id
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_task_artifact(
        self,
        task_id: str,
        payload: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Save a completed task's output to disk losslessly."""
        clean_task_id = re.sub(r"[^a-zA-Z0-9_-]", "-", task_id).strip("-") or "task"
        out_file = self.base_dir / f"{clean_task_id}_payload.md"
        out_file.write_text(payload or "", encoding="utf-8")

        # If payload contains a JSON block or if metadata is provided, write structured json
        meta = metadata or {}
        json_file = self.base_dir / f"{clean_task_id}_payload.json"
        
        extracted_json = None
        if "```json" in payload:
            try:
                raw_json = payload.split("```json")[1].split("```")[0].strip()
                extracted_json = json.loads(raw_json)
            except Exception:
                extracted_json = None
        elif payload.strip().startswith("{") and payload.strip().endswith("}"):
            try:
                extracted_json = json.loads(payload.strip())
            except Exception:
                extracted_json = None

        if extracted_json is not None or meta:
            save_dict = {
                "task_id": task_id,
                "workflow_id": self.workflow_id,
                "size_bytes": out_file.stat().st_size,
                "metadata": meta,
                "structured_data": extracted_json,
            }
            try:
                json_file.write_text(json.dumps(save_dict, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.debug("Could not write json artifact for %s: %s", task_id, e)

        logger.info(
            "Saved task artifact for '%s' (%d bytes) at %s",
            task_id, out_file.stat().st_size, out_file,
        )
        return out_file

    def save_source_document(
        self,
        filename: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Store complete raw text extracted from uploaded Word (.docx), PDF, or text files."""
        clean_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename).strip("_") or "source_document.txt"
        doc_file = self.base_dir / f"source_{clean_filename}"
        doc_file.write_text(content or "", encoding="utf-8")

        if metadata:
            meta_file = self.base_dir / f"source_{clean_filename}.meta.json"
            try:
                meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.debug("Could not write source doc meta for %s: %s", filename, e)

        logger.info("Saved source document '%s' (%d chars) at %s", filename, len(content), doc_file)
        return doc_file

    def get_artifact_pointer(self, task_id: str) -> dict[str, Any] | None:
        """Return path and size metadata for a saved task artifact."""
        clean_task_id = re.sub(r"[^a-zA-Z0-9_-]", "-", task_id).strip("-") or "task"
        out_file = self.base_dir / f"{clean_task_id}_payload.md"
        json_file = self.base_dir / f"{clean_task_id}_payload.json"
        if not out_file.exists():
            return None

        return {
            "task_id": task_id,
            "path": str(out_file.resolve()),
            "size_bytes": out_file.stat().st_size,
            "has_json": json_file.exists(),
            "json_path": str(json_file.resolve()) if json_file.exists() else None,
        }

    def read_task_artifact(self, task_id: str) -> str:
        """Read full payload of a task artifact from disk."""
        pointer = self.get_artifact_pointer(task_id)
        if not pointer or not pointer.get("path"):
            return ""
        try:
            return Path(pointer["path"]).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Could not read artifact for %s: %s", task_id, e)
            return ""

    def list_artifacts(self) -> list[dict[str, Any]]:
        """List all saved artifacts in this workflow repository."""
        if not self.base_dir.is_dir():
            return []
        items = []
        for p in self.base_dir.glob("*_payload.md"):
            tid = p.name.replace("_payload.md", "")
            items.append({
                "task_id": tid,
                "path": str(p.resolve()),
                "size_bytes": p.stat().st_size,
            })
        return items


def get_artifact_exchange(workflow_id: str) -> WorkflowArtifactExchange:
    """Convenience factory returning a WorkflowArtifactExchange instance."""
    return WorkflowArtifactExchange(workflow_id)
