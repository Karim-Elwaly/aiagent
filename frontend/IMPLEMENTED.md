# Implemented Work

This file records what is present in the repository and what was verified locally. It is an implementation inventory, not a production certification.

## Control Plane

- FastAPI v1 routes backed by async SQLAlchemy and PostgreSQL.
- Alembic migrations through `0007_hermes_stored_session` for missions, proposals/blueprints, agents/workflows, runs/steps, evidence/policies, challenge gates, Decision Rooms, daemon jobs, and Hermes session continuations.
- Mission intake, clarification answers, capability-driven proposal generation, blueprint versioning, persisted challenge gates, and draft/ready state.
- Blueprint compilation validates exact discovered skill/tool/model IDs, per-skill required tools, step capabilities, workflow DAG dependencies, duplicate IDs, and cycles.
- Reconciliation compares declared agent specs with last applied state. Changes require explicit human confirmation; removals and approval-required actions require separate confirmation.
- Idempotent daemon jobs for reconciliation, scheduled cycles, event handoffs, and signed webhooks.

## Hermes Integration

- Authenticated read-only discovery uses Hermes Agent 0.21.x JSON-RPC over `/api/ws`: `tools.list`, `tools.show`, `skills.manage`, `model.options`, `mcp.servers.list`, and `setup.status`.
- The connected local Hermes 0.21.3 instance returned 57 skills, 42 enabled tools, and 21 model IDs during verification.
- Hermes fields it does not expose remain unknown. Native tools default to mutating and approval-required; MCP tools default to external-egress and approval-required. Residency and cost must be known before a model can satisfy those constraints.
- The host daemon restores CRON/continuous-poll schedules and drives ordered workflow steps as Hermes sessions. Event and signed-webhook triggers are idempotent.
- The Hermes shell hook enforces managed-session tool allowlists, creates Decision Rooms for approval-required calls, blocks unbound tools, records redacted evidence, and fails closed if the API is unavailable. Unmanaged Hermes sessions pass through.
- Runtime step challenges persist the run/session/step, pause before execution, and queue a continuation of that same Hermes session after approval. Rejections mark the step policy-blocked.

## Governance and Assurance

- Five-role Authlib OIDC boundaries for `PlatformEngineer`, `FleetArchitect`, `Operator`, `ComplianceOfficer`, and `Approver`.
- Decision Room dispositions are persisted, attributed to the authenticated user, and cannot be changed twice.
- Agent-authored `JUDGMENT` is rejected; decision-required workflow results go to a human room.
- Transcript assurance implements `EVIDENCE_FOUND`, `NO_EVIDENCE`, `NOT_VERIFIABLE`, and `POLICY_BLOCKED`.
- OTel spans and evidence store correlation identifiers for fleet, agent, workflow cycle, and step. OTLP export endpoint/headers are configurable.
- Approved-room forms are generated/validated from JSON Schema. Email and structured-webhook outputs require an approved room and have duplicate-dispatch state.

## Frontend and Packaging

- Next.js App Router UI for Mission Control, missions, fleet roster/topology, Decision Rooms, and live Hermes inventory.
- Wizard challenge controls, dynamic capability selectors, model/version pinning, trigger configuration, per-step challenge toggles, and real zero states.
- Mission, roster, inventory, rooms, and telemetry views consume the API; no seeded fleet metrics are presented as live data.
- Compose starts PostgreSQL 16, API, frontend, and daemon. The host API is published at `127.0.0.1:8001` to avoid conflicting with a service on port 8000.
- Helm templates render and lint; chart values include RKE2 placement, ingress, services, secrets, and daemon deployment.

## Verified

- 16 backend unit/API tests pass on the available host Python 3.11 runtime.
- Frontend lint and production build pass.
- Compose images built and all four services ran healthy; the API reports the latest Alembic revision.
- Helm template and lint commands pass through a disposable Helm container.
- Browser smoke test persisted a mission through all four design gates and compiled it as `DRAFT` without applying it to Hermes.

## Still Required Before Production Execution

- The connected Hermes instance reports `provider_configured=false`. Configure a working inference provider first.
- Install and test the fail-closed shell hook in the Hermes process, then explicitly enable `FLEET_STUDIO_HERMES_HOOKS_ENABLED`. It is disabled by default.
- Configure production OIDC, PostgreSQL, daemon/webhook/SMTP/OTLP secrets and TLS. The Docker loopback token bridge is local development only; remote Hermes OIDC-ticket authentication is not implemented.
- Langfuse ingestion, production connector delivery tests, RKE2/SAS Viya deployment tests, high-availability daemon leasing, retention, backup/restore, load, and incident-recovery tests remain outstanding.
- Docker images target Python 3.12, but the host test interpreter is Python 3.11. Production images were built; tests were not run under Python 3.12 on this host.

Two named smoke missions remain in the local database; neither has been applied to Hermes.
