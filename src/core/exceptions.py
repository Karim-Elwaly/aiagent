"""
UAOS Custom Exception Hierarchy

Structured exceptions for clear error classification and recovery decisions.
The orchestrator uses exception types to decide: retry, re-plan, or abort.
"""


class UAOSError(Exception):
    """Base exception for all UAOS errors."""



# ─── Planning Errors ─────────────────────────────────────────────


class PlanningError(UAOSError):
    """Raised when the Meta-Planner fails to produce a valid TaskDAG."""



class DAGValidationError(PlanningError):
    """Raised when a TaskDAG has structural issues (cycles, missing deps)."""



class JSONParseError(PlanningError):
    """Raised when the LLM output cannot be parsed as valid JSON."""

    def __init__(self, raw_output: str, parse_error: str):
        self.raw_output = raw_output
        self.parse_error = parse_error
        super().__init__(
            f"Failed to parse LLM output as JSON: {parse_error}"
        )


# ─── Tool Errors ─────────────────────────────────────────────────


class ToolError(UAOSError):
    """Base for all tool-related errors."""



class ToolNotFoundError(ToolError):
    """Raised when no tool can satisfy a required skill."""

    def __init__(self, skill: str):
        self.skill = skill
        super().__init__(
            f"No tool registered for skill: '{skill}'"
        )


class ToolExecutionError(ToolError):
    """Raised when a tool call fails during execution."""

    def __init__(self, tool_name: str, original_error: Exception):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(
            f"Tool '{tool_name}' failed: {original_error}"
        )


# ─── Worker Errors ───────────────────────────────────────────────


class WorkerError(UAOSError):
    """Base for Universal Worker Agent errors."""



class MaxIterationsExceeded(WorkerError):
    """Raised when the ReAct loop hits the iteration limit."""

    def __init__(self, iterations: int, last_output: str = ""):
        self.iterations = iterations
        self.last_output = last_output
        super().__init__(
            f"ReAct loop reached max iterations ({iterations})"
        )


class WorkerTimeoutError(WorkerError):
    """Raised when a worker exceeds its task timeout."""

    def __init__(self, task_id: str, timeout_seconds: int):
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Task '{task_id}' timed out after {timeout_seconds}s"
        )


class TransientLLMError(WorkerError):
    """Raised when the inference server is unreachable or drops the response.

    Signals the orchestrator that a retry may succeed, unlike deterministic
    failures such as an unparseable response or an exhausted ReAct loop.
    """

    def __init__(self, detail: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(detail)


# ─── Orchestration Errors ────────────────────────────────────────


class OrchestrationError(UAOSError):
    """Base for workflow orchestration errors."""



class ApprovalRejectedError(OrchestrationError):
    """Raised when a human rejects a high-risk task."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(
            f"Human rejected task '{task_id}'"
        )


class ReplanLimitExceeded(OrchestrationError):
    """Raised when the system has re-planned too many times."""

    def __init__(self, replan_count: int):
        self.replan_count = replan_count
        super().__init__(
            f"Exceeded maximum re-plan attempts ({replan_count})"
        )
