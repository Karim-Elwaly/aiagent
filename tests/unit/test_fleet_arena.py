"""
Unit test suite for the Autonomous Fleet Arena (Reusable Named Hermes Agent Profiles).

Verifies:
1. Profile Naming: deterministic slugification, fleet prefix recognition, LRU eviction immunity
2. Manifest & Unit Models: FleetArenaUnit, FleetArenaManifest lifecycle states
3. Fleet Arena Store: JSON persistence, loading, listing, status updates, deletion
4. Fleet Arena Composer: 4-phase lifecycle (Plan -> Provision -> Attach Files -> Start)
5. Hermetic isolation: Fleet profiles exempt from dynamic profile LRU eviction
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import FleetArenaManifest, FleetArenaUnit, Task, TaskDAG
from src.fleet.arena import (
    FleetArenaComposer,
    _infer_arena_name,
    _infer_arena_slug,
    _infer_operational_stage,
)
from src.fleet.arena_store import FleetArenaStore
from src.hermes.profiles import (
    DEFAULT_PROFILE,
    FLEET_PROFILE_PREFIX,
    ORCHESTRATOR_PROFILE,
    fleet_profile_name,
    is_dynamic_profile_name,
    is_fleet_profile_name,
)


def test_fleet_profile_naming():
    """Verify deterministic naming and profile prefix logic."""
    name1 = fleet_profile_name("soc-alert", "Telemetry Extraction")
    assert name1 == "fleet-soc-alert-telemetry-extraction"
    assert is_fleet_profile_name(name1)
    # Crucial: fleet profiles are NOT dynamic profiles (they are persistent & exempt from LRU eviction)
    assert not is_dynamic_profile_name(name1)

    # Edge cases: special characters, spaces, excessive length
    name2 = fleet_profile_name("audit & compliance!", "Extract 100% of Financial Ledgers / Transactions")
    assert name2.startswith("fleet-audit-compliance-")
    assert is_fleet_profile_name(name2)
    assert not is_dynamic_profile_name(name2)


def test_arena_slug_and_name_inference():
    """Verify slug and name inference from user mission prompt."""
    prompt = "Investigate unauthorized credential access and lateral movement in Active Directory"
    slug = _infer_arena_slug(prompt)
    assert "investigate" in slug or "unauthorized" in slug
    assert len(slug) <= 24

    name = _infer_arena_name(prompt)
    assert name.endswith("Arena")

    stage_recon = _infer_operational_stage(0, 4, "Ingest cloud audit logs")
    assert stage_recon == "RECON_INGESTION"

    stage_synth = _infer_operational_stage(3, 4, "Final Investigation Report")
    assert stage_synth == "DELIVERABLE_SYNTHESIS"

    stage_verify = _infer_operational_stage(1, 4, "Correlate and verify suspicious hashes")
    assert stage_verify == "CROSS_VERIFICATION"


def test_arena_store_crud():
    """Verify persistent file-based JSON storage of Fleet Arena manifests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FleetArenaStore(root=Path(tmpdir))

        unit = FleetArenaUnit(
            profile_name="fleet-test-analyst",
            unit_codename="ANALYST",
            task_id="t1",
            task_name="Analyze Data",
            operational_stage="DEEP_ANALYSIS",
            scoped_tools=["search_tool"],
            required_skills=["analysis"],
            description="Analyzes input logs",
            input_contract="Input logs",
            output_contract="Analysis report",
            profile_exists=False,
        )

        manifest = FleetArenaManifest(
            arena_id="arena-test-123",
            arena_name="Test Arena",
            arena_slug="test",
            mission_prompt="Analyze logs",
            units=[unit],
            dag={"tasks": [{"id": "t1", "name": "Analyze Data"}]},
            status="draft",
            created_at=time.time(),
            profiles_to_create=["fleet-test-analyst"],
            profiles_existing=[],
        )

        # Save
        store.save(manifest)
        assert (Path(tmpdir) / "arena-test-123.json").is_file()

        # Load
        loaded = store.load("arena-test-123")
        assert loaded is not None
        assert loaded.arena_id == "arena-test-123"
        assert len(loaded.units) == 1
        assert loaded.units[0].profile_name == "fleet-test-analyst"
        assert loaded.status == "draft"

        # Update status
        updated = store.update_status("arena-test-123", "provisioned")
        assert updated is not None
        assert updated.status == "provisioned"

        # List all
        all_arenas = store.list_all()
        assert len(all_arenas) == 1
        assert all_arenas[0].status == "provisioned"

        # Delete
        deleted = store.delete("arena-test-123")
        assert deleted is True
        assert store.load("arena-test-123") is None


def test_arena_attach_files():
    """Verify Phase 3 file attachment enriches unit attachments and DAG task descriptions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FleetArenaStore(root=Path(tmpdir))
        composer = FleetArenaComposer(store=store)

        unit1 = FleetArenaUnit(
            profile_name="fleet-audit-parser",
            unit_codename="PARSER",
            task_id="t1",
            task_name="Parse Audit Log",
            description="Extract log entries",
        )
        unit2 = FleetArenaUnit(
            profile_name="fleet-audit-synthesizer",
            unit_codename="SYNTHESIZER",
            task_id="t2",
            task_name="Synthesize Report",
            description="Generate audit report",
        )

        manifest = FleetArenaManifest(
            arena_id="arena-audit-456",
            arena_name="Audit Arena",
            arena_slug="audit",
            mission_prompt="Audit system",
            units=[unit1, unit2],
            dag={
                "tasks": [
                    {"id": "t1", "name": "Parse Audit Log", "description": "Extract log entries"},
                    {"id": "t2", "name": "Synthesize Report", "description": "Generate audit report"},
                ]
            },
            status="provisioned",
            created_at=time.time(),
        )
        store.save(manifest)

        # Attach file to task t1
        attachments = {
            "t1": [
                {
                    "filename": "security_events.json",
                    "file_path": "/var/log/security_events.json",
                    "extracted_text": '{"event_id": 4624, "account": "admin"}',
                }
            ]
        }
        updated = composer.attach_files("arena-audit-456", attachments)

        assert updated.status == "files_attached"
        assert len(updated.units[0].attached_files) == 1
        assert updated.units[0].attached_files[0]["filename"] == "security_events.json"

        # Verify DAG task description was enriched with the attached file content
        enriched_dag = composer.get_enriched_dag("arena-audit-456")
        task1 = enriched_dag["tasks"][0]
        assert "Attached Files:" in task1["description"]
        assert "security_events.json" in task1["description"]
        assert '{"event_id": 4624, "account": "admin"}' in task1["description"]


def test_fleet_profile_eviction_immunity():
    """Verify HermesProfiles.evict_lru_dynamic_profiles never evicts fleet-* profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.hermes.profiles import HermesProfiles

        settings = MagicMock()
        settings.hermes_profiles_dir = tmpdir
        settings.hermes_home = tmpdir
        settings.hermes_max_dynamic_profiles = 2
        settings.worker_engine = "hermes"
        settings.llm_model = "test-model"

        hp = HermesProfiles(settings)

        # Create dummy profile dirs in home/profiles
        profiles_dir = hp.home / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        # Create 2 dynamic profiles and 2 fleet profiles
        (profiles_dir / "uaos-aeu-1111").mkdir()
        (profiles_dir / "uaos-aeu-2222").mkdir()
        (profiles_dir / "fleet-soc-analyst").mkdir()
        (profiles_dir / "fleet-soc-hunter").mkdir()

        # Register in state with timestamps
        hp.state.update("uaos-aeu-1111", {"last_used_at": 100.0})
        hp.state.update("uaos-aeu-2222", {"last_used_at": 200.0})
        hp.state.update("fleet-soc-analyst", {"last_used_at": 50.0})
        hp.state.update("fleet-soc-hunter", {"last_used_at": 60.0})

        # Request eviction of 1 dynamic profile
        evicted = hp.evict_lru_dynamic_profiles(needed_slots=1, max_dynamic=2)

        # Only uaos-aeu-1111 should be candidate / evicted
        assert "uaos-aeu-1111" in evicted
        # Fleet profiles must NEVER be evicted!
        assert "fleet-soc-analyst" not in evicted
        assert "fleet-soc-hunter" not in evicted
        assert (profiles_dir / "fleet-soc-analyst").is_dir()
        assert (profiles_dir / "fleet-soc-hunter").is_dir()


def test_delete_fleet_profile():
    """Verify HermesProfiles.delete_profile can delete fleet-* profiles but preserves permanent profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.hermes.profiles import HermesProfiles

        settings = MagicMock()
        settings.hermes_profiles_dir = tmpdir
        settings.hermes_home = tmpdir
        settings.worker_engine = "hermes"
        settings.llm_model = "test-model"

        hp = HermesProfiles(settings)
        profiles_dir = hp.home / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        fleet_prof = profiles_dir / "fleet-soc-test"
        fleet_prof.mkdir()
        hp.state.update("fleet-soc-test", {"last_used_at": 100.0})

        # Can delete fleet profile
        res = hp.delete_profile("fleet-soc-test")
        assert res is True
        assert not fleet_prof.exists()

        # Cannot delete permanent profiles
        assert hp.delete_profile(DEFAULT_PROFILE) is False
        assert hp.delete_profile(ORCHESTRATOR_PROFILE) is False


def test_clone_arena():
    """Verify FleetArenaComposer.clone_arena duplicates topology, clears attachments, and starts provisioned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.hermes.profiles import HermesProfiles

        settings = MagicMock()
        settings.hermes_profiles_dir = tmpdir
        settings.hermes_home = tmpdir
        settings.worker_engine = "hermes"
        settings.llm_model = "test-model"

        store = FleetArenaStore(root=Path(tmpdir))
        composer = FleetArenaComposer(settings=settings, store=store)

        unit1 = FleetArenaUnit(
            profile_name="fleet-soc-analyst",
            unit_codename="ANALYST",
            task_id="t1",
            task_name="Extract Logs",
            operational_stage="RECON_INGESTION",
            scoped_tools=["search_tool"],
            required_skills=["analysis"],
            description="Analyzes input logs",
            input_contract="Input logs",
            output_contract="Analysis report",
            profile_exists=True,
            attached_files=[{"filename": "old_logs.txt", "file_path": "/path/old_logs.txt"}],
        )

        orig_manifest = FleetArenaManifest(
            arena_id="arena-soc-original",
            arena_name="Original SOC Fleet",
            arena_slug="soc-original",
            mission_prompt="Investigate original incident",
            units=[unit1],
            dag={
                "tasks": [
                    {
                        "id": "t1",
                        "name": "Extract Logs",
                        "description": "Original desc with old_logs.txt attached:\n--- ATTACHED FILE old_logs.txt ---\nDATA",
                        "agent_id": "fleet-soc-analyst",
                    }
                ]
            },
            status="completed",
            profiles_existing=["fleet-soc-analyst"],
            profiles_to_create=[],
        )
        store.save(orig_manifest)

        # Create dummy profile in tmpdir so _list_existing_fleet_profiles finds it
        p_dir = Path(tmpdir) / "profiles" / "fleet-soc-analyst"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "config.yaml").write_text("model: test-model\n")

        cloned = composer.clone_arena(
            "arena-soc-original",
            new_name="Incident #202 Reusable Fleet",
            new_prompt="Investigate incident #202 in AWS VPC",
        )

            # Verified properties
            assert cloned.arena_id != "arena-soc-original"
            assert cloned.arena_name == "Incident #202 Reusable Fleet"
            assert cloned.mission_prompt == "Investigate incident #202 in AWS VPC"
            # Since profile exists in Hermes, status is immediately provisioned (0 restarts needed)
            assert cloned.status == "provisioned"
            assert cloned.profiles_existing == ["fleet-soc-analyst"]
            assert cloned.profiles_to_create == []

            # Unit verification
            assert len(cloned.units) == 1
            cloned_unit = cloned.units[0]
            assert cloned_unit.profile_name == "fleet-soc-analyst"
            assert cloned_unit.profile_exists is True
            # Crucial: previous phase attachments are stripped out for the fresh run
            assert cloned_unit.attached_files == []

            # Clean DAG verification
            cloned_task = cloned.dag["tasks"][0]
            assert "old_logs.txt" not in cloned_task["description"]

            # Persistent store verification
            loaded = store.load(cloned.arena_id)
            assert loaded is not None
            assert loaded.arena_id == cloned.arena_id
            assert loaded.arena_name == "Incident #202 Reusable Fleet"

