"""Fail-closed Hermes pre-tool hook backed by Fleet Studio's compiled policy API."""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def _request(path: str, payload: dict | None = None) -> dict:
    api_url = os.environ.get("FLEET_STUDIO_API_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.environ.get("FLEET_STUDIO_DAEMON_TOKEN", "")
    if not token:
        raise RuntimeError("FLEET_STUDIO_DAEMON_TOKEN is not configured")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{api_url}{path}",
        data=body,
        headers={
            "X-Fleet-Daemon-Token": token,
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("Fleet Studio returned an invalid policy response")
    return result


def _block(message: str) -> int:
    print(json.dumps({"action": "block", "message": message}), flush=True)
    return 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name") not in {"pre_tool_call", "post_tool_call"}:
            return 0
        session_id = event.get("session_id")
        tool_name = event.get("tool_name")
        if not isinstance(session_id, str) or not session_id or not isinstance(tool_name, str) or not tool_name:
            return _block("Fleet Studio could not identify this managed Hermes tool call.")
        result = _request(
            "/api/v1/daemon/tool-policy",
            {"hook_event_name": event["hook_event_name"], "session_id": session_id, "tool_name": tool_name},
        )
        decision = result.get("decision")
        if decision in {"ALLOW", "RECORDED", "PASS_UNMANAGED"}:
            return 0
        if decision == "BLOCK":
            return _block(str(result.get("reason") or "Blocked by Fleet Studio policy."))
        if decision == "PAUSE_FOR_APPROVAL":
            room_id = str(result.get("room_id", ""))
            if not room_id:
                return _block("Fleet Studio did not return an approval room.")
            timeout_seconds = min(240, max(10, int(os.environ.get("FLEET_STUDIO_HOOK_APPROVAL_TIMEOUT", "180"))))
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                room = _request(f"/api/v1/daemon/decision-rooms/{room_id}")
                status = room.get("status")
                if status in {"APPROVE", "APPROVED"}:
                    return 0
                if status in {"REJECT", "REJECTED", "RETURNED"}:
                    return _block("The runtime tool call was rejected in its Decision Room.")
                time.sleep(2)
            return _block(f"Approval timed out in Decision Room {room_id}; retry after disposition.")
        return _block("Fleet Studio returned an unknown policy decision.")
    except (OSError, ValueError, URLError, TimeoutError, RuntimeError) as error:
        print(f"Fleet Studio hook failed closed: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())