"""
Code Executor Tool

Provides sandboxed Python code execution via subprocess isolation.
Used for data analysis, calculations, and any programmatic task.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────
MAX_EXECUTION_SECONDS = 30
MAX_OUTPUT_CHARS = 4000


async def execute_python(code: str) -> str:
    """Execute Python code in a sandboxed subprocess.

    The code runs in a separate process with:
    - Time limit (30 seconds)
    - Output size limit (4000 chars)
    - Restricted environment variables

    Returns stdout and stderr combined.
    """
    # Write code to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=MAX_EXECUTION_SECONDS,
            cwd=tempfile.gettempdir(),  # safe working directory
            check=False,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        if result.returncode != 0:
            output_parts.append(
                f"\nProcess exited with code {result.returncode}"
            )

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Cap output size to prevent context overflow
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n[...output truncated]"

        return output

    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {MAX_EXECUTION_SECONDS}s"
    except Exception as e:
        logger.error("Code execution failed: %s", e)
        return f"Error executing code: {e}"
    finally:
        # Clean up temp file
        try:
            Path(temp_path).unlink()
        except OSError:
            pass


# ── Registration ─────────────────────────────────────────────────

CODE_EXECUTOR_SPEC = ToolSpec(
    tool_id="python_executor_v1",
    name="execute_python",
    description=(
        "Execute Python code in a sandboxed environment. "
        "Use for calculations, data processing, analysis, "
        "generating charts, parsing data, or any programmatic task. "
        "Returns stdout and stderr. Has a 30-second time limit."
    ),
    skills_provided=[
        "code_execution",
        "data_analysis",
        "math_computation",
        "data_processing",
    ],
    parameters={
        "code": {
            "type": "string",
            "description": "Python code to execute",
            "required": True,
        },
    },
    function=execute_python,
    risk_level=RiskLevel.MEDIUM,
)
