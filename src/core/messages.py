"""
UAOS Structured Message Models

Typed representations of tool calls and tool results that replace the
previous convention of embedding raw strings with ad-hoc separators
(``" returned:\\n\\n"``).

These models are used inside the worker's ReAct loop *only*; they are
serialised to plain ``{role, content}`` dicts before being sent to the
LLM, so the LLM interface is unchanged.

Checkpoint schema versioning
-----------------------------
Heartbeat checkpoints written by the worker now include a ``schema_version``
key.  Readers accept both:

* **v1** (legacy): ``messages`` is a ``list[dict[str, str]]`` with no
  structured metadata.
* **v2** (current): ``messages`` remains the same format (for LLM compat),
  but a parallel ``tool_history`` list of :class:`ToolCallRecord` dicts is
  attached.  This lets future phases (memory, eval) reconstruct what
  happened without parsing free-form text.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


# ── Parsed tool call ────────────────────────────────────────────


@dataclass
class ParsedToolCall:
    """A single tool invocation extracted from an LLM response.

    A response may contain multiple parallel calls (e.g. native mode),
    so the parser returns ``list[ParsedToolCall]``.
    """

    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    # Which parser tier resolved this call: "native", "tags", "json", "react", "forced"
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Tool result ─────────────────────────────────────────────────


@dataclass
class ToolResult:
    """The outcome of executing a single tool call."""

    call_id: str = ""
    name: str = ""
    content: str = ""
    is_error: bool = False
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_message(self) -> dict[str, str]:
        """Convert to a chat message dict for the LLM conversation history.

        Uses ``role: user`` with a structured prefix so the existing
        context-accumulator logic (``_get_accumulated_tool_outputs``) still
        works during the transition.
        """
        prefix = f"Tool `{self.name}` returned:\n\n"
        suffix = ""
        if self.is_error:
            suffix = (
                f"\n\nThe tool encountered an error. "
                f"Diagnose the cause and try a different approach."
            )
        return {
            "role": "user",
            "content": f"{prefix}{self.content}{suffix}",
        }


# ── Full round-trip record (for eval / memory) ─────────────────


@dataclass
class ToolCallRecord:
    """Complete request → response record of one tool invocation.

    Stored in checkpoint ``tool_history`` and surfaced to the eval harness
    and memory store.
    """

    call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result_content: str = ""
    is_error: bool = False
    elapsed_ms: int = 0
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCallRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Checkpoint versioning ───────────────────────────────────────

CHECKPOINT_SCHEMA_VERSION = 2


def make_checkpoint(
    *,
    step: int,
    messages: list[dict[str, str]],
    tool_calls_made: list[str],
    tool_history: list[ToolCallRecord] | None = None,
) -> dict[str, Any]:
    """Build a checkpoint dict with schema versioning."""
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "step": step,
        "messages": messages,
        "tool_calls_made": tool_calls_made,
        "tool_history": [r.to_dict() for r in (tool_history or [])],
    }


def read_checkpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a checkpoint from any schema version to the current format.

    Returns a dict with guaranteed keys: ``schema_version``, ``step``,
    ``messages``, ``tool_calls_made``, ``tool_history``.
    """
    version = data.get("schema_version", 1)
    out = {
        "schema_version": version,
        "step": data.get("step", 0),
        "messages": data.get("messages", []),
        "tool_calls_made": list(data.get("tool_calls_made", [])),
        "tool_history": [],
    }
    if version >= 2 and "tool_history" in data:
        out["tool_history"] = [
            ToolCallRecord.from_dict(r) for r in data["tool_history"]
        ]
    return out
