"""Dispatch ingest work: in-process background task locally, Pub/Sub -> Cloud Run worker in the cloud.

With Pub/Sub the API only stores the file and publishes an id, so it stays responsive under batch
uploads; workers scale out (and to zero) independently.
"""

import json
import logging
from functools import lru_cache

from fastapi import BackgroundTasks

from app.config import get_settings
from app.ingest import process_document

log = logging.getLogger(__name__)


@lru_cache
def _publisher():
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def enqueue(background: BackgroundTasks, document_ids: list[str]) -> None:
    s = get_settings()
    if s.task_backend == "pubsub":
        topic = _publisher().topic_path(s.gcp_project, s.pubsub_topic)
        futures = [_publisher().publish(topic, json.dumps({"document_id": d}).encode()) for d in document_ids]
        for f in futures:
            f.result(timeout=30)  # surface publish errors to the request
        return
    for d in document_ids:
        background.add_task(process_document, d)
