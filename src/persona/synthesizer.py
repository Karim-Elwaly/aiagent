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

    # Appended to every persona. A worker that invents a value poisons every
    # downstream task that consumes its output, so the contract is stated once
    # here rather than relying on each agent profile to remember it.
    GROUNDING_CONTRACT = """
# Evidence Grounding Contract (non-negotiable)
- Report ONLY what a tool actually returned. Never supply a value from memory or
  plausibility — not an IP address, hostname, account, file hash, port, byte
  count, record count or timestamp.
- When a tool result includes evidence ids of the form `EV-000123`, cite them
  next to the claim they support, e.g. `... 4 failed logons for that account [EV-000031]`.
- Never invent an evidence id. If nothing supports a statement you consider
  important, write it followed by `[UNVERIFIED]`.
- Use tool-reported counts verbatim. Do not estimate or recompute them.
- "Not found" is a valid and valuable result. If a tool reports that something
  was looked for and not observed, say so explicitly rather than omitting it or
  substituting a likely-sounding finding.
- If a tool returns an error or an empty result, report that plainly. Do not
  describe what the data would probably have shown.
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
You are a worker agent executing ONE task on the host machine using available tools.

# Your Task
**{task.name}**
{task.description}

# Expected Output
{task.expected_output}

# Available Tools
Tool call format:
{{"tool": "<tool_name>", "args": {{"param1": "value1"}}}}

{tool_block}

# Workflow & Rules
1. Always call tools first to inspect real paths and compute data.
2. Host environment with direct filesystem/drive access (C:, D:). Never claim lack of access.
3. When done, output: FINAL_ANSWER: <complete findings, table, and data>.
4. If truly impossible with tools, output: CANNOT_COMPLETE: <reason>.
5. Never return an empty FINAL_ANSWER. Always include tool results.
6. Do NOT invent tools. Only use tools listed above.
{self.GROUNDING_CONTRACT}
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
                tool_section = "" if "{tools}" in template else f"\n# Available Tools\n{tool_block}\n"
                prompt += f"""{tool_section}
# Workflow & Rules
1. Think about what you need to do and execute tools proactively to inspect real host system data.
2. When you need to call a tool, output a JSON tool call:
{{"tool": "<tool_name>", "args": {{"param1": "value1"}}}}
3. After analyzing tool results, if you have sufficient findings, write:

FINAL_ANSWER: <your complete, well-structured response>

4. If truly impossible with available tools, write:
CANNOT_COMPLETE: <specific explanation of what's missing>
"""
            # The grounding contract applies to every persona, including custom
            # templates that already define their own workflow section.
            if "Evidence Grounding Contract" not in prompt:
                prompt += self.GROUNDING_CONTRACT
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
- You run on the host machine. Tools have real access to filesystem and drives (C:, D:).
- Always execute tools first to get real data (e.g. call list_directory or get_disk_usage).
- After receiving tool results, provide your full response under: FINAL_ANSWER: <complete findings, table, and data>.
- Never return an empty or blank FINAL_ANSWER. Always include the data and findings obtained from the tools.
- Never claim to lack filesystem access or be in a sandbox. Call tools to inspect real paths.
- Use tools proactively — do not guess.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
{self.GROUNDING_CONTRACT}
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
        """Generate a realistic example args dict for the tool."""
        example = {}
        for pname, pinfo in tool.parameters.items():
            ptype = pinfo.get("type", "string")
            pname_lower = pname.lower()
            if ptype == "integer":
                example[pname] = 20
            elif ptype == "boolean":
                example[pname] = True
            elif "path" in pname_lower or "dir" in pname_lower or "folder" in pname_lower or "target" in pname_lower:
                example[pname] = "D:\\"
            elif "file" in pname_lower:
                example[pname] = "D:\\example.txt"
            elif "code" in pname_lower or "script" in pname_lower:
                example[pname] = "print('Hello')"
            elif "query" in pname_lower or "search" in pname_lower:
                example[pname] = "system metrics"
            elif "command" in pname_lower or "cmd" in pname_lower:
                example[pname] = "dir D:\\"
            else:
                example[pname] = "value"
        return json.dumps(example)

    def _format_upstream_context(
        self, upstream: dict[str, str]
    ) -> str:
        """Format upstream task outputs with size capping.

        The budget is shared fairly across tasks rather than granted
        first-come: with greedy allocation an early task's large output would
        consume the entire window and silently starve the most recent — and
        most refined — upstream analysis, dropping its evidence citations.
        Outputs shorter than their share donate the surplus to the rest.
        """
        if not upstream:
            return ""

        block = "\n# Context from Prior Tasks\n"
        block += (
            "The following information was produced by tasks that ran "
            "before yours. Use it as input for your work. If it appears "
            "truncated, re-query the evidence store rather than guessing.\n"
        )

        remaining = self.max_context_chars
        items = list(upstream.items())
        truncated_any = False

        for index, (task_id, output) in enumerate(items):
            tasks_left = len(items) - index
            share = max(remaining // tasks_left, 0)
            if share < 100:
                truncated_any = True
                break

            clipped = output[:share]
            if len(output) > share:
                clipped += "\n[...truncated — re-query the evidence store for full detail]"
                truncated_any = True

            block += f"\n## From task `{task_id}`:\n{clipped}\n"
            remaining -= len(clipped)

        if truncated_any:
            block += (
                "\n> [Some upstream context was truncated to fit the context "
                "window. Retrieve exact values with query_evidence/get_evidence "
                "instead of relying on the excerpts above.]\n"
            )

        return block
