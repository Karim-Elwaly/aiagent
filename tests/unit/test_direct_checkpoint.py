"""Unit tests for the direct-engine disk checkpoint store."""

import importlib

import pytest


@pytest.fixture()
def checkpoint_mod(tmp_path, monkeypatch):
    """Load the checkpoint module with its directory redirected to a temp path."""
    import src.orchestrator.direct_checkpoint as cp

    cp = importlib.reload(cp)
    monkeypatch.setattr(cp, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    return cp


def _state(workflow_id="uaos-abc123", status="running", completed=None):
    return {
        "workflow_id": workflow_id,
        "query": "investigate logs",
        "agent_id": "",
        "resilience": "standard",
        "custom_dag": None,
        "dag": {"tasks": [{"id": "t1"}, {"id": "t2"}]},
        "completed": completed or {"t1": "done"},
        "task_statuses": {"t1": "completed", "t2": "pending"},
        "supervisor_evaluations": [],
        "status": status,
    }


def test_save_and_load_round_trip(checkpoint_mod):
    cp = checkpoint_mod
    state = _state()
    cp.save_checkpoint(state)
    loaded = cp.load_checkpoint("uaos-abc123")
    assert loaded is not None
    assert loaded["completed"] == {"t1": "done"}
    assert loaded["dag"]["tasks"][0]["id"] == "t1"
    assert loaded["status"] == "running"


def test_load_missing_returns_none(checkpoint_mod):
    assert checkpoint_mod.load_checkpoint("uaos-does-not-exist") is None


def test_save_without_workflow_id_is_noop(checkpoint_mod):
    cp = checkpoint_mod
    cp.save_checkpoint({"status": "running"})  # no workflow_id
    assert cp.list_resumable() == []


def test_delete_checkpoint(checkpoint_mod):
    cp = checkpoint_mod
    cp.save_checkpoint(_state())
    cp.delete_checkpoint("uaos-abc123")
    assert cp.load_checkpoint("uaos-abc123") is None


def test_mark_status_updates_field(checkpoint_mod):
    cp = checkpoint_mod
    cp.save_checkpoint(_state(status="running"))
    cp.mark_status("uaos-abc123", cp.STATUS_FAILED)
    assert cp.load_checkpoint("uaos-abc123")["status"] == cp.STATUS_FAILED


def test_list_resumable_only_running(checkpoint_mod):
    cp = checkpoint_mod
    cp.save_checkpoint(_state(workflow_id="uaos-run1", status="running"))
    cp.save_checkpoint(_state(workflow_id="uaos-done1", status="completed"))
    cp.save_checkpoint(_state(workflow_id="uaos-run2", status="running"))
    ids = sorted(s["workflow_id"] for s in cp.list_resumable())
    assert ids == ["uaos-run1", "uaos-run2"]


def test_atomic_overwrite_preserves_latest(checkpoint_mod):
    cp = checkpoint_mod
    cp.save_checkpoint(_state(completed={"t1": "v1"}))
    cp.save_checkpoint(_state(completed={"t1": "v1", "t2": "v2"}))
    loaded = cp.load_checkpoint("uaos-abc123")
    assert loaded["completed"] == {"t1": "v1", "t2": "v2"}
    # Exactly one checkpoint file, no leftover temp files.
    files = list((cp.CHECKPOINT_DIR).glob("*"))
    assert len(files) == 1
    assert files[0].name.endswith(".json")
