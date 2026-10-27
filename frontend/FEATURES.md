# Fleet Studio Feature List

Status legend: **Implemented** means the code path exists and has automated/local verification. **Configured** means it requires operator-owned credentials or Hermes settings. **Not complete** means it is not implemented or has not been validated for production.

## Admin and Mission Control

- **Implemented:** Mission intake with data residency, cloud access, budget, cadence, action approval, and fleet-only benchmarking fields.
- **Implemented:** Clarifying questions are generated from the mission and saved before proposal generation.
- **Implemented:** The four design stages have persisted challenge gates: intake, clarification, roster, and compilation. Latest gate decisions block compilation unless approved.
- **Implemented:** Hermes-driven skill/tool/model discovery through the documented Hermes 0.21.x JSON-RPC WebSocket.
- **Implemented:** Fleet proposals bind only discovered skill/tool IDs. Missing matches become capability gaps; unresolved gaps keep the blueprint in `DRAFT`.
- **Implemented:** The roster editor supports agent add/remove/split, exact discovered skill/tool choices, model family/version selection, trigger policy, upstream dependencies, and per-step human challenge requirements.
- **Implemented:** Blueprint versioning, database persistence, declared/applied agent state, drift planning, explicit apply/removal/external-action approvals, and daemon reconciliation jobs.
- **Implemented:** Mission, roster, telemetry, and inventory screens read persisted/API-backed state. Empty states do not invent fleets or metrics.

## Continuous Workflows and Hermes

- **Implemented:** Cron and continuous-poll schedule registration; event-driven handoffs and HMAC-signed webhook triggers are persisted and idempotent.
- **Implemented:** Host daemon long-polls jobs, claims them, reports outcomes, restores schedules, starts Hermes sessions for workflow cycles, records steps/evidence, and resumes approved runtime step challenges.
- **Implemented:** Hermes pre/post tool shell hook blocks unbound calls, pauses approval-required calls in Decision Rooms, redacts arguments, and fails closed on policy-service errors. Unmanaged interactive Hermes sessions pass through.
- **Configured:** The shell hook must be merged into the Hermes user's existing `config.yaml`, consented to, and enabled. Fleet Studio's `FLEET_STUDIO_HERMES_HOOKS_ENABLED` must remain false until that install is tested.
- **Configured:** A working Hermes inference provider is required. The connected Hermes instance currently reports `provider_configured=false`; execution stays disabled and blueprints remain drafts.
- **Not complete:** Remote/OIDC-ticket authentication to a Hermes dashboard. The current token bridge is restricted to local loopback/Compose use.
- **Not available from Hermes inventory:** Native parameter schemas, skill versions/descriptions, explicit native-tool risk, provider pricing, reasoning tiers, and most residency metadata. Fleet Studio leaves these unknown and uses conservative tool approvals.

## Governance and Assurance

- **Implemented:** Persistent Decision Rooms with authenticated approver/compliance decisions and duplicate-decision protection.
- **Implemented:** Agent `JUDGMENT` is rejected by schema; runtime decisions are escalated to a human room.
- **Implemented:** Four transcript assurance verdicts; analytical evidence requires a matching supporting quote and trace availability or is marked not verifiable.
- **Implemented:** OpenTelemetry spans carry `fleet_id`, `agent_id`, `workflow_cycle_id`, and `step_id` correlations; OTLP endpoint/headers are configurable.
- **Implemented:** Approved-room JSON Schema generation, submission validation, email sign-off, structured webhook output, and dispatch idempotency state.
- **Configured:** SMTP and webhook credentials/URLs are external settings or Kubernetes Secrets. Live delivery against a production provider has not been tested.
- **Not complete:** Langfuse ingestion and cross-system trace/transcript correlation.

## Identity and Deployment

- **Implemented:** Authlib OIDC login/callback and role checks for `PlatformEngineer`, `FleetArchitect`, `Operator`, `ComplianceOfficer`, and `Approver`; daemon and webhook interfaces use separate service credentials.
- **Configured:** Production OIDC issuer/client/role claim, database, daemon, webhook, SMTP, and OTLP secrets.
- **Implemented:** PostgreSQL 16, async SQLAlchemy, Alembic revisions through `0007`, Docker Compose, and an RKE2-oriented Helm chart.
- **Verified locally:** Compose builds and starts PostgreSQL/API/frontend/daemon; Helm template rendering and lint pass.
- **Not validated:** Installation into an RKE2/SAS Viya cluster, HA/leader election, backup/restore, retention policy, network policy, TLS, production load, and incident recovery.
