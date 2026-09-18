"""
Text processing and formatting utilities.
"""

from __future__ import annotations


def smart_truncate(
    text: str,
    max_chars: int = 2000,
    head_ratio: float = 0.55,
) -> str:
    """Smart Head-Tail truncation for tool outputs, logs, and structured documents.

    Instead of simply slicing the first `max_chars` (which cuts off critical trailing
    stack traces, exit codes, and summary lines), this function preserves:
      - Head: schemas, column headers, and initial items
      - Tail: final status, error messages, and summary lines
      - Middle: replaced with an explicit indicator of omitted characters

    Args:
        text: Input string to truncate.
        max_chars: Maximum allowable character length (including truncation indicator).
        head_ratio: Fraction of available characters assigned to the head (default 0.55 / 55%).

    Returns:
        Truncated string with head and tail preserved, or original text if within budget.
    """
    if not text or len(text) <= max_chars:
        return text

    # If max_chars is too small for a meaningful head/tail split, fallback to simple slice
    if max_chars < 150:
        return text[:max_chars] + "... [TRUNCATED]"

    # Estimated separator overhead (e.g. "\n\n... [MIDDLE 12,345 CHARACTERS TRUNCATED] ...\n\n")
    separator_overhead = 60
    available = max_chars - separator_overhead
    if available <= 0:
        return text[:max_chars]

    head_chars = max(10, int(available * head_ratio))
    tail_chars = max(10, available - head_chars)

    head_slice = text[:head_chars]
    tail_slice = text[-tail_chars:]

    omitted = len(text) - (len(head_slice) + len(tail_slice))
    if omitted <= 0:
        return text

    return f"{head_slice}\n\n... [MIDDLE {omitted:,} CHARACTERS TRUNCATED] ...\n\n{tail_slice}"
