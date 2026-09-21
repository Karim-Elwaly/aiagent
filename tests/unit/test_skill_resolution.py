"""
Regression tests for skill -> tool resolution and pipeline reachability.

These guard wiring defects that unit tests of individual tools cannot catch:
a tool can be perfectly implemented and registered yet never be handed to the
worker that needs it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.models import RiskLevel
from src.registry.auto_discover import register_all_tools
from src.registry.tool_registry import ToolRegistry, ToolSpec

ROOT = Path(__file__).resolve().parents[2]


async def _noop(**_kwargs) -> str:
    return "ok"


def _spec(tool_id: str, name: str, skills: list[str]) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        name=name,
        description=f"test tool {name}",
        skills_provided=skills,
        parameters={},
        function=_noop,
        risk_level=RiskLevel.LOW,
    )


@pytest.fixture(scope="module")
def full_registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_all_tools(reg)
    return reg


# --------------------------------------------------------------------------
# resolve() must return every provider of a skill, not just the first
# --------------------------------------------------------------------------


def test_resolve_returns_all_providers_of_a_skill():
    """A skill served by several complementary tools must yield all of them."""
    reg = ToolRegistry()
    reg.register(_spec("t1", "alpha", ["shared_skill"]))
    reg.register(_spec("t2", "beta", ["shared_skill"]))
    reg.register(_spec("t3", "gamma", ["shared_skill"]))

    names = {t.name for t in reg.resolve(["shared_skill"])}
    assert names == {"alpha", "beta", "gamma"}


def test_resolve_is_not_registration_order_dependent():
    """Reversing registration order must not change the resolved tool set."""
    forward = ToolRegistry()
    forward.register(_spec("t1", "alpha", ["shared_skill"]))
    forward.register(_spec("t2", "beta", ["shared_skill"]))

    backward = ToolRegistry()
    backward.register(_spec("t2", "beta", ["shared_skill"]))
    backward.register(_spec("t1", "alpha", ["shared_skill"]))

    assert {t.name for t in forward.resolve(["shared_skill"])} == {
        t.name for t in backward.resolve(["shared_skill"])
    }


def test_resolve_caps_providers_per_skill():
    """The tool schema handed to the model stays bounded."""
    reg = ToolRegistry()
    for i in range(10):
        reg.register(_spec(f"t{i}", f"tool{i}", ["crowded_skill"]))

    assert len(reg.resolve(["crowded_skill"], max_tools_per_skill=3)) == 3


def test_resolve_deduplicates_across_skills():
    reg = ToolRegistry()
    reg.register(_spec("t1", "alpha", ["skill_a", "skill_b"]))

    resolved = reg.resolve(["skill_a", "skill_b"])
    assert len(resolved) == 1


def test_resolve_unknown_skill_returns_nothing_extra():
    reg = ToolRegistry()
    reg.register(_spec("t1", "alpha", ["skill_a"]))
    assert reg.resolve(["totally_unknown_skill_xyz"]) == []


# --------------------------------------------------------------------------
# The shipped SOC pipeline must actually receive the tools it depends on
# --------------------------------------------------------------------------


def _soc_pipeline_tasks() -> list[tuple[str, list[str]]]:
    """Extract (task name, required_skills) from the shipped 10-phase template."""
    main_py = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    start = main_py.index("soc-10-phase-investigation")
    end = main_py.find('\n        {\n            "id": "', start)
    block = main_py[start : end if end > start else len(main_py)]

    pattern = re.compile(r'"name": "([^"]+)"[\s\S]{0,500}?"required_skills": \[([^\]]*)\]')
    out = []
    for m in pattern.finditer(block):
        skills = [s.strip().strip('"\'') for s in m.group(2).split(",") if s.strip()]
        out.append((m.group(1), skills))
    return out


def test_soc_pipeline_template_has_ten_phases():
    assert len(_soc_pipeline_tasks()) == 10


def test_every_soc_phase_resolves_at_least_one_tool(full_registry: ToolRegistry):
    """A phase with no tools cannot gather evidence but will still write prose."""
    starved = [
        name for name, skills in _soc_pipeline_tasks() if not full_registry.resolve(skills)
    ]
    assert not starved, f"SOC phases resolved to zero tools: {starved}"


@pytest.mark.parametrize(
    "phase_fragment,required_tool",
    [
        ("Ingestion", "ingest_logs"),
        ("Coverage", "query_evidence"),
        ("Network", "analyze_traffic_patterns"),
        ("Network", "detect_lolbin_activity"),
        ("Identity", "analyze_auth_sequences"),
        ("Identity", "analyze_identity_velocity"),
        ("Identity", "analyze_device_posture"),
        ("Identity", "actor_pivot"),
        ("Impact", "correlate_events"),
        ("Kill-Chain", "build_attack_hypothesis"),
        ("Kill-Chain", "classify_technique"),
        ("Cross-Examination", "verify_claims_against_evidence"),
        ("Cross-Examination", "check_benign_baseline"),
        ("Cross-Examination", "query_evidence"),
        ("Cross-Examination", "score_severity"),
        ("Containment", "propose_containment_response"),
    ],
)
def test_critical_tools_reach_their_phase(
    full_registry: ToolRegistry, phase_fragment: str, required_tool: str
):
    """Each analytic must actually be handed to the phase that depends on it."""
    matches = [
        (name, skills)
        for name, skills in _soc_pipeline_tasks()
        if phase_fragment.lower() in name.lower()
    ]
    assert matches, f"No SOC phase matching {phase_fragment!r}"

    name, skills = matches[0]
    resolved = {t.name for t in full_registry.resolve(skills)}
    assert required_tool in resolved, (
        f"Phase {name!r} (skills={skills}) does not receive {required_tool!r}; "
        f"it resolved to {sorted(resolved)}"
    )


# --------------------------------------------------------------------------
# Ingestion must have a single unambiguous entry point
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill", ["evidence_gathering", "log_ingestion", "log_forensics", "log_parsing"]
)
def test_ingestion_skills_have_one_canonical_tool(full_registry: ToolRegistry, skill: str):
    """Two near-identical ingestion tools would confuse the model about which to run."""
    providers = [
        t.name for t in full_registry.get_all_tools() if skill in t.skills_provided
    ]
    assert providers == ["ingest_logs"], (
        f"Skill {skill!r} should be provided by ingest_logs alone, got {providers}"
    )


# --------------------------------------------------------------------------
# Profile filtering must not silently starve a task of tools
# --------------------------------------------------------------------------


def test_soc_profile_curates_every_pipeline_skill():
    """execute_task intersects required_skills with the profile's curated list."""
    import json

    agent = json.loads(
        (ROOT / "data" / "agents" / "soc-investigator.json").read_text(encoding="utf-8")
    )
    curated = set(agent["curated_skills"])

    missing: set[str] = set()
    for _name, skills in _soc_pipeline_tasks():
        missing |= {s for s in skills if s not in curated}

    assert not missing, (
        f"SOC profile does not curate pipeline skills {sorted(missing)}; "
        f"those phases would be filtered down and lose their tools"
    )
