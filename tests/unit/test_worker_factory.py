"""
Unit tests for worker engine selection, agent model validation and the persona protocol.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.core.agent_models import AgentCreateRequest, AgentProfile, AgentUpdateRequest
from src.core.models import Task
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.tool_registry import ToolSpec
from src.workers.factory import create_worker, resolve_engine
from src.workers.hermes_agent_worker import HermesAgentWorker
from src.workers.universal_worker import UniversalWorkerAgent


def _settings(engine="universal"):
    return SimpleNamespace(
        worker_engine=engine,
        worker_max_iterations=5,
        worker_max_output_chars=1000,
        worker_max_context_chars=9000,
        hermes_api_url="http://127.0.0.1:8642",
        hermes_home="",
        hermes_bin="",
    )


def test_agent_override_beats_global_beats_default():
    assert resolve_engine(SimpleNamespace(worker_engine="hermes"), _settings("universal")) == "hermes"
    assert resolve_engine(SimpleNamespace(worker_engine=None), _settings("hermes")) == "hermes"
    assert resolve_engine(None, _settings(None)) == "universal"


def test_invalid_engine_falls_back_to_universal():
    assert resolve_engine(SimpleNamespace(worker_engine="turbo"), _settings("hermes")) == "universal"
    assert resolve_engine(None, _settings("turbo")) == "universal"


def test_create_worker_types_and_settings():
    agent = AgentProfile(id="soc", name="SOC", description="d")
    hermes = create_worker("hermes", llm=object(), settings=_settings(), agent=agent)
    assert isinstance(hermes, HermesAgentWorker)
    assert hermes.agent is agent
    assert hermes.client.base_url == "http://127.0.0.1:8642"
    assert isinstance(create_worker("universal", llm=object(), settings=_settings()), UniversalWorkerAgent)


def test_legacy_agent_json_without_field_loads():
    profile = AgentProfile.model_validate({"id": "a", "name": "A", "description": "d"})
    assert profile.worker_engine is None
    assert profile.hermes_toolsets == []


def test_agent_requests_validate_engine():
    assert AgentCreateRequest(name="a", description="d", worker_engine="Hermes").worker_engine == "hermes"
    assert AgentUpdateRequest(worker_engine="").worker_engine == ""
    with pytest.raises(ValidationError):
        AgentCreateRequest(name="a", description="d", worker_engine="turbo")


@pytest.fixture
def task():
    return Task(id="t1", name="Scan", description="Scan the disk", required_skills=["s"], expected_output="a table")


@pytest.fixture
def tools():
    return [
        ToolSpec(
            tool_id="ls",
            name="list_directory",
            description="List files",
            skills_provided=["s"],
            parameters={"path": {"type": "string", "required": True}},
            function=lambda path: path,
        )
    ]


def test_legacy_protocol_is_the_default(task, tools):
    synth = PersonaSynthesizer()
    default = synth.synthesize(task, tools)
    assert default == synth.synthesize(task, tools, protocol="legacy")
    assert '{"tool":' in default and "FINAL_ANSWER:" in default


def test_hermes_protocol_has_no_json_tool_instructions(task, tools):
    synth = PersonaSynthesizer()
    plain = AgentProfile(id="a", name="Analyst", description="Finds things")
    templated = AgentProfile(
        id="b", name="SOC", description="d", system_prompt_template="You are SOC.\n# Task\n{task_name}\n{tools}"
    )
    for prompt in (
        synth.synthesize(task, tools, protocol="hermes"),
        synth.synthesize_from_profile(plain, task, tools, protocol="hermes"),
        synth.synthesize_from_profile(templated, task, tools, protocol="hermes"),
    ):
        assert '{"tool":' not in prompt
        assert "FINAL_ANSWER:" not in prompt
        assert "# Tool Use" in prompt
        assert "mcp__aiagent__list_directory" in prompt
        assert "mcp__aiagent__request_tool" in prompt

    templated_prompt = synth.synthesize_from_profile(templated, task, tools, protocol="hermes")
    assert templated_prompt.startswith("You are SOC.\n# Task\nScan")
    assert templated_prompt.count("## `mcp__aiagent__list_directory`") == 1
