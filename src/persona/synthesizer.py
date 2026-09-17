"""
UAOS Persona Synthesizer

Generates dynamic system prompts that transform blank-slate Universal
Worker Agents into domain specialists. Critical for local LLMs — strong
persona steering dramatically improves tool usage and output quality.

The synthesizer handles:
  - Tool description formatting for the worker prompt
  - Upstream context injection with size capping (prevents window overflow)
  - Clear instruction structure for reliable ReAct loop behavior
"""

from __future__ import annotations

import json
import logging

from src.core.agent_models import AgentProfile
from src.core.models import Task
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


class PersonaSynthesizer:
    """Generates focused system prompts for Universal Worker Agents.

    Every worker is born as a blank slate. The persona prompt is what
    makes it behave as a "Security Analyst" vs a "Data Scientist" vs
    a "Technical Writer". This steering is especially important for
    local LLMs that benefit from strong role-setting.
    """

    def __init__(self, max_context_chars: int = 3000):
        """
        Args:
            max_context_chars: Maximum characters of upstream context
                to include in the prompt. Prevents context window overflow
                for models with small windows (8K). Increase for 32K+ models.
        """
        self.max_context_chars = max_context_chars

    def synthesize(
        self,
        task: Task,
        tools: list[ToolSpec],
        upstream_context: dict[str, str] | None = None,
    ) -> str:
        """Generate a complete system prompt for a worker agent.

        Args:
            task: The task to execute.
            tools: Resolved concrete tools from the ToolRegistry.
            upstream_context: {task_id: output} from completed dependencies.

        Returns:
            A system prompt string ready to be injected as the worker's
            system message.
        """
        tool_block = self._format_tools(tools)
        context_block = self._format_upstream_context(
            upstream_context or {}
        )

        return f"""# Your Role
You are a specialized worker agent executing ONE specific task. Your entire focus is on completing this task accurately using your available tools.

# Your Task
**{task.name}**

{task.description}

# Expected Output
{task.expected_output}

# Available Tools
When you need to use a tool, output a tool call in this EXACT JSON format on its own line:
{{"tool": "<tool_name>", "args": {{"param1": "value1", "param2": "value2"}}}}

{tool_block}

# Workflow
1. Think about what you need to do.
2. If you need information or need to perform an action, call a tool.
3. After receiving a tool result, analyze it and decide your next step.
4. You may call multiple tools sequentially.
5. When you have enough information to provide a complete answer, write:

FINAL_ANSWER: <your complete, well-structured response>

6. If you truly cannot complete the task with available tools, write:

CANNOT_COMPLETE: <specific explanation of what's missing>

# Rules
- Use tools proactively — don't guess when you can look up or compute.
- Be precise and structured — downstream tasks depend on your output.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
{context_block}"""

    def synthesize_from_profile(
        self,
        profile: AgentProfile,
        task: Task,
        tools: list[ToolSpec],
        upstream_context: dict[str, str] | None = None,
    ) -> str:
        """Generate a custom persona prompt based on an AgentProfile configuration.

        If the profile has a system_prompt_template, it fills placeholders:
        {task_name}, {task_description}, {expected_output}, {tools}.
        Otherwise, falls back to standard synthesis steered by the agent's role.
        """
        tool_block = self._format_tools(tools)
        context_block = self._format_upstream_context(upstream_context or {})

        if profile.system_prompt_template and profile.system_prompt_template.strip():
            template = profile.system_prompt_template
            prompt = (
                template.replace("{task_name}", task.name)
                .replace("{task_description}", task.description)
                .replace("{expected_output}", task.expected_output)
                .replace("{tools}", tool_block)
            )

            # Ensure tool call format and workflow rules are provided if omitted in template
            if "FINAL_ANSWER:" not in prompt:
                prompt += f"""

# Available Tools
When you need to use a tool, output a tool call in this EXACT JSON format on its own line:
{{"tool": "<tool_name>", "args": {{"param1": "value1", "param2": "value2"}}}}

{tool_block}

# Workflow
1. Think about what you need to do.
2. If you need information or need to perform an action, call a tool.
3. After receiving a tool result, analyze it and decide your next step.
4. You may call multiple tools sequentially.
5. When you have enough information to provide a complete answer, write:

FINAL_ANSWER: <your complete, well-structured response>

6. If you truly cannot complete the task with available tools, write:

CANNOT_COMPLETE: <specific explanation of what's missing>

# Rules
- Use tools proactively — don't guess when you can look up or compute.
- Be precise and structured — downstream tasks depend on your output.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
"""
            if context_block and context_block not in prompt:
                prompt += f"\n{context_block}"
            return prompt

        # Fallback: standard synthesis steered by agent's custom persona name and description
        return f"""# Your Role: {profile.name}
{profile.description}

You are operating as the specialized agent '{profile.name}'. Your entire focus is on completing this task accurately within your domain specialty.

# Your Task
**{task.name}**

{task.description}

# Expected Output
{task.expected_output}

# Available Tools
When you need to use a tool, output a tool call in this EXACT JSON format on its own line:
{{"tool": "<tool_name>", "args": {{"param1": "value1", "param2": "value2"}}}}

{tool_block}

# Workflow
1. Think about what you need to do.
2. If you need information or need to perform an action, call a tool.
3. After receiving a tool result, analyze it and decide your next step.
4. You may call multiple tools sequentially.
5. When you have enough information to provide a complete answer, write:

FINAL_ANSWER: <your complete, well-structured response>

6. If you truly cannot complete the task with available tools, write:

CANNOT_COMPLETE: <specific explanation of what's missing>

# Rules
- Use tools proactively — don't guess when you can look up or compute.
- Be precise and structured — downstream tasks depend on your output.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
{context_block}"""

    def _format_tools(self, tools: list[ToolSpec]) -> str:
        """Format tool descriptions for the worker prompt."""
        if not tools:
            return (
                "No tools available. Answer based on your knowledge only.\n"
                "Provide your response as: FINAL_ANSWER: <response>"
            )

        lines = []
        for t in tools:
            # Build parameter descriptions
            param_parts = []
            for pname, pinfo in t.parameters.items():
                ptype = pinfo.get("type", "any")
                pdesc = pinfo.get("description", "")
                preq = "required" if pinfo.get("required") else "optional"
                param_parts.append(f"  - **{pname}** ({ptype}, {preq}): {pdesc}")

            params_str = "\n".join(param_parts) if param_parts else "  (no parameters)"

            lines.append(
                f"## `{t.name}`\n"
                f"{t.description}\n"
                f"Parameters:\n{params_str}\n"
                f"Example: {{\"tool\": \"{t.name}\", \"args\": {self._example_args(t)}}}"
            )

        return "\n\n".join(lines)

    def _example_args(self, tool: ToolSpec) -> str:
        """Generate an example args dict for the tool."""
        example = {}
        for pname, pinfo in tool.parameters.items():
            ptype = pinfo.get("type", "string")
            if ptype == "string":
                example[pname] = f"<{pname}>"
            elif ptype == "integer":
                example[pname] = 5
            elif ptype == "boolean":
                example[pname] = True
            else:
                example[pname] = f"<{pname}>"
        return json.dumps(example)

    def _format_upstream_context(
        self, upstream: dict[str, str]
    ) -> str:
        """Format upstream task outputs with size capping.

        Prevents context window overflow by truncating each upstream
        output and capping total context size.
        """
        if not upstream:
            return ""

        block = "\n# Context from Prior Tasks\n"
        block += (
            "The following information was produced by tasks that ran "
            "before yours. Use it as input for your work.\n"
        )

        remaining = self.max_context_chars

        for task_id, output in upstream.items():
            if remaining <= 100:
                block += (
                    "\n> [Additional upstream context truncated to "
                    "fit context window]\n"
                )
                break

            # Truncate individual output if needed
            truncated = output[:remaining]
            if len(output) > remaining:
                truncated += "\n[...truncated]"

            block += f"\n## From task `{task_id}`:\n{truncated}\n"
            remaining -= len(truncated)

        return block
