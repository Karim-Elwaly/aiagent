"""
Unit tests for PersonaSynthesizer: dynamic system prompt generation,
tool description injection, and upstream context truncation.
"""

import re

from src.core.models import RiskLevel, Task
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.tool_registry import ToolSpec


async def dummy_calc(expression: str) -> str:
    return "42"


def test_synthesize_with_tools():
    synth = PersonaSynthesizer()
    task = Task(
        id="t1",
        name="Calculate Metrics",
        description="Compute sum of numbers",
        required_skills=["math"],
        expected_output="Total sum",
    )
    tools = [
        ToolSpec(
            tool_id="calculator_tool",
            name="calculator",
            description="Performs arithmetic",
            skills_provided=["math"],
            parameters={
                "expression": {
                    "type": "string",
                    "description": "Math expression",
                    "required": True,
                }
            },
            risk_level=RiskLevel.LOW,
            function=dummy_calc,
        )
    ]

    prompt = synth.synthesize(task, tools)

    assert "Calculate Metrics" in prompt
    assert "Compute sum of numbers" in prompt
    assert "calculator" in prompt
    assert "Math expression" in prompt
    assert "FINAL_ANSWER:" in prompt
    assert "CANNOT_COMPLETE:" in prompt


def test_synthesize_without_tools():
    synth = PersonaSynthesizer()
    task = Task(
        id="t1",
        name="Direct Reasoning",
        description="Think through a problem",
        required_skills=[],
        expected_output="Insights",
    )

    prompt = synth.synthesize(task, tools=[])
    assert "No tools available" in prompt
    assert "Direct Reasoning" in prompt


def test_synthesize_with_upstream_context_and_truncation():
    max_chars = 200
    synth = PersonaSynthesizer(max_context_chars=max_chars)
    task = Task(
        id="t2",
        name="Summarize Research",
        description="Summarize previous findings",
        required_skills=[],
        expected_output="Summary",
    )

    long_context = "A" * 500
    upstream = {"t1": long_context}

    prompt = synth.synthesize(task, tools=[], upstream_context=upstream)

    assert "Context from Prior Tasks" in prompt
    assert "From task `t1`:" in prompt
    assert "[...truncated" in prompt
    # The upstream context itself must be truncated to max_chars; the rest of
    # the prompt is fixed scaffolding (role, rules, grounding contract).
    assert long_context not in prompt
    longest_run = max(len(run) for run in re.findall(r"A+", prompt))
    assert longest_run <= max_chars
