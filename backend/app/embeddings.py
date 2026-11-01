"""Two embedding spaces:
- text: Sentence-BERT (all-MiniLM-L6-v2, 384-d) for OCR/caption chunks
- clip: CLIP ViT-B/32 (512-d) - images and text share one space, so "mountain" finds mountain photos.

FAKE_MODELS=1 swaps both for deterministic bag-of-words hashing (no downloads), used by tests.
"""

import hashlib
import re
from functools import lru_cache

import numpy as np
from PIL import Image

from app.config import get_settings

TEXT_DIM = 384
CLIP_DIM = 512


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype="float32")
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def _hash_embed(texts: list[str], dim: int) -> np.ndarray:
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            out[i, h % dim] += 1.0 if (h >> 64) & 1 else -1.0
    return _normalize(out + 1e-6)


@lru_cache
def _sbert():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().text_model)


@lru_cache
def _clip():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().clip_model)


def embed_text(texts: list[str]) -> np.ndarray:
    if get_settings().fake_models:
        return _hash_embed(texts, TEXT_DIM)
    return _normalize(_sbert().encode(texts, batch_size=32, show_progress_bar=False))


def clip_text(texts: list[str]) -> np.ndarray:
    if get_settings().fake_models:
        return _hash_embed(texts, CLIP_DIM)
    return _normalize(_clip().encode(texts, show_progress_bar=False))


def clip_image(image: Image.Image, fake_hint: str = "") -> np.ndarray:
    if get_settings().fake_models:
        return _hash_embed([fake_hint], CLIP_DIM)
    return _normalize(_clip().encode([image.convert("RGB")], show_progress_bar=False))
