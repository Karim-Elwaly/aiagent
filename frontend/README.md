# Fleet Studio

Fleet Studio is a desired-state governance and control plane for specialized Hermes Agent fleets. Hermes runs the model and tools; Fleet Studio owns mission blueprints, capability policy, approvals, reconciliation, and evidence.

## Quick Start

Requirements: Docker Desktop, Hermes Agent 0.21.x, and a configured Hermes dashboard. The checked-in Compose defaults are for an isolated local machine only.

1. Copy `.env.example` to `.env` and set unique `FLEET_STUDIO_SESSION_SECRET` and `FLEET_STUDIO_DAEMON_TOKEN` values.
2. Set `FLEET_STUDIO_HERMES_BASE_URL=http://host.docker.internal:9119`. For local Compose only, keep `FLEET_STUDIO_HERMES_LOOPBACK_BRIDGE_ENABLED=true`; do not use it with a remote or public Hermes dashboard.
3. Start PostgreSQL, API, web, and daemon:

   ```powershell
   docker compose -f deploy/docker-compose.yml up --build
   ```

4. Open [Mission Control](http://localhost:3000). The API is at `http://127.0.0.1:8001`, with OpenAPI docs at `/docs`.

See [IMPLEMENTED.md](IMPLEMENTED.md) for the delivered-work inventory, [FEATURES.md](FEATURES.md) for the feature status matrix, and [DEMO_SHOW.md](DEMO_SHOW.md) for a guided walkthrough.

## Hermes Runtime Hook

The adapter uses Hermes 0.21.x JSON-RPC over `/api/ws`. The local bridge reads the loopback dashboard session bootstrap token in memory and does not log it. Remote Hermes OIDC ticket auth is not implemented.

To enable runtime calls, configure the Hermes process with `FLEET_STUDIO_API_URL` and `FLEET_STUDIO_DAEMON_TOKEN`, merge [`agents/fleetcontrol_plugin/hermes-hooks.example.yaml`](agents/fleetcontrol_plugin/hermes-hooks.example.yaml) into the existing Hermes `config.yaml`, restart Hermes, and accept first-use hook consent. Enable `FLEET_STUDIO_HERMES_HOOKS_ENABLED=true` only after testing blocked and approval-held calls. The hook sends session/tool identifiers only, not parameters or results.

## Production Gate

The connected Hermes instance currently reports `provider_configured=false`, and the runtime hook is disabled. Fleet Studio therefore keeps blueprints in `DRAFT` and refuses workflow cycles. Configure an inference provider and install/test the fail-closed hook before expecting execution.

Other production work remains: remote Hermes service authentication, Langfuse ingestion, production SMTP/webhook delivery tests, HA daemon leasing, retention/backup drills, TLS/network policies, secret-manager integration, and an RKE2 deployment test. Hermes does not report native tool schemas, skill versions, or risk/residency/pricing metadata; those values remain unknown and native tools default to approval-required. Do not relax those defaults without operator review.

## Verification

- 16 backend tests pass on the host's Python 3.11; container images target Python 3.12.
- Frontend lint/build, Compose startup, Alembic migrations through `0007`, Helm render/lint, and live Hermes inventory were verified.
- The connected Hermes v0.21.3 instance reports 57 skills, 42 tools, and 21 model IDs.
- Browser smoke test completed all four challenge gates and created a draft blueprint; nothing was applied to Hermes.

