"""
Unit tests for WorkflowArtifactExchange: saving, retrieval, structured payload detection, and document staging.
"""

import shutil
import tempfile
from pathlib import Path

from src.core.artifact_exchange import WorkflowArtifactExchange


def test_artifact_exchange_lifecycle():
    temp_dir = Path(tempfile.mkdtemp(prefix="test_artifacts_"))
    try:
        wf_id = "test-wf-123"
        exchange = WorkflowArtifactExchange(wf_id, base_dir=temp_dir)

        # 1. Save task artifact with markdown and embedded JSON
        payload = (
            "# Task Report\n\n"
            "Here are the findings:\n"
            "```json\n"
            "{\"status\": \"success\", \"rows_processed\": 450, \"total_cost\": 12500}\n"
            "```\n"
        )
        task_path = exchange.save_task_artifact("t1", payload, metadata={"agent": "ingestion-agent"})

        assert task_path.exists()
        assert task_path.name == "t1_payload.md"

        # Check structured JSON was automatically created
        json_file = task_path.parent / "t1_payload.json"
        assert json_file.exists()

        # Check pointer
        pointer = exchange.get_artifact_pointer("t1")
        assert pointer is not None
        assert pointer["task_id"] == "t1"
        assert pointer["has_json"] is True
        assert pointer["size_bytes"] > 0

        # Read artifact back
        read_back = exchange.read_task_artifact("t1")
        assert "rows_processed" in read_back

        # 2. Save source document
        source_content = "Clause 1: The vendor must provide 99.9% uptime.\nClause 2: Billing is monthly."
        doc_path = exchange.save_source_document("rfp_spec.docx", source_content, metadata={"char_count": len(source_content)})
        assert doc_path.exists()
        assert "source_rfp_spec.docx" in doc_path.name
        assert doc_path.read_text(encoding="utf-8") == source_content

        # 3. List artifacts
        artifacts = exchange.list_artifacts()
        assert len(artifacts) >= 1
        assert any(a["task_id"] == "t1" for a in artifacts)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
