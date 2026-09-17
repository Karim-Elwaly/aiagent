"""
UAOS Universal Worker Agent

A blank-slate executor with a custom ReAct (Reasoning + Acting) loop
built specifically for local LLM reliability. Every worker instance is
identical at creation — differentiated ONLY by runtime-injected persona
and tools.

The worker is created per-task and destroyed after execution.
No state leaks between tasks. No memory of previous work.

5 Guardrails for Local LLM Reliability:
  1. MAX ITERATIONS — stops infinite reasoning loops
  2. TOOL NAME VALIDATION — catches hallucinated tool names
  3. OUTPUT SIZE CAPPING — prevents context window overflow
  4. IMPLICIT FINAL ANSWER — handles LLMs that forget the protocol
  5. TIMEOUT PER TASK — prevents hung LLM calls
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from src.core.llm_client import LocalLLMClient
from src.core.models import Task, TaskResult, TaskStatus
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


class UniversalWorkerAgent:
    """A blank-slate agent with a guarded ReAct loop.

    Born empty — configured at runtime with persona + tools.
    Created per-task, destroyed after execution. No state leaks.

    The ReAct loop:
      1. Send persona + conversation history to LLM
      2. Parse response for tool calls or final answer
      3. If tool call → validate → execute → append result → loop
      4. If final answer → return
      5. If max iterations hit → force return with what we have
    """

    def __init__(
        self,
        llm: LocalLLMClient,
        max_iterations: int = 8,
        max_output_chars: int = 2000,
    ):
        """
        Args:
            llm: The local LLM client for inference.
            max_iterations: Maximum ReAct loop iterations before forced stop.
                Prevents infinite reasoning loops. Default: 8.
            max_output_chars: Maximum chars per tool output. Prevents
                context window overflow from large tool results. Default: 2000.
        """
        self.llm = llm
        self.max_iterations = max_iterations
        self.max_output_chars = max_output_chars

    async def execute(
        self,
        task: Task,
        persona: str,
        tools: list[ToolSpec],
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> TaskResult:
        """Execute a single task via the guarded ReAct loop.

        Args:
            task: The task to execute.
            persona: System prompt from PersonaSynthesizer.
            tools: Resolved concrete tools from ToolRegistry.
            on_token: Optional callback for streaming tokens.
            on_event: Optional callback for tool/task lifecycle events.

        Returns:
            TaskResult with status, output, and metadata.
        """
        start_time = time.monotonic()
        tool_map = {t.name: t for t in tools}
        tool_calls_made: list[str] = []

        # Conversation history for the ReAct loop
        messages: list[dict[str, str]] = [
            {"role": "system", "content": persona},
            {"role": "user", "content": task.description},
        ]

        logger.info(
            "Worker starting task '%s' (%s) with %d tools, max %d iterations",
            task.name,
            task.id,
            len(tools),
            self.max_iterations,
        )

        for iteration in range(1, self.max_iterations + 1):
            logger.debug(
                "Task '%s' iteration %d/%d",
                task.id,
                iteration,
                self.max_iterations,
            )

            # ── Step 1: LLM thinks ──────────────────────────
            try:
                if on_token:
                    tokens_list: list[str] = []
                    async for token in self.llm.chat_stream(messages):
                        tokens_list.append(token)
                        on_token(token)
                    response = "".join(tokens_list)
                else:
                    response = await asyncio.wait_for(
                        self.llm.chat(messages),
                        timeout=task.timeout_seconds,
                    )
            except TimeoutError:
                elapsed = int((time.monotonic() - start_time) * 1000)
                logger.warning(
                    "Task '%s' LLM call timed out at iteration %d",
                    task.id,
                    iteration,
                )
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    output="",
                    error=f"LLM call timed out after {task.timeout_seconds}s",
                    tool_calls_made=tool_calls_made,
                    execution_time_ms=elapsed,
                )
            except Exception as e:
                elapsed = int((time.monotonic() - start_time) * 1000)
                logger.error(
                    "Task '%s' LLM call failed: %s", task.id, e
                )
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    output="",
                    error=f"LLM call failed: {e}",
                    tool_calls_made=tool_calls_made,
                    execution_time_ms=elapsed,
                )

            final = self._extract_final_answer(response)
            if final is not None:
                elapsed = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Task '%s' completed at iteration %d (%dms)",
                    task.id,
                    iteration,
                    elapsed,
                )
                if on_event:
                    on_event({
                        "type": "final_answer",
                        "task_id": task.id,
                        "answer": final,
                    })
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.COMPLETED,
                    output=final,
                    tool_calls_made=tool_calls_made,
                    execution_time_ms=elapsed,
                )

            # ── Step 3: Check for tool call ─────────────────
            tool_call = self._extract_tool_call(response)

            if tool_call is None:
                # Guardrail 4: IMPLICIT FINAL ANSWER
                # LLM produced text that isn't a tool call or explicit
                # final answer. Common with local LLMs — treat as answer.
                elapsed = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Task '%s' implicit final answer at iteration %d",
                    task.id,
                    iteration,
                )
                if on_event:
                    on_event({
                        "type": "final_answer",
                        "task_id": task.id,
                        "answer": response,
                    })
                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.COMPLETED,
                    output=response,
                    tool_calls_made=tool_calls_made,
                    execution_time_ms=elapsed,
                )

            tool_name = tool_call.get("tool", "")
            tool_args = tool_call.get("args", {})

            # ── Guardrail 2: Validate tool exists ───────────
            if tool_name not in tool_map:
                logger.warning(
                    "Task '%s' hallucinated tool: '%s'",
                    task.id,
                    tool_name,
                )
                messages.append(
                    {"role": "assistant", "content": response}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Error: Tool '{tool_name}' does not exist. "
                            f"Available tools: {list(tool_map.keys())}. "
                            f"Use one of the listed tools or provide your "
                            f"FINAL_ANSWER."
                        ),
                    }
                )
                continue

            # ── Step 4: Execute tool ────────────────────────
            tool_spec = tool_map[tool_name]
            logger.debug(
                "Task '%s' calling tool '%s' with args: %s",
                task.id,
                tool_name,
                json.dumps(tool_args)[:200],
            )

            if on_event:
                on_event({
                    "type": "tool_start",
                    "task_id": task.id,
                    "tool": tool_name,
                    "args": tool_args,
                })

            try:
                result = await tool_spec.function(**tool_args)
                result_str = str(result)

                # Guardrail 3: Cap output size
                if len(result_str) > self.max_output_chars:
                    result_str = (
                        result_str[: self.max_output_chars]
                        + "\n[...output truncated]"
                    )

                tool_calls_made.append(tool_name)

                if on_event:
                    on_event({
                        "type": "tool_end",
                        "task_id": task.id,
                        "tool": tool_name,
                        "output": result_str[:200],
                    })

            except TypeError as e:
                # Wrong arguments passed to tool
                result_str = (
                    f"Error: Invalid arguments for tool '{tool_name}': {e}. "
                    f"Check the parameter names and types."
                )
                logger.warning(
                    "Task '%s' tool '%s' argument error: %s",
                    task.id,
                    tool_name,
                    e,
                )

            except Exception as e:
                result_str = f"Error: Tool '{tool_name}' failed: {e}"
                logger.error(
                    "Task '%s' tool '%s' execution error: %s",
                    task.id,
                    tool_name,
                    e,
                )

            # ── Step 5: Append to conversation and loop ─────
            messages.append(
                {"role": "assistant", "content": response}
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool `{tool_name}` returned:\n\n"
                        f"{result_str}\n\n"
                        f"Analyze this result. Either call another tool "
                        f"or provide your FINAL_ANSWER."
                    ),
                }
            )

        # ── Guardrail 1: Max iterations reached ────────────
        elapsed = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "Task '%s' reached max iterations (%d). Forcing completion.",
            task.id,
            self.max_iterations,
        )

        # Return the last assistant message as the output
        last_assistant = ""
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break

        return TaskResult(
            task_id=task.id,
            status=TaskStatus.COMPLETED,
            output=(
                f"[Reached max {self.max_iterations} iterations] "
                + last_assistant
            ),
            tool_calls_made=tool_calls_made,
            execution_time_ms=elapsed,
        )

    # ── Response Parsing ─────────────────────────────────────────

    def _extract_final_answer(self, response: str) -> str | None:
        """Check if the LLM produced an explicit final answer.

        Looks for:
          FINAL_ANSWER: <content>
          CANNOT_COMPLETE: <reason>
        """
        for marker in ("FINAL_ANSWER:", "CANNOT_COMPLETE:"):
            if marker in response:
                return response.split(marker, 1)[1].strip()
        return None

    def _extract_tool_call(self, response: str) -> dict | None:
        """Extract a tool call JSON from the LLM response.

        Handles common local LLM quirks:
        - Clean JSON on its own line
        - JSON wrapped in markdown code blocks
        - JSON embedded in surrounding text
        - Extra whitespace or formatting

        Returns:
            Dict with 'tool' and 'args' keys, or None if no tool call found.
        """
        # Pattern: {"tool": "name", "args": {...}}
        # Allow for whitespace variations common in local LLM output
        patterns = [
            # Standard format
            r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[^}]*\})\s*\}',
            # Inside markdown code block
            r'```(?:json)?\s*(\{[^`]*"tool"[^`]*\})\s*```',
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    if match.lastindex == 2:
                        # First pattern: captured name and args separately
                        tool_name = match.group(1)
                        args_str = match.group(2)
                        args = json.loads(args_str)
                        return {"tool": tool_name, "args": args}
                    else:
                        # Second pattern: full JSON captured
                        parsed = json.loads(match.group(1))
                        if "tool" in parsed:
                            return parsed
                except (json.JSONDecodeError, IndexError):
                    continue

        # Fallback: try to find ANY JSON with a "tool" key
        try:
            start = response.find("{")
            if start != -1:
                brace_count = 0
                for i in range(start, len(response)):
                    if response[i] == "{":
                        brace_count += 1
                    elif response[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            candidate = response[start : i + 1]
                            parsed = json.loads(candidate)
                            if "tool" in parsed:
                                return parsed
                            break
        except (json.JSONDecodeError, IndexError):
            pass

        return None
