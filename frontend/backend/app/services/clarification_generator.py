import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.domain import (
    ClarifyingQuestion,
    HermesEstateInventory,
    Mission,
)

logger = logging.getLogger(__name__)

CLARIFICATION_GENERATOR_PROMPT = """You are an Enterprise Pre-Flight Mission Architect.
Before an autonomous agent fleet is deployed, your job is to evaluate the mission prompt, constraints, and discovered estate capabilities, and generate targeted, high-leverage clarifying questions to lock down the optimal execution strategy.

## Mission Context
- Mission Name: {name}
- Mission Goal: {goal}
- Discovered Tools & Connectors: {tools_summary}
- Data Residency: {residency}
- Execution Frequency: {frequency}

## Rules
1. If the user's mission is already fully specified, self-contained, or standard with zero ambiguity, set "needs_clarification": false and "questions": [].
2. If there are high-leverage architectural forks, target environment selections, containment thresholds, or specific deliverable formats to choose from, set "needs_clarification": true and formulate 2 to 4 concise operational questions.
3. Every question must have 2 to 4 concrete selectable options plus support for custom input.
4. Focus on:
   - Target Scope & Environment (e.g., "Live Investigation" vs "Forensic Offline Simulation")
   - Action Posture (e.g., "Advisory & Recommend" vs "Active Automated Containment")
   - Preferred Deliverable (e.g., "Executive Briefing Summary", "Structured Incident Action Form", or "Full Technical Dossier")

## Output Format
Return ONLY valid JSON matching this exact structure:
{{
  "needs_clarification": true,
  "detected_mission_type": "incident_response",
  "questions": [
    {{
      "id": "remediation-posture",
      "question": "What is the desired remediation posture for identified threat indicators?",
      "category": "governance",
      "rationale": "Determines whether execution should execute live containment commands or provide advisory recommendations.",
      "options": ["Advisory Only (Generate containment playbook)", "Active Automated Quarantine (Isolate host / block IPs)"],
      "allow_custom": true,
      "default_answer": "Advisory Only (Generate containment playbook)"
    }}
  ]
}}"""


def _extract_json(text: str) -> str:
    """Extract JSON object from markdown code blocks or raw text."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return text[brace_start : brace_end + 1]
    return text


def _heuristic_clarifying_questions(mission: Mission) -> list[ClarifyingQuestion]:
    """Domain-aware intelligent fallback question generator when LLM is offline."""
    text = f"{mission.name} {mission.goal}".lower()
    questions: list[ClarifyingQuestion] = []

    # 1. Kubernetes & Container Security Breakout
    if any(k in text for k in ["k8s", "kubernetes", "container", "breakout", "pod", "namespace", "docker", "cgroup", "nsenter"]):
        questions.extend([
            ClarifyingQuestion(
                question_id="target-scope",
                prompt="Which cluster runtime layer and telemetry stream is in scope for this investigation?",
                category="integrations",
                rationale="Bounds evidence extraction to pod stdout/stderr, API server audit logs, or host kernel events.",
                options=[
                    "Container Runtime & Pod Logs (In-cluster)",
                    "Host Node Kernel & auditd Telemetry",
                    "Full Fleet Scope (Cluster API + Host Nodes)",
                ],
                default_answer="Full Fleet Scope (Cluster API + Host Nodes)",
            ),
            ClarifyingQuestion(
                question_id="containment-posture",
                prompt="What is the permitted containment and remediation posture for compromised pods?",
                category="governance",
                rationale="Controls whether worker units may stage active iptables/CAPI network drops or only generate playbooks.",
                options=[
                    "Advisory Only (Stage containment rules for human review in Decision Room)",
                    "Active Automated Pod Quarantine (Drop pod traffic & revoke service account)",
                    "Dry-Run Simulation Only",
                ],
                default_answer="Advisory Only (Stage containment rules for human review in Decision Room)",
            ),
            ClarifyingQuestion(
                question_id="forensic-artifacts",
                prompt="What forensic evidence artifacts are required for completion disposition?",
                category="assurance",
                rationale="Ensures the deliverable synthesizes specific technical proofs required by your IR playbook.",
                options=[
                    "Confirmed Threat Indicators (Attacker IPs, reverse shells, privileged pods)",
                    "Deep Kernel Rootkit & Process Hierarchy Analysis (nsenter, eBPF)",
                    "Executive Summary & Full Incident Dossier",
                ],
                default_answer="Confirmed Threat Indicators (Attacker IPs, reverse shells, privileged pods)",
            ),
        ])

    # 2. SOC / Incident Triage / Threat Hunting / Malware
    elif any(k in text for k in ["soc", "incident", "security", "threat", "c2", "malware", "firewall", "iptables", "intrusion", "exfil", "ransomware"]):
        questions.extend([
            ClarifyingQuestion(
                question_id="source-systems",
                prompt="Which telemetry feeds and source log boundaries are primary for this investigation?",
                category="integrations",
                rationale="Guides data gathering units to focus on relevant authentication, network, or perimeter systems.",
                options=[
                    "Host Auth & System Audit Logs (syslog, auth.log, Windows EVTX)",
                    "Perimeter Firewall, Zeek & DNS Exfiltration Telemetry",
                    "Unified Multi-Source SIEM Aggregation",
                ],
                default_answer="Unified Multi-Source SIEM Aggregation",
            ),
            ClarifyingQuestion(
                question_id="escalation",
                prompt="Which findings must pause for a human decision before any external action?",
                category="governance",
                rationale="Defines the Human-In-The-Loop gate threshold before containment execution.",
                options=[
                    "All State-Mutating Containment Actions (IP blocks, isolation)",
                    "Only High-Confidence C2 IPs & Critical Severity Findings",
                    "Autonomous Remediation within Stated Budget",
                ],
                default_answer="All State-Mutating Containment Actions (IP blocks, isolation)",
            ),
            ClarifyingQuestion(
                question_id="completion",
                prompt="What evidence makes a workflow cycle complete and acceptable?",
                category="assurance",
                rationale="Establishes definitive exit criteria for the incident investigation cycle.",
                options=[
                    "Executive Summary Table with Confirmed Threat Indicators (IoCs)",
                    "Full Forensic Timeline & MITRE ATT&CK Mapping",
                    "Machine-Readable STIX/TAXII & Suricata Rule Package",
                ],
                default_answer="Executive Summary Table with Confirmed Threat Indicators (IoCs)",
            ),
        ])

    # 3. Financial Crime / Anti-Money Laundering (AML) / Fraud
    elif any(k in text for k in ["aml", "fraud", "transaction", "money laundering", "sar", "goaml", "sanction", "pep", "kyc"]):
        questions.extend([
            ClarifyingQuestion(
                question_id="risk-threshold",
                prompt="Which transaction threshold should trigger automated investigator assignment?",
                category="integrations",
                rationale="Determines transaction volume scoping and velocity anomaly detection boundaries.",
                options=[
                    "Standard Regulatory ($10,000+ USD or rapid structuring patterns)",
                    "High-Risk PEP & OFAC Sanctions Screening Only",
                    "Dynamic Statistical Anomaly Clustering (Top 1% score deviation)",
                ],
                default_answer="Standard Regulatory ($10,000+ USD or rapid structuring patterns)",
            ),
            ClarifyingQuestion(
                question_id="escalation",
                prompt="What level of human escalation is required before filing a Suspicious Activity Report (SAR)?",
                category="governance",
                rationale="Enforces compliance oversight and dual-control sign-off.",
                options=[
                    "Two-Person Integrity (Architect & Compliance Officer)",
                    "Single Senior Investigator Disposition",
                    "Automated Draft Queue with Batch Human Review",
                ],
                default_answer="Two-Person Integrity (Architect & Compliance Officer)",
            ),
            ClarifyingQuestion(
                question_id="completion",
                prompt="What evidence artifact must be synthesized upon cycle completion?",
                category="assurance",
                rationale="Ensures compatibility with financial intelligence reporting engines.",
                options=[
                    "goAML / FinCEN SAR XML Package",
                    "Comprehensive Case Dossier with Entity Graphs",
                    "Audit-Ready Tabular CSV with Verification Signatures",
                ],
                default_answer="goAML / FinCEN SAR XML Package",
            ),
        ])

    # 4. RFP / Commercial Proposal Generation / Procurement
    elif any(k in text for k in ["rfp", "proposal", "procurement", "bid", "tender", "request for proposal", "sow", "statement of work"]):
        questions.extend([
            ClarifyingQuestion(
                question_id="rfp-scope",
                prompt="Which components and documentation boundaries of the RFP are in scope?",
                category="integrations",
                rationale="Guides requirements extraction across technical architecture, commercial terms, and SLAs.",
                options=[
                    "Full Technical & Commercial Scope (End-to-End Proposal)",
                    "Technical Architecture, Methodology & System Implementation Only",
                    "Statement of Work (SOW), Milestones & SLA Deliverables",
                ],
                default_answer="Full Technical & Commercial Scope (End-to-End Proposal)",
            ),
            ClarifyingQuestion(
                question_id="proposal-strategy",
                prompt="What core win-theme and strategic positioning should anchor the response?",
                category="governance",
                rationale="Defines the tone and competitive differentiators emphasized across all proposal sections.",
                options=[
                    "Enterprise Technical Superiority & Proven Architecture Methodology",
                    "Accelerated Delivery, Operational Reliability & Proven SLAs",
                    "Cost-Efficiency, Scalable Architecture & ROI Optimization",
                ],
                default_answer="Enterprise Technical Superiority & Proven Architecture Methodology",
            ),
            ClarifyingQuestion(
                question_id="compliance-gate",
                prompt="What level of human oversight and review is required before proposal finalization?",
                category="governance",
                rationale="Enforces dual-control sign-off and review in Decision Rooms.",
                options=[
                    "Mandatory Bid-Review Gate in Decision Room (Two-Person Integrity)",
                    "Single Commercial Architect Approval",
                    "Automated Draft Generation with Batch Stakeholder Review",
                ],
                default_answer="Mandatory Bid-Review Gate in Decision Room (Two-Person Integrity)",
            ),
            ClarifyingQuestion(
                question_id="completion",
                prompt="What is the required deliverable format for the proposal submission?",
                category="assurance",
                rationale="Determines the artifact package structure and compliance matrices generated.",
                options=[
                    "Full Technical & Commercial Proposal Dossier with Compliance Matrix",
                    "Executive Briefing Deck & Scope Summary",
                    "Comprehensive SOW with Pricing Table & Implementation Timeline",
                ],
                default_answer="Full Technical & Commercial Proposal Dossier with Compliance Matrix",
            ),
        ])

    # 5. General IT, Operations, or Data Management
    else:
        questions.extend([
            ClarifyingQuestion(
                question_id="source-systems",
                prompt="Which source systems and record types are in scope for this mission?",
                category="integrations",
                rationale="Explicitly bounds which data repositories and APIs the fleet may inspect.",
                options=[
                    "Local Filesystem & Git Repositories",
                    "Connected Hermes Tools & Registered MCP Servers",
                    "Enterprise Cloud APIs & Relational Databases",
                ],
                default_answer="Connected Hermes Tools & Registered MCP Servers",
            ),
            ClarifyingQuestion(
                question_id="cadence",
                prompt=f"Is {mission.constraints.execution_frequency} the required cadence, or should an event trigger start work sooner?",
                category="cadence",
                rationale="Determines whether specialists run on a schedule or listen for event streams.",
                options=[
                    f"Scheduled {mission.constraints.execution_frequency}",
                    "Continuous Polling Loop",
                    "Event-Driven Webhook / Message Trigger",
                ],
                default_answer=f"Scheduled {mission.constraints.execution_frequency}",
            ),
            ClarifyingQuestion(
                question_id="escalation",
                prompt="Which findings must pause for a human decision before any external action?",
                category="governance",
                rationale="Preserves safety boundaries and ensures human oversight for state modifications.",
                options=[
                    "All State-Mutating or External Egress Actions",
                    "Only Actions Modifying Production Infrastructure",
                    "Autonomous Operation within Daily Budget Limits",
                ],
                default_answer="All State-Mutating or External Egress Actions",
            ),
            ClarifyingQuestion(
                question_id="completion",
                prompt="What evidence makes a workflow cycle complete and acceptable?",
                category="assurance",
                rationale="Defines the definitive deliverable criteria for the blueprint compiler.",
                options=[
                    "Structured Deliverable Dossier with Verification Audit",
                    "Deterministic Unit Test / Benchmark Passing",
                    "Human Sign-off in Decision Room",
                ],
                default_answer="Structured Deliverable Dossier with Verification Audit",
            ),
        ])

    if mission.competitive_benchmarking:
        questions.append(
            ClarifyingQuestion(
                question_id="fleet-benchmark",
                prompt="Should performance comparisons be limited to specialized multi-agent fleet architectures?",
                category="benchmarking",
                rationale="Scopes the baseline comparison matrix for the blueprint evaluation.",
                options=[
                    "Specialized Multi-Agent Fleets Only",
                    "Single Monolithic Agent vs Multi-Agent",
                    "Multi-Agent Fleet vs Deterministic Script Baseline",
                ],
                default_answer="Specialized Multi-Agent Fleets Only",
            )
        )

    return questions


def _parse_questions_json(raw_text: str, competitive_benchmarking: bool = False) -> list[ClarifyingQuestion] | None:
    try:
        parsed = json.loads(_extract_json(raw_text))
        raw_questions = parsed.get("questions", [])
        if not isinstance(raw_questions, list) or not raw_questions:
            return None
        questions: list[ClarifyingQuestion] = []
        for idx, q in enumerate(raw_questions):
            qid = str(q.get("id") or f"clarification-{idx+1}")
            prompt = str(q.get("question") or q.get("prompt") or "")
            category = str(q.get("category") or "integrations")
            options = [str(o) for o in q.get("options", [])]
            rationale = q.get("rationale")
            default_ans = q.get("default_answer") or (options[0] if options else None)
            if prompt:
                questions.append(
                    ClarifyingQuestion(
                        question_id=qid,
                        prompt=prompt,
                        category=category,
                        options=options,
                        rationale=rationale,
                        allow_custom=bool(q.get("allow_custom", True)),
                        default_answer=default_ans,
                    )
                )
        if questions and competitive_benchmarking:
            questions.append(
                ClarifyingQuestion(
                    question_id="fleet-benchmark",
                    prompt="Should comparisons be limited to specialized multi-agent fleet architectures?",
                    category="benchmarking",
                    options=[
                        "Specialized Multi-Agent Fleets Only",
                        "Single Monolithic Agent vs Multi-Agent",
                        "Multi-Agent Fleet vs Deterministic Script Baseline",
                    ],
                    default_answer="Specialized Multi-Agent Fleets Only",
                )
            )
        return questions if questions else None
    except Exception as exc:
        logger.debug("Failed to parse LLM clarifying questions JSON: %s", exc)
        return None


async def _generate_via_hermes(
    mission: Mission,
    system_prompt: str,
    user_prompt: str,
) -> list[ClarifyingQuestion] | None:
    """Ask the connected Hermes gateway to formulate pre-flight clarifying questions."""
    try:
        from app.services.hermes_gateway import HermesGatewayError, connected_hermes
        async with connected_hermes() as hermes:
            setup = await hermes.call("setup.status")
            if not setup.get("provider_configured"):
                logger.info("Hermes inference provider unconfigured; using domain heuristics.")
                return None

            created = await hermes.call(
                "session.create",
                {
                    "title": f"Pre-flight Clarifications: {mission.name}",
                    "source": "fleet-studio",
                    "close_on_disconnect": True,
                },
            )
            session_id = created.get("session_id")
            if not session_id:
                return None

            combined = f"{system_prompt}\n\nTask:\n{user_prompt}\n\nRespond ONLY with the raw JSON object."
            await hermes.call("prompt.submit", {"session_id": session_id, "text": combined})

            deadline = asyncio.get_event_loop().time() + 15.0
            while asyncio.get_event_loop().time() < deadline:
                snap = await hermes.call(
                    "session.resume",
                    {"session_id": session_id, "lazy": True, "omit_messages": True},
                )
                status = str(snap.get("status") or "").lower()
                if snap.get("running") is False or status in {"idle", "completed", "complete", "stopped"}:
                    break
                await asyncio.sleep(1.0)

            history = await hermes.call("session.history", {"session_id": session_id})
            try:
                await hermes.call("session.delete", {"session_id": session_id})
            except Exception:
                pass

            for msg in reversed(history.get("messages", [])):
                if msg.get("role") == "assistant":
                    content = msg.get("content")
                    raw = content if isinstance(content, str) else "\n".join(str(i.get("text", i)) for i in content if isinstance(i, dict))
                    return _parse_questions_json(raw, mission.competitive_benchmarking)
    except Exception as exc:
        logger.info("Hermes LLM pre-flight generation bypassed (%s); using domain heuristics.", exc)
        return None


async def generate_clarifying_questions(
    mission: Mission,
    inventory: HermesEstateInventory | None = None,
) -> list[ClarifyingQuestion]:
    """Generate intelligent, targeted pre-flight clarifying questions.

    Order of evaluation:
    1. External LLM endpoint if FLEET_STUDIO_LLM_BASE_URL is configured.
    2. Connected Hermes gateway LLM session as the default intelligent agent.
    3. Resilient domain-aware heuristics fallback if Hermes inference is in standby.
    """
    tools_summary = "None detected"
    if inventory and inventory.registered_tools:
        tools_summary = ", ".join(t.tool_id for t in inventory.registered_tools[:12])

    system_prompt = CLARIFICATION_GENERATOR_PROMPT.format(
        name=mission.name,
        goal=mission.goal,
        tools_summary=tools_summary,
        residency=mission.constraints.data_residency,
        frequency=mission.constraints.execution_frequency,
    )
    user_prompt = f"Analyze this mission and formulate pre-flight clarifying questions: {mission.goal}"

    # 1. External LLM (if explicitly configured)
    if settings.llm_base_url:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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
                        "max_tokens": 1024,
                    },
                )
                if resp.status_code == 200:
                    raw_content = resp.json()["choices"][0]["message"]["content"]
                    questions = _parse_questions_json(raw_content, mission.competitive_benchmarking)
                    if questions:
                        return questions
        except Exception as exc:
            logger.warning("External LLM clarification generation unavailable (%s); trying Hermes.", exc)

    # 2. Connected Hermes Gateway LLM (Default)
    hermes_questions = await _generate_via_hermes(mission, system_prompt, user_prompt)
    if hermes_questions:
        return hermes_questions

    # 3. Resilient domain-aware heuristics fallback
    return _heuristic_clarifying_questions(mission)

