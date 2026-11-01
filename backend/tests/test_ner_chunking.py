from app.chunking import SentenceWindowSplitter
from app.ner import extract_fields, summarize_fields

WARRANTY = (
    "CERTIFICATE OF WARRANTY. Dyson Pure Cool TP07. Purchase date: 14 November 2024. "
    "This product is guaranteed for 2 years from the date of purchase. Serial no. TP7-4821-9930."
)
RECEIPT = "Fabrica Coffee Roasters, Lisbon. Coffee beans 250g 28.00. Oat flat white x2 16.50. TOTAL EUR 44.50."


def by_field(fields):
    return {f.field: f for f in fields}


def test_warranty_expiry_is_derived_from_purchase_date():
    f = by_field(extract_fields(WARRANTY))
    assert f["purchase_date"].value == "2024-11-14"
    assert f["expiry_date"].value == "2026-11-14"
    assert f["serial"].value == "TP7-4821-9930"


def test_receipt_total():
    f = by_field(extract_fields(RECEIPT))
    assert f["total"].value == "44.50"


def test_summarize_fields_orders_and_labels():
    rows = summarize_fields(extract_fields(WARRANTY))
    assert rows[0] == {"field": "expiry_date", "label": "Expires", "value": "2026-11-14"}


def test_splitter_respects_limit_and_overlaps():
    text = " ".join(f"Sentence number {i} has five words." for i in range(40))
    chunks = SentenceWindowSplitter(max_words=30, overlap_sentences=1).split_text(text)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 30 for c in chunks)
    last_sentence_of_first = chunks[0].split(". ")[-1]
    assert chunks[1].startswith(last_sentence_of_first.rstrip("."))


def test_splitter_hard_wraps_run_on_ocr():
    chunks = SentenceWindowSplitter(max_words=10).split_text("word " * 35)
    assert all(len(c.split()) <= 10 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 35
