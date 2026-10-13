"""Unit tests for per-task agents, uncurated-skill handling and the Hermes <-> AgentHub catalog."""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.brain.meta_planner import MetaPlanner
from src.core.agent_models import AgentProfile
from src.core.models import Task, TaskDAG
from src.hermes.catalog import CatalogError, HermesCatalog
from src.hermes.profiles import HermesProfiles, ProfileState
from src.hermes.skills import skill_documents
from src.registry.tool_registry import ToolRegistry, ToolSpec
from src.workers.hermes_agent_worker import HermesAgentWorker


def _settings(tmp_path, **kw):
    base = dict(hermes_api_url="http://h", hermes_home=str(tmp_path / "hermes"), hermes_bin="hermes",
                hermes_mcp_url="http://127.0.0.1:8000/mcp/", hermes_default_toolsets=[],
                hermes_run_timeout_seconds=30, worker_max_context_chars=12000)
    base.update(kw)
    return SimpleNamespace(**base)


def _spec(name, skills):
    return ToolSpec(tool_id=name, name=name, description=f"{name} tool", skills_provided=skills,
                    parameters={}, function=lambda **_: "ok")


# ── Hermes run input ─────────────────────────────────────────


def test_run_input_has_parameters_and_tools_needing_approval(tmp_path):
    worker = HermesAgentWorker(_settings(tmp_path), client=SimpleNamespace(), profiles=SimpleNamespace())
    task = Task(id="t1", name="Scan", description="d", required_skills=["s"],
                parameters={"target_path": "D:\\logs", "max_files": 5})
    text = worker._user_content(task, [], "", None, [_spec("execute_command", ["system_command"])])
    assert '# Task Parameters\n{"target_path": "D:\\\\logs", "max_files": 5}' in text
    assert "# Tools That Need Operator Approval\nmcp__aiagent__execute_command" in text
    assert "None assigned" not in text


# ── planner agent roster ─────────────────────────────────────


def test_planner_lists_agents_and_drops_unknown_or_default_assignments():
    planner = MetaPlanner(llm=None, available_skills=["a"], default_agent_id="soc",
                          agents=[{"id": "soc", "name": "SOC", "description": "d", "skills": ["a"]},
                                  {"id": "fw", "name": "Firewall", "description": "rules", "skills": ["b"]}])
    section = planner._agents_section()
    assert "## Available Agents" in section and "- fw (Firewall): rules Skills: b" in section
    dag = TaskDAG(goal="g", reasoning="r", tasks=[
        Task(id="t1", name="a", description="d", required_skills=["a"], agent_id="fw"),
        Task(id="t2", name="b", description="d", required_skills=["a"], agent_id="ghost"),
        Task(id="t3", name="c", description="d", required_skills=["a"], agent_id="soc"),
    ])
    planner._check_agents(dag)
    assert [t.agent_id for t in dag.tasks] == ["fw", None, None]


def test_planner_scope_unions_curated_skills(monkeypatch):
    from src.orchestrator import activities

    agents = [AgentProfile(id="soc", name="SOC", description="d", curated_skills=["a"]),
              AgentProfile(id="fw", name="FW", description="d", curated_skills=["b"])]
    monkeypatch.setattr("src.core.agent_store.AgentStore.list_all", lambda self: agents)
    registry = SimpleNamespace(list_skills=lambda: ["a", "b", "c"])
    skills, roster = activities._planner_scope(registry, "soc")
    assert skills == ["a", "b"] and [r["id"] for r in roster] == ["soc", "fw"]
    assert activities._planner_scope(registry, "")[0] == ["a", "b", "c"]


# ── profiles: disabled Hermes skills ─────────────────────────


def test_ensure_applies_disabled_hermes_skills_once(tmp_path):
    home = tmp_path / "hermes"
    (home / "profiles" / "aiagent-soc").mkdir(parents=True)
    calls = []
    profiles = HermesProfiles(_settings(tmp_path), runner=lambda a: calls.append(a) or "",
                              state=ProfileState(tmp_path / "profiles.json"), skills_root=tmp_path / "skills")
    agent = AgentProfile(id="soc", name="SOC", description="d", hermes_disabled_skills=["godmode"])
    profiles.ensure("soc", [], {}, agent=agent)
    disable = ["-p", "aiagent-soc", "config", "set", "skills.platform_disabled.api_server", '["godmode"]']
    assert disable in calls
    calls.clear()
    profiles.ensure("soc", [], {}, agent=agent)
    assert disable not in calls


# ── catalog ─────────────────────────────────────────────────


def _write_skill(path, name, description):
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nSteps.\n", encoding="utf-8")


def _catalog(tmp_path, runner=None):
    profiles = HermesProfiles(_settings(tmp_path), runner=runner or (lambda a: ""),
                              state=ProfileState(tmp_path / "profiles.json"), skills_root=tmp_path / "skills")
    return HermesCatalog(profiles, client=SimpleNamespace())


def test_catalog_lists_skills_with_source_and_enabled_state(tmp_path):
    pdir = tmp_path / "hermes" / "profiles" / "aiagent-soc"
    skills = pdir / "skills"
    _write_skill(skills / "security" / "godmode", "godmode", "Hub skill")
    _write_skill(skills / "research" / "arxiv", "arxiv", "Bundled")
    _write_skill(skills / "notes", "my-notes", "Local")
    _write_skill(skills / ".curator_backups" / "old", "old", "ignored")
    (skills / ".bundled_manifest").write_text("arxiv:abc\n", encoding="utf-8")
    (skills / ".hub").mkdir()
    (skills / ".hub" / "lock.json").write_text(json.dumps({"installed": {"godmode": {
        "trust_level": "builtin", "scan_verdict": "caution"}}}), encoding="utf-8")
    (pdir / "config.yaml").write_text("skills:\n  platform_disabled:\n    api_server: [arxiv]\n", encoding="utf-8")
    _write_skill(tmp_path / "skills" / "aiagent-soc" / "aiagent-read-file", "aiagent-read-file", "aiagent tool")

    found = {s["name"]: s for s in _catalog(tmp_path).skills("aiagent-soc")}
    assert set(found) == {"godmode", "arxiv", "my-notes", "aiagent-read-file"}
    assert found["godmode"]["source"] == "hub" and found["godmode"]["scan_verdict"] == "caution"
    assert found["arxiv"]["source"] == "builtin" and not found["arxiv"]["enabled"]
    assert found["my-notes"]["source"] == "local" and found["my-notes"]["enabled"]
    assert found["aiagent-read-file"]["source"] == "aiagent"


def test_catalog_rejects_unsafe_names_and_never_forces_installs(tmp_path):
    calls = []
    catalog = _catalog(tmp_path, runner=lambda a: calls.append(a) or "done")
    catalog.install("aiagent-soc", "official/security/godmode")
    assert calls[-1] == ["-p", "aiagent-soc", "skills", "install", "official/security/godmode", "--yes"]
    for bad in ("--force", "a b", "../x"):
        try:
            catalog.uninstall("aiagent-soc", bad)
        except CatalogError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_imported_hermes_skill_is_not_exported_back(tmp_path, monkeypatch):
    import src.hermes.skills as hs
    import src.registry.hermes.hermes_loader as loader

    monkeypatch.setattr(hs, "HERMES_ORIGIN_FILE", tmp_path / "origin.json")
    monkeypatch.setattr(loader, "HERMES_SKILLS_DIR", tmp_path / "imported")
    _write_skill(tmp_path / "hermes" / "profiles" / "aiagent-soc" / "skills" / "research" / "arxiv", "arxiv",
                 "Search papers")
    spec = _catalog(tmp_path).import_skill("aiagent-soc", "arxiv", ToolRegistry())
    assert (tmp_path / "imported" / f"{spec.name}.md").exists()
    docs = skill_documents(None, None, imported_dir=tmp_path / "imported")
    assert spec.name not in docs and "arxiv" not in docs
