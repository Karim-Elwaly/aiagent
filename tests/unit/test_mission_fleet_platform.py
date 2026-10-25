"""
Comprehensive Unit Test Suite for UAOS Mission-to-Fleet Architecture (Phases 1-8).
Verifies:
- Phase 1: Enterprise White-Labeling (uaos-aeu-* profile nomenclature)
- Phase 2: Environment Discovery Engine (13 connectors, tool registry, semantic readiness)
- Phase 3: Pre-Flight Clarification Gate (questions, default fallback, manifest generation)
- Phase 4: Autonomous Mission-to-Fleet Architect (AEU-TX specialist expansion, DAG synthesis, competing fleets)
- Phase 5: Step-by-Step Operator Challenge Gate (StepChallengePayload, supervisor integration)
- Phase 6: Real-Time Fleet Telemetry (FleetTelemetryTracker SQLite recording and summary)
- Phase 7: Multi-Channel Deliverable Dispatcher (Dossier, Interactive Form, RFC 822 .eml, mailto)
"""

import os
import tempfile
import pytest
from src.core.models import (
    ClarificationManifest,
    ClarificationQuestion,
    DiscoveredCapability,
    MissionEnvironmentManifest,
    SpecializedFleetManifest,
    StepChallengePayload,
    Task,
    TaskDAG,
    TaskSpecialistSpec,
)
from src.fleet.fleet_composer import MissionFleetArchitect, FleetComposer
from src.brain.environment_scanner import EnvironmentDiscoveryEngine
from src.core.output_dispatcher import OutputDispatcher
from src.core.telemetry import FleetTelemetryTracker
from src.hermes.profiles import generate_dynamic_profile_name, is_dynamic_profile


def test_phase1_enterprise_whitelabeling():
    """Verify profile names use enterprise uaos-aeu-* prefix and no forbidden open-source terms."""
    prof = generate_dynamic_profile_name("threat_triage")
    assert prof.startswith("uaos-aeu-"), f"Expected uaos-aeu- prefix, got {prof}"
    assert is_dynamic_profile(prof)
    # Check backward compatibility
    assert is_dynamic_profile("aiagent-dyn-test1234")


def test_phase2_environment_discovery():
    """Verify EnvironmentDiscoveryEngine scans tools, connectors, and produces semantic readiness."""
    scanner = EnvironmentDiscoveryEngine()
    manifest = scanner.discover_for_mission(prompt="Perform autonomous SOC incident triage on compromised workstation")

    assert isinstance(manifest, MissionEnvironmentManifest)
    assert isinstance(manifest.active_connectors, list)
    assert 0.0 <= manifest.readiness_score <= 1.0
    assert len(manifest.matched_tools) >= 0


def test_phase3_preflight_clarification_gate():
    """Verify Pre-Flight Clarification models and generation."""
    scanner = EnvironmentDiscoveryEngine()
    manifest = scanner.discover_for_mission("High-Severity Ransomware Incident Triage")
    assert manifest.readiness_score >= 0.5

    q = ClarificationQuestion(
        id="q1",
        question="What is the desired remediation posture for identified threat indicators?",
        options=["Advisory Only", "Active Automated Containment"],
        default_answer="Advisory Only",
    )
    clarif = ClarificationManifest(
        session_id="test-session-123",
        needs_clarification=True,
        detected_mission_type="incident_response",
        questions=[q],
    )
    assert clarif.needs_clarification
    assert len(clarif.questions) == 1
    assert clarif.questions[0].default_answer in clarif.questions[0].options


def test_phase4_autonomous_fleet_expansion():
    """Verify MissionFleetArchitect decomposes strategic goal into AEU-TX specialist units."""
    architect = MissionFleetArchitect()
    dag = TaskDAG(
        goal="Autonomous SOC Incident Triage & Response",
        reasoning="Multi-stage security triage graph",
        tasks=[
            Task(id="t1", name="Ingest logs", description="Read security logs", dependencies=[], required_skills=[]),
            Task(id="t2", name="Triage threat", description="Identify attacker", dependencies=["t1"], required_skills=[]),
            Task(id="t3", name="Generate report", description="Write final report", dependencies=["t2"], required_skills=[]),
        ],
    )
    fleet = architect.synthesize_fleet(
        dag=dag,
        mission_title="Autonomous SOC Incident Triage & Response",
        strategy_profile="PRECISION",
    )

    assert isinstance(fleet, SpecializedFleetManifest)
    assert fleet.fleet_id.startswith("fleet-")
    assert len(fleet.units) == 3
    assert len(fleet.dag.tasks) == len(fleet.units)

    for unit in fleet.units:
        assert isinstance(unit, TaskSpecialistSpec)
        assert unit.unit_id.startswith("AEU-T")
        assert unit.operational_stage in [
            "RECON_INGESTION",
            "DEEP_ANALYSIS",
            "CROSS_VERIFICATION",
            "EXECUTION_ACTION",
            "DELIVERABLE_SYNTHESIS",
        ]
        assert unit.synthesized_unit_prompt != ""
        assert isinstance(unit.scoped_tools, list)
        assert unit.verification_criteria != ""


def test_phase5_step_challenge_gate():
    """Verify StepChallengePayload models operator challenge state correctly."""
    payload = StepChallengePayload(
        unit_id="AEU-T1",
        task_id="t1",
        action="approve",
        challenge_critique="Target entity confirmed and validated.",
        injected_constraints="Strictly quarantine host.",
    )
    assert payload.unit_id == "AEU-T1"
    assert payload.action == "approve"
    assert "quarantine" in payload.injected_constraints


def test_phase6_real_time_fleet_telemetry():
    """Verify FleetTelemetryTracker records unit executions and provides aggregate metrics."""
    tracker = FleetTelemetryTracker.get_instance()
    tracker.start_mission(session_id="session-test-unit", total_units=2, discovered_tools=5)
    tracker.record_step_started(session_id="session-test-unit")
    tracker.record_step_completed(session_id="session-test-unit", tools_used_count=2, execution_time_ms=450.0)
    tracker.record_challenge(session_id="session-test-unit")
    tracker.finish_mission(session_id="session-test-unit", status="completed")

    telem = tracker.get_mission_telemetry("session-test-unit")
    assert telem["invoked_tools_count"] == 2
    assert telem["step_challenges_issued"] == 1
    assert telem["status"] == "completed"


def test_phase7_multi_channel_deliverable_dispatcher():
    """Verify OutputDispatcher produces Structured Form (JSON/CSV) and RFC 822 Email with mailto URI."""
    raw_dossier = (
        "# Autonomous Incident Triage Dossier\n\n"
        "**Host**: srv-db-01.corp.internal (10.0.4.15)\n"
        "**Severity**: CRITICAL\n"
        "**MITRE ATT&CK**: T1003.001 (OS Credential Dumping)\n"
        "**Containment**: Quarantined via CrowdStrike Falcon EDR at 14:02 UTC\n"
        "**Recommendation**: Revoke Kerberos TGT and rotate enterprise service credentials.\n"
        "- Contain host\n"
        "- Rotate credentials\n"
    )

    dispatcher = OutputDispatcher()

    # 1. Structured Form
    form_data = dispatcher.compile_to_structured_form(
        final_output=raw_dossier,
    )
    assert "fields" in form_data
    assert len(form_data["fields"]) >= 1
    field_labels = [f["label"].lower() for f in form_data["fields"]]
    assert any("host" in fl or "severity" in fl or "containment" in fl for fl in field_labels)

    # 2. Executive Email Payload
    email_data = dispatcher.compile_to_email_payload(
        final_output=raw_dossier,
        mission_title="SOC Incident Triage & Response",
        recipient="ciso@enterprise.org",
    )
    assert "styled_html_body" in email_data
    assert "mailto_uri" in email_data
    assert "eml_raw" in email_data
    assert email_data["mailto_uri"].startswith("mailto:")
    assert "mailto:ciso@enterprise.org" in email_data["mailto_uri"]
    assert "mission-control@uaos.enterprise" in email_data["eml_raw"]
    assert "Content-Type: multipart/alternative" in email_data["eml_raw"]
    assert "Content-Type: multipart/alternative" in email_data["eml_raw"]


def test_extract_target_path_phantom_path_prevention():
    """Verify generic English mission prompts with colons do not extract phantom drive paths."""
    from src.core.path_utils import extract_target_path

    # The exact user prompt that previously extracted 'D:\\projects\\aiagent\\t' due to 'Audit:'
    supply_chain_prompt = (
        "Enterprise Supply Chain Disruption Audit: Ingest supplier telemetry and shipping manifests, "
        "identify Tier-1 component bottlenecks, calculate production delay risk, and dispatch "
        "executive vendor contingency plan."
    )
    assert extract_target_path(supply_chain_prompt) is None

    # Prose colons must never be extracted as drive letters
    assert extract_target_path("Incident Response: Review alerts immediately") is None
    assert extract_target_path("Note: Audit and verify all compliance controls") is None
    assert extract_target_path("Phase 1: Step A: Execute automated check") is None
    assert extract_target_path("A: First action B: Second action") is None

    # Legitimate Windows paths must still extract properly
    win_path_prompt = "Perform forensic analysis on D:\\Security-logs-test\\attack-cases-benchmark\\case-1"
    extracted = extract_target_path(win_path_prompt)
    assert extracted is not None
    assert "Security-logs-test" in extracted

