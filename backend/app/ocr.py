"""Text extraction: Google Cloud Vision for images, embedded text for PDFs."""

import io
import logging

from app.config import get_settings

log = logging.getLogger(__name__)


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:50])


def image_text(data: bytes) -> str:
    if get_settings().ocr_backend != "vision":
        return ""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    resp = client.document_text_detection(image=vision.Image(content=data))
    if resp.error.message:
        raise RuntimeError(f"Vision API: {resp.error.message}")
    return resp.full_text_annotation.text or ""


def extract_text(data: bytes, mime: str) -> str:
    if mime == "application/pdf":
        return pdf_text(data)
    return image_text(data)
