"""Custom chunking built on LangChain's TextSplitter.

Sentence-aware packing (spaCy sentencizer) up to N words with sentence overlap, plus a
"contextual header" (document title) prefixed to every chunk so short fragments stay retrievable.
"""

from functools import lru_cache

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import TextSplitter

from app.config import get_settings


@lru_cache
def _sentencizer():
    import spacy

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


class SentenceWindowSplitter(TextSplitter):
    def __init__(self, max_words: int = 120, overlap_sentences: int = 1, **kwargs):
        super().__init__(chunk_size=max_words, chunk_overlap=0, **kwargs)
        self.max_words = max_words
        self.overlap = overlap_sentences

    def split_text(self, text: str) -> list[str]:
        text = " ".join(text.split())
        if not text:
            return []
        sents = [s.text.strip() for s in _sentencizer()(text).sents if s.text.strip()]
        chunks: list[str] = []
        cur: list[str] = []
        words = 0
        for s in sents:
            n = len(s.split())
            if cur and words + n > self.max_words:
                chunks.append(" ".join(cur))
                cur = cur[-self.overlap :] if self.overlap else []
                words = sum(len(x.split()) for x in cur)
            if n > self.max_words:  # pathological run-on sentence (common in OCR): hard-wrap
                ws = s.split()
                for i in range(0, len(ws), self.max_words):
                    chunks.append(" ".join(ws[i : i + self.max_words]))
                cur, words = [], 0
                continue
            cur.append(s)
            words += n
        if cur and (not chunks or " ".join(cur) != chunks[-1]):
            chunks.append(" ".join(cur))
        return chunks


def build_chunks(title: str, header: str, body: str, metadata: dict) -> list[LCDocument]:
    """First chunk = descriptive header (title, summary, caption, fields); then body chunks."""
    s = get_settings()
    splitter = SentenceWindowSplitter(s.chunk_max_words, s.chunk_overlap_sentences)
    docs = []
    if header.strip():
        docs.append(LCDocument(page_content=header.strip(), metadata={**metadata, "idx": 0}))
    for i, piece in enumerate(splitter.split_text(body), start=len(docs)):
        docs.append(LCDocument(page_content=f"{title}: {piece}" if title else piece, metadata={**metadata, "idx": i}))
    return docs
