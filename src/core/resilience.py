"""
Resilience profiles for outage tolerance.

A single, case-agnostic mapping from a human-chosen *resilience level* to the
concrete retry parameters used by both execution engines:

  - The Temporal path turns a profile into an activity ``RetryPolicy`` so a task
    keeps retrying across an LLM/model outage instead of failing the run.
  - The in-process ("direct") engine and the LLM client use the same numbers to
    retry individual calls with bounded backoff.

The levels describe roughly *how long an outage a task should ride through*
before giving up — e.g. long enough to absorb a model-server or VM restart. The
operator picks one per investigation from the UI; a default lives in settings.

Everything here is pure data and deterministic, so it is safe to evaluate inside
a Temporal workflow (no clocks, no I/O, no randomness).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Levels ───────────────────────────────────────────────────────
BRIEF = "brief"
STANDARD = "standard"
EXTENDED = "extended"
UNLIMITED = "unlimited"

DEFAULT_RESILIENCE = STANDARD


@dataclass(frozen=True)
class ResilienceProfile:
    """Concrete retry knobs derived from a resilience level.

    Attributes:
        level: the canonical level name.
        label: short human description for UIs/logs.
        approx_outage_seconds: roughly how long an outage this rides through
            (0 == effectively unlimited, bounded only by the run timeout).
        max_attempts: Temporal-style attempt cap (0 == unlimited attempts).
        initial_interval_seconds: first backoff wait.
        backoff_coefficient: multiplier applied to each successive wait.
        max_interval_seconds: ceiling on any single backoff wait so retries keep
            firing steadily across a long outage instead of exploding.
    """

    level: str
    label: str
    approx_outage_seconds: int
    max_attempts: int
    initial_interval_seconds: float
    backoff_coefficient: float
    max_interval_seconds: float


# Attempt counts are sized so the summed backoff (with a 30s ceiling) spans the
# advertised outage window: 2+4+8+16+30… ≈ 60s per ~5 attempts beyond the ramp.
_PROFILES: dict[str, ResilienceProfile] = {
    BRIEF: ResilienceProfile(
        level=BRIEF,
        label="Brief (~1 min) — absorb short blips",
        approx_outage_seconds=60,
        max_attempts=5,
        initial_interval_seconds=2.0,
        backoff_coefficient=2.0,
        max_interval_seconds=30.0,
    ),
    STANDARD: ResilienceProfile(
        level=STANDARD,
        label="Standard (~5 min) — absorb a model-server restart",
        approx_outage_seconds=300,
        max_attempts=13,
        initial_interval_seconds=2.0,
        backoff_coefficient=2.0,
        max_interval_seconds=30.0,
    ),
    EXTENDED: ResilienceProfile(
        level=EXTENDED,
        label="Extended (~15 min) — absorb a VM/host restart",
        approx_outage_seconds=900,
        max_attempts=33,
        initial_interval_seconds=2.0,
        backoff_coefficient=2.0,
        max_interval_seconds=30.0,
    ),
    UNLIMITED: ResilienceProfile(
        level=UNLIMITED,
        label="Unlimited — retry until the run deadline",
        approx_outage_seconds=0,
        max_attempts=0,  # Temporal: unbounded (still capped by the run timeout)
        initial_interval_seconds=2.0,
        backoff_coefficient=2.0,
        max_interval_seconds=30.0,
    ),
}


def normalize_level(level: str | None) -> str:
    """Return a valid resilience level name, falling back to the default."""
    if not level:
        return DEFAULT_RESILIENCE
    candidate = str(level).strip().lower()
    return candidate if candidate in _PROFILES else DEFAULT_RESILIENCE


def get_profile(level: str | None) -> ResilienceProfile:
    """Return the :class:`ResilienceProfile` for ``level`` (default if unknown)."""
    return _PROFILES[normalize_level(level)]


def all_profiles() -> list[ResilienceProfile]:
    """Return every profile in ascending outage-tolerance order (for UIs)."""
    order = [BRIEF, STANDARD, EXTENDED, UNLIMITED]
    return [_PROFILES[name] for name in order]


def client_retry_budget(level: str | None) -> tuple[int, float, float, float]:
    """Return ``(max_retries, initial_interval, backoff, max_interval)`` for a
    single LLM call.

    The client is one layer *inside* an activity/task attempt, so it uses a
    smaller share of the budget to avoid multiplying the outer retry count into
    an excessively long total. Unlimited maps to a large but finite ceiling so a
    call can never hang forever.
    """
    profile = get_profile(level)
    if profile.max_attempts == 0:
        client_retries = 30
    else:
        # Half of the outer attempts (at least 1), so client + activity retries
        # compound gracefully rather than exploding.
        client_retries = max(1, profile.max_attempts // 2)
    return (
        client_retries,
        profile.initial_interval_seconds,
        profile.backoff_coefficient,
        profile.max_interval_seconds,
    )
