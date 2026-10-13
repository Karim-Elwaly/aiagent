"""Unit tests for per-run skills, tool-group profiles and orchestration on Hermes."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from src.core.agent_models import AgentProfile
from src.core.agent_store import AgentStore
from src.hermes.active_runs import ActiveRuns
from src.hermes.bundles import BUNDLES, bundle_profile, bundle_tools, select_bundle
from src.hermes.client import HermesAPIError
from src.hermes.llm import HermesLLMClient, split_messages
from src.hermes.mcp_server import ToolGate
from src.hermes.profiles import ORCHESTRATOR_PROFILE, HermesProfiles, ProfileState
from src.hermes.provision import provision_profiles
from src.hermes.skills import skill_documents
from src.registry.tool_registry import ToolRegistry, ToolSpec


def _settings(tmp_path, **kw):
    base = dict(hermes_api_url="http://h", hermes_home=str(tmp_path / "hermes"), hermes_bin="hermes",
                hermes_mcp_url="http://127.0.0.1:8000/mcp/", hermes_default_toolsets=[],
                hermes_run_timeout_seconds=30, worker_max_context_chars=12000, worker_engine="hermes",
                hermes_tool_bundles=True, hermes_orchestration=True, hermes_orchestration_timeout_seconds=5)
    base.update(kw)
    return SimpleNamespace(**base)


def _spec(name, skills):
    return ToolSpec(tool_id=name, name=name, description=f"{name} tool", skills_provided=skills,
                    parameters={}, function=lambda **_: "ok")


def _profiles(tmp_path, calls=None, **kw):
    def runner(args):
        if calls is not None:
            calls.append(args)
        if args[:2] == ["profile", "create"]:  # what the hermes CLI does
            (tmp_path / "hermes" / "profiles" / args[2]).mkdir(parents=True, exist_ok=True)
        return ""

    return HermesProfiles(_settings(tmp_path, **kw), runner=runner, state=ProfileState(tmp_path / "profiles.json"),
                          skills_root=tmp_path / "skills")


# ── per-run skills ───────────────────────────────────────────


def test_skill_documents_keep_only_the_tasks_tools_and_skills(tmp_path):
    reg = ToolRegistry()
    reg.register(_spec("read_file", ["file_reading"]))
    reg.register(_spec("execute_command", ["shell_command"]))
    imported = tmp_path / "imported"
    imported.mkdir()
    for name, skills in (("stripe_payments", "payments"), ("log_helper", "log_forensics")):
        (imported / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: d\nskills: [{skills}]\n---\nSteps.\n", encoding="utf-8")

    everything = skill_documents(None, reg, imported)
    assert {"aiagent-read-file", "aiagent-execute-command", "stripe-payments", "log-helper"} <= set(everything)

    focused = skill_documents(None, reg, imported, focus_tools={"read_file"}, focus_skills={"log_forensics"})
    assert set(focused) == {"aiagent-read-file", "log-helper"}


# ── tool groups ──────────────────────────────────────────────


def test_select_bundle_picks_the_smallest_group_covering_the_tools():
    assert select_bundle({"list_directory"}) == "files"
    assert select_bundle({"gather_log_evidence", "read_file"}) == "security"
    assert select_bundle({"read_file", "execute_command"}) is None
    assert select_bundle({"some_connector_tool"}) is None
    assert select_bundle(set()) == min(BUNDLES, key=lambda b: (len(BUNDLES[b]), b))


def test_bundle_profile_filters_tools_and_is_ready_only_after_hermes_lists_them(tmp_path):
    calls: list = []
    profiles = _profiles(tmp_path, calls)
    (tmp_path / "hermes" / "profiles" / "aiagent-bundle-files").mkdir(parents=True)
    info = profiles.ensure(None, [], None, bundle="files")
    assert info.name == bundle_profile("files") == "aiagent-bundle-files" and info.changed
    include = ["-p", "aiagent-bundle-files", "config", "set", "mcp_servers.aiagent.tools.include",
               '["read_file", "write_file", "list_directory", "get_disk_usage", "delete_file"]']
    assert include in calls
    assert profiles.state.get("aiagent-bundle-files")["bundle"] == bundle_tools("files")

    assert not profiles.bundle_ready("files")  # Hermes has not listed the tools yet
    profiles.state.update("aiagent-bundle-files", {"mcp_listed_at": time.time() + 1})
    assert profiles.bundle_ready("files")

    calls.clear()
    assert not profiles.ensure(None, [], None, bundle="files").changed
    assert include not in calls


def test_gate_shows_a_group_profile_only_its_tools(tmp_path):
    reg = ToolRegistry()
    for name in ("list_directory", "read_file", "execute_command"):
        reg.register(_spec(name, [name]))
    gate = ToolGate(reg, _settings(tmp_path), state=ProfileState(tmp_path / "p.json"),
                    active=ActiveRuns(tmp_path / "active"), store=AgentStore(storage_dir=tmp_path / "agents"),
                    ask=None)
    entry = {"profile": "aiagent-bundle-files", "agent_id": "", "bundle": ["list_directory", "read_file"]}
    assert {t.name for t in gate.exposed_tools(entry)} == {"list_directory", "read_file"}


def test_low_risk_tools_of_the_tasks_group_need_no_approval(tmp_path):
    from src.core.models import RiskLevel

    reg = ToolRegistry()
    for name, risk in (("list_directory", RiskLevel.LOW), ("read_file", RiskLevel.LOW),
                       ("execute_command", RiskLevel.HIGH)):
        spec = _spec(name, [name])
        spec.risk_level = risk
        reg.register(spec)
    gate = ToolGate(reg, _settings(tmp_path), state=ProfileState(tmp_path / "p.json"),
                    active=ActiveRuns(tmp_path / "active"), store=AgentStore(storage_dir=tmp_path / "agents"),
                    ask=None)
    entry = {"profile": "aiagent-bundle-files", "agent_id": "",
             "bundle": ["list_directory", "read_file", "execute_command"]}
    allowed = gate.allowed(entry, {"task_tools": ["list_directory"], "workflow_id": "w"})
    assert allowed == {"list_directory", "read_file"}  # execute_command still asks the operator


def test_worker_uses_a_group_only_when_it_is_ready(tmp_path):
    from src.workers.hermes_agent_worker import HermesAgentWorker

    ready = {"files": False}
    profiles = SimpleNamespace(bundle_ready=lambda b: ready.get(b, False))
    worker = HermesAgentWorker(_settings(tmp_path), client=SimpleNamespace(), profiles=profiles)
    tools = [_spec("list_directory", ["directory_listing"])]
    assert worker._ready_bundle(tools, []) is None
    ready["files"] = True
    assert worker._ready_bundle(tools, []) == "files"
    assert HermesAgentWorker(_settings(tmp_path, hermes_tool_bundles=False), client=SimpleNamespace(),
                             profiles=profiles)._ready_bundle(tools, []) is None
    agent = AgentProfile(id="a", name="A", description="d")
    assert HermesAgentWorker(_settings(tmp_path), agent=agent, client=SimpleNamespace(),
                             profiles=profiles)._ready_bundle(tools, []) is None


# ── provisioning ─────────────────────────────────────────────


def test_provisioning_creates_profiles_and_restarts_the_gateway_once_when_idle(tmp_path):
    calls: list = []
    profiles = _profiles(tmp_path, calls)
    active = ActiveRuns(tmp_path / "active")
    active.set("aiagent-default", {"task_id": "t1"})
    sleeps: list = []

    def sleep(seconds):
        sleeps.append(seconds)
        active.clear("aiagent-default")  # the busy run finishes while provisioning waits

    assert provision_profiles(_settings(tmp_path), profiles, active, sleep=sleep, quiet_seconds=0) is True
    assert sleeps and calls.count(["gateway", "restart"]) == 1
    assert profiles.state.gateway_restarted_at() > 0

    calls.clear()
    for bundle in BUNDLES:  # Hermes lists each group's tools when the gateway starts
        profiles.state.update(bundle_profile(bundle), {"mcp_listed_at": time.time() + 1})
    assert provision_profiles(_settings(tmp_path), profiles, active, sleep=sleep, quiet_seconds=0) is False
    assert ["gateway", "restart"] not in calls


def test_provisioning_waits_out_the_gap_between_two_runs_of_a_workflow(tmp_path):
    calls: list = []
    profiles = _profiles(tmp_path, calls)
    active = ActiveRuns(tmp_path / "active")
    active.set("aiagent-default", {"task_id": "t1"})
    active.clear("aiagent-default")  # the run just ended; the supervisor check and the next task follow
    assert provision_profiles(_settings(tmp_path), profiles, active, sleep=lambda s: None, idle_wait_seconds=10,
                              quiet_seconds=3600) is False
    assert ["gateway", "restart"] not in calls


def test_provisioning_is_skipped_when_hermes_is_not_in_use(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.agent_store.AgentStore.list_all", lambda self: [])
    calls: list = []
    assert provision_profiles(_settings(tmp_path, worker_engine="universal"), _profiles(tmp_path, calls)) is False
    assert calls == []


# ── orchestration on Hermes ──────────────────────────────────


def test_split_messages_separates_instructions_from_the_conversation():
    assert split_messages([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]) == ("S", "U")
    system, text = split_messages([{"role": "system", "content": "S"}, {"role": "user", "content": "one"},
                                   {"role": "user", "content": "two"}])
    assert system == "S" and "### user\none" in text and text.endswith("Reply to the last user message.")


class FakeHermes:
    def __init__(self, outcomes):
        self.outcomes, self.created, self.stopped = list(outcomes), [], []

    async def create_run(self, profile, key, input_text, instructions=None, session_id=None):
        self.created.append({"profile": profile, "input": input_text, "instructions": instructions})
        return f"run_{len(self.created)}"

    async def events(self, profile, key, run_id, last_seq=-1):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    async def get_run(self, *a):
        return {}

    async def stop_run(self, profile, key, run_id):
        self.stopped.append(run_id)


class Direct:
    def __init__(self):
        self.calls = []

    async def chat(self, messages):
        self.calls.append(messages)
        return "direct"


def _llm(tmp_path, outcomes, **kw):
    hermes = FakeHermes(outcomes)
    direct = Direct()
    profiles = SimpleNamespace(ensure_orchestrator=lambda: SimpleNamespace(api_key="k"))
    return HermesLLMClient(_settings(tmp_path, **kw), fallback=direct, profiles=profiles, client=hermes), hermes, direct


MESSAGES = [{"role": "system", "content": "Plan as JSON"}, {"role": "user", "content": "Investigate"}]


async def test_orchestration_call_runs_on_the_orchestrator_profile(tmp_path):
    llm, hermes, direct = _llm(tmp_path, [{"event": "run.completed", "output": ' {"tasks": []} ', "seq": 0}])
    assert await llm.chat(MESSAGES) == '{"tasks": []}'
    sent = hermes.created[0]
    assert sent["profile"] == ORCHESTRATOR_PROFILE and sent["input"] == "Investigate"
    assert sent["instructions"].endswith("Plan as JSON") and "No tools are available" in sent["instructions"]
    assert direct.calls == []


async def test_orchestration_retries_model_errors_then_falls_back(tmp_path):
    peg = {"event": "run.failed", "error": '{"code":500,"type":"server_error"}', "seq": 0}
    llm, hermes, direct = _llm(tmp_path, [dict(peg), {"event": "run.completed", "output": "ok", "seq": 0}])
    assert await llm.chat(MESSAGES) == "ok" and len(hermes.created) == 2

    llm, hermes, direct = _llm(tmp_path, [dict(peg), dict(peg), dict(peg)])
    assert await llm.chat(MESSAGES) == "direct" and len(hermes.created) == 3 and len(direct.calls) == 1


async def test_orchestration_falls_back_when_hermes_is_unavailable(tmp_path):
    llm, _, direct = _llm(tmp_path, [HermesAPIError("rejected the profile's API key (401)")])
    assert await llm.chat(MESSAGES) == "direct" and len(direct.calls) == 1


async def test_orchestration_timeout_stops_the_run_and_raises(tmp_path):
    llm, hermes, direct = _llm(tmp_path, [], hermes_orchestration_timeout_seconds=0.05)

    async def hang(profile, key, run_id, last_seq=-1):
        await asyncio.Event().wait()
        yield {}

    hermes.events = hang
    with pytest.raises(TimeoutError):
        await llm.chat(MESSAGES)
    assert hermes.stopped == ["run_1"] and direct.calls == []


def test_orchestration_client_follows_the_runs_engine(tmp_path, monkeypatch):
    from src.hermes.llm import HermesLLMClient as Hermes
    from src.orchestrator import activities

    direct = Direct()
    monkeypatch.setattr(activities, "_get_planner_llm", lambda: direct)
    monkeypatch.setattr("src.core.agent_store.AgentStore.load", lambda self, aid: None)
    monkeypatch.setattr(activities, "get_settings", lambda: _settings(tmp_path))
    assert isinstance(activities.get_orchestration_llm(""), Hermes)
    monkeypatch.setattr(activities, "get_settings", lambda: _settings(tmp_path, worker_engine="universal"))
    assert activities.get_orchestration_llm("") is direct
    monkeypatch.setattr(activities, "get_settings", lambda: _settings(tmp_path, hermes_orchestration=False))
    assert activities.get_orchestration_llm("") is direct
