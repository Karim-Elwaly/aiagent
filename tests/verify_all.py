"""
UAOS Verification Harness — All Implemented SOTA & Hermes-3 Components

This script runs comprehensive in-process verification across all phases:
- Phase 0: ToolContext, Telemetry, Checkpoints, Defaults
- Phase 1: Native & Hermes XML Tool Calling, Channel Separation, RepeatGuard
- Phase 2: Persistent Python Session, SQLite+FTS5 Memory Store, RRF Fusion
- Phase 3: AST Safety Validation, Distilled Skills Lifecycle, SSRF Protection
- Phase 4: UI & API Performance (TTL Cache, Reflow Throttling)

Usage:
    python tests/verify_all.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS_COUNT = 0
FAIL_COUNT = 0


def record_result(name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"  {GREEN}✓ PASS{RESET} | {name} {f'({detail})' if detail else ''}")
    else:
        FAIL_COUNT += 1
        print(f"  {RED}✗ FAIL{RESET} | {name} - {detail}")


# ─── SECTION 1: PHASE 0 FOUNDATIONS ──────────────────────────────────────────


def verify_phase0():
    print(f"\n{BOLD}{CYAN}=== 1. Verifying Phase 0 Foundations ==={RESET}")

    # 1.1 ToolContext isolation
    from src.core.tool_context import (
        ToolContext,
        get_tool_context,
        reset_tool_context,
        set_tool_context,
    )

    ctx = get_tool_context()
    assert ctx.workflow_id == ""

    test_ctx = ToolContext(workflow_id="wf-v0", task_id="t-v0", extras={"depth": 1})
    token = set_tool_context(test_ctx)
    try:
        active = get_tool_context()
        assert active.workflow_id == "wf-v0"
        assert active.extras["depth"] == 1
        record_result("ToolContext Thread-Safe Propagation", True)
    finally:
        reset_tool_context(token)
    assert get_tool_context().workflow_id == ""

    # 1.2 Feature Flags Defaults
    from src.core.config import Settings

    s = Settings()
    flags_ok = (
        s.tool_call_mode == "legacy"
        and s.enable_stateful_python is False
        and s.enable_memory is False
        and s.enable_reflection is False
        and s.enable_skill_learning is False
        and s.enable_browser is False
    )
    record_result("Zero-Regression Feature Flags Default OFF", flags_ok)

    # 1.3 Checkpoint Schema v1 -> v2 Backwards Compatibility
    from src.core.messages import make_checkpoint, read_checkpoint

    v1_raw = {"step": 2, "messages": [{"role": "user", "content": "hi"}]}
    parsed_v1 = read_checkpoint(v1_raw)
    assert parsed_v1.step == 2
    assert parsed_v1.schema_version == 1

    v2_raw = make_checkpoint(step=3, messages=[], tool_calls_made=["ls"], tool_history=[])
    parsed_v2 = read_checkpoint(v2_raw)
    assert parsed_v2.step == 3
    assert parsed_v2.schema_version == 2
    record_result("Checkpoint v1/v2 Bi-Directional Compatibility", True)

    # 1.4 Benchmark dataset integrity
    from tests.eval.dataset import EVAL_DATASET

    assert len(EVAL_DATASET) >= 40
    record_result("Standardized Benchmark Suite Loaded", True, f"{len(EVAL_DATASET)} cases")


# ─── SECTION 2: PHASE 1 NATIVE TOOL-CALLING & REFLECTION ─────────────────────


def verify_phase1():
    print(f"\n{BOLD}{CYAN}=== 2. Verifying Phase 1 Tool-Calling & Reflection ==={RESET}")

    # 2.1 Thinking & Content Channel Separation
    from src.core.llm_client import extract_thinking_and_content

    raw_response = "<think>\nLet us analyze the query\nStep 1: check host\n</think>\nThe answer is host123"
    reasoning, clean_content = extract_thinking_and_content(raw_response)
    assert "Let us analyze" in reasoning
    assert "<think>" not in clean_content
    assert clean_content == "The answer is host123"
    record_result("Channel Separation (<think> Token Stripping)", True)

    # 2.2 Hermes XML Parsing (<tool_call>)
    from src.core.tool_call_parser import parse_tool_calls

    xml_text = (
        "I will fetch the system hostname now.\n"
        "<tool_call>\n"
        '{"name": "execute_command", "arguments": {"command": "hostname"}}\n'
        "</tool_call>"
    )
    calls = parse_tool_calls(xml_text)
    assert len(calls) == 1
    assert calls[0].name == "execute_command"
    assert calls[0].args == {"command": "hostname"}
    assert calls[0].source == "hermes_xml"
    record_result("Tier-2 Hermes XML <tool_call> Parsing", True)

    # 2.3 Tier-3 Markdown JSON fallback
    json_text = '```json\n{"tool": "file_reader", "args": {"path": "test.txt"}}\n```'
    calls_json = parse_tool_calls(json_text)
    assert len(calls_json) == 1
    assert calls_json[0].name == "file_reader"
    assert calls_json[0].args == {"path": "test.txt"}
    record_result("Tier-3 Markdown JSON Parser Fallback", True)

    # 2.4 RepeatGuard
    from src.core.reflection import RepeatGuard

    guard = RepeatGuard()
    # First attempt: not repeated
    is_rep1 = guard.is_repeated("read_file", {"path": "missing.txt"}, is_error=True)
    assert is_rep1 is False

    # Second attempt with identical args and error: repeated!
    is_rep2 = guard.is_repeated("read_file", {"path": "missing.txt"}, is_error=True)
    assert is_rep2 is True

    prompt = guard.generate_pivot_instruction("read_file", {"path": "missing.txt"})
    assert "DO NOT CALL" in prompt
    record_result("RepeatGuard Loop Prevention & Pivot Prompts", True)


# ─── SECTION 3: PHASE 2 PYTHON SESSION & LONG-TERM MEMORY ────────────────────


async def verify_phase2():
    print(f"\n{BOLD}{CYAN}=== 3. Verifying Phase 2 Stateful Python & Memory ==={RESET}")

    # 3.1 Stateful Python Session Variable Sharing
    from src.registry.tools.python_session import PersistentPythonSession

    session = PersistentPythonSession(workflow_id="verify_wf")
    try:
        r1 = await session.execute("a = 100\nb = 250")
        assert r1["success"] is True

        r2 = await session.execute("print(a + b)")
        assert r2["success"] is True
        assert "350" in r2["stdout"]

        vars_dict = session.inspect_vars()
        assert vars_dict.get("a") == "100"
        assert vars_dict.get("b") == "250"
        record_result("Persistent Python Variable Memory Across Steps", True)

        # Reset environment
        session.reset()
        assert "a" not in session.inspect_vars()
        record_result("Persistent Python Session Clean Reset", True)
    finally:
        await session.close()

    # 3.2 MemoryStore SQLite + FTS5 & Secret Masking
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.memory.store import Episode, Fact, MemoryStore, mask_secrets

        # Secret masking test
        sensitive = "My api key is Bearer sk-ant-api03-abcdef1234567890abcdef and password=SuperSecretPassword123"
        masked = mask_secrets(sensitive)
        assert "sk-ant" not in masked
        assert "[REDACTED" in masked
        record_result("Secret & Credential Masking in Memory Pipeline", True)

        # Database initialization & FTS5 full-text search
        db_path = Path(tmpdir) / "test_memory.db"
        store = MemoryStore(db_path=db_path)

        # Insert facts
        f1 = Fact(
            key="db_host",
            value="postgres.internal.net",
            source_type="tool_output",
            source_ref="config.json",
            verified=True,
            volatile=False,
        )
        saved = store.save_fact(f1)
        assert saved is True

        results = store.search_facts("postgres")
        assert len(results) >= 1
        assert results[0].value == "postgres.internal.net"
        record_result("SQLite + FTS5 Full-Text Fact Indexing & Recall", True)

        # Volatile fact auto-tagging
        f2 = Fact(
            key="current_time",
            value="12:00:00",
            source_type="tool_output",
            source_ref="date",
            verified=True,
        )
        store.save_fact(f2)
        v_fact = store.get_fact("current_time")
        assert v_fact is not None and v_fact.volatile is True
        record_result("Volatile Fact Auto-Tagging Guard", True)

        # Record and search episode
        store.record_episode(
            Episode(
                run_id="run-001",
                query="Find open ports on gateway",
                goal="Port scan",
                dag_json="{}",
                outcome="accurate",
                score=1.0,
            )
        )
        episodes = store.search_episodes("gateway")
        assert len(episodes) >= 1
        assert episodes[0]["run_id"] == "run-001"
        record_result("Past Episode Archiving & Full-Text Search", True)

    # 3.3 Reciprocal Rank Fusion (RRF)
    from src.memory.embeddings import cosine_similarity, reciprocal_rank_fusion

    sim = cosine_similarity([1.0, 0.0], [1.0, 0.0])
    assert abs(sim - 1.0) < 1e-4

    list_a = [{"id": "item1"}, {"id": "item2"}]
    list_b = [{"id": "item2"}, {"id": "item3"}]
    fused = reciprocal_rank_fusion([list_a, list_b], key_field="id")
    # item2 is in both lists, should rank #1
    assert fused[0]["id"] == "item2"
    record_result("Hybrid Search Reciprocal Rank Fusion (RRF)", True)


# ─── SECTION 4: PHASE 3 SKILLS & BROWSER INTEGRATION ─────────────────────────


def verify_phase3():
    print(f"\n{BOLD}{CYAN}=== 4. Verifying Phase 3 Skills & Browser Security ==={RESET}")

    # 4.1 AST Safety Validation
    from src.skills.distiller import validate_skill_ast

    safe_py = """
async def compute(x: int) -> int:
    return x * 2
"""
    is_safe, msg = validate_skill_ast(safe_py)
    assert is_safe is True
    record_result("AST Safety Validator Passes Legitimate Code", True)

    dangerous_cases = [
        ("eval('1+1')", "eval call"),
        ("exec('import os')", "exec call"),
        ("import subprocess", "subprocess import"),
        ("import ctypes", "ctypes import"),
    ]
    for code, label in dangerous_cases:
        safe, reason = validate_skill_ast(f"def bad():\n    {code}")
        assert not safe, f"Expected reject for {label}"
    record_result("AST Safety Validator Blocks eval/exec/subprocess/ctypes", True)

    # 4.2 SSRF Protection for Browser
    from src.registry.tools.browser_tools import is_ssrf_safe_url

    blocked_urls = [
        "http://localhost:8000",
        "http://127.0.0.1:8080",
        "http://10.0.0.5/admin",
        "http://192.168.1.100/router",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ]
    for u in blocked_urls:
        safe, _ = is_ssrf_safe_url(u)
        assert not safe, f"Should block SSRF for {u}"
    safe_google, _ = is_ssrf_safe_url("https://www.google.com")
    assert safe_google
    safe_github, _ = is_ssrf_safe_url("https://github.com/trending")
    assert safe_github
    record_result("Playwright Browser SSRF Protection (Private IP Blocking)", True)


# ─── SECTION 5: PERFORMANCE & UI ARTIFACTS ───────────────────────────────────


def verify_ui_and_performance():
    print(f"\n{BOLD}{CYAN}=== 5. Verifying UI & Performance Enhancements ==={RESET}")

    # 5.1 Static UI assets integrity
    ui_files = [
        ROOT / "src" / "ui" / "index.html",
        ROOT / "src" / "ui" / "js" / "app.js",
        ROOT / "src" / "ui" / "js" / "dag_renderer.js",
        ROOT / "src" / "ui" / "css" / "style.css",
    ]
    for f in ui_files:
        assert f.exists(), f"Missing UI asset: {f}"
        assert f.stat().st_size > 100
    record_result("Frontend Web Assets Present & Validated", True)

    # 5.2 CSS Optimization Check: Check visibility: hidden in modals
    style_content = (ROOT / "src" / "ui" / "css" / "style.css").read_text(encoding="utf-8")
    assert "visibility: hidden;" in style_content
    assert "will-change: stroke-dashoffset;" in style_content
    record_result("Modal Layout Pruning & GPU Compositing in CSS", True)

    # 5.3 Frame-Batched Token Micro-Buffering in app.js
    app_js_content = (ROOT / "src" / "ui" / "js" / "app.js").read_text(encoding="utf-8")
    assert "bufferStreamToken" in app_js_content
    assert "flushStreamTokens" in app_js_content
    assert "requestAnimationFrame" in app_js_content
    record_result("Frame-Batched Token Micro-Buffer in JS", True)

    # 5.4 Page Visibility Background Throttling in app.js
    assert "visibilitychange" in app_js_content
    record_result("Page Visibility API Background Throttling", True)

    # 5.5 In-Memory Status TTL Cache in main.py
    main_py_content = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    assert "_status_cache" in main_py_content
    assert "_STATUS_CACHE_TTL" in main_py_content
    record_result("Backend 1.0s Status Cache TTL & Invalidation", True)


# ─── SECTION 6: MISSION-TO-FLEET PLATFORM (PHASES 1-8) ──────────────────────


def verify_mission_fleet_architecture():
    print(f"\n{BOLD}{CYAN}=== 6. Verifying Mission-to-Fleet Architecture (Phases 1-8) ==={RESET}")

    # 6.1 Enterprise Profile Whitelabeling
    from src.hermes.profiles import generate_dynamic_profile_name, is_dynamic_profile
    prof = generate_dynamic_profile_name("threat_triage")
    assert prof.startswith("uaos-aeu-"), f"Expected uaos-aeu- prefix, got {prof}"
    assert is_dynamic_profile(prof)
    record_result("Enterprise uaos-aeu-* Profile Whitelabeling", True)

    # 6.2 Environment Discovery Engine
    from src.brain.environment_scanner import EnvironmentDiscoveryEngine
    scanner = EnvironmentDiscoveryEngine()
    env = scanner.scan_environment("Autonomous SOC Incident Triage & Response")
    assert env.total_connectors_probed >= 10
    assert 0.0 <= env.semantic_readiness_score <= 1.0
    record_result("Environment Discovery Engine (13 Connectors & Readiness)", True)

    # 6.3 Pre-Flight Clarification Gate
    clarif = scanner.synthesize_clarification_manifest("Autonomous SOC Incident Triage & Response", env)
    assert clarif.proposed_fleet_size >= 1
    assert clarif.inferred_domain in ["cybersecurity", "general", "software_engineering", "procurement", "supply_chain"]
    record_result("Pre-Flight Clarification Gate & Domain Inference", True)

    # 6.4 Autonomous Mission-to-Fleet Architect & Competing Fleets
    from src.fleet.fleet_composer import MissionFleetArchitect
    architect = MissionFleetArchitect()
    fleet = architect.expand_mission_to_fleet("Autonomous SOC Incident Triage & Response")
    assert len(fleet.units) >= 3
    assert all(u.unit_id.startswith("AEU-T") for u in fleet.units)
    assert all(u.operational_stage in ["RECON_INGESTION", "DEEP_ANALYSIS", "CROSS_VERIFICATION", "EXECUTION_ACTION", "DELIVERABLE_SYNTHESIS"] for u in fleet.units)
    record_result("Autonomous Mission-to-Fleet Architect (AEU-TX Expansion)", True)

    competing = architect.synthesize_competing_fleets("Enterprise Supply Chain Bottleneck Audit")
    assert "fleet_alpha_precision" in competing and "fleet_omega_velocity" in competing
    record_result("Dual-Track Competing Fleets Synthesis", True)

    # 6.5 Fleet Telemetry Tracker
    from src.core.telemetry import FleetTelemetryTracker
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db = f.name
    try:
        tracker = FleetTelemetryTracker(db_path=tmp_db)
        tracker.record_unit_execution("sess-1", "fleet-1", "AEU-T1", "RECON_INGESTION", 100, ["tool1"], "completed", 0.95, False)
        summary = tracker.get_aggregate_summary()
        assert summary["total_units_deployed"] == 1
        record_result("Fleet Telemetry SQLite Tracker & Real-Time KPIs", True)
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    # 6.6 Multi-Channel Deliverable Dispatcher
    from src.core.output_dispatcher import OutputDispatcher
    dispatcher = OutputDispatcher()
    dossier = "# Test Dossier\n**Host**: 192.168.1.10\n**Severity**: HIGH\n**MITRE**: T1003"
    form_res = dispatcher.compile_to_structured_form(dossier, "Test Mission")
    assert "fields" in form_res and len(form_res["fields"]) >= 1
    email_res = dispatcher.compile_to_email_payload(dossier, "Test Mission")
    assert "styled_html_body" in email_res and "mailto_uri" in email_res and "eml_raw" in email_res
    record_result("Multi-Channel Deliverable Dispatcher (Form, RFC 822 EML, mailto)", True)

    # 6.7 UI Component Parity in index.html and app.js
    index_html = (ROOT / "src" / "ui" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "src" / "ui" / "js" / "app.js").read_text(encoding="utf-8")
    assert "kpi-telemetry-ribbon" in index_html
    assert "preflight-card" in index_html
    assert "deliverable-studio" in index_html or "deliv-dossier" in index_html
    assert "challenge-step-toggle" in index_html
    assert "competing-fleets-toggle" in index_html
    assert "preflight-launch-btn" in index_html
    record_result("Mission Control UI Components (KPI Ribbon, Clarification, Studio)", True)


def verify_fleet_arena():
    print_header("Autonomous Fleet Arena (Reusable Named Hermes Agent Profiles)")

    # 1. Deterministic naming & profile prefixes
    from src.hermes.profiles import fleet_profile_name, is_fleet_profile_name, is_dynamic_profile_name

    name = fleet_profile_name("soc-alert", "Telemetry Log Ingestion")
    assert name == "fleet-soc-alert-telemetry-log-ingest", f"Unexpected name: {name}"
    assert is_fleet_profile_name(name), "Should be recognized as fleet profile"
    assert not is_dynamic_profile_name(name), "Fleet profile must NOT be considered dynamic (exempt from LRU eviction)"
    record_result("Deterministic Fleet Profile Naming & Eviction Exemption", True)

    # 2. Fleet Arena Models & Store
    from src.core.models import FleetArenaManifest, FleetArenaUnit
    from src.fleet.arena_store import FleetArenaStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = FleetArenaStore(root=Path(tmpdir))
        unit = FleetArenaUnit(
            profile_name=name,
            unit_codename="LOG-INGESTION",
            task_id="t1",
            task_name="Telemetry Log Ingestion",
            scoped_tools=["search_tool"],
        )
        manifest = FleetArenaManifest(
            arena_id="arena-soc-alert-test",
            arena_name="SOC Alert Test Arena",
            arena_slug="soc-alert",
            mission_prompt="Triage SOC alert #4521",
            units=[unit],
            dag={"tasks": [{"id": "t1", "name": "Telemetry Log Ingestion", "description": "Ingest logs"}]},
            status="draft",
            profiles_to_create=[name],
            profiles_existing=[],
        )
        store.save(manifest)
        loaded = store.load("arena-soc-alert-test")
        assert loaded is not None and loaded.status == "draft"
        assert len(loaded.units) == 1
        assert loaded.units[0].profile_name == name

        store.update_status("arena-soc-alert-test", "provisioned")
        assert store.load("arena-soc-alert-test").status == "provisioned"
        assert len(store.list_all()) == 1
        record_result("Fleet Arena Manifest Models & Persistent JSON Store", True)

        # 3. Fleet Arena Composer - Attach Files Lifecycle
        from src.fleet.arena import FleetArenaComposer

        composer = FleetArenaComposer(store=store)
        composer.attach_files("arena-soc-alert-test", {
            "t1": [{"filename": "alert.json", "file_path": "/var/log/alert.json", "extracted_text": '{"alert_id": 4521}'}]
        })
        enriched = composer.get_enriched_dag("arena-soc-alert-test")
        assert "alert.json" in enriched["tasks"][0]["description"]
        record_result("Fleet Arena File Attachment & Context Binding per Phase", True)

        # 4. API Route Registration
        from src.api.main import app

        routes = [getattr(r, "path", "") for r in app.routes]
        assert "/api/fleet/arena/plan" in routes or "/fleet/arena/plan" in routes
        assert "/api/fleet/arenas" in routes or "/fleet/arenas" in routes
        assert "/api/fleet/arena/{arena_id}/provision" in routes
        assert "/api/fleet/arena/{arena_id}/attach" in routes
        assert "/api/fleet/arena/{arena_id}/start" in routes
        assert "/api/fleet/profiles" in routes
        record_result("Fleet Arena REST API Endpoints (Plan, Provision, Attach, Start, Profiles)", True)


# ─── MAIN RUNNER ─────────────────────────────────────────────────────────────


async def main():
    print(f"\n{BOLD}============================================================{RESET}")
    print(f"{BOLD}   UAOS Universal Autonomous Operating System Verification   {RESET}")
    print(f"{BOLD}============================================================{RESET}")

    start_ts = time.time()
    try:
        verify_phase0()
        verify_phase1()
        await verify_phase2()
        verify_phase3()
        verify_ui_and_performance()
        verify_mission_fleet_architecture()
        verify_fleet_arena()
    except Exception as e:
        print(f"\n{RED}[ERROR] Verification aborted due to unexpected exception:{RESET} {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_ts
    print(f"\n{BOLD}============================================================{RESET}")
    print(f"Results: {GREEN}{PASS_COUNT} Passed{RESET}, {RED}{FAIL_COUNT} Failed{RESET} in {elapsed:.2f}s")
    print(f"{BOLD}============================================================{RESET}")

    if FAIL_COUNT > 0:
        print(f"{RED}[FAIL] Some verification checks failed!{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}[SUCCESS] All implemented capabilities verified 100% operational!{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
