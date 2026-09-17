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


@pytest.mark.asyncio
async def test_react_forced_tool_steering_when_tools_available(mock_llm, simple_task, math_tool):
    """If tools are available and iteration 1 produces no tool call, worker must steer the model to call tools."""
    mock_llm.chat.side_effect = [
        "I will calculate this by adding numbers.",  # Conversational text without tool call
        '{"tool": "add", "args": {"a": 2, "b": 2}}',  # Steered into tool call
        "FINAL_ANSWER: 4",  # Final answer with data
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
    # Check that iteration 2 prompt was a steering message requiring tool execution
    iter2_messages = mock_llm.chat.call_args_list[1][0][0]
    assert any("You have NOT executed any tools yet" in m["content"] for m in iter2_messages)


def test_react_flexible_tool_call_parsing(mock_llm):
    """Test robust tool call extraction: JSON, single quotes, function syntax, and positional args."""
    worker = UniversalWorkerAgent(llm=mock_llm)

    # Standard JSON
    call1 = worker._extract_tool_call('{"tool": "list_directory", "args": {"directory_path": "D:\\\\ai_gpu"}}')
    assert call1 == {"tool": "list_directory", "args": {"directory_path": "D:\\ai_gpu"}}

    # Python dict with single quotes
    call2 = worker._extract_tool_call("{'tool': 'get_disk_usage', 'args': {'path': 'D:\\\\ai_gpu'}}")
    assert call2 == {"tool": "get_disk_usage", "args": {"path": "D:\\ai_gpu"}}

    # Function call syntax with kwargs
    call3 = worker._extract_tool_call('list_directory(directory_path="D:\\\\ai_gpu", recursive=True)')
    assert call3["tool"] == "list_directory"
    assert call3["args"]["directory_path"] == "D:\\ai_gpu"
    assert call3["args"]["recursive"] is True

    # Function call syntax with positional argument
    call4 = worker._extract_tool_call('get_disk_usage("D:\\\\ai_gpu")')
    assert call4["tool"] == "get_disk_usage"
    assert call4["args"]["path"] == "D:\\ai_gpu"


def test_context_history_compression(mock_llm):
    """Test that older intermediate tool outputs are compressed to preserve token bounds."""
    worker = UniversalWorkerAgent(llm=mock_llm)

    messages = [
        {"role": "system", "content": "You are a specialized SOC agent."},
        {"role": "user", "content": "Investigate security logs in /var/log"},
        {"role": "assistant", "content": "I will execute the first discovery tool."},
        {
            "role": "user",
            "content": (
                "Tool `gather_log_evidence` returned:\n\n"
                + "Log record 1: connection from 198.51.100.44\n" * 50
                + "\n\nAnalyze this result. Either call another tool or provide your FINAL_ANSWER."
            ),
        },
        {"role": "assistant", "content": "I see multiple connections. I will now lookup the threat indicator."},
        {
            "role": "user",
            "content": (
                "Tool `lookup_threat_indicators` returned:\n\n"
                + "Indicator 198.51.100.44 is a known C2 server.\n"
                + "\n\nAnalyze this result. Either call another tool or provide your FINAL_ANSWER."
            ),
        },
        {"role": "assistant", "content": "The C2 is confirmed. Executing mitigation."},
        {
            "role": "user",
            "content": (
                "Tool `propose_containment` returned:\n\n"
                + "Firewall rule created.\n"
                + "\n\nAnalyze this result. Either call another tool or provide your FINAL_ANSWER."
            ),
        },
    ]

    compressed = worker._compress_context_history(messages)

    # Immutable anchors preserved
    assert compressed[0] == messages[0]
    assert compressed[1] == messages[1]

    # Working horizon preserved (last 2 messages)
    assert compressed[-1] == messages[-1]
    assert compressed[-2] == messages[-2]

    # Historical turn 3 (tool 1) was compressed
    hist_tool_msg = compressed[3]
    assert "[Historical output compressed]" in hist_tool_msg["content"]
    assert len(hist_tool_msg["content"]) < len(messages[3]["content"])


@pytest.mark.asyncio
async def test_heartbeat_callback_invoked(mock_llm, simple_task):
    mock_llm.chat.return_value = "FINAL_ANSWER: 4"
    worker = UniversalWorkerAgent(llm=mock_llm)
    heartbeat_calls = []

    def on_heartbeat():
        heartbeat_calls.append(True)

    result = await worker.execute(
        simple_task,
        persona="You are a math helper",
        tools=[],
        on_heartbeat=on_heartbeat,
    )
    assert result.status == TaskStatus.COMPLETED
    assert len(heartbeat_calls) >= 1

