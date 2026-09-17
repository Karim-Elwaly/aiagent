"""
Multi-Channel Messaging & Webhook Gateways for UAOS.

Allows external platforms (Slack, Telegram, CI/CD, generic webhooks) to trigger
UAOS problem-solving workflows and receive asynchronous solution callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["Gateways"])


class GenericWebhookPayload(BaseModel):
    """Payload for triggering UAOS via generic webhook (e.g. GitHub Actions, Grafana)."""

    query: str = Field(description="The problem query to solve")
    agent_id: str | None = Field(default=None, description="Optional Agent Profile ID")
    callback_url: str | None = Field(default=None, description="Webhook URL to POST final solution to")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary event metadata")


async def _notify_callback(callback_url: str, workflow_id: str, query: str, app_instance: Any) -> None:
    """Wait for workflow completion and post results back to the external platform."""
    logger.info("Monitoring workflow '%s' for webhook callback to %s", workflow_id, callback_url)

    # Poll status for up to 5 minutes
    for _ in range(60):
        await asyncio.sleep(5.0)
        try:
            status = None
            response_text = ""

            if workflow_id in app_instance.state.direct_workflows:
                dw = app_instance.state.direct_workflows[workflow_id]
                status = dw.get("status")
                if status in ("completed", "failed"):
                    res = dw.get("result", {})
                    response_text = res.get("response", "Workflow finished with no output")
            elif getattr(app_instance.state, "temporal", None):
                try:
                    handle = app_instance.state.temporal.get_workflow_handle(workflow_id)
                    desc = await handle.describe()
                    t_status = desc.status.name.lower()
                    if t_status in ("completed", "failed"):
                        status = t_status
                        res = await handle.result()
                        response_text = res.get("response", "") if isinstance(res, dict) else str(res)
                except Exception:
                    pass

            if status in ("completed", "failed"):
                async with httpx.AsyncClient(timeout=15.0) as client:
                    await client.post(
                        callback_url,
                        json={
                            "workflow_id": workflow_id,
                            "query": query,
                            "status": status,
                            "solution": response_text or "Workflow finished with no output",
                        },
                    )
                logger.info("Successfully posted webhook callback for '%s'", workflow_id)
                return
        except Exception as e:
            logger.debug("Error checking workflow status for callback: %s", e)


@router.post("/generic")
async def generic_webhook_endpoint(
    payload: GenericWebhookPayload,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Trigger a workflow via JSON webhook."""
    from uuid import uuid4

    app = request.app
    workflow_id = f"uaos-wh-{uuid4().hex[:8]}"

    # Dispatch workflow using existing dispatch logic
    if hasattr(app.state, "dispatch_workflow"):
        actual_id = await app.state.dispatch_workflow(payload.query, payload.agent_id)
        if actual_id:
            workflow_id = actual_id

    if payload.callback_url:
        background_tasks.add_task(_notify_callback, payload.callback_url, workflow_id, payload.query, app)

    return {
        "status": "dispatched",
        "workflow_id": workflow_id,
        "query": payload.query,
        "callback_configured": bool(payload.callback_url),
    }


@router.post("/slack")
async def slack_slash_command_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Handle Slack slash commands (e.g. /uaos <query>) and reply asynchronously."""
    content_type = request.headers.get("content-type", "")
    query = ""
    response_url = ""

    if "application/json" in content_type:
        try:
            body = await request.json()
            query = str(body.get("text") or body.get("query") or "").strip()
            response_url = str(body.get("response_url") or "")
        except Exception:
            pass
    else:
        raw_body = await request.body()
        try:
            parsed = parse_qs(raw_body.decode("utf-8", errors="ignore"))
            text_list = parsed.get("text", [])
            query = (text_list[0] if text_list else "").strip()
            url_list = parsed.get("response_url", [])
            response_url = url_list[0] if url_list else ""
        except Exception as e:
            logger.warning("Failed to parse Slack form body: %s", e)

    if not query:
        return {
            "response_type": "ephemeral",
            "text": "⚠️ Please provide a query or instruction: `/uaos [problem to solve]`",
        }

    app = request.app
    from uuid import uuid4
    workflow_id = f"uaos-slack-{uuid4().hex[:8]}"

    if hasattr(app.state, "dispatch_workflow"):
        actual_id = await app.state.dispatch_workflow(query, None)
        if actual_id:
            workflow_id = actual_id

    # Background task to send full markdown response back to Slack
    async def _send_slack_reply():
        for _ in range(60):
            await asyncio.sleep(5.0)
            try:
                status = None
                resp_text = ""

                if workflow_id in app.state.direct_workflows:
                    dw = app.state.direct_workflows[workflow_id]
                    status = dw.get("status")
                    if status in ("completed", "failed"):
                        res = dw.get("result", {})
                        resp_text = res.get("response", "Completed without text.")
                elif getattr(app.state, "temporal", None):
                    try:
                        handle = app.state.temporal.get_workflow_handle(workflow_id)
                        desc = await handle.describe()
                        t_status = desc.status.name.lower()
                        if t_status in ("completed", "failed"):
                            status = t_status
                            res = await handle.result()
                            resp_text = res.get("response", "") if isinstance(res, dict) else str(res)
                    except Exception:
                        pass

                if status in ("completed", "failed") and response_url:
                    try:
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            await client.post(
                                response_url,
                                json={
                                    "response_type": "in_channel",
                                    "text": f"✅ *UAOS Solution for:* _{query}_\n\n{resp_text or 'Completed without text.'}",
                                },
                            )
                    except Exception as e:
                        logger.error("Failed to post Slack response: %s", e)
                    return
            except Exception as e:
                logger.debug("Error checking Slack workflow status: %s", e)

    if response_url:
        background_tasks.add_task(_send_slack_reply)

    return {
        "response_type": "ephemeral",
        "text": f"🚀 *UAOS Orchestrator Active*\nWorkflow `{workflow_id}` started for: _{query}_. Results will be posted here momentarily.",
    }
