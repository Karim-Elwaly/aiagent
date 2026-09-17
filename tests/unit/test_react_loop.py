"""
Unit tests for UniversalWorkerAgent ReAct loop and 5 reliability guardrails:
1. Max iterations
2. Hallucinated tool name handling
3. Tool output truncation
4. Implicit final answer
5. Timeout
"""

from unittest.mock import AsyncMock

import pytest

from src.core.llm_client import LocalLLMClient
from src.core.models import RiskLevel, Task, TaskStatus
from src.registry.tool_registry import ToolSpec
from src.workers.universal_worker import UniversalWorkerAgent


@pytest.fixture
def mock_llm():
    return AsyncMock(spec=LocalLLMClient)


@pytest.fixture
def simple_task():
    return Task(
        id="t1",
        name="Test Task",
        description="Compute 2 + 2",
        required_skills=["math"],
        expected_output="4",
        timeout_seconds=5,
    )


@pytest.fixture
def math_tool():
    async def add(a: int, b: int) -> int:
        return a + b

    return ToolSpec(
        tool_id="math_add",
        name="add",
        description="Add two numbers",
        skills_provided=["math"],
        parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
        risk_level=RiskLevel.LOW,
        function=add,
    )


@pytest.mark.asyncio
async def test_react_direct_final_answer(mock_llm, simple_task):
    mock_llm.chat.return_value = "FINAL_ANSWER: 4"
    worker = UniversalWorkerAgent(llm=mock_llm)

    result = await worker.execute(simple_task, persona="You are a math helper", tools=[])
    assert result.status == TaskStatus.COMPLETED
    assert result.output.strip() == "4"
    assert len(result.tool_calls_made) == 0


@pytest.mark.asyncio
async def test_react_implicit_final_answer(mock_llm, simple_task):
    # LLM outputs answer without prefix
    mock_llm.chat.return_value = "The sum of 2 and 2 is 4."
    worker = UniversalWorkerAgent(llm=mock_llm)

    result = await worker.execute(simple_task, persona="You are a math helper", tools=[])
    assert result.status == TaskStatus.COMPLETED
    assert "The sum of 2 and 2 is 4." in result.output


@pytest.mark.asyncio
async def test_react_tool_call_execution(mock_llm, simple_task, math_tool):
    # Iteration 1: call tool
    # Iteration 2: final answer after tool observation
    mock_llm.chat.side_effect = [
        '{"tool": "add", "args": {"a": 2, "b": 2}}',
        "FINAL_ANSWER: 4",
    ]
    worker = UniversalWorkerAgent(llm=mock_llm)

    result = await worker.execute(
        simple_task,
        persona="Math specialist",
        tools=[math_tool],
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.output.strip() == "4"
    assert result.tool_calls_made == ["add"]
    assert mock_llm.chat.call_count == 2


@pytest.mark.asyncio
async def test_guardrail_hallucinated_tool(mock_llm, simple_task, math_tool):
    # Iteration 1: call non-existent tool 'magic_solve'
    # Iteration 2: model corrects itself and calls 'add'
    # Iteration 3: final answer
    mock_llm.chat.side_effect = [
        '{"tool": "magic_solve", "args": {"q": "2+2"}}',
        '{"tool": "add", "args": {"a": 2, "b": 2}}',
        "FINAL_ANSWER: 4",
    ]
    worker = UniversalWorkerAgent(llm=mock_llm)

    result = await worker.execute(
        simple_task,
        persona="Math specialist",
        tools=[math_tool],
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.tool_calls_made == ["add"]
    assert mock_llm.chat.call_count == 3


@pytest.mark.asyncio
async def test_guardrail_max_iterations(mock_llm, simple_task, math_tool):
    # Always loop with tool calls
    mock_llm.chat.return_value = '{"tool": "add", "args": {"a": 1, "b": 1}}'
    worker = UniversalWorkerAgent(llm=mock_llm, max_iterations=3)

    result = await worker.execute(
        simple_task,
        persona="Math specialist",
        tools=[math_tool],
    )
    assert result.status == TaskStatus.COMPLETED
    assert "[Reached max 3 iterations]" in result.output
    assert len(result.tool_calls_made) == 3


@pytest.mark.asyncio
async def test_guardrail_output_truncation(mock_llm, simple_task):
    async def verbose_tool() -> str:
        return "X" * 1000

    tool = ToolSpec(
        tool_id="verbose",
        name="verbose",
        description="Verbose tool",
        skills_provided=["verbose"],
        parameters={},
        function=verbose_tool,
    )
    mock_llm.chat.side_effect = [
        '{"tool": "verbose", "args": {}}',
        "FINAL_ANSWER: Done",
    ]
    worker = UniversalWorkerAgent(llm=mock_llm, max_output_chars=100)

    result = await worker.execute(simple_task, persona="", tools=[tool])
    assert result.status == TaskStatus.COMPLETED
    # Inspect messages sent to chat in 2nd call
    call_messages = mock_llm.chat.call_args_list[1][0][0]
    observation_msg = call_messages[-1]["content"]
    assert "[...output truncated]" in observation_msg
