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


# Google Vision returns label and value columns separately; rules must cope with that layout.
VISION_RECEIPT = ("COPPER KETTLE COFFEE\nRua das Flores 41\n1200-195 Lisboa\n31/10/2026 09:42\nCoffee beans 250g\n28.00\n"
                  "Oat flat white x2\n9.50\nPastel de nata x3\n7.00\nTOTAL EUR\nPAID BY CARD **** 4417\nThank you see you soon!\n44.50")
VISION_WARRANTY = ("CERTIFICATE OF WARRANTY\nAeroBreeze Home Appliances\nProduct:\nSerial no.:\nPurchase date:\nRetailer:\n"
                   "AeroBreeze Pure Cool AB-7 Air Purifier Fan\nAB7-4821-9930\n14 November 2024\nHartley & Sons, Manchester\n"
                   "This product is guaranteed for 2 years from the date of purchase\nquoting the serial number.")


def test_total_when_amount_is_in_a_separate_column():
    assert by_field(extract_fields(VISION_RECEIPT))["total"].value == "44.50"


def test_total_on_next_line():
    assert by_field(extract_fields("Item 1\n5.00\nTOTAL GBP\n129.99\nPAID"))["total"].value == "129.99"


def test_serial_in_separate_column_and_needs_a_digit():
    f = by_field(extract_fields(VISION_WARRANTY))
    assert f["serial"].value == "AB7-4821-9930"
    assert f["expiry_date"].value == "2026-11-14"
