"""Unit tests for the agent-facing evidence tools (Phases A3/A5/A6).

Fixtures are synthetic and unrelated to any benchmark dataset.
"""

from __future__ import annotations

import json

import pytest

from src.core.evidence import EvidenceStore
from src.registry.tools import evidence_tools
from src.registry.tools.evidence_tools import (
    EVIDENCE_COVERAGE_SPEC,
    GET_EVIDENCE_SPEC,
    INGEST_LOGS_SPEC,
    QUERY_EVIDENCE_SPEC,
    evidence_coverage_report,
    get_evidence,
    ingest_logs,
    query_evidence,
)


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Route the tools' store lookup at a temporary directory."""
    store = EvidenceStore("tool-test", root=tmp_path / "evidence")
    monkeypatch.setattr(evidence_tools, "get_store", lambda _run_id="": store)
    return store


@pytest.fixture()
def log_dir(tmp_path):
    directory = tmp_path / "logs"
    directory.mkdir()
    rows = [
        {
            "timestamp": f"2031-03-02T08:{i:02d}:00",
            "user": "rlopez" if i % 2 == 0 else "tmehta",
            "source_ip": "198.51.100.4",
            "destination_ip": "203.0.113.9",
            "destination_port": 8443,
            "status": "failure" if i < 3 else "success",
        }
        for i in range(6)
    ]
    (directory / "auth.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    return directory


class TestIngestLogs:
    @pytest.mark.asyncio
    async def test_ingests_all_records(self, isolated_store, log_dir):
        output = await ingest_logs(str(log_dir))

        assert "Log Ingestion Complete" in output
        assert isolated_store.count() == 6

    @pytest.mark.asyncio
    async def test_reports_citation_id_range(self, isolated_store, log_dir):
        output = await ingest_logs(str(log_dir))
        assert "EV-000001" in output

    @pytest.mark.asyncio
    async def test_missing_path_is_explicit_not_silent(self, isolated_store, tmp_path):
        output = await ingest_logs(str(tmp_path / "absent"))

        assert "not found" in output.lower()
        assert isolated_store.count() == 0

    @pytest.mark.asyncio
    async def test_empty_directory(self, isolated_store, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert "No files found" in await ingest_logs(str(empty))

    @pytest.mark.asyncio
    async def test_unmapped_sources_are_flagged(self, isolated_store, tmp_path):
        directory = tmp_path / "odd"
        directory.mkdir()
        (directory / "notes.txt").write_text("free form text\n", encoding="utf-8")

        output = await ingest_logs(str(directory))

        assert "Unmapped sources" in output


class TestQueryEvidence:
    @pytest.mark.asyncio
    async def test_empty_store_directs_to_ingestion(self, isolated_store):
        output = await query_evidence(user="rlopez")
        assert "empty" in output.lower()
        assert "ingest_logs" in output

    @pytest.mark.asyncio
    async def test_filters_and_reports_total(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await query_evidence(user="rlopez")

        assert "Matched **3**" in output

    @pytest.mark.asyncio
    async def test_status_filter(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))
        assert "Matched **3**" in await query_evidence(status="failure")

    @pytest.mark.asyncio
    async def test_pagination_warns_about_partial_results(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await query_evidence(limit=2)

        assert "More results available" in output
        assert "offset=2" in output

    @pytest.mark.asyncio
    async def test_no_match_is_explicit(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await query_evidence(user="nobody")

        assert "Matched **0**" in output

    @pytest.mark.asyncio
    async def test_invalid_pagination_falls_back_to_defaults(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))
        assert "Matched **6**" in await query_evidence(limit="abc", offset="xyz")


class TestGetEvidence:
    @pytest.mark.asyncio
    async def test_returns_verbatim_raw_line(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await get_evidence("EV-000001")

        assert "EV-000001" in output
        assert "rlopez" in output

    @pytest.mark.asyncio
    async def test_accepts_comma_separated_ids(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await get_evidence("EV-000001, EV-000002")

        assert "EV-000001" in output and "EV-000002" in output

    @pytest.mark.asyncio
    async def test_unknown_id_is_reported_as_uncitable(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await get_evidence("EV-999999")

        assert "Not found" in output
        assert "must NOT be cited" in output

    @pytest.mark.asyncio
    async def test_blank_input(self, isolated_store):
        assert "Error" in await get_evidence("   ")


class TestCoverageReport:
    @pytest.mark.asyncio
    async def test_empty_store_states_no_findings_possible(self, isolated_store):
        output = await evidence_coverage_report()

        assert "EMPTY" in output
        assert "ingest_logs" in output

    @pytest.mark.asyncio
    async def test_counts_are_authoritative(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await evidence_coverage_report()

        assert "Total events ingested: **6**" in output
        assert "authoritative" in output.lower()

    @pytest.mark.asyncio
    async def test_reports_time_span_and_entities(self, isolated_store, log_dir):
        await ingest_logs(str(log_dir))

        output = await evidence_coverage_report()

        assert "2031-03-02T08:00:00" in output
        assert "Distinct users/accounts: 2" in output


class TestToolSpecs:
    @pytest.mark.parametrize(
        "spec",
        [INGEST_LOGS_SPEC, QUERY_EVIDENCE_SPEC, GET_EVIDENCE_SPEC, EVIDENCE_COVERAGE_SPEC],
    )
    def test_declare_run_context(self, spec):
        """Without this flag the tools cannot reach the run's evidence store."""
        assert spec.needs_run_context is True

    @pytest.mark.parametrize(
        "spec",
        [INGEST_LOGS_SPEC, QUERY_EVIDENCE_SPEC, GET_EVIDENCE_SPEC, EVIDENCE_COVERAGE_SPEC],
    )
    def test_run_id_is_not_an_llm_visible_parameter(self, spec):
        assert "_run_id" not in spec.parameters

    @pytest.mark.parametrize(
        "spec",
        [INGEST_LOGS_SPEC, QUERY_EVIDENCE_SPEC, GET_EVIDENCE_SPEC, EVIDENCE_COVERAGE_SPEC],
    )
    def test_returns_text_for_react_loop(self, spec):
        assert spec.skills_provided
        assert spec.name
