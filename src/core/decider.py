"""
Typed decision readout — the integration point for AnyJev.

The system asks the LLM to choose from a fixed set of answers in several places.
Today those answers are *generated* as JSON text and then parsed, which has two
consequences: the reply can fail to parse at all, and the reported confidence is
whatever the model wrote rather than a measurement of its uncertainty.

A decider reads the answer out of the model's own distribution instead. Nothing
is generated and nothing is parsed, so there is no parse-failure path, and the
probability attached to the answer is a real one.

This module is the seam. It defines the contract and an AnyJev-backed
implementation; it does not change how any decision is currently made. Nothing
here runs unless explicitly enabled.

Levels, in increasing order of trustworthiness:

    raw  restricted softmax over the answer tokens. Position-biased and
         uncalibrated — present for comparison only, never for acting on.
    L0   zero labels. Averages position bias out over option rotations and
         divides out the label prior.
    L1   temperature scaling on top of L0. Needs labels; does not change the
         ranking, only the probabilities.
    L2   a closed-form head on a hidden state. Needs labels and an engine that
         exposes hidden states.

``Decision.level`` travels with every result and ``require_level`` lets a caller
refuse to act on a weaker readout than it was designed for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# AnyJev integration is DORMANT.
#
# The code below is complete and tested, but refuses to construct a backend
# while this is True — so setting decision_backend="anyjev" is not sufficient
# to activate it. This is a deliberate stop, not an unfinished feature: the
# deployment prerequisites are not in place yet.
#
# To re-enable, all four are required:
#   1. pip install "anyjev[hf]"          (optional dependency, not in pyproject)
#   2. An inference server exposing token scores. The current LM Studio chat
#      endpoint does not; L2 additionally needs hidden states, meaning a vLLM
#      `--task embed` pooler or transformers.
#   3. A decision model with a usable head. Shipped AnyJev heads are Qwen3-only
#      and the configured model is gpt-oss-20b, so either point the decision
#      model at a small Qwen3 or fit a head. The decision model need not be the
#      generation model.
#   4. Set ANYJEV_DORMANT = False here.
#
# Everything else in the decision pipeline — capture, analysis, and order-flip
# replay — is independent of AnyJev and stays active. Those measure the current
# generated-and-parsed system and are what justify (or refute) turning this on.
ANYJEV_DORMANT = True
# ─────────────────────────────────────────────────────────────────

# Ordered weakest to strongest. Used to enforce require_level.
LEVELS = ("raw", "L0", "L1", "L2")


class DecisionUnavailable(RuntimeError):
    """Raised when a decision could not be read out.

    Deliberately distinct from "the model chose an answer I dislike": callers
    must be able to tell a missing decision from a real one, which is precisely
    the distinction the generate-and-parse path loses.
    """


@dataclass
class Decision:
    """One typed choice, with the probability mass behind it."""

    decision: str
    distribution: dict[str, float] = field(default_factory=dict)
    level: str = "raw"
    backend: str = "unknown"
    latency_ms: float = 0.0

    @property
    def confidence(self) -> float | None:
        """Probability assigned to the chosen answer."""
        return self.distribution.get(self.decision)

    @property
    def margin(self) -> float | None:
        """Gap between the top two answers.

        A decision can be high-confidence and still nearly tied when a third
        option absorbed the remaining mass, so margin is reported separately
        rather than inferred from confidence.
        """
        if len(self.distribution) < 2:
            return None
        ranked = sorted(self.distribution.values(), reverse=True)
        return ranked[0] - ranked[1]

    def meets(self, required: str | None) -> bool:
        """Whether this readout is at least as strong as ``required``."""
        if not required:
            return True
        try:
            return LEVELS.index(self.level) >= LEVELS.index(required)
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "distribution": self.distribution,
            "level": self.level,
            "backend": self.backend,
            "confidence": self.confidence,
            "margin": self.margin,
            "latency_ms": round(self.latency_ms, 1),
        }


class DecisionBackend(Protocol):
    """Reads a typed choice out of a model."""

    name: str

    async def decide(
        self, question: str, options: list[str], context: str
    ) -> Decision: ...


class AnyJevBackend:
    """Reads decisions via AnyJev (https://github.com/nokia-applied-research/AnyJev).

    AnyJev is an optional dependency and is imported lazily, so the project runs
    normally without it installed. It also requires an inference server that
    exposes token scores — L2 additionally needs hidden states, which means a
    vLLM embed pooler or transformers rather than a plain chat endpoint.
    """

    name = "anyjev"

    def __init__(
        self,
        base_url: str,
        model: str,
        level: str = "L0",
        timeout: float = 60.0,
    ):
        if level not in LEVELS:
            raise ValueError(f"Unknown level {level!r}; expected one of {LEVELS}")
        self.base_url = base_url
        self.model = model
        self.level = level
        self.timeout = timeout
        self._decider: Any = None

    def _ensure_decider(self) -> Any:
        """Build the AnyJev decider, explaining precisely what is missing."""
        if self._decider is not None:
            return self._decider

        try:
            from anyjev import Decider  # type: ignore[import-not-found]
            from anyjev.backends.vllm import VLLMBackend  # type: ignore[import-not-found]
        except ImportError as e:
            raise DecisionUnavailable(
                "AnyJev is not installed. Install it with: pip install \"anyjev[hf]\". "
                "Note it also needs an inference server exposing token scores; a "
                "plain chat endpoint is not sufficient."
            ) from e

        try:
            self._decider = Decider(
                VLLMBackend(self.base_url, self.model), level=self.level
            )
        except Exception as e:
            raise DecisionUnavailable(
                f"Could not initialise AnyJev against {self.base_url}: {e}"
            ) from e
        return self._decider

    async def decide(
        self, question: str, options: list[str], context: str
    ) -> Decision:
        import asyncio
        import time

        if len(options) < 2:
            raise DecisionUnavailable("A typed decision needs at least two options")
        # AnyJev's letter readout addresses options by letter, so it cannot
        # express more than 26. Fail loudly rather than silently truncating.
        if len(options) > 26:
            raise DecisionUnavailable(
                f"AnyJev supports at most 26 options; {len(options)} given"
            )

        decider = self._ensure_decider()

        try:
            from anyjev import Question  # type: ignore[import-not-found]
        except ImportError as e:
            raise DecisionUnavailable("AnyJev is not installed") from e

        q = Question.choice(question, options, name="decision")
        started = time.perf_counter()
        try:
            # AnyJev's API is synchronous; keep the event loop free.
            result = await asyncio.wait_for(
                asyncio.to_thread(decider.decide, context, [q]),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError as e:
            raise DecisionUnavailable(
                f"AnyJev decision timed out after {self.timeout}s"
            ) from e
        except Exception as e:
            raise DecisionUnavailable(f"AnyJev decision failed: {e}") from e

        elapsed_ms = (time.perf_counter() - started) * 1000

        try:
            answer = result["decision"]
            distribution = dict(answer.distribution)
            # Trust the level the library reports over the one requested: a
            # backend may legitimately serve a weaker readout than asked for,
            # and require_level checks must see the truth.
            level = str(getattr(answer, "level", self.level))
            choice = getattr(answer, "value", None) or max(
                distribution, key=distribution.get
            )
        except Exception as e:
            raise DecisionUnavailable(
                f"Unexpected AnyJev result shape: {e}"
            ) from e

        return Decision(
            decision=str(choice),
            distribution={str(k): float(v) for k, v in distribution.items()},
            level=level,
            backend=self.name,
            latency_ms=elapsed_ms,
        )


def build_backend(settings: Any) -> DecisionBackend | None:
    """Construct the configured backend, or None when decisions stay generated.

    Returns None rather than raising so that a misconfiguration degrades to the
    existing behaviour instead of taking the system down.
    """
    backend_name = str(getattr(settings, "decision_backend", "none") or "none").lower()
    if backend_name in ("none", "", "off", "disabled"):
        return None

    if backend_name == "anyjev":
        if ANYJEV_DORMANT:
            # Deliberately refused, not broken. Setting decision_backend=anyjev
            # is not enough on its own; see ANYJEV_DORMANT above for what the
            # deployment actually needs before this can work.
            logger.warning(
                "decision_backend is 'anyjev' but the integration is dormant "
                "(ANYJEV_DORMANT in src/core/decider.py). Decisions stay "
                "generated-and-parsed."
            )
            return None

        base_url = getattr(settings, "decision_backend_url", "") or getattr(
            settings, "llm_base_url", ""
        )
        model = getattr(settings, "decision_backend_model", "") or getattr(
            settings, "llm_model", ""
        )
        level = str(getattr(settings, "decision_level", "L0"))
        try:
            return AnyJevBackend(base_url=base_url, model=model, level=level)
        except Exception as e:
            logger.warning("Could not build AnyJev backend: %s", e)
            return None

    logger.warning("Unknown decision_backend %r; decisions stay generated", backend_name)
    return None
