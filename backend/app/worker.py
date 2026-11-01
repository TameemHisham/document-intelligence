"""Cloud Run ingest worker: receives Pub/Sub push messages and processes one document per request.

Deployed from the same image as the API with `uvicorn app.worker:app`. The service is private
(only the Pub/Sub push service account has run.invoker); when PUBSUB_PUSH_AUDIENCE is set we also
verify the OIDC token ourselves (defense in depth).
"""

import base64
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response

from app.config import get_settings
from app.db import init_db
from app.ingest import process_document

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Document Intelligence worker", lifespan=lifespan)


def _verify(request: Request) -> None:
    s = get_settings()
    if not s.pubsub_push_audience:
        return
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing token")
    try:
        claims = id_token.verify_oauth2_token(auth[7:], g_requests.Request(), audience=s.pubsub_push_audience)
    except ValueError:
        raise HTTPException(401, "invalid token")
    if s.pubsub_push_sa_email and claims.get("email") != s.pubsub_push_sa_email:
        raise HTTPException(403, "unexpected caller")


@app.post("/pubsub/push", status_code=204)
async def push(request: Request) -> Response:
    _verify(request)
    envelope = await request.json()
    try:
        payload = json.loads(base64.b64decode(envelope["message"]["data"]))
        document_id = str(payload["document_id"])
    except (KeyError, ValueError, TypeError):
        log.warning("dropping malformed message")
        return Response(status_code=204)  # ack: retrying a malformed message never helps
    # process_document never raises: failures mark the document "failed" (no paid retry loops).
    process_document(document_id)
    return Response(status_code=204)


@app.get("/health")
def health():
    return {"ok": True}
