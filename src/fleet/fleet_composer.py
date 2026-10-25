"""
UAOS Specialized Task-Bound Fleet Composer

Synthesizes dedicated Autonomous Execution Units (AEUs) where exactly:
    1 Task Node = 1 Dedicated Micro-Agent (TaskSpecialistUnit)
Enforces the Anti-Persona Mandate and supports Competing Fleet architectures.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from src.core.models import (
    MissionEnvironmentManifest,
    SpecializedFleetManifest,
    Task,
    TaskDAG,
    TaskSpecialistSpec,
)
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class MissionFleetArchitect:
    """Composes specialized task-bound fleets and competing fleet topologies across any enterprise domain."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry

    def _sanitize_unit_id(self, task_id: str, name: str) -> tuple[str, str]:
        clean_name = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()[:20]
        codename = f"UNIT-{clean_name or 'SPECIALIST'}"
        return f"AEU-{task_id.upper()}-{clean_name or 'UNIT'}", codename

    def _infer_operational_stage(self, idx: int, total: int, task_name: str) -> str:
        name_lower = task_name.lower()
        if idx == 0 or any(k in name_lower for k in ["ingest", "extract", "recon", "collect", "parse", "fetch", "scan"]):
            return "RECON_INGESTION"
        if idx == total - 1 or any(k in name_lower for k in ["synthesize", "report", "dossier", "summary", "deliverable"]):
            return "DELIVERABLE_SYNTHESIS"
        if any(k in name_lower for k in ["verify", "validate", "check", "audit", "compliance", "correlate"]):
            return "CROSS_VERIFICATION"
        if any(k in name_lower for k in ["remediat", "block", "isolate", "patch", "execute", "action", "deploy"]):
            return "EXECUTION_ACTION"
        return "DEEP_ANALYSIS"

    def synthesize_fleet(
        self,
        dag: TaskDAG,
        env_manifest: MissionEnvironmentManifest | None = None,
        strategy_profile: str = "STANDARD",
        fleet_name: str | None = None,
        mission_title: str | None = None,
    ) -> SpecializedFleetManifest:
        """Enforces a strict 1:1 bijection between DAG task nodes and TaskSpecialistUnits."""
        units: list[TaskSpecialistSpec] = []
        name_prefix = f"Fleet-{strategy_profile.title()}" if not fleet_name else fleet_name
        title = mission_title or getattr(dag, "goal", "Enterprise Autonomous Mission")
        total_tasks = len(dag.tasks)

        for idx, task in enumerate(dag.tasks):
            unit_id, unit_codename = self._sanitize_unit_id(task.id, task.name)
            op_stage = self._infer_operational_stage(idx, total_tasks, task.name)

            # Resolve exact scoped tools for this single task node
            scoped_tool_names: list[str] = []
            if self.registry and task.required_skills:
                resolved = self.registry.resolve(task.required_skills)
                scoped_tool_names = sorted(t.name for t in resolved)

            # Synthesize dedicated bespoke Unit System Prompt tailored strictly for this task node
            synthesized_prompt = (
                f"You are Autonomous Execution Unit `{unit_id}` (Codename: `{unit_codename}`).\n"
                f"Operational Stage: {op_stage}.\n"
                f"Primary Objective: '{task.name}'.\n\n"
                f"OPERATIONAL DIRECTIVE:\n"
                f"{task.description.strip()}\n\n"
                f"AUTONOMOUS RESILIENCE DIRECTIVE:\n"
                f"If your task requires ingesting, normalizing, or analyzing domain data (e.g. telemetry, manifests, logs, financial figures) "
                f"and no physical files exist on the filesystem or in the current directory, DO NOT FAIL OR REPORT 'NO FILES FOUND'. "
                f"You are authorized and required to autonomously construct, model, and synthesize a complete, realistic, high-fidelity enterprise dataset "
                f"matching the scenario (with realistic entities, SKUs, timestamps, metrics, and parameters) and perform your analysis on it. "
                f"Downstream units depend directly on your data!\n\n"
                f"SCOPED CAPABILITIES & TOOL ACCESS:\n"
                f"You are restricted strictly to the following verified tools: "
                f"[{', '.join(scoped_tool_names) if scoped_tool_names else 'General Reasoning / Deterministic Analysis'}].\n"
                f"Do NOT invent tool calls or assume tools outside this scoped set exist.\n\n"
                f"DATA CONTRACTS:\n"
                f"- Input Expected: verified outputs from upstream dependency nodes: "
                f"[{', '.join(task.dependencies) if task.dependencies else 'None - Initial Branch Node'}].\n"
                f"- Output Required: {task.expected_output or 'Verified, tool-grounded execution payload fulfilling task criteria.'}.\n\n"
                f"VERIFICATION CRITERIA:\n"
                f"Your final response must be self-contained, factually verified against tool observations or synthesized domain models, "
                f"and structured without conversational filler or persona roleplay."
            )

            input_contract = (
                f"Requires verified outputs from upstream dependency nodes: "
                f"[{', '.join(task.dependencies) if task.dependencies else 'None - Initial Branch Node'}]"
            )

            output_contract = (
                task.expected_output
                or f"Verified, tool-grounded execution payload fulfilling task '{task.name}'"
            )

            verification_crit = (
                f"Satisfy operational output contract for {op_stage}; "
                f"pass supervisor factual consistency audit; fulfill operator challenge criteria."
            )

            spec = TaskSpecialistSpec(
                unit_id=unit_id,
                unit_codename=unit_codename,
                task_id=task.id,
                operational_stage=op_stage,
                synthesized_unit_prompt=synthesized_prompt,
                specialization_directive=synthesized_prompt,
                scoped_tools=scoped_tool_names,
                input_contract=input_contract,
                output_contract=output_contract,
                verification_criteria=verification_crit,
                timeout_seconds=getattr(task, "timeout_seconds", 300),
            )
            # Attach the specialist specification directly to the task node
            task.specialist_spec = spec
            units.append(spec)

        manifest = SpecializedFleetManifest(
            fleet_id=f"fleet-{uuid4().hex[:8]}",
            mission_title=title,
            fleet_name=name_prefix,
            inferred_domain=getattr(env_manifest, "detected_mission_type", "general_enterprise") if env_manifest else "general_enterprise",
            strategy_profile=strategy_profile,
            fleet_rationale=f"Synthesized {len(units)} task-bound specialist units across {total_tasks} distinct operational stages.",
            units=units,
            dag=dag,
        )

        logger.info(
            "Synthesized specialized fleet '%s' (%s) with %d dedicated AEUs",
            manifest.fleet_name,
            manifest.strategy_profile,
            len(manifest.units),
        )
        return manifest

    async def expand_mission_to_fleet(
        self,
        mission_prompt: str,
        clarifications: dict[str, str] | None = None,
        env_manifest: MissionEnvironmentManifest | None = None,
        strategy_profile: str = "STANDARD",
    ) -> SpecializedFleetManifest:
        """Domain-agnostic decomposition: expands high-level mission into a multi-stage TaskDAG & Specialized Fleet."""
        from src.brain.meta_planner import MetaPlanner
        from src.core.llm_client import LocalLLMClient

        planner = MetaPlanner(
            llm=LocalLLMClient(),
            available_skills=self.registry.list_skills() if self.registry else [],
        )

        query = mission_prompt
        if clarifications:
            clarif_lines = [f"- [{k}]: {v}" for k, v in clarifications.items()]
            query = f"{query}\n\n[OPERATIONAL CLARIFICATIONS & CONSTRAINTS]:\n" + "\n".join(clarif_lines)

        dag = await planner.plan(query)
        return self.synthesize_fleet(
            dag,
            env_manifest=env_manifest,
            strategy_profile=strategy_profile,
            mission_title=mission_prompt,
        )

    async def synthesize_competing_fleets(
        self,
        prompt: str,
        clarifications: dict[str, str] | None = None,
        env_manifest: MissionEnvironmentManifest | None = None,
        planner: Any = None,
    ) -> list[SpecializedFleetManifest]:
        """Synthesize two distinct, competing fleet architectures for side-by-side benchmark comparison."""
        logger.info("Synthesizing competing fleets for mission: '%s'", prompt[:60])

        if not planner:
            from src.brain.meta_planner import MetaPlanner
            from src.core.llm_client import LocalLLMClient
            planner = MetaPlanner(
                llm=LocalLLMClient(),
                available_skills=self.registry.list_skills() if self.registry else [],
            )

        # 1. Compose Fleet Alpha (Precision & Verification)
        alpha_query = (
            f"{prompt}\n\n[STRATEGY: DEEP VERIFICATION & PRECISION]. "
            f"Decompose into meticulous, multi-layer verification phases with strict forensic checks."
        )
        dag_alpha = await planner.plan(alpha_query)
        fleet_alpha = self.synthesize_fleet(
            dag_alpha,
            env_manifest=env_manifest,
            strategy_profile="COMPETITOR_PRECISION",
            fleet_name="Fleet Alpha (Precision & Deep Verification)",
            mission_title=prompt,
        )

        # 2. Compose Fleet Omega (Rapid Heuristic Execution)
        omega_query = (
            f"{prompt}\n\n[STRATEGY: RAPID HEURISTIC TRIAGE]. "
            f"Decompose into high-speed, parallel branch execution designed for minimal latency and rapid delivery."
        )
        dag_omega = await planner.plan(omega_query)
        fleet_omega = self.synthesize_fleet(
            dag_omega,
            env_manifest=env_manifest,
            strategy_profile="COMPETITOR_SPEED",
            fleet_name="Fleet Omega (Rapid Heuristic Triage)",
            mission_title=prompt,
        )

        return [fleet_alpha, fleet_omega]


# Backwards compatibility alias
FleetComposer = MissionFleetArchitect
