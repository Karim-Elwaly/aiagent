"""
Unit tests for Dynamic Bespoke Hermes Profiles: toolset hashing,
profile provisioning, LRU capacity capping, and single gateway restart post-planning.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.models import RiskLevel
from src.hermes.active_runs import ActiveRuns
from src.hermes.profiles import (
    DEFAULT_PROFILE,
    DYNAMIC_PROFILE_PREFIX,
    ORCHESTRATOR_PROFILE,
    HermesProfiles,
    ProfileState,
)
from src.hermes.provision import compute_toolset_hash, provision_dag_profiles
from src.registry.tool_registry import ToolRegistry, ToolSpec


def _settings(**overrides):
    base = dict(
        hermes_api_url="http://127.0.0.1:8642",
        hermes_home="",
        hermes_bin="hermes",
        hermes_mcp_url="http://127.0.0.1:8000/mcp/",
        hermes_default_toolsets=["web"],
        hermes_dynamic_profiles=True,
        hermes_max_dynamic_profiles=3,
        hermes_profile_prefix_dynamic=DYNAMIC_PROFILE_PREFIX,
        hermes_gateway_restart_timeout_seconds=5,
        hermes_run_timeout_seconds=30,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _spec(name, skills):
    return ToolSpec(
        tool_id=f"{name}_v1",
        name=name,
        description=f"{name} tool",
        skills_provided=skills,
        parameters={"path": {"type": "string"}},
        function=lambda **kwargs: f"{name}:ok",
        risk_level=RiskLevel.LOW,
        source_type="native",
    )


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(_spec("read_file", ["file_reading"]))
    reg.register(_spec("list_directory", ["directory_listing"]))
    reg.register(_spec("execute_command", ["shell_command"]))
    reg.register(_spec("triage_alert", ["security_triage"]))
    return reg


def test_compute_toolset_hash_determinism():
    hash1 = compute_toolset_hash(["read_file", "list_directory"])
    hash2 = compute_toolset_hash(["list_directory", "read_file"])
    assert hash1 == hash2
    assert len(hash1) == 8


def test_dynamic_profile_creation_and_state(tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    calls = []
    runner = lambda a: calls.append(a) or ""  # noqa: E731

    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=runner, state=state)
    pname = f"{DYNAMIC_PROFILE_PREFIX}1234abcd"
    tools = ["read_file", "list_directory"]

    info = profiles.ensure(None, dynamic_tools=tools, profile_name_override=pname)
    assert info.name == pname

    entry = state.get(pname)
    assert entry.get("is_dynamic") is True
    assert entry.get("bundle") == tools
    assert "last_used_at" in entry
    assert any("profile" in c and pname in c for c in calls)
    assert any("tools.include" in str(c) for c in calls)


def test_touch_profile_updates_timestamp(tmp_path):
    state = ProfileState(tmp_path / "profiles.json")
    pname = f"{DYNAMIC_PROFILE_PREFIX}touch1"
    state.update(pname, {"is_dynamic": True, "created_at": 100.0, "last_used_at": 100.0})

    before = time.time()
    state.touch_profile(pname)
    after = time.time()

    entry = state.get(pname)
    assert before <= entry["last_used_at"] <= after


def test_lru_eviction_purges_oldest_under_capacity_cap(tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=lambda a: "", state=state)

    # Pre-create 3 dynamic profiles
    for i, t in enumerate([10.0, 20.0, 30.0]):
        pname = f"{DYNAMIC_PROFILE_PREFIX}p{i}"
        (home / "profiles" / pname).mkdir(parents=True)
        (profiles.skills_root / pname).mkdir(parents=True)
        state.update(pname, {"is_dynamic": True, "created_at": t, "last_used_at": t})

    # Permanent profiles that MUST NOT be evicted
    (home / "profiles" / DEFAULT_PROFILE).mkdir(parents=True)
    state.update(DEFAULT_PROFILE, {"is_dynamic": False, "last_used_at": 1.0})
    (home / "profiles" / ORCHESTRATOR_PROFILE).mkdir(parents=True)
    state.update(ORCHESTRATOR_PROFILE, {"role": "orchestrator", "last_used_at": 2.0})

    # Evict for 2 needed slots with cap of 3 (current dynamic = 3, total would be 5 -> 2 excess)
    evicted = profiles.evict_lru_dynamic_profiles(needed_slots=2, max_dynamic=3)
    assert evicted == [f"{DYNAMIC_PROFILE_PREFIX}p0", f"{DYNAMIC_PROFILE_PREFIX}p1"]

    # Verify evicted directories were deleted from disk and state
    assert not (home / "profiles" / f"{DYNAMIC_PROFILE_PREFIX}p0").exists()
    assert not (home / "profiles" / f"{DYNAMIC_PROFILE_PREFIX}p1").exists()
    assert state.get(f"{DYNAMIC_PROFILE_PREFIX}p0") == {}
    assert state.get(f"{DYNAMIC_PROFILE_PREFIX}p1") == {}

    # Verify youngest profile and permanent profiles remain intact
    assert (home / "profiles" / f"{DYNAMIC_PROFILE_PREFIX}p2").exists()
    assert (home / "profiles" / DEFAULT_PROFILE).exists()
    assert (home / "profiles" / ORCHESTRATOR_PROFILE).exists()


def test_lru_eviction_protects_active_runs(tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=lambda a: "", state=state)

    # p0 is oldest (10.0) but currently active!
    p0 = f"{DYNAMIC_PROFILE_PREFIX}p0"
    p1 = f"{DYNAMIC_PROFILE_PREFIX}p1"
    (home / "profiles" / p0).mkdir(parents=True)
    (home / "profiles" / p1).mkdir(parents=True)
    state.update(p0, {"is_dynamic": True, "last_used_at": 10.0})
    state.update(p1, {"is_dynamic": True, "last_used_at": 20.0})

    # Mark p0 as active
    evicted = profiles.evict_lru_dynamic_profiles(needed_slots=1, max_dynamic=1, active_profiles={p0})
    # Must skip p0 and evict p1 instead
    assert evicted == [p1]
    assert (home / "profiles" / p0).exists()
    assert not (home / "profiles" / p1).exists()


def test_provision_dag_profiles_workflow(registry, tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    active = ActiveRuns(tmp_path / "active")
    calls = []
    runner = lambda a: calls.append(a) or ""  # noqa: E731
    settings = _settings(hermes_home=str(home), hermes_max_dynamic_profiles=5)
    profiles = HermesProfiles(settings, runner=runner, state=state)

    dag = {
        "tasks": [
            {"id": "t1", "name": "Read", "required_skills": ["file_reading"]},
            {"id": "t2", "name": "List", "required_skills": ["directory_listing"]},
            {"id": "t3", "name": "Agent Task", "required_skills": ["shell_command"], "agent_id": "soc"},
        ]
    }

    # Mock health endpoint
    import httpx
    orig_get = httpx.get
    mock_resp = MagicMock(status_code=200)
    httpx.get = lambda *args, **kwargs: mock_resp

    try:
        updated_dag, restarted = provision_dag_profiles(
            dag, registry, settings, profiles=profiles, active=active, sleep=lambda s: None
        )

        assert restarted is True
        assert ["gateway", "restart"] in calls

        t1_prof = updated_dag["tasks"][0]["_hermes_profile"]
        t2_prof = updated_dag["tasks"][1]["_hermes_profile"]
        assert t1_prof.startswith(DYNAMIC_PROFILE_PREFIX)
        assert t2_prof.startswith(DYNAMIC_PROFILE_PREFIX)
        assert t1_prof != t2_prof  # different tools produce different hashes
        assert "_hermes_profile" not in updated_dag["tasks"][2]  # agent_id task untouched

        # Second call with the same DAG when already connected -> no restart needed!
        calls.clear()
        # Mark as listed so it's ready
        state.update(t1_prof, {"mcp_listed_at": time.time()})
        state.update(t2_prof, {"mcp_listed_at": time.time()})

        _, restarted_again = provision_dag_profiles(
            dag, registry, settings, profiles=profiles, active=active, sleep=lambda s: None
        )
        assert restarted_again is False
        assert ["gateway", "restart"] not in calls

    finally:
        httpx.get = orig_get


def test_provision_dag_profiles_skips_restart_when_busy(registry, tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    active = ActiveRuns(tmp_path / "active")
    calls = []
    settings = _settings(hermes_home=str(home))
    profiles = HermesProfiles(settings, runner=lambda a: calls.append(a) or "", state=state)

    # Simulate an ongoing task in another workflow
    active.set("aiagent-busy-profile", {"workflow_id": "other_wf", "task_id": "task_9"})

    dag = {
        "tasks": [
            {"id": "t1", "name": "Inspect", "required_skills": ["file_reading"]},
        ]
    }

    _, restarted = provision_dag_profiles(
        dag, registry, settings, profiles=profiles, active=active, sleep=lambda s: None
    )
    assert restarted is False
    assert ["gateway", "restart"] not in calls


def test_purge_orphan_profiles(tmp_path):
    home = tmp_path / "hermes"
    state = ProfileState(tmp_path / "profiles.json")
    calls = []
    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=lambda a: calls.append(a) or "", state=state)

    # Create an orphan profile
    orphan_dir = home / "profiles" / "case-orchestrator"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "config.yaml").write_text("model: test", encoding="utf-8")
    state.update("case-orchestrator", {"role": "old"})

    purged = profiles.purge_orphan_profiles()
    assert "case-orchestrator" in purged
    assert not orphan_dir.exists()
    assert state.get("case-orchestrator") == {}

