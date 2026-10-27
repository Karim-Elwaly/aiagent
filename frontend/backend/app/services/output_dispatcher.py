import asyncio
import re
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.schemas.domain import EmailDispatchRequest, FormSchemaRequest


def build_form_schema(request: FormSchemaRequest) -> dict:
    unknown_required = set(request.required) - set(request.properties)
    if unknown_required:
        raise ValueError(f"Required fields are undefined: {', '.join(sorted(unknown_required))}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": request.title,
        "type": "object",
        "properties": request.properties,
        "required": request.required,
        "additionalProperties": False,
    }


def _redact(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted email]", text)
    return re.sub(r"\b(?:\+?\d[\d ()-]{7,}\d)\b", "[redacted phone]", text)


def _send_message(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def dispatch_governance_email(
    request: EmailDispatchRequest,
    *,
    approver: str,
    decision: str,
    summary: str,
    evidence_references: list[str],
) -> None:
    if not settings.smtp_host or not settings.smtp_sender:
        raise RuntimeError("SMTP output connector is not configured.")
    message = EmailMessage()
    message["To"] = request.recipient
    message["From"] = settings.smtp_sender
    message["Subject"] = request.subject
    message["Message-ID"] = f"<fleet-studio-{request.room_id}@{settings.smtp_sender.split('@')[-1]}>"
    references = "\n".join(f"- {_redact(reference)}" for reference in evidence_references)
    message.set_content(
        "Fleet Studio governance decision\n\n"
        f"Decision: {decision}\n"
        f"Approver: {_redact(approver)}\n\n"
        f"Summary:\n{_redact(summary)}\n\n"
        f"Redacted evidence references:\n{references or '- None attached'}\n"
    )
    await asyncio.to_thread(_send_message, message)


async def dispatch_structured_webhook(payload: dict, idempotency_key: str) -> None:
    if not settings.output_webhook_url:
        raise RuntimeError("Structured output webhook is not configured.")
    headers = {"Authorization": f"Bearer {settings.output_webhook_token}"} if settings.output_webhook_token else {}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                settings.output_webhook_url,
                json=payload,
                headers={**headers, "Idempotency-Key": idempotency_key},
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("Structured output webhook delivery failed.") from error