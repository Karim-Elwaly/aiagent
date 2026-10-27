# Fleet Studio Demo Show

Estimated time: 5-8 minutes. This walkthrough demonstrates discovery and governance. It does not apply a blueprint to Hermes.

## Before the Demo

- Start the local stack with `docker compose -f deploy/docker-compose.yml up --build`.
- Open `http://localhost:3000`.
- Confirm the estate badge reports live Hermes discovery. The current local instance should show its discovered skill, tool, and model counts.
- Check **Estate inventory**. Hermes's current setup status should be shown accurately. If inference is not configured, Fleet Studio will keep designs in draft.

## Walkthrough

1. From **Mission control**, select **New mission**.
2. Enter a mission such as **Supplier exception review** and a broad goal such as: “Review supplier source documents, compare findings with policy, and route exceptions for human disposition.” Set data residency, budget, model access, execution cadence, external-action approval, and the fleet benchmarking filter.
3. Select **Continue**. The first Challenge Gate is persisted before the wizard advances. Choose **Approve and continue** to move to clarifying questions.
4. Answer the generated questions about source systems, cadence, escalation, and acceptable evidence. Continue through the clarification gate.
5. Review the generated specialist roster. Each selected skill/tool comes from Hermes inventory. Reconfigure a specialist, add or split one, choose a model/version, select a trigger, and optionally mark a workflow step as requiring a runtime human challenge. Unmatched needs appear as capability gaps.
6. Approve the roster gate, inspect the final policy/residency summary, then open the compilation gate and approve.
7. The compiled mission appears in **Missions**. If Hermes reports no configured inference provider or runtime hooks are disabled, its blueprint is `DRAFT`; no runtime change is applied.
8. Open **Decision rooms** to review pending evidence. Approved rooms expose the schema-driven form and governance email controls. SMTP/webhook dispatch remains disabled until those connectors are configured.

## Runtime Demonstration

A live workflow cycle requires all of the following:

- Configure a working inference provider in Hermes and verify `setup.status` reports it ready.
- Install the fail-closed hook using [`agents/fleetcontrol_plugin/hermes-hooks.example.yaml`](agents/fleetcontrol_plugin/hermes-hooks.example.yaml), set the API URL/daemon token in the Hermes process environment, restart Hermes, and accept hook consent.
- Set `FLEET_STUDIO_HERMES_HOOKS_ENABLED=true` only after testing that an unbound tool is blocked and an approval-required tool pauses.
- Compile a `READY` blueprint, review its plan, and explicitly approve reconciliation.

The runtime hook sends tool IDs and session IDs to Fleet Studio, not tool arguments or outputs. The demo Compose bridge is for a local loopback Hermes dashboard only; it is not a remote-gateway authentication solution.

## Demo Data

The local database contains two clearly named smoke missions from browser verification: **Fleet Studio smoke test** and **Runtime step challenge smoke**. Neither was applied to Hermes. Use a fresh mission for a presentation, or clear the local PostgreSQL volume only when its contents are disposable.
