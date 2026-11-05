import json
import logging
import re
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.schemas.domain import (
    AvailableModel,
    CapabilityGapWarning,
    FleetAgentProposal,
    FleetProposal,
    HermesEstateInventory,
    Mission,
    TriggerKind,
    WorkflowStep,
)
from app.services.llm_recommender import recommend_model

logger = logging.getLogger(__name__)


class MissionFleetArchitect:
    """Dynamically synthesizes specialized, task-stage Autonomous Execution Units (AEUs)

    tailored to the mission's operational domain, complexity, and clarification answers.
    Replaces static archetypes with dynamic operational stages:
    - RECON_INGESTION: Telemetry, log, and evidence collection
    - DEEP_ANALYSIS: Correlation, anomaly, and root-cause investigation
    - CROSS_VERIFICATION: Benign baseline discrimination & compliance audit
    - EXECUTION_ACTION: Containment, firewall rules, and safe remediation staging
    - DELIVERABLE_SYNTHESIS: Executive dossier, regulatory forms, and report synthesis
    """

    def __init__(self, inventory: HermesEstateInventory | None = None):
        self.inventory = inventory

    def _detect_domain(self, context: str) -> str:
        ctx = context.lower()
        # 1. RFP & Commercial Proposals (Check first so "security architecture" or "zero-trust" doesn't falsely trigger SOC)
        if any(k in ctx for k in ["rfp", "proposal", "procurement", "bid", "tender", "request for proposal", "sow", "statement of work"]):
            return "rfp_proposal"
        # 2. Financial Crime & AML
        if any(k in ctx for k in ["aml", "fraud", "money laundering", "sar", "goaml", "sanction", "pep", "kyc"]):
            return "financial_aml"
        # 3. Kubernetes Container Security
        if any(k in ctx for k in ["k8s", "kubernetes", "breakout", "cgroup", "nsenter", "privileged pod"]):
            return "k8s_container_security"
        # 4. Cybersecurity SOC Incident Triage (Targeted incident terms, not ambiguous 'security')
        if any(k in ctx for k in ["soc", "incident", "threat hunt", "c2", "malware", "firewall", "iptables", "intrusion", "exfil", "ransomware", "beacon", "siem", "edr"]):
            return "cybersecurity_soc"
        return "general_operations"

    def _synthesize_stages(
        self,
        domain: str,
        mission: Mission,
        context: str,
    ) -> list[tuple[str, str, set[str], int, str]]:
        """Return list of (RoleName, ScopeDescription, KeywordTerms, Complexity, StageKind)."""
        complexity = mission.constraints.task_complexity or 3
        wants_action = (
            complexity >= 4
            or any(k in context.lower() for k in ["contain", "block", "quarantine", "remediat", "action", "isolate", "kill"])
        )

        stages: list[tuple[str, str, set[str], int, str]] = []

        if domain == "k8s_container_security":
            stages.append((
                "Pod & Container Ingestion Specialist",
                f"Extract, stream, and normalize pod runtime events, cluster audit logs, and host telemetry relevant to: {mission.goal}",
                {"container", "pod", "k8s", "kubernetes", "log", "audit", "read", "extract", "file", "recon", "source"},
                3,
                "RECON_INGESTION",
            ))
            stages.append((
                "Kernel & Escape Forensic Analyst",
                f"Analyze process lineages, namespace breakout attempts (nsenter/cgroups), rootkits, and attacker reverse shells for: {mission.goal}",
                {"forensics", "kernel", "rootkit", "cgroup", "privilege", "breakout", "auditd", "correlate", "shell", "analysis"},
                4,
                "DEEP_ANALYSIS",
            ))
            stages.append((
                "Runtime RBAC & Policy Auditor",
                f"Audit cluster RBAC rolebindings, service accounts, and distinguish benign operator traffic from adversary actions for: {mission.goal}",
                {"policy", "rbac", "security", "compliance", "audit", "serviceaccount", "baseline", "review", "gate"},
                3,
                "CROSS_VERIFICATION",
            ))
            if wants_action:
                stages.append((
                    "Pod Containment & Isolation Operator",
                    f"Stage targeted iptables drops, pod network isolation rules, and service account revocations for human approval in Decision Room: {mission.goal}",
                    {"containment", "iptables", "isolate", "quarantine", "block", "networkpolicy", "remediation", "action", "security"},
                    3,
                    "EXECUTION_ACTION",
                ))
            stages.append((
                "Incident Dossier Synthesizer",
                f"Synthesize comprehensive forensic timeline, confirmed IOC table, and containment executive report for: {mission.goal}",
                {"report", "dossier", "synthesize", "timeline", "summary", "ioc", "deliverable", "workflow", "publish"},
                2,
                "DELIVERABLE_SYNTHESIS",
            ))

        elif domain == "cybersecurity_soc":
            stages.append((
                "Perimeter & Log Ingestion Specialist",
                f"Harvest, filter, and parse security telemetry across syslog, auth, firewall, and DNS streams for: {mission.goal}",
                {"source", "log", "syslog", "auth", "network", "firewall", "dns", "zeek", "read", "extract", "recon"},
                3,
                "RECON_INGESTION",
            ))
            stages.append((
                "Forensic Threat Analyst",
                f"Identify intrusion vectors, decode covert channels, detect C2 beaconing, and establish forensic chronological timelines for: {mission.goal}",
                {"threat", "forensics", "investigation", "analysis", "c2", "beacon", "malware", "exfiltration", "timeline", "cve"},
                4,
                "DEEP_ANALYSIS",
            ))
            stages.append((
                "Benign Baseline & False-Positive Auditor",
                f"Discriminate legitimate cloud backups and administrative tasks from true adversarial activity for: {mission.goal}",
                {"baseline", "audit", "policy", "review", "compliance", "false-positive", "verify", "gate", "governance"},
                3,
                "CROSS_VERIFICATION",
            ))
            if wants_action:
                stages.append((
                    "Active Quarantine & Remediation Operator",
                    f"Stage perimeter firewall drop rules, DNS sinkhole entries, and asset isolation commands for operator approval: {mission.goal}",
                    {"firewall", "iptables", "contain", "block", "isolate", "quarantine", "remediation", "action", "defense"},
                    3,
                    "EXECUTION_ACTION",
                ))
            stages.append((
                "Executive IR Dossier Synthesizer",
                f"Compile executive incident summary, verified IOC tables, MITRE ATT&CK mappings, and remediation playbooks for: {mission.goal}",
                {"report", "synthesize", "dossier", "summary", "ioc", "mitre", "playbook", "workflow", "deliverable"},
                2,
                "DELIVERABLE_SYNTHESIS",
            ))

        elif domain == "financial_aml":
            stages.append((
                "Transaction Ingestion Specialist",
                f"Extract and ingest transactional streams, wire transfers, and customer account ledgers for: {mission.goal}",
                {"source", "transaction", "extract", "read", "database", "ledger", "account", "wire", "ingest", "file"},
                3,
                "RECON_INGESTION",
            ))
            stages.append((
                "Behavioral Anomaly & Entity Investigator",
                f"Profile transaction velocities, detect structuring/smurfing patterns, and map shell company entity networks for: {mission.goal}",
                {"aml", "fraud", "anomaly", "analysis", "investigate", "pattern", "velocity", "network", "entity", "structuring"},
                4,
                "DEEP_ANALYSIS",
            ))
            stages.append((
                "Regulatory & Sanctions Gatekeeper",
                f"Screen entities against OFAC/PEP watchlists, verify statutory thresholds, and apply jurisdictional compliance rules for: {mission.goal}",
                {"compliance", "sanctions", "pep", "ofac", "policy", "regulatory", "audit", "threshold", "gate"},
                3,
                "CROSS_VERIFICATION",
            ))
            stages.append((
                "goAML & SAR Package Synthesizer",
                f"Generate authoritative FinCEN/goAML SAR XML filings, case dossiers, and audit-ready evidence packages for: {mission.goal}",
                {"sar", "goaml", "report", "xml", "synthesize", "dossier", "filing", "workflow", "deliverable"},
                2,
                "DELIVERABLE_SYNTHESIS",
            ))

        elif domain == "rfp_proposal":
            stages.append((
                "RFP Ingestion & Requirements Specialist",
                f"Ingest RFP tender documents, parse client specifications, extract mandatory evaluation criteria and SLAs for: {mission.goal}",
                {"document", "read", "extract", "rfp", "requirement", "file", "ingest", "search", "source"},
                3,
                "RECON_INGESTION",
            ))
            stages.append((
                "Technical Solution & Architecture Designer",
                f"Synthesize comprehensive technical solution architecture, methodology, system diagrams, and implementation milestones for: {mission.goal}",
                {"architecture", "solution", "technical", "design", "methodology", "analysis", "system", "code"},
                4,
                "DEEP_ANALYSIS",
            ))
            stages.append((
                "RFP Compliance & Risk Gatekeeper",
                f"Audit proposal response against RFP compliance matrix, verify mandatory criteria, and identify contractual risks for: {mission.goal}",
                {"compliance", "audit", "matrix", "policy", "risk", "legal", "sla", "review", "gate"},
                3,
                "CROSS_VERIFICATION",
            ))
            if wants_action:
                stages.append((
                    "Commercial & Pricing Modeler",
                    f"Model cost breakdown, staffing schedules, licensing tiers, and milestone deliverables for Decision Room sign-off: {mission.goal}",
                    {"pricing", "budget", "commercial", "cost", "calculation", "finance", "schedule", "action"},
                    3,
                    "EXECUTION_ACTION",
                ))
            stages.append((
                "Executive Proposal Dossier Synthesizer",
                f"Compile authoritative client-ready proposal dossier, executive summary, compliance matrix, and win themes for: {mission.goal}",
                {"proposal", "dossier", "report", "executive", "synthesize", "deliverable", "summary", "bid"},
                2,
                "DELIVERABLE_SYNTHESIS",
            ))

        else:
            # General Enterprise IT / Data Operations
            stages.append((
                "Evidence & Source Ingestion Specialist",
                f"Collect, inspect, and normalize source files, documents, and system telemetry relevant to: {mission.goal}",
                {"source", "document", "file", "read", "extract", "search", "research", "evidence", "web", "browser", "inspect"},
                3,
                "RECON_INGESTION",
            ))
            stages.append((
                "Analytical Evaluation Specialist",
                f"Perform deep analytical evaluation, quantitative modeling, and metric calculations for: {mission.goal}",
                {"analysis", "code", "python", "data", "calculate", "model", "benchmark", "evaluate", "metric"},
                4,
                "DEEP_ANALYSIS",
            ))
            stages.append((
                "Policy & Quality Assurance Auditor",
                f"Verify outputs against organizational constraints, data residency boundaries, and governance criteria for: {mission.goal}",
                {"policy", "security", "compliance", "audit", "risk", "governance", "review", "assurance", "validate"},
                3,
                "CROSS_VERIFICATION",
            ))
            if wants_action:
                stages.append((
                    "System Automation Operator",
                    f"Execute approved system commands, migrations, or state modifications within declared boundaries for: {mission.goal}",
                    {"command", "execute", "system", "automation", "deploy", "action", "mutate", "terminal"},
                    3,
                    "EXECUTION_ACTION",
                ))
            stages.append((
                "Executive Deliverable Synthesizer",
                f"Synthesize final authoritative executive deliverable, structured documentation, and action items for: {mission.goal}",
                {"workflow", "task", "automation", "delegate", "project", "issue", "ticket", "mail", "summary", "synthesize"},
                2,
                "DELIVERABLE_SYNTHESIS",
            ))

        return stages

    def compose_fleet(self, mission: Mission, inventory: HermesEstateInventory) -> FleetProposal:
        """Compose a specialized multi-agent fleet tailored to the mission outcome."""
        tool_ids = {tool.tool_id for tool in inventory.registered_tools}
        skills_by_id = {skill.skill_id: skill for skill in inventory.installed_skills}
        unused_skills = set(skills_by_id)

        mission_context = " ".join([mission.goal, *mission.clarification_answers.values()])
        goal_terms = set(re.findall(r"[a-z0-9]+", mission_context.lower())) - {
            "the", "and", "for", "with", "from", "that", "this", "into", "their", "your", "about", "what", "which"
        }

        domain = self._detect_domain(mission_context)
        stages = self._synthesize_stages(domain, mission, mission_context)

        frequency = mission.constraints.execution_frequency.strip().lower()
        if frequency in {"continuous", "continuous_poll", "poll"}:
            trigger_policy = TriggerKind.CONTINUOUS_POLL
            schedule = ""
        elif frequency in {"event", "event-driven", "event_driven"}:
            trigger_policy = TriggerKind.EVENT_DRIVEN
            schedule = ""
        else:
            trigger_policy = TriggerKind.CRON
            schedule = "0 * * * *" if frequency == "hourly" else "0 8 * * *"

        agents: list[FleetAgentProposal] = []

        for idx, (name, scope, role_terms, stage_complexity, stage_kind) in enumerate(stages):
            model_constraints = mission.constraints.model_copy(update={"task_complexity": stage_complexity})
            try:
                model = recommend_model(model_constraints, inventory.available_models)
            except ValueError:
                model = AvailableModel(
                    family="local",
                    version="default",
                    cloud=False,
                    data_residencies=["local", mission.constraints.data_residency],
                    estimated_daily_cost_usd=0.0,
                    residency_verified=True,
                    reasoning_tier=stage_complexity,
                )

            # Smart skill matching with domain awareness and noise suppression
            skill_id: str | None = None
            if stage_kind == "DELIVERABLE_SYNTHESIS" and domain == "rfp_proposal":
                if "docx" in unused_skills:
                    skill_id = "docx"
                elif "pdf-creation" in unused_skills:
                    skill_id = "pdf-creation"

            if not skill_id and stage_kind not in {"DEEP_ANALYSIS", "CROSS_VERIFICATION"}:
                # Filter out generic stop words and entertainment skills
                noise_terms = {"document", "action", "items", "task", "read", "source", "file", "recon", "review", "gate", "search", "web", "browser", "inspect", "get", "extract"}
                entertainment_prefixes = {"gif", "music", "song", "video", "manim", "p5js"}
                ranked: list[tuple[int, str]] = []
                for s_id in unused_skills:
                    if any(ep in s_id.lower() for ep in entertainment_prefixes):
                        continue
                    s_terms = set(re.findall(r"[a-z0-9]+", f"{s_id} {skills_by_id[s_id].description}".lower())) - noise_terms
                    matched_role = (role_terms - noise_terms) & s_terms
                    if matched_role:
                        score = 4 * len(matched_role) + len((goal_terms - noise_terms) & s_terms)
                        ranked.append((score, s_id))

                ranked.sort(key=lambda item: (-item[0], item[1]))
                if ranked and ranked[0][0] >= 4:
                    skill_id = ranked[0][1]

            gaps: list[CapabilityGapWarning] = []
            if skill_id is not None:
                unused_skills.remove(skill_id)
                required_tools = skills_by_id[skill_id].required_tools
            else:
                required_tools = []

            # Stage-appropriate curated toolsets
            stage_tools_map = {
                "RECON_INGESTION": ["read_file", "search_files", "web_extract", "web_search"],
                "DEEP_ANALYSIS": ["read_file", "search_files", "execute_code"],
                "CROSS_VERIFICATION": ["read_file", "search_files"],
                "EXECUTION_ACTION": ["execute_code", "terminal", "patch", "write_file"],
                "DELIVERABLE_SYNTHESIS": ["write_file", "read_file", "execute_code"],
            }
            curated_defaults = stage_tools_map.get(stage_kind, ["read_file", "search_files"])

            candidate_tools = list(required_tools)
            for default_tool in curated_defaults:
                if default_tool in tool_ids and default_tool not in candidate_tools:
                    candidate_tools.append(default_tool)

            if not candidate_tools:
                for tool in inventory.registered_tools:
                    tool_terms = set(re.findall(r"[a-z0-9]+", f"{tool.tool_id} {tool.description}".lower()))
                    if len(role_terms & tool_terms) > 1 and tool.tool_id not in candidate_tools:
                        candidate_tools.append(tool.tool_id)

            for req_tool in candidate_tools:
                if req_tool not in tool_ids:
                    gaps.append(CapabilityGapWarning(capability_id=req_tool, reason="Tool is not registered in the live estate."))

            bound_tools = [t for t in candidate_tools if t in tool_ids]
            step_capability = skill_id or (bound_tools[0] if bound_tools else "read_file")

            # Pipeline Topology:
            # Stage 0 (Root/Ingestion) executes on mission schedule / cadence
            # Downstream stages (1..N) are automatically event-driven by their immediate predecessor
            if idx == 0:
                agent_trigger = trigger_policy
                agent_schedule = schedule
                agent_upstreams: list[str] = []
            else:
                agent_trigger = TriggerKind.EVENT_DRIVEN
                agent_schedule = ""
                agent_upstreams = [agents[-1].agent_id]

            # Build agent proposal
            agent_id = str(uuid4())
            agent = FleetAgentProposal(
                agent_id=agent_id,
                name=name,
                role=f"{name} ({stage_kind})",
                scope=scope,
                bound_skills=[skill_id] if skill_id else [],
                bound_tools=bound_tools,
                capability_gaps=gaps,
                trigger_policy=agent_trigger,
                schedule=agent_schedule,
                upstream_agent_ids=agent_upstreams,
                workflow_steps=[
                    WorkflowStep(
                        name=f"Execute {name}",
                        capability_id=step_capability,
                        parameters={"operational_stage": stage_kind, "scope": scope},
                    )
                ],
                assigned_llm=model,
            )
            agents.append(agent)

        logger.info(
            "Synthesized %d specialized agents for domain '%s' (mission: '%s')",
            len(agents),
            domain,
            mission.name,
        )
        return FleetProposal(mission_id=mission.mission_id, agents=agents)

    async def compose_fleet_with_llm(
        self,
        mission: Mission,
        inventory: HermesEstateInventory,
    ) -> FleetProposal:
        """Compose fleet using deep LLM reasoning if available; falls back to domain heuristics."""
        skills_summary = ", ".join(f"{s.skill_id} ({s.description[:40]})" for s in inventory.installed_skills) or "None"
        tools_summary = ", ".join(t.tool_id for t in inventory.registered_tools) or "None"
        clarification_summary = "\n".join(f"- {k}: {v}" for k, v in mission.clarification_answers.items()) or "None provided"

        prompt = FLEET_COMPOSER_PROMPT.format(
            name=mission.name,
            goal=mission.goal,
            clarification_answers=clarification_summary,
            frequency=mission.constraints.execution_frequency,
            residency=mission.constraints.data_residency,
            installed_skills=skills_summary,
            registered_tools=tools_summary,
        )

        # 1. External LLM if configured
        if settings.llm_base_url:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Design the optimal autonomous fleet for: {mission.name} - {mission.goal}"},
            ]
            try:
                async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
                    resp = await client.post(
                        url,
                        json={
                            "model": settings.llm_model,
                            "messages": messages,
                            "temperature": 0.2,
                            "max_tokens": 2048,
                        },
                    )
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"]["content"]
                        proposal = _parse_fleet_json(raw, mission, inventory)
                        if proposal:
                            return proposal
            except Exception as exc:
                logger.warning("External LLM fleet composition unavailable (%s); trying Hermes.", exc)

        # 2. Hermes Gateway LLM (Default)
        hermes_proposal = await _generate_fleet_via_hermes(mission, prompt, inventory)
        if hermes_proposal:
            return hermes_proposal

        # 3. Fallback: Fast domain heuristics composer
        return self.compose_fleet(mission, inventory)


FLEET_COMPOSER_PROMPT = """You are a Principal Multi-Agent Fleet Architect.
Your task is to design an elite, production-grade autonomous agent fleet for an enterprise mission.
You must analyze the mission goal, clarification answers, and discovered Hermes estate capabilities (installed skills, tools, models), and synthesize the exact operational stages required.

## Mission Context:
- Name: {name}
- Goal: {goal}
- Clarification Answers:
{clarification_answers}
- Execution Frequency: {frequency}
- Data Residency: {residency}

## Discovered Estate Inventory:
- Installed Hermes Skills: {installed_skills}
- Available Hermes Tools: {registered_tools}

## Fleet Architecture Rules:
1. Operational Stages: Design a sequential pipeline of 3 to 5 distinct specialized agents (e.g. Ingestion/Recon -> Deep Analysis -> Compliance/Verification -> Optional Execution Action -> Deliverable Synthesis).
2. Pipeline Topology (CRITICAL):
   - Specialist 1 (Root Ingestion) must have execution_trigger "CRON" or "CONTINUOUS_POLL" and upstream_agent_name null.
   - Specialists 2 through N MUST have execution_trigger "EVENT_DRIVEN" and upstream_agent_name must be strictly the immediate previous specialist's name.
3. Skill Binding (CRITICAL):
   - Only bind an installed Hermes skill if it directly, genuinely, and specifically solves the specialist's core objective (e.g. "docx" for writing Microsoft Word proposals, "pdf-creation" for PDFs, "airtable" for Airtable records).
   - NEVER bind unrelated utility or entertainment skills (e.g. NEVER bind "gif-search", "music", "song", "video", "manim", "p5js", or "meeting-action-items" to a document ingestion or analysis specialist).
   - If a specialist performs analytical, architectural, or audit reasoning, leave bound_skills empty [] (Pure LLM Reasoning).
4. Tool Selection: Assign appropriate Hermes tools from the available tools list (e.g. "read_file", "search_files", "write_file", "execute_code").
5. Stage Complexity: Rate from 2 (simple compilation) to 4 (deep forensic / architectural design).

## Output Format:
Return ONLY a valid JSON object matching this exact schema:
{{
  "agents": [
    {{
      "name": "RFP Ingestion & Requirements Specialist",
      "role": "RFP Ingestion & Requirements Specialist (RECON_INGESTION)",
      "scope": "Ingest RFP tender documents, parse client specifications, extract mandatory evaluation criteria and SLAs",
      "stage_kind": "RECON_INGESTION",
      "stage_complexity": 3,
      "bound_skills": [],
      "bound_tools": ["read_file", "search_files"],
      "execution_trigger": "CRON",
      "schedule": "0 8 * * *",
      "upstream_agent_name": null,
      "requires_human_challenge": false
    }},
    {{
      "name": "Technical Solution & Architecture Designer",
      "role": "Technical Solution & Architecture Designer (DEEP_ANALYSIS)",
      "scope": "Synthesize comprehensive technical solution architecture, methodology, system diagrams, and implementation milestones",
      "stage_kind": "DEEP_ANALYSIS",
      "stage_complexity": 4,
      "bound_skills": [],
      "bound_tools": [],
      "execution_trigger": "EVENT_DRIVEN",
      "schedule": "",
      "upstream_agent_name": "RFP Ingestion & Requirements Specialist",
      "requires_human_challenge": false
    }},
    {{
      "name": "RFP Compliance & Risk Gatekeeper",
      "role": "RFP Compliance & Risk Gatekeeper (CROSS_VERIFICATION)",
      "scope": "Audit proposal response against RFP compliance matrix, verify mandatory criteria, and identify contractual risks",
      "stage_kind": "CROSS_VERIFICATION",
      "stage_complexity": 3,
      "bound_skills": [],
      "bound_tools": [],
      "execution_trigger": "EVENT_DRIVEN",
      "schedule": "",
      "upstream_agent_name": "Technical Solution & Architecture Designer",
      "requires_human_challenge": false
    }},
    {{
      "name": "Executive Proposal Dossier Synthesizer",
      "role": "Executive Proposal Dossier Synthesizer (DELIVERABLE_SYNTHESIS)",
      "scope": "Compile authoritative client-ready proposal dossier, executive summary, compliance matrix, and win themes",
      "stage_kind": "DELIVERABLE_SYNTHESIS",
      "stage_complexity": 3,
      "bound_skills": ["docx"],
      "bound_tools": ["write_file"],
      "execution_trigger": "EVENT_DRIVEN",
      "schedule": "",
      "upstream_agent_name": "RFP Compliance & Risk Gatekeeper",
      "requires_human_challenge": false
    }}
  ]
}}
"""


def _extract_json_block(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return text[brace_start : brace_end + 1]
    return text


def _parse_fleet_json(
    raw_text: str,
    mission: Mission,
    inventory: HermesEstateInventory,
) -> FleetProposal | None:
    try:
        parsed = json.loads(_extract_json_block(raw_text))
        raw_agents = parsed.get("agents", [])
        if not isinstance(raw_agents, list) or len(raw_agents) < 2:
            return None

        tool_ids = {tool.tool_id for tool in inventory.registered_tools}
        skills_by_id = {skill.skill_id: skill for skill in inventory.installed_skills}

        agents: list[FleetAgentProposal] = []
        name_to_id: dict[str, str] = {}

        for idx, item in enumerate(raw_agents):
            name = str(item.get("name") or f"Specialist {idx+1}")
            agent_id = str(uuid4())
            name_to_id[name] = agent_id

            stage_kind = str(item.get("stage_kind") or "RECON_INGESTION")
            role = str(item.get("role") or f"{name} ({stage_kind})")
            scope = str(item.get("scope") or f"Execute {role} for {mission.goal}")
            complexity = int(item.get("stage_complexity") or 3)

            # Skills
            raw_skills = item.get("bound_skills", [])
            if isinstance(raw_skills, str):
                raw_skills = [raw_skills] if raw_skills else []
            valid_skills = [s for s in raw_skills if s in skills_by_id]

            # Tools
            raw_tools = item.get("bound_tools", [])
            if isinstance(raw_tools, str):
                raw_tools = [raw_tools] if raw_tools else []
            valid_tools = [t for t in raw_tools if t in tool_ids]

            # Gaps
            gaps: list[CapabilityGapWarning] = []
            for s in raw_skills:
                if s not in skills_by_id:
                    gaps.append(CapabilityGapWarning(capability_id=f"skill:{s}", reason=f"Skill '{s}' not installed in Hermes."))
            for t in raw_tools:
                if t not in tool_ids:
                    gaps.append(CapabilityGapWarning(capability_id=t, reason=f"Tool '{t}' not registered in Hermes."))

            # Triggers & Upstreams: Pipeline topology
            trigger_str = str(item.get("execution_trigger") or "").upper()
            if idx == 0:
                trigger = TriggerKind.CRON if "CRON" in trigger_str else (TriggerKind.CONTINUOUS_POLL if "POLL" in trigger_str else TriggerKind.CRON)
                schedule = str(item.get("schedule") or "0 8 * * *") if trigger == TriggerKind.CRON else ""
                upstreams = []
            else:
                trigger = TriggerKind.EVENT_DRIVEN
                schedule = ""
                upstreams = [agents[-1].agent_id]

            # Model Recommendation
            model_constraints = mission.constraints.model_copy(update={"task_complexity": complexity})
            try:
                model = recommend_model(model_constraints, inventory.available_models)
            except ValueError:
                model = AvailableModel(
                    family="local",
                    version="default",
                    cloud=False,
                    data_residencies=["local", mission.constraints.data_residency],
                    estimated_daily_cost_usd=0.0,
                    residency_verified=True,
                    reasoning_tier=complexity,
                )

            requires_gate = bool(item.get("requires_human_challenge", False))
            step_cap = valid_skills[0] if valid_skills else (valid_tools[0] if valid_tools else "read_file")
            step = WorkflowStep(
                name=f"Execute {name}",
                capability_id=step_cap,
                parameters={"operational_stage": stage_kind, "scope": scope},
                requires_step_challenge=requires_gate,
            )

            agent = FleetAgentProposal(
                agent_id=agent_id,
                name=name,
                role=role,
                scope=scope,
                bound_skills=valid_skills,
                bound_tools=valid_tools,
                capability_gaps=gaps,
                trigger_policy=trigger,
                schedule=schedule,
                upstream_agent_ids=upstreams,
                workflow_steps=[step],
                assigned_llm=model,
            )
            agents.append(agent)

        logger.info("Successfully synthesized %d agents via LLM for mission '%s'", len(agents), mission.name)
        return FleetProposal(mission_id=mission.mission_id, agents=agents)
    except Exception as exc:
        logger.warning("Failed to parse LLM fleet proposal JSON (%s)", exc)
        return None


async def _generate_fleet_via_hermes(
    mission: Mission,
    prompt: str,
    inventory: HermesEstateInventory,
) -> FleetProposal | None:
    """Ask the connected Hermes gateway to synthesize an elite multi-agent fleet."""
    try:
        from app.services.hermes_gateway import connected_hermes
        from app.services.hermes_runtime import (
            assistant_text,
            close_session,
            get_session_history,
            provider_ready,
            session_create_params,
            wait_for_turn,
        )

        async with connected_hermes() as hermes:
            if not await provider_ready(hermes):
                logger.info("Hermes has no usable current provider; using heuristic composer.")
                return None

            created = await hermes.call(
                "session.create",
                session_create_params(
                    f"Fleet Architecture: {mission.name}",
                    close_on_disconnect=True,
                ),
            )
            session_id = created.get("session_id")
            stored_session_id = created.get("stored_session_id")
            if not session_id or not stored_session_id:
                return None

            combined = f"{prompt}\n\nSynthesize the fleet proposal now. Respond ONLY with the raw JSON object."
            await hermes.call("prompt.submit", {"session_id": session_id, "text": combined})

            snapshot = await wait_for_turn(
                hermes,
                stored_session_id,
                settings.hermes_generation_timeout_seconds,
                poll_interval=1.0,
            )
            runtime_session_id = snapshot.get("session_id") or session_id
            history = await get_session_history(hermes, runtime_session_id)
            await close_session(hermes, runtime_session_id)

            raw = assistant_text(history)
            if not raw:
                return None
            return _parse_fleet_json(raw, mission, inventory)
    except Exception as exc:
        logger.info("Hermes LLM fleet synthesis bypassed (%s); falling back to heuristic composer.", exc)
        return None

