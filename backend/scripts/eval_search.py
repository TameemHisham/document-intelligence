"""Retrieval eval on the demo library (hit@1, hit@3, MRR, latency). Free: local models + rule parser.

Run from backend/ after seeding the demo template: PYTHONPATH=. python scripts/eval_search.py
"""
import statistics
import time

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import User
from app.query_parser import parse_rules
from app.search import search

# (query, relevant filenames) - paraphrased, not copied from titles
QUERIES = [
    ("mountain in the background", {"mountain-lake.jpg"}),
    ("snow capped peaks and a lake", {"mountain-lake.jpg"}),
    ("palm trees by the sea", {"tropical-beach.jpg"}),
    ("person wearing a hoodie", {"person-hoodie.jpg"}),
    ("someone smiling", {"person-hoodie.jpg"}),
    ("city at night with lights", {"city-night.jpg"}),
    ("plate of food for breakfast", {"dinner-table.jpg"}),
    ("people having a picnic on grass", {"dog-park.jpg"}),
    ("path through the woods", {"forest-trail.jpg"}),
    ("coffee with milk foam art", {"latte-art.jpg"}),
    ("winter street covered in snow", {"snowy-street.jpg"}),
    ("bike pulled out of the water", {"bicycle-canal.jpg"}),
    ("warranty", {"doc-warranty-air-purifier.jpg"}),
    ("air purifier guarantee certificate", {"doc-warranty-air-purifier.jpg"}),
    ("coffee shop receipt", {"doc-receipt-coffee.jpg"}),
    ("headphones purchase", {"doc-receipt-headphones.jpg"}),
    ("receipts", {"doc-receipt-coffee.jpg", "doc-receipt-headphones.jpg"}),
    ("cell division mitosis notes", {"doc-lecture-notes-biology.jpg"}),
    ("how to clean the coffee grinder", {"doc-grinder-manual.jpg"}),
    ("serial number AB7-4821-9930", {"doc-warranty-air-purifier.jpg"}),
]

init_db()
db = SessionLocal()
uid = db.query(User).filter(User.google_sub == "demo:template").one().id
search(db, uid, "warmup")  # load models

h1 = h3 = 0
rr, lat = [], []
for q, rel in QUERIES:
    f = parse_rules(q)
    t = time.perf_counter()
    hits = search(db, uid, q, filters=f)
    lat.append((time.perf_counter() - t) * 1000)
    names = [h.document.filename for h in hits]
    ranks = [i for i, n in enumerate(names, 1) if n in rel]
    first = ranks[0] if ranks else None
    h1 += first == 1
    h3 += bool(first and first <= 3)
    rr.append(1 / first if first else 0)
    print(f"{'OK ' if first == 1 else ('~' + str(first) + ' ' if first else 'MISS')} {q!r:45} -> {names[:3]}")

n = len(QUERIES)
print(f"\nqueries={n} hit@1={h1/n:.0%} hit@3={h3/n:.0%} MRR={statistics.mean(rr):.2f} "
      f"latency p50={statistics.median(lat):.0f}ms p95={sorted(lat)[int(0.95*n)-1]:.0f}ms "
      f"backend={get_settings().vector_backend}")
