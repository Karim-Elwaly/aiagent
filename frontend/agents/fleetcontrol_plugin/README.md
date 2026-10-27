# Hermes Runtime Hook

`hook.py` implements Hermes Agent 0.21.x `pre_tool_call` / `post_tool_call` shell hooks. It sends only the Hermes session ID and tool name to Fleet Studio; tool arguments and results are never sent. The API maps the session to an applied workflow cycle, blocks tools outside that agent's allowlist, and waits for a Decision Room before approval-required calls continue.

## Configure

1. Set `FLEET_STUDIO_API_URL` and `FLEET_STUDIO_DAEMON_TOKEN` in the environment inherited by the Hermes process. The token must match Fleet Studio's daemon token.
2. Merge [`hermes-hooks.example.yaml`](hermes-hooks.example.yaml) into the existing Hermes `config.yaml`, replacing both paths with absolute paths valid to the Hermes process.
3. Enable `FLEET_STUDIO_HERMES_HOOKS_ENABLED=true` in the API only after the hook has been installed and tested. Without this flag, Fleet Studio will keep blueprints in `DRAFT` and refuse reconciliation.
4. Restart Hermes so it loads the hooks. Hermes requires first-use hook consent unless its administrator has already approved the command.

The hook fails closed on API/network errors. `pre_tool_call` uses `fail_closed: true`; keep the backend highly available and monitor hook failures. The daemon token grants policy API access and must be stored in a secret manager, never in source control.