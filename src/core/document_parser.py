"""
Document and File Parser Service for User Attachments.

Handles parsing and text extraction for various document formats:
- Plain text / logs / data: .txt, .log, .csv, .json, .md, .xml, .yaml, .yml, .py
- PDF documents: .pdf (via pypdf if available, with robust pure-python stream fallback)
- Word documents: .docx (via python-docx if available, with pure-python zip/XML fallback)

Parsed files are stored locally under data/uploads/{session_id}/ to allow
direct filesystem inspection by worker agent tools (read_file, grep_search, etc.).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Max characters extracted into prompt context to prevent context window saturation
MAX_EXTRACT_CHARS = 24000
MAX_PREVIEW_CHARS = 600

# Base uploads directory
UPLOADS_BASE_DIR = Path("data/uploads")


class AttachmentMeta(BaseModel):
    id: str
    filename: str
    file_path: str
    file_type: str
    size_bytes: int
    extracted_text: str
    char_count: int
    preview: str


def _clean_text(text: str) -> str:
    """Normalize whitespace and strip null/control characters."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()


def parse_plaintext_file(file_path: Path) -> str:
    """Read plaintext, logs, csv, json, yaml, etc. with encoding fallbacks."""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            content = file_path.read_text(encoding=enc)
            return _clean_text(content)
        except Exception:
            continue
    try:
        raw = file_path.read_bytes()
        return _clean_text(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        return f"[Error reading plaintext: {exc}]"


def parse_pdf_file(file_path: Path) -> str:
    """Extract text from PDF using pypdf if available, else pure-python stream parsing."""
    # 1. Try pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        pages_text: list[str] = []
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"--- [Page {idx + 1}] ---\n{txt.strip()}")
            if sum(len(p) for p in pages_text) > MAX_EXTRACT_CHARS:
                pages_text.append("\n[...text truncated due to length...]")
                break
        if pages_text:
            return "\n\n".join(pages_text)
    except ImportError:
        logger.debug("pypdf not installed; attempting fallback PDF stream extractor")
    except Exception as exc:
        logger.warning("pypdf failed on '%s': %s; trying fallback", file_path.name, exc)

    # 2. Pure-Python stream extraction fallback
    try:
        data = file_path.read_bytes()
        # Look for literal string chunks inside PDF streams
        text_chunks: list[str] = []
        for match in re.finditer(rb"\(([^\(\)\\]{3,})\)", data):
            chunk = match.group(1).decode("latin-1", errors="replace")
            clean_chunk = "".join(c for c in chunk if c.isprintable() or c in "\n\t ")
            if len(clean_chunk.strip()) > 3:
                text_chunks.append(clean_chunk.strip())
            if sum(len(c) for c in text_chunks) > MAX_EXTRACT_CHARS:
                break
        if text_chunks:
            return " ".join(text_chunks)
    except Exception as exc:
        logger.warning("PDF stream extraction failed on '%s': %s", file_path.name, exc)

    return f"[PDF: {file_path.name} saved on disk. Tools can inspect raw structure if needed.]"


def parse_docx_file(file_path: Path) -> str:
    """Extract text from Word (.docx) using python-docx if installed, or pure-python XML parsing."""
    # 1. Try python-docx
    try:
        import docx
        doc = docx.Document(str(file_path))
        paragraphs: list[str] = []
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                paragraphs.append(p.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
            if sum(len(p) for p in paragraphs) > MAX_EXTRACT_CHARS:
                paragraphs.append("[...document truncated...]")
                break
        if paragraphs:
            return "\n".join(paragraphs)
    except ImportError:
        logger.debug("python-docx not installed; attempting pure-python docx XML extraction")
    except Exception as exc:
        logger.warning("python-docx extraction failed on '%s': %s; trying fallback", file_path.name, exc)

    # 2. Pure-Python docx extraction from word/document.xml
    try:
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as z:
                if "word/document.xml" in z.namelist():
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    # Namespace for WordprocessingML
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    paragraphs = []
                    for p in tree.iter(f"{{{ns['w']}}}p"):
                        texts = [t.text for t in p.iter(f"{{{ns['w']}}}t") if t.text]
                        line = "".join(texts).strip()
                        if line:
                            paragraphs.append(line)
                        if sum(len(l) for l in paragraphs) > MAX_EXTRACT_CHARS:
                            paragraphs.append("[...document truncated...]")
                            break
                    if paragraphs:
                        return "\n".join(paragraphs)
    except Exception as exc:
        logger.warning("Pure XML docx extraction failed on '%s': %s", file_path.name, exc)

    return f"[Word Document: {file_path.name} saved on disk at {file_path.resolve()}]"


def process_uploaded_file(file_bytes: bytes, filename: str, session_id: str | None = None) -> AttachmentMeta:
    """Save an uploaded file to disk and parse its contents."""
    sess_id = session_id or uuid.uuid4().hex[:8]
    target_dir = UPLOADS_BASE_DIR / sess_id
    target_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    clean_name = re.sub(r"[^\w\.\-\_]", "_", filename)
    file_path = target_dir / clean_name

    file_path.write_bytes(file_bytes)
    size_bytes = len(file_bytes)

    ext = file_path.suffix.lower()
    file_type = "text"
    extracted = ""

    if ext == ".pdf":
        file_type = "pdf"
        extracted = parse_pdf_file(file_path)
    elif ext in (".docx", ".doc"):
        file_type = "docx"
        extracted = parse_docx_file(file_path)
    else:
        file_type = ext.lstrip(".") or "text"
        extracted = parse_plaintext_file(file_path)

    # Bound extracted text
    if len(extracted) > MAX_EXTRACT_CHARS:
        extracted = extracted[:MAX_EXTRACT_CHARS] + f"\n\n[...Truncated: total length {len(extracted)} chars. Full file saved at {file_path.resolve()}...]"

    preview = extracted[:MAX_PREVIEW_CHARS].strip()
    if len(extracted) > MAX_PREVIEW_CHARS:
        preview += "..."

    return AttachmentMeta(
        id=f"att-{uuid.uuid4().hex[:8]}",
        filename=clean_name,
        file_path=str(file_path.resolve()),
        file_type=file_type,
        size_bytes=size_bytes,
        extracted_text=extracted,
        char_count=len(extracted),
        preview=preview,
    )
