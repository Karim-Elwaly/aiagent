"""Unit tests for universal log ingestion (Phase A3).

All fixtures are synthetic and independently authored: documentation-range
addresses (RFC 5737 / RFC 1918) with values unrelated to any benchmark
dataset, invented account names, and future-dated timestamps. They exercise
*format and mapping behaviour*, not any particular incident.
"""

from __future__ import annotations

import json

import pytest

from src.registry.ingestion import (
    LogMapping,
    build_event,
    detect_format,
    discover_log_files,
    ingest_file,
    load_mappings,
    select_mapping,
)


@pytest.fixture(scope="module")
def shipped_mappings():
    mappings = load_mappings()
    assert mappings, "shipped YAML mappings should load"
    return mappings


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestFormatDetection:
    def test_json_array(self, tmp_path):
        path = _write(tmp_path, "a.json", '[{"timestamp": "2031-03-02T08:00:00"}]')
        assert detect_format(path) == "json"

    def test_jsonl(self, tmp_path):
        path = _write(tmp_path, "a.log", '{"a": 1}\n{"a": 2}\n')
        assert detect_format(path) == "jsonl"

    def test_csv(self, tmp_path):
        path = _write(tmp_path, "a.csv", "time,src,dst,bytes\n2031-03-02,198.51.100.4,203.0.113.9,10\n")
        assert detect_format(path) == "csv"

    def test_xml(self, tmp_path):
        path = _write(tmp_path, "a.xml", "<Events><Event><EventID>1</EventID></Event></Events>")
        assert detect_format(path) == "xml"

    def test_syslog(self, tmp_path):
        path = _write(tmp_path, "a.log", "Mar  2 2031 08:00:00 gw : %XYZ-6-100001: something happened\n")
        assert detect_format(path) == "syslog"

    def test_plain_text_fallback(self, tmp_path):
        path = _write(tmp_path, "a.log", "just some free-form notes\nanother line\n")
        assert detect_format(path) == "text"

    def test_empty_file(self, tmp_path):
        assert detect_format(_write(tmp_path, "a.log", "")) == "text"


class TestGenericIngestion:
    def test_jsonl_fields_are_mapped(self, tmp_path, shipped_mappings):
        rows = [
            {
                "timestamp": "2031-03-02T08:00:00Z",
                "user": "rlopez",
                "source_ip": "198.51.100.4",
                "destination_ip": "203.0.113.9",
                "destination_port": 8443,
                "status": "success",
            }
        ]
        path = _write(tmp_path, "events.jsonl", "\n".join(json.dumps(r) for r in rows))

        events, result = ingest_file(path, shipped_mappings)

        assert result.event_count == 1
        event = events[0]
        assert event.user == "rlopez"
        assert event.src_ip == "198.51.100.4"
        assert event.dst_port == 8443
        assert event.timestamp.startswith("2031-03-02T08:00:00")

    def test_csv_with_header(self, tmp_path, shipped_mappings):
        path = _write(
            tmp_path,
            "flows.csv",
            "timestamp,src_ip,dst_ip,dst_port,bytes_sent\n"
            "2031-03-02T08:00:00,198.51.100.4,203.0.113.9,443,512\n"
            "2031-03-02T08:01:00,198.51.100.4,203.0.113.9,443,518\n",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.event_count == 2
        assert events[0].bytes_sent == 512
        assert events[1].dst_port == 443

    def test_json_envelope_is_unwrapped(self, tmp_path, shipped_mappings):
        doc = {"value": [{"timestamp": "2031-03-02T08:00:00", "user": "rlopez"}]}
        path = _write(tmp_path, "export.json", json.dumps(doc))

        events, _ = ingest_file(path, shipped_mappings)

        assert len(events) == 1
        assert events[0].user == "rlopez"

    def test_csv_comment_lines_are_not_evidence(self, tmp_path, shipped_mappings):
        """CSV exports start with ``#`` banner lines; those are documentation.

        Regression: comment lines were ingested as records (28 junk events in
        one corpus), inflating authoritative counts and polluting citations.
        """
        path = _write(
            tmp_path,
            "flows.csv",
            "# Export banner\n"
            "# Generated for review\n"
            "timestamp,src_ip,dst_ip,dst_port,bytes_sent\n"
            "2031-03-02T08:00:00,198.51.100.4,203.0.113.9,443,512\n",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.event_count == 1
        assert events[0].src_ip == "198.51.100.4"

    def test_csv_with_syslog_prefix_and_declared_columns(self, tmp_path):
        """Syslog-wrapped headerless CSV parses via mapping-declared columns.

        The mechanism is generic: any vendor whose exporter prepends a syslog
        header and omits the header row is handled by ``line_prefix_pattern``
        plus ``columns`` in its mapping — no code change required.
        """
        mapping = LogMapping.from_dict(
            {
                "id": "vendor_csv",
                "format": "csv",
                "match": {"filename_patterns": ["*flows*.log"]},
                "line_prefix_pattern": r"^<\d+>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+",
                "columns": ["seq", "time_generated", "src", "dst", "dport", "bytes_sent"],
                "fields": {
                    "timestamp": "time_generated",
                    "src_ip": "src",
                    "dst_ip": "dst",
                    "dst_port": "dport",
                    "bytes_sent": "bytes_sent",
                },
            }
        )
        path = _write(
            tmp_path,
            "flows.log",
            "# banner comment\n"
            "<14>Mar  2 08:00:00 fw01 1,2031/03/02 08:00:00,198.51.100.4,203.0.113.9,8443,512\n"
            "<14>Mar  2 08:01:00 fw01 2,2031/03/02 08:01:00,198.51.100.4,203.0.113.9,8443,518\n",
        )

        events, result = ingest_file(path, [mapping])

        assert result.event_count == 2
        assert events[0].src_ip == "198.51.100.4"
        assert events[0].dst_port == 8443
        assert events[0].bytes_sent == 512
        assert events[0].timestamp.startswith("2031-03-02T08:00:00")
        # The verbatim line, including the stripped syslog header, stays citable.
        assert events[0].raw_excerpt.startswith("<14>")


class TestNoTruncation:
    def test_every_record_becomes_evidence(self, tmp_path, shipped_mappings):
        """Regression guard for the truncation class of bug.

        Historic parsers capped output at a few dozen records, which silently
        discarded later events. Ingestion must preserve all of them.
        """
        lines = [
            json.dumps({"timestamp": f"2031-03-02T08:{i // 60:02d}:{i % 60:02d}", "user": f"u{i}"})
            for i in range(250)
        ]
        path = _write(tmp_path, "many.jsonl", "\n".join(lines))

        events, result = ingest_file(path, shipped_mappings)

        assert result.event_count == 250
        assert events[-1].user == "u249"


class TestUnmappedSources:
    def test_unknown_format_still_yields_citable_evidence(self, tmp_path):
        path = _write(
            tmp_path,
            "weird.log",
            "2031-03-02T08:00:00 device=edge note=unparseable 198.51.100.4 -> 203.0.113.9\n",
        )

        events, result = ingest_file(path, [])

        assert result.mapping_id == "unmapped"
        assert len(events) == 1
        assert events[0].raw_excerpt.startswith("2031-03-02T08:00:00")

    def test_generic_extraction_only_captures_present_values(self, tmp_path):
        """An unmapped line must not gain invented structure."""
        path = _write(tmp_path, "weird.log", "no addresses or timestamps here\n")

        events, _ = ingest_file(path, [])

        assert events[0].src_ip == ""
        assert events[0].timestamp == ""
        assert events[0].user == ""


class TestMappingSelection:
    def test_content_signature_beats_filename(self, tmp_path, shipped_mappings):
        """A renamed file is still recognised by its content."""
        path = _write(
            tmp_path,
            "renamed_export.txt",
            "Mar  2 2031 08:00:00 fw : %ASA-6-113015: AAA user authentication Rejected : "
            "reason = 'User authentication failed' : user = rlopez",
        )

        mapping, _ = select_mapping(path, shipped_mappings)

        assert mapping is not None
        assert mapping.id == "cisco_asa_syslog"

    def test_no_match_returns_none(self, tmp_path, shipped_mappings):
        path = _write(tmp_path, "notes.txt", "shopping list\nmilk\n")

        mapping, _ = select_mapping(path, shipped_mappings)

        assert mapping is None


class TestVendorMappings:
    def test_asa_syslog_extracts_user_and_outcome(self, tmp_path, shipped_mappings):
        path = _write(
            tmp_path,
            "vpn.log",
            "Mar  2 2031 08:00:00 gw : %ASA-6-113015: AAA user authentication Rejected : "
            "reason = 'User authentication failed' : user = rlopez : IP = 198.51.100.4\n"
            "Mar  2 2031 08:00:20 gw : %ASA-6-113039: Group <Staff> User <rlopez> "
            "IP <198.51.100.4> AnyConnect session started.\n",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.mapping_id == "cisco_asa_syslog"
        assert result.event_count == 2
        assert events[0].user == "rlopez"
        assert events[0].status == "failure"
        assert events[1].status == "success"

    def test_asa_angle_bracket_dialect_extracts_identity(self, tmp_path, shipped_mappings):
        """Session-lifecycle messages use ``User <x> IP <y>``, not ``user = x``.

        Regression: only the AAA colon dialect was parsed, so most VPN events
        lost their user and source address entirely.
        """
        path = _write(
            tmp_path,
            "vpn.log",
            "Mar  2 2031 08:00:20 gw : %ASA-4-722051: Group <Staff> User <rlopez> "
            "IP <198.51.100.4> IPv4 Address <10.60.1.7> assigned to session\n",
        )

        events, _ = ingest_file(path, shipped_mappings)

        assert events[0].user == "rlopez"
        assert events[0].src_ip == "198.51.100.4"
        assert events[0].extra.get("assigned_ip") == "10.60.1.7"

    def test_asa_rfc3164_timestamp_without_year(self, tmp_path, shipped_mappings):
        """RFC3164 syslog carries no year; the file's own mtime supplies it.

        Regression: the record pattern required a year, so every stock-format
        ASA line lost its timestamp (0% parse rate) and chronological analytics
        went blind.
        """
        path = _write(
            tmp_path,
            "vpn.log",
            "Sep 14 12:15:02 gw %ASA-6-113039: Group <Staff> User <rlopez> "
            "IP <198.51.100.4> AnyConnect session started.\n",
        )

        events, _ = ingest_file(path, shipped_mappings)

        event = events[0]
        assert event.timestamp, "no-year syslog timestamp must still parse"
        assert "-09-14T12:15:02" in event.timestamp
        # Year must come from the file, never strptime's 1900 default.
        assert not event.timestamp.startswith("1900")

    def test_comment_lines_are_not_evidence(self, tmp_path, shipped_mappings):
        """``#`` banner lines are documentation, not citable events.

        Regression: header comments were ingested as records, inflating counts
        (28 junk events in one 21-line log) and polluting the citation space.
        """
        path = _write(
            tmp_path,
            "vpn.log",
            "# Cisco ASA VPN log export\n"
            "# Generated for review\n"
            "\n"
            "Sep 14 12:15:02 gw %ASA-6-113039: Group <Staff> User <rlopez> "
            "IP <198.51.100.4> AnyConnect session started.\n",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.event_count == 1
        # Line numbers still reflect true file positions for verbatim retrieval.
        assert events[0].line_no == 4

    def test_azure_signin_json_maps_outcome_and_device(self, tmp_path, shipped_mappings):
        doc = {
            "value": [
                {
                    "createdDateTime": "2031-03-02T08:00:00Z",
                    "userPrincipalName": "rlopez@example.test",
                    "ipAddress": "198.51.100.4",
                    "appDisplayName": "Portal",
                    "status": {"errorCode": 0},
                    "deviceDetail": {
                        "operatingSystem": "Windows",
                        "browser": "Firefox",
                        "isCompliant": True,
                    },
                    "location": {"city": "Springfield", "countryOrRegion": "XX"},
                },
                {
                    "createdDateTime": "2031-03-02T08:05:00Z",
                    "userPrincipalName": "rlopez@example.test",
                    "ipAddress": "203.0.113.9",
                    "status": {"errorCode": 500121},
                    "deviceDetail": {"operatingSystem": "Linux", "isCompliant": False},
                    "location": {"city": "Elsewhere", "countryOrRegion": "YY"},
                },
            ]
        }
        path = _write(tmp_path, "signins.json", json.dumps(doc))

        events, result = ingest_file(path, shipped_mappings)

        assert result.mapping_id == "azure_ad_signins_json"
        assert events[0].status == "success"
        assert events[0].device.is_compliant is True
        assert events[0].geo.country == "XX"
        # Any non-zero provider error code is a failure.
        assert events[1].status == "failure"
        assert events[1].error_code == "500121"
        assert events[1].device.is_compliant is False

    def test_sysmon_xml_extracts_lineage_and_hash(self, tmp_path, shipped_mappings):
        digest = "c" * 64
        path = _write(
            tmp_path,
            "sysmon.xml",
            "<Events xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>"
            "<Event><System><Provider Name='Microsoft-Windows-Sysmon'/>"
            "<EventID>1</EventID></System><EventData>"
            "<Data Name='UtcTime'>2031-03-02 08:00:00</Data>"
            "<Data Name='Image'>C:\\tools\\runner.exe</Data>"
            "<Data Name='ParentImage'>C:\\shell\\host.exe</Data>"
            "<Data Name='CommandLine'>runner.exe --mode batch</Data>"
            f"<Data Name='Hashes'>SHA256={digest}</Data>"
            "</EventData></Event></Events>",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.mapping_id == "sysmon_xml"
        event = events[0]
        assert event.process.endswith("runner.exe")
        assert event.parent_process.endswith("host.exe")
        assert event.hashes["sha256"] == digest
        assert event.action == "process_create"

    def test_windows_security_xml_maps_event_semantics(self, tmp_path, shipped_mappings):
        path = _write(
            tmp_path,
            "windows_endpoint.xml",
            "<Events><Event><System>"
            "<Provider Name='Microsoft-Windows-Security-Auditing'/>"
            "<EventID>4625</EventID>"
            "<TimeCreated SystemTime='2031-03-02T08:00:00'/>"
            "<Computer>ws-104</Computer></System><EventData>"
            "<Data Name='TargetUserName'>rlopez</Data>"
            "<Data Name='IpAddress'>198.51.100.4</Data>"
            "</EventData></Event></Events>",
        )

        events, result = ingest_file(path, shipped_mappings)

        assert result.mapping_id == "windows_security_evtx"
        assert events[0].user == "rlopez"
        assert events[0].status == "failure"
        assert events[0].action == "logon_failed"


class TestExtractionSemantics:
    def test_alternative_paths_first_non_empty_wins(self):
        mapping = LogMapping(id="t", fmt="json", fields={"user": ["missing", "actor"]})
        event = build_event({"actor": "rlopez"}, "raw", 1, "f.json", mapping)
        assert event.user == "rlopez"

    def test_value_map_wildcard_default(self):
        mapping = LogMapping(
            id="t",
            fmt="json",
            fields={"status": "code"},
            value_maps={"status": {"0": "success", "*": "failure"}},
        )
        assert build_event({"code": "0"}, "r", 1, "f", mapping).status == "success"
        assert build_event({"code": "77"}, "r", 1, "f", mapping).status == "failure"

    def test_missing_field_stays_empty(self):
        mapping = LogMapping(id="t", fmt="json", fields={"user": "absent"})
        assert build_event({}, "raw", 1, "f.json", mapping).user == ""

    def test_type_coercion(self):
        mapping = LogMapping(
            id="t",
            fmt="json",
            fields={"dst_port": "port", "bytes_sent": "sent", "is_compliant": "compliant"},
        )
        event = build_event(
            {"port": "443", "sent": "2048", "compliant": "false"}, "r", 1, "f", mapping
        )
        assert event.dst_port == 443
        assert event.bytes_sent == 2048
        assert event.device.is_compliant is False

    def test_uncoercible_number_is_dropped_not_guessed(self):
        mapping = LogMapping(id="t", fmt="json", fields={"dst_port": "port"})
        assert build_event({"port": "n/a"}, "r", 1, "f", mapping).dst_port is None

    def test_provenance_is_recorded(self):
        mapping = LogMapping(id="t", fmt="json", fields={})
        event = build_event({}, "the raw line", 42, "source.log", mapping)
        assert event.source_file == "source.log"
        assert event.line_no == 42
        assert event.raw_excerpt == "the raw line"
        assert event.source_type == "t"


class TestDiscovery:
    def test_single_file(self, tmp_path):
        path = _write(tmp_path, "a.log", "x")
        assert discover_log_files(path) == [path]

    def test_recursive_directory(self, tmp_path):
        (tmp_path / "nested").mkdir()
        _write(tmp_path, "a.log", "x")
        _write(tmp_path / "nested", "b.log", "y")

        assert len(discover_log_files(tmp_path, recursive=True)) == 2

    def test_non_recursive_honours_flag(self, tmp_path):
        """Regression guard: the flag used to be accepted but ignored."""
        (tmp_path / "nested").mkdir()
        _write(tmp_path, "a.log", "x")
        _write(tmp_path / "nested", "b.log", "y")

        assert len(discover_log_files(tmp_path, recursive=False)) == 1

    def test_missing_path(self, tmp_path):
        assert discover_log_files(tmp_path / "nope") == []


class TestResilience:
    def test_malformed_json_does_not_abort_run(self, tmp_path, shipped_mappings):
        path = _write(tmp_path, "broken.json", "{not valid json")
        events, result = ingest_file(path, shipped_mappings)
        assert isinstance(events, list)
        assert result.source_file == "broken.json"

    def test_malformed_jsonl_line_preserved_as_raw(self, tmp_path, shipped_mappings):
        path = _write(tmp_path, "mixed.jsonl", '{"user": "rlopez"}\nnot-json\n')
        events, _ = ingest_file(path, shipped_mappings)
        assert len(events) == 2
        assert events[1].raw_excerpt == "not-json"
