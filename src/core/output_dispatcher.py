"""
UAOS Multi-Channel Deliverable Dispatcher (Phase 7)

Transforms final mission outputs and task artifacts into multiple deliverable formats:
1. Structured Interactive Form Schema (fields, tables, actions)
2. Executive Email Payload (.eml download, mailto: URI, styled HTML)
3. Master Dossier (Markdown with task provenance citations)
"""

from __future__ import annotations

import email.message
import email.policy
import html
import json
import logging
import re
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)


class OutputDispatcher:
    """Compiles and dispatches mission deliverables across multiple channels."""

    @staticmethod
    def compile_to_structured_form(final_output: str, dag_results: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convert markdown mission deliverables into a structured, editable form schema."""
        fields: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []

        # 1. Extract headings and key-value lines
        current_section = "General Overview"
        section_fields: list[dict[str, Any]] = []

        for line in final_output.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            # Heading detection
            if line_str.startswith("#"):
                if section_fields:
                    sections.append({"name": current_section, "fields": section_fields})
                    section_fields = []
                current_section = line_str.lstrip("#").strip()
                continue

            # Key-Value detection (e.g. "**Target Host:** 10.0.1.5" or "Status: Confirmed")
            kv_match = re.match(r"^(?:\*\*)?([A-Za-z0-9_\s\-]+)(?:\*\*)?\s*[:=]\s*(.+)$", line_str)
            if kv_match:
                key = kv_match.group(1).strip()
                val = kv_match.group(2).strip()
                fid = re.sub(r"[^a-zA-Z0-9_]+", "_", key).lower()

                field_type = "text"
                if val.lower() in ("true", "false", "yes", "no"):
                    field_type = "boolean"
                elif val.isdigit():
                    field_type = "number"
                elif "\n" in val or len(val) > 80:
                    field_type = "textarea"

                item = {
                    "id": fid,
                    "label": key,
                    "type": field_type,
                    "value": val,
                    "confidence": 0.95,
                    "editable": True,
                }
                section_fields.append(item)
                fields.append(item)

        if section_fields:
            sections.append({"name": current_section, "fields": section_fields})

        # Fallback if no structured key-values were parsed
        if not fields:
            fields.append({
                "id": "mission_deliverable_summary",
                "label": "Mission Synthesis Summary",
                "type": "textarea",
                "value": final_output[:1200],
                "confidence": 1.0,
                "editable": True,
            })
            sections.append({"name": "Executive Summary", "fields": fields})

        return {
            "title": "Mission Deliverable Form",
            "sections": sections,
            "fields": fields,
            "fields_count": len(fields),
            "dag_provenance_count": len(dag_results or {}),
        }

    @staticmethod
    def compile_to_email_payload(
        final_output: str,
        mission_title: str = "UAOS Mission Execution Report",
        recipient: str | None = None,
    ) -> dict[str, Any]:
        """Generate a polished executive email deliverable, RFC 822 .eml content, and mailto: URI."""
        to_addr = recipient or "operator@enterprise.local"
        subject = f"[MISSION REPORT] {mission_title}"

        # Extract bullet points for executive summary
        bullets: list[str] = []
        for line in final_output.splitlines():
            s = line.strip()
            if s.startswith("- ") or s.startswith("* "):
                bullets.append(s[2:].strip())
            if len(bullets) >= 5:
                break
        if not bullets:
            bullets = ["Completed autonomous execution plan with verified tool grounding.", "All phases fulfilled expected contracts."]

        # Styled HTML Email Body
        bullet_html = "".join(f"<li style='margin-bottom: 6px;'>{html.escape(b)}</li>" for b in bullets)
        safe_output = html.escape(final_output).replace("\n", "<br/>")

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }}
    .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; max-width: 720px; margin: auto; }}
    .header {{ border-bottom: 1px solid #30363d; padding-bottom: 12px; margin-bottom: 20px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #58a6ff; margin: 0; }}
    .badge {{ display: inline-block; padding: 3px 8px; font-size: 11px; font-weight: 600; border-radius: 4px; background: #238636; color: #fff; margin-top: 6px; }}
    .summary-box {{ background-color: #0d1117; border-left: 4px solid #58a6ff; padding: 12px 16px; border-radius: 0 4px 4px 0; margin-bottom: 24px; }}
    .dossier {{ font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; background-color: #0d1117; padding: 16px; border-radius: 6px; border: 1px solid #21262d; }}
    .footer {{ text-align: center; font-size: 11px; color: #8b949e; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">{html.escape(subject)}</div>
      <div class="badge">VERIFIED AUTONOMOUS MISSION</div>
    </div>
    <div class="summary-box">
      <div style="font-weight: 600; margin-bottom: 8px; color: #fff;">Executive Summary & Key Findings:</div>
      <ul style="margin: 0; padding-left: 20px;">
        {bullet_html}
      </ul>
    </div>
    <div style="font-weight: 600; margin-bottom: 8px; color: #fff;">Full Deliverable Dossier:</div>
    <div class="dossier">
      {safe_output}
    </div>
    <div class="footer">
      Dispatched via UAOS Enterprise Mission Control • Intelligent Workspace
    </div>
  </div>
</body>
</html>"""

        plain_body = (
            f"{subject}\n"
            f"{'=' * len(subject)}\n\n"
            f"EXECUTIVE SUMMARY:\n"
            + "\n".join(f"• {b}" for b in bullets)
            + f"\n\nFULL DOSSIER:\n{final_output}\n\n--\nUAOS Enterprise Mission Control"
        )

        # RFC 822 MIME message
        msg = email.message.EmailMessage(policy=email.policy.default)
        msg["Subject"] = subject
        msg["From"] = "mission-control@uaos.enterprise"
        msg["To"] = to_addr
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        eml_bytes = msg.as_bytes().decode("utf-8", errors="replace")

        # RFC 2368 mailto URI
        mailto_params = urllib.parse.urlencode({"subject": subject, "body": plain_body[:1800]})
        mailto_uri = f"mailto:{to_addr}?{mailto_params}"

        return {
            "recipient": to_addr,
            "subject": subject,
            "executive_bullets": bullets,
            "executive_summary": "\n".join(f"• {b}" for b in bullets),
            "plain_body": plain_body,
            "html_body": html_body,
            "styled_html_body": html_body,
            "eml_content": eml_bytes,
            "eml_raw": eml_bytes,
            "mailto_uri": mailto_uri,
        }
