from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec
import textwrap

async def summarize_to_presentation(content: str) -> str:
    """
    Summarizes the provided content into a concise presentation format.
    The output is a structured string with slide titles and bullet points.
    """
    # Simple heuristic: split by paragraphs, take first sentence as title, rest as bullets
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    slides = []
    for idx, para in enumerate(paragraphs, start=1):
        sentences = [s.strip() for s in para.replace(". ", ".| ").split("|") if s.strip()]
        title = sentences[0] if sentences else f"Slide {idx}"
        bullets = sentences[1:5]  # limit to 4 bullets
        slide_text = f"Slide {idx}: {title}\n" + "\n".join(f"- {b}" for b in bullets)
        slides.append(slide_text)
    presentation = "\n\n---\n\n".join(slides)
    return presentation

SUMMARIZE_TO_PRESENTATION_SPEC = ToolSpec(
    tool_id="summarize_to_presentation_v1",
    name="summarize_to_presentation",
    description="Summarizes provided content into a concise presentation format with slide titles and bullet points.",
    skills_provided=["summarization"],
    parameters={
        "content": {
            "type": "string",
            "description": "The raw text or report to be summarized for a presentation.",
            "required": True
        }
    },
    function=summarize_to_presentation,
    risk_level=RiskLevel.LOW
)
