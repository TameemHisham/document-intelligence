"""Per-user FAISS indexes persisted to disk.

IndexIDMap2(IndexFlatIP) over L2-normalized vectors = exact cosine search, keyed by our DB ids.
IDMap2 (not IDMap) so vectors can be reconstructed for scoped search inside a project.
"""

import threading
from collections import defaultdict
from pathlib import Path

import faiss
import numpy as np

from app.config import get_settings
from app.embeddings import CLIP_DIM, TEXT_DIM

_DIMS = {"text": TEXT_DIM, "image": CLIP_DIM}
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


class UserIndex:
    def __init__(self, user_id: str, kind: str):
        if kind not in _DIMS:
            raise ValueError(kind)
        self.kind = kind
        self.path: Path = get_settings().data_dir / "indexes" / user_id / f"{kind}.faiss"
        self.lock = _locks[str(self.path)]

    def _load(self) -> faiss.IndexIDMap2:
        if self.path.exists():
            return faiss.read_index(str(self.path))
        return faiss.IndexIDMap2(faiss.IndexFlatIP(_DIMS[self.kind]))

    def _save(self, index) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        faiss.write_index(index, str(tmp))
        tmp.replace(self.path)

    def add(self, ids: list[int], vecs: np.ndarray) -> None:
        if not ids:
            return
        with self.lock:
            index = self._load()
            index.add_with_ids(np.ascontiguousarray(vecs, dtype="float32"), np.asarray(ids, dtype="int64"))
            self._save(index)

    def remove(self, ids: list[int]) -> None:
        if not ids:
            return
        with self.lock:
            index = self._load()
            index.remove_ids(np.asarray(ids, dtype="int64"))
            self._save(index)

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        with self.lock:
            index = self._load()
        if index.ntotal == 0:
            return []
        scores, ids = index.search(np.ascontiguousarray(query.reshape(1, -1), dtype="float32"), min(k, index.ntotal))
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def search_subset(self, query: np.ndarray, ids: list[int], k: int) -> list[tuple[int, float]]:
        """Exact search restricted to given ids (project / single-document scope)."""
        if not ids:
            return []
        with self.lock:
            index = self._load()
        vecs, kept = [], []
        for i in ids:
            try:
                vecs.append(index.reconstruct(int(i)))
                kept.append(i)
            except RuntimeError:
                continue  # id not in index (e.g. failed ingest)
        if not kept:
            return []
        scores = np.vstack(vecs) @ query.reshape(-1)
        order = np.argsort(-scores)[:k]
        return [(int(kept[j]), float(scores[j])) for j in order]
