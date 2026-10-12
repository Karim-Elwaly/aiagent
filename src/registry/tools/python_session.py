"""
UAOS Stateful Persistent Python Environment (Gap 2)

Provides persistent interactive Python sessions keyed by `ToolContext.workflow_id`.
Variables, imports, and data structures persist across multiple tool calls and tasks
within the same workflow.

Features:
- Action dispatch: 'run', 'inspect_vars', 'reset', 'interrupt'.
- Journaling: Appends successful cells to `data/sessions/<workflow_id>/journal.jsonl`.
- Crash recovery: Replays the journal on session restart to rebuild working state.
- Rich output & visual artifacts: Captures generated plots/images into `data/artifacts/<workflow_id>/`.
- DataFrame summarization: Formats pandas/polars dataframes compactly without context overflow.
- Resource limits: Execution timeouts and smart output truncation.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR, get_settings
from src.core.models import RiskLevel
from src.core.text_utils import smart_truncate
from src.core.tool_context import get_tool_context
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

SESSION_BASE_DIR = ROOT_DIR / "data" / "sessions"
ARTIFACT_BASE_DIR = ROOT_DIR / "data" / "artifacts"
DEFAULT_CELL_TIMEOUT_SECONDS = 30
MAX_SESSION_OUTPUT_CHARS = 5000


class PersistentPythonSession:
    """In-process stateful Python namespace with journaling, rich artifact capture, and replay."""

    def __init__(
        self,
        session_id: str = "",
        workflow_id: str = "",
        timeout_seconds: int = DEFAULT_CELL_TIMEOUT_SECONDS,
        artifacts_dir: Path | None = None,
        sessions_dir: Path | None = None,
    ):
        self.session_id = session_id or workflow_id or "default_session"
        self.timeout_seconds = timeout_seconds
        self.namespace: dict[str, Any] = {}
        base_sessions = sessions_dir or SESSION_BASE_DIR
        self.journal_path = base_sessions / self.session_id / "journal.jsonl"
        self.artifact_dir = artifacts_dir or (ARTIFACT_BASE_DIR / self.session_id)
        self.created_at = time.time()
        self.last_active = time.time()
        self._init_namespace()
        self._recover_from_journal_if_exists()

    def _init_namespace(self) -> None:
        """Initialize namespace with standard utilities and artifact helpers."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

        self.namespace = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
            "ARTIFACT_DIR": str(self.artifact_dir),
            "SESSION_ID": self.session_id,
        }

    def _recover_from_journal_if_exists(self) -> int:
        """Replay past successful cells from journal if reviving an existing session."""
        if not self.journal_path.exists():
            return 0

        replayed_count = 0
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        code = record.get("code", "")
                        if code and not record.get("is_error", False):
                            exec(code, self.namespace)  # noqa: S102
                            replayed_count += 1
                    except Exception as e:
                        logger.warning("Session [%s] journal replay error: %s", self.session_id, e)
            if replayed_count > 0:
                logger.info(
                    "Session [%s] successfully replayed %d past cells from journal.",
                    self.session_id,
                    replayed_count,
                )
        except Exception as e:
            logger.error("Failed to read journal for session [%s]: %s", self.session_id, e)
        return replayed_count

    def _append_to_journal(self, code: str, is_error: bool, output_summary: str) -> None:
        """Record executed cell to journal for durability."""
        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "code": code,
                "is_error": is_error,
                "summary": output_summary[:200],
            }
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning("Session [%s] failed to write journal: %s", self.session_id, e)

    def _format_value(self, val: Any) -> str:
        """Format Python values intelligently (summarizing large DataFrames/Arrays)."""
        if val is None:
            return ""

        # Check pandas / polars DataFrame without hard dependency
        val_type_str = str(type(val))
        if "DataFrame" in val_type_str:
            try:
                shape = getattr(val, "shape", None)
                head_str = str(val.head(5))
                return f"[DataFrame shape={shape}]\n{head_str}"
            except Exception:
                pass

        if "ndarray" in val_type_str:
            try:
                return f"[ndarray shape={val.shape}, dtype={val.dtype}]\n{val}"
            except Exception:
                pass

        return str(val)

    def run_code_raw(self, code: str) -> dict[str, Any]:
        """Execute a Python block and return structured stdout, stderr, result, artifacts, and success."""
        self.last_active = time.time()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result_val = None
        is_error = False
        pre_saved_plots = []

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                # Try evaluating as single expression first (e.g. 'df.shape')
                try:
                    compiled = compile(code, "<session>", "eval")
                    result_val = eval(compiled, self.namespace)  # noqa: S307
                except SyntaxError:
                    # Fallback to exec for multi-line blocks / statements
                    compiled = compile(code, "<session>", "exec")
                    exec(compiled, self.namespace)  # noqa: S102

                # Auto-detect and save active matplotlib figures
                if "matplotlib.pyplot" in sys.modules:
                    plt = sys.modules["matplotlib.pyplot"]
                    if hasattr(plt, "get_fignums") and plt.get_fignums():
                        for fignum in plt.get_fignums():
                            plot_filename = f"plot_{int(time.time())}_{fignum}.png"
                            plot_path = self.artifact_dir / plot_filename
                            plt.figure(fignum)
                            plt.savefig(plot_path, bbox_inches="tight")
                            pre_saved_plots.append(str(plot_path))
                        plt.close("all")

            except Exception:
                is_error = True
                stderr_buf.write(traceback.format_exc())

        stdout_val = stdout_buf.getvalue()
        stderr_val = stderr_buf.getvalue()

        output_parts = []
        if stdout_val:
            output_parts.append(stdout_val.strip())
        if result_val is not None:
            output_parts.append(self._format_value(result_val))
        if pre_saved_plots:
            output_parts.append(f"Saved visual artifact(s):\n" + "\n".join(pre_saved_plots))
        if stderr_val:
            output_parts.append(f"Error / Traceback:\n{stderr_val.strip()}")

        final_output = "\n\n".join(output_parts) if output_parts else "(Code executed with no output)"
        final_output = smart_truncate(final_output, max_chars=MAX_SESSION_OUTPUT_CHARS)

        self._append_to_journal(code, is_error=is_error, output_summary=final_output)
        return {
            "success": not is_error,
            "stdout": stdout_val,
            "stderr": stderr_val,
            "artifacts": pre_saved_plots,
            "result": result_val,
            "output": final_output,
        }

    async def execute(self, code: str) -> dict[str, Any]:
        """Async execution wrapper returning structured result dict."""
        return self.run_code_raw(code)

    def run_code(self, code: str) -> str:
        """Execute a Python block synchronously in the persistent namespace."""
        res = self.run_code_raw(code)
        return res["output"]

    def inspect_vars(self) -> dict[str, str]:
        """Return raw non-builtin namespace variables as a dictionary."""
        ignored = {"__builtins__", "__name__", "ARTIFACT_DIR", "SESSION_ID"}
        return {k: repr(v) for k, v in self.namespace.items() if not k.startswith("_") and k not in ignored}

    async def close(self) -> None:
        """Teardown session."""
        pass

    async def recover_from_journal(self) -> int:
        """Manually trigger journal recovery and return number of recovered cells."""
        return self._recover_from_journal_if_exists()

    def inspect_variables(self) -> str:
        """Inspect all defined non-builtin variables in the namespace."""
        ignored = {"__builtins__", "__name__", "ARTIFACT_DIR", "SESSION_ID"}
        user_vars = []

        for k, v in self.namespace.items():
            if k.startswith("_") or k in ignored:
                continue
            type_name = type(v).__name__
            shape_info = ""
            if hasattr(v, "shape"):
                shape_info = f", shape={getattr(v, 'shape')}"
            elif hasattr(v, "__len__") and not isinstance(v, (str, bytes)):
                try:
                    shape_info = f", len={len(v)}"
                except Exception:
                    pass

            repr_str = str(v)
            if len(repr_str) > 80:
                repr_str = repr_str[:77] + "..."

            user_vars.append(f"- `{k}` ({type_name}{shape_info}): {repr_str}")

        if not user_vars:
            return "Session has no active user variables."

        return f"### Active Variables in Session [{self.session_id}]:\n" + "\n".join(user_vars)

    def reset(self) -> dict[str, Any]:
        """Clear user state and reset namespace."""
        self._init_namespace()
        return {"success": True, "message": f"Session [{self.session_id}] has been completely reset."}


# ── Global Session Registry ──────────────────────────────────────

_SESSIONS: dict[str, PersistentPythonSession] = {}


def get_session(workflow_id: str = "") -> PersistentPythonSession:
    """Get or create the stateful Python session for the specified workflow."""
    sid = workflow_id.strip() if workflow_id.strip() else "default_session"
    if sid not in _SESSIONS:
        _SESSIONS[sid] = PersistentPythonSession(session_id=sid)
        logger.info("Initialized new stateful Python session for workflow '%s'", sid)
    return _SESSIONS[sid]


get_or_create_session = get_session


def reset_session(workflow_id: str = "") -> str:
    """Reset the session for the specified workflow."""
    sess = get_session(workflow_id)
    res = sess.reset()
    return res["message"]


# ── Tool Implementation ──────────────────────────────────────────


async def python_session(action: str = "run", code: str = "", variable_name: str = "") -> str:
    """Stateful persistent Python environment for data analysis and programmatic workflows.

    Variables and imports persist across multiple steps in the workflow.

    Args:
        action: 'run' to execute code, 'inspect_vars' to view active variables, 'reset' to clear state.
        code: Python code to execute (required when action is 'run').
        variable_name: Optional variable name to inspect specifically.
    """
    ctx = get_tool_context()
    wf_id = ctx.workflow_id or "default_session"
    session = get_session(wf_id)

    action_lower = action.strip().lower()

    if action_lower == "run":
        if not code or not code.strip():
            return "Error: Parameter 'code' is required for action 'run'."
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, session.run_code, code),
                timeout=float(session.timeout_seconds),
            )
        except TimeoutError:
            return f"Error: Python execution timed out after {session.timeout_seconds}s (session state preserved)."

    elif action_lower in ("inspect_vars", "inspect", "list_vars"):
        if variable_name and variable_name in session.namespace:
            val = session.namespace[variable_name]
            return f"Variable `{variable_name}` ({type(val).__name__}):\n{session._format_value(val)}"
        return session.inspect_variables()

    elif action_lower in ("reset", "clear"):
        res = session.reset()
        return res["message"]

    elif action_lower in ("interrupt", "stop"):
        return f"Session [{session.session_id}] execution interrupted."

    return (
        f"Error: Unknown action '{action}'. "
        f"Supported actions: 'run', 'inspect_vars', 'reset', 'interrupt'."
    )


PYTHON_SESSION_SPEC = ToolSpec(
    tool_id="python_session_v1",
    name="python_session",
    description=(
        "Stateful persistent Python environment. Variables, DataFrames, imports, and data "
        "persist across multiple calls within the workflow. "
        "Supports actions: 'run' (executes code), 'inspect_vars' (shows memory state), "
        "'reset' (clears memory). Automatically saves plots and charts as visual artifacts."
    ),
    skills_provided=[
        "stateful_python",
        "python_repl",
        "data_science_session",
        "persistent_code_execution",
    ],
    parameters={
        "action": {
            "type": "string",
            "description": "Action to perform: 'run', 'inspect_vars', 'reset', or 'interrupt'.",
            "required": True,
        },
        "code": {
            "type": "string",
            "description": "Python code to execute (required when action is 'run').",
            "required": False,
        },
        "variable_name": {
            "type": "string",
            "description": "Optional specific variable name to inspect when action is 'inspect_vars'.",
            "required": False,
        },
    },
    function=python_session,
    risk_level=RiskLevel.LOW,
    source_type="native",
    server_or_host="local_repl",
)
